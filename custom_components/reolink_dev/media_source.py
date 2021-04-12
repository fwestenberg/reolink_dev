"""Reolink Camera Media Source Implementation."""
import datetime as dt
import logging
import os
from typing import Dict, Optional, Tuple, cast
from aiohttp import web

from dateutil import relativedelta
from homeassistant.components.http.auth import async_sign_path

from homeassistant.components.http import current_request
from homeassistant.components.http.const import KEY_HASS_REFRESH_TOKEN_ID

from homeassistant.core import HomeAssistant, callback

import homeassistant.util.dt as dt_utils

from homeassistant.components.http import HomeAssistantView

from homeassistant.components.media_player.errors import BrowseError
from homeassistant.components.media_player.const import (
    MEDIA_CLASS_DIRECTORY,
    MEDIA_CLASS_VIDEO,
    MEDIA_TYPE_VIDEO,
)
from homeassistant.components.media_source.const import MEDIA_MIME_TYPES
from homeassistant.components.media_source.error import MediaSourceError, Unresolvable
from homeassistant.components.media_source.models import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
)

from homeassistant.components.stream import create_stream

from .base import ReolinkBase, searchtime_to_datetime

from . import typings

from .const import (
    BASE,
    DOMAIN,
    DOMAIN_DATA,
    MEDIA_SOURCE,
    THUMBNAIL_EXTENSION as EXTENSION,
)

_LOGGER = logging.getLogger(__name__)
# MIME_TYPE = "rtmp/mp4"
# MIME_TYPE = "video/mp4"
MIME_TYPE = "application/x-mpegURL"

NAME = "Reolink IP Camera"

THUMBNAIL_URL = "/api/" + DOMAIN + "/media_proxy/{camera_id}/{event_id}.jpg"
VOD_URL = "/api/" + DOMAIN + "/vod/{camera_id}/{event_id}"
STORAGE_VERSION = 1
THUMBNAIL_FOLDER = DOMAIN + ".pbt"


class IncompatibleMediaSource(MediaSourceError):
    """Incompatible media source attributes."""


async def async_get_media_source(hass: HomeAssistant):
    """Set up Reolink media source."""

    _LOGGER.debug("Creating REOLink Media Source")
    source = ReolinkMediaSource(hass)
    hass.http.register_view(ReolinkSourceThumbnailView(hass))
    hass.http.register_view(ReolinkSourceVODView(hass))

    return source


class ReolinkMediaSource(MediaSource):
    """Provide Reolink camera recordings as media sources."""

    name: str = NAME

    def __init__(self, hass: HomeAssistant):
        """Initialize Reolink source."""
        super().__init__(DOMAIN)
        self.hass = hass
        self._file_cache: Dict[str, str] = dict()

    # def _walk_entries(self):
    #     data: Dict[str, dict] = self.hass.data[self.domain]
    #     for entry_id in data:
    #         if (
    #             not isinstance(data[entry_id], dict)
    #             or not BASE in data[entry_id]
    #             or not isinstance(data[entry_id][BASE], ReolinkBase)
    #         ):
    #             continue
    #         yield (entry_id, cast(ReolinkBase, data[entry_id][BASE]))

    # def _get_or_create_cache_entry(
    #     self,
    #     entry_id: Optional[str] = None,
    #     camera_id: Optional[str] = None,
    #     base: Optional[ReolinkBase] = None,
    # ):
    #     if camera_id and camera_id in self._cache:
    #         _LOGGER.debug("Found cache for camera: %s", camera_id)
    #         return self._cache[camera_id]

    #     if not (entry_id and base):
    #         if entry_id:
    #             entry = cast(
    #                 dict, cast(dict, self.hass.data[self.domain]).get(entry_id)
    #             )
    #             base = entry[BASE] if entry else None
    #         else:
    #             (entry_id, base) = next(
    #                 (
    #                     e
    #                     for e in self._walk_entries()
    #                     if e[1] == base or e[1].unique_id == camera_id
    #                 ),
    #                 (None, None),
    #             )

    #     if not entry_id or not base:
    #         _LOGGER.debug("Could not find matching camera entry: %s", entry_id)
    #         return None

    #     camera_id = base.unique_id
    #     return self._cache.setdefault(
    #         camera_id, typings.ReolinkMediaSourceCacheEntry(entry_id)
    #     )

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve a media item to a playable item."""
        _, camera_id, event_id = async_parse_identifier(item)

        data: dict = self.hass.data[self.domain]
        entry: dict = data.get(camera_id) if camera_id else None
        base: ReolinkBase = entry.get(BASE) if entry else None
        if not base:
            raise BrowseError("Camera does not exist.")

        file = self._file_cache.get(f"{camera_id}/{event_id}", "")
        if not file:
            raise BrowseError("Event does not exist.")

        url = await base.api.get_vod_source(file)
        _LOGGER.debug("Load VOD %s", url)
        stream = create_stream(self.hass, url)
        stream.add_provider("hls", timeout=600)
        url: str = stream.endpoint_url("hls")
        # the media browser seems to have a problem with the master_playlist
        # ( it does not load the referenced playlist ) so we will just
        # force the reference playlist instead, this seems to work
        # though technically wrong
        url = url.replace("master_", "")
        _LOGGER.debug("Proxy %s", url)
        return PlayMedia(url, MIME_TYPE)

    async def async_browse_media(
        self, item: MediaSourceItem, media_types: Tuple[str] = MEDIA_MIME_TYPES
    ) -> BrowseMediaSource:
        """Browse media."""

        try:
            source, camera_id, event_id = async_parse_identifier(item)
        except Unresolvable as err:
            raise BrowseError(str(err)) from err

        _LOGGER.debug("Browsing %s, %s, %s", source, camera_id, event_id)

        data: dict = self.hass.data[self.domain]
        entry: dict = data.get(camera_id) if camera_id else None
        base: ReolinkBase = entry.get(BASE) if entry else None
        if camera_id and not base:
            raise BrowseError("Camera does not exist.")

        if event_id and not "/" in event_id:
            raise BrowseError("Event does not exist.")

        return await self._async_browse_media(source, camera_id, event_id, base)

    async def _async_browse_media(
        self,
        source: str,
        camera_id: str = None,
        event_id: str = None,
        base: ReolinkBase = None,
    ) -> BrowseMediaSource:
        """ actual browse after input validation """

        start_date: dt.datetime = None

        def create_item(title: str, path: str, thumbnail: bool = False):
            nonlocal self, camera_id, event_id, start_date

            if not title or not path:
                if event_id and "/" in event_id:
                    year, *rest = event_id.split("/", 3)
                    month = rest[0] if len(rest) > 0 else None
                    day = rest[1] if len(rest) > 1 else None

                    start_date = dt.datetime.combine(
                        dt.date(
                            int(year),
                            int(month) if month else 1,
                            int(day) if day else 1,
                        ),
                        dt.time.min,
                        dt_utils.now().tzinfo,
                    )

                    title = f"{start_date.date()}"
                    path = f"{source}/{camera_id}/{event_id}"
                elif base:
                    title = base.name
                    path = f"{source}/{camera_id}"
                else:
                    title = self.name
                    path = source + "/"

            media_class = (
                MEDIA_CLASS_DIRECTORY
                if not event_id or "/" in event_id
                else MEDIA_CLASS_VIDEO
            )

            media = BrowseMediaSource(
                domain=self.domain,
                identifier=path,
                media_class=media_class,
                media_content_type=MEDIA_TYPE_VIDEO,
                title=title,
                can_play=not bool(media_class == MEDIA_CLASS_DIRECTORY),
                can_expand=bool(media_class == MEDIA_CLASS_DIRECTORY),
            )

            if thumbnail:
                url = THUMBNAIL_URL.format(camera_id=camera_id, event_id=event_id)
                refresh_token_id = current_request[KEY_HASS_REFRESH_TOKEN_ID]
                # leave expiration 30 seconds?
                media.thumbnail = async_sign_path(
                    self.hass, refresh_token_id, url, dt.timedelta(seconds=30)
                )

            if not media.can_play and not media.can_expand:
                _LOGGER.debug(
                    "Camera %s with event %s without media url found",
                    camera_id,
                    event_id,
                )
                raise IncompatibleMediaSource

            return media

        def create_root_children():
            nonlocal base, camera_id

            children = []
            data: Dict[str, dict] = self.hass.data[self.domain]
            for entry_id in data:
                entry = data[entry_id]
                if not isinstance(entry, dict) or not BASE in entry:
                    continue
                base = entry[BASE]
                if not base.api.hdd_info:
                    continue
                camera_id = entry_id
                child = create_item(None, None)
                children.append(child)

            return children

        async def create_day_children():
            nonlocal event_id

            children = []
            end_date = dt_utils.now()
            start_date = dt.datetime.combine(
                end_date.date().replace(day=1), dt.time.min
            )
            if base.playback_months > 1:
                start_date -= relativedelta.relativedelta(
                    months=int(base.playback_months)
                )

            search, _ = await base.api.send_search(start_date, end_date, True)

            if not search is None:
                for status in search:
                    year = status["year"]
                    month = status["mon"]
                    for day, flag in enumerate(status["table"], start=1):
                        if flag == "1":
                            event_id = f"{year}/{month}/{day}"
                            child = create_item(None, None)
                            children.append(child)

            children.reverse()
            return children

        async def create_vod_children():
            nonlocal base, start_date, event_id

            children = []
            end_date = dt.datetime.combine(
                start_date.date(), dt.time.max, start_date.tzinfo
            )

            _, files, save = await base.commit_thumbnails(start_date, end_date)

            for file in files:
                end_date = searchtime_to_datetime(file["EndTime"], end_date.tzinfo)
                start_date = searchtime_to_datetime(file["StartTime"], end_date.tzinfo)
                event_id = str(start_date.timestamp())
                evt_id = f"{camera_id}/{event_id}"
                self._file_cache[evt_id] = file["name"]
                thumbnail = os.path.isfile(
                    f"{base.thumbnail_path}/{event_id}.{EXTENSION}"
                )

                time = start_date.time()
                duration = end_date - start_date
                child = create_item(
                    f"{time} {duration}", f"{source}/{evt_id}", thumbnail
                )
                children.append(child)

            children.reverse()

            if save:
                await save

            return children

        if base and event_id and not "/" in event_id:
            event = base.in_memory_events[event_id]
            start_date = event.start

        media = create_item(None, None)

        if not media.can_expand:
            return media

        if not camera_id:
            media.children = create_root_children()
            return media

        if not start_date:
            media.children = await create_day_children()
        else:
            media.children = await create_vod_children()

        return media

    # async def _get_events(
    #     self,
    #     camera_id: str,
    #     base: ReolinkBase,
    #     start: dt.datetime,
    #     end: dt.datetime,
    #     tasks: list = None,
    # ):
    #     cache = self._cache[camera_id]

    #     _, files = await base.send_search(start, end)

    #     if not files is None:
    #         for file in files:
    #             dto = file["EndTime"]
    #             end = dt.datetime(
    #                 dto["year"],
    #                 dto["mon"],
    #                 dto["day"],
    #                 dto["hour"],
    #                 dto["min"],
    #                 dto["sec"],
    #                 0,
    #                 end.tzinfo,
    #             )
    #             dto = file["StartTime"]
    #             start = dt.datetime(
    #                 dto["year"],
    #                 dto["mon"],
    #                 dto["day"],
    #                 dto["hour"],
    #                 dto["min"],
    #                 dto["sec"],
    #                 0,
    #                 end.tzinfo,
    #             )
    #             event_id = str(start.timestamp())
    #             event = cache.events.setdefault(
    #                 event_id, typings.ReolinkMediaSourceVodEntry(start)
    #             )
    #             if event.incomplete:
    #                 event.start = start
    #                 event.end = end
    #                 event.file = file["name"]
    #                 if not event.thumbnail and tasks:
    #                     drop = []
    #                     for _event_id in cache.events:
    #                         _event = cache.events[_event_id]
    #                         if (
    #                             not _event.incomplete
    #                             or _event.start < start
    #                             or _event.start > end
    #                         ):
    #                             continue
    #                         drop.append(_event_id)
    #                         if (
    #                             isinstance(_event.thumbnail, bytes)
    #                             and not event.thumbnail
    #                         ):
    #                             event.thumbnail = _event.thumbnail
    #                             tasks.append(
    #                                 self.hass.async_create_task(
    #                                     self.hass.async_add_executor_job(
    #                                         self._save_thumbnail, camera_id, _event_id
    #                                     )
    #                                 )
    #                             )
    #                     if drop:
    #                         for _event_id in drop:
    #                             cache.events.pop(_event_id)

    #             if not event.thumbnail is None and base.playback_thumbnails:
    #                 thumbnail = os.path.join(cache.thumbnail_path, event_id) + EXTENSION
    #                 if os.path.isfile(thumbnail):
    #                     event.thumbnail = thumbnail
    #                 elif tasks:
    #                     event.thumbnail = ""

    #             yield (event_id, event)

    # async def async_synchronize_thumbnails(
    #     self,
    #     camera_id: str,
    #     start: Optional[dt.datetime] = None,
    #     end: Optional[dt.datetime] = None,
    # ):
    #     """ Synchronize in memory thumbnails with VoDs """
    #     cache = self._cache.get(camera_id, None)
    #     if not cache:
    #         return
    #     if not start:
    #         start = next(
    #             (
    #                 cache.events[e].start
    #                 for e in cache.events
    #                 if cache.events[e].incomplete
    #             ),
    #             None,
    #         )
    #     if start:
    #         if not end:
    #             end = dt_utils.now()

    #         jobs = []
    #         async for _ in self._get_events(
    #             camera_id,
    #             self.hass.data[self.domain][cache.entry_id][BASE],
    #             start,
    #             end,
    #             jobs,
    #         ):
    #             pass

    #         await gather(jobs)

    # async def async_query_vods(
    #     self,
    #     camera_id: str,
    #     start: Optional[dt.datetime] = None,
    #     end: Optional[dt.datetime] = None,
    #     thumbnail_path: Optional[str] = None,
    # ):
    #     """ Query camera for VoDs and emit them as events """
    #     cache = self._cache.get(camera_id, None)
    #     if not cache:
    #         return
    #     base: ReolinkBase = self.hass.data[self.domain][cache.entry_id][BASE]
    #     if not end:
    #         end = dt_utils.now()
    #     if not start:
    #         start = dt.datetime.combine(end.date().replace(day=1), dt.time.min)
    #         if base.playback_months > 1:
    #             start -= relativedelta.relativedelta(months=int(base.playback_months))
    #     if thumbnail_path:
    #         if not os.path.isdir(thumbnail_path):
    #             os.makedirs(thumbnail_path)

    #         if (
    #             cache.thumbnail_path
    #             and cache.thumbnail_path == self._get_default_thumb_path(camera_id)
    #         ):
    #             self.hass.async_create_task(
    #                 self.hass.async_run_job(
    #                     _move_thumbnails, cache.thumbnail_path, thumbnail_path
    #                 )
    #             )

    #         cache.thumbnail_path = thumbnail_path
    #     else:
    #         thumbnail_path = (
    #             cache.thumbnail_path
    #             if cache.thumbnail_path
    #             else self._get_default_thumb_path(camera_id)
    #         )

    #     async for (event_id, event) in self._get_events(camera_id, base, start, end):
    #         if not event.token:
    #             event.token = secrets.token_hex()
    #         url = (
    #             VOD_URL.format(camera_id=camera_id, event_id=event_id)
    #             + "?token="
    #             + parse.quote_plus(event.token)
    #         )
    #         self.hass.bus.async_fire(
    #             EVENT_VOD_DATA,
    #             {
    #                 "url": url,
    #                 "event": {
    #                     "start": event.start,
    #                     "end": event.end,
    #                     "file": event.file,
    #                 },
    #                 "thumbnail": f"{thumbnail_path}/{event_id}.{EXTENSION}",
    #             },
    #         )


class ReolinkSourceVODView(HomeAssistantView):
    """ VOD security handler """

    url = VOD_URL
    name = "api:" + DOMAIN + ":video"
    requires_auth = False
    cors_allowed = True

    def __init__(self, hass: HomeAssistant):
        """Initialize media view """

        self.hass = hass

    async def get(
        self, request: web.Request, camera_id: str, event_id: str
    ) -> web.Response:
        """ start a GET request. """

        if not camera_id or not event_id:
            raise web.HTTPNotFound()

        cache = cast(
            Dict[str, typings.ReolinkMediaSourceCacheEntry],
            cast(dict, self.hass.data[DOMAIN_DATA]).get(MEDIA_SOURCE, {}),
        ).get(camera_id, None)

        if not cache:
            _LOGGER.debug("camera %s not found", camera_id)
            raise web.HTTPNotFound()

        event = cache.events.get(event_id, None)
        if not event:
            _LOGGER.debug("camera %s, event %s not found", camera_id, event_id)
            raise web.HTTPNotFound()

        token = request.query.get("token")
        if (token and event.token != token) or (not token and not self.requires_auth):
            _LOGGER.debug(
                "invalid or missing token %s for camera %s, event %s",
                token,
                camera_id,
                event_id,
            )
            raise web.HTTPNotFound()

        _LOGGER.debug("vod %s, %s", camera_id, event_id)
        base: ReolinkBase = (
            cast(dict, self.hass.data[DOMAIN].get(cache.entry_id, {})).get(BASE, None)
            if cache
            else None
        )
        url = await base.api.get_vod_source(event.file)
        return web.HTTPTemporaryRedirect(url)


class ReolinkSourceThumbnailView(HomeAssistantView):
    """ Thumbnial view handler """

    url = THUMBNAIL_URL
    name = "api:" + DOMAIN + ":image"
    cors_allowed = True

    def __init__(self, hass: HomeAssistant):
        """Initialize media view """

        self.hass = hass

    async def get(
        self,
        request: web.Request,  # pylint: disable=unused-argument
        camera_id: str,
        event_id: str,
    ) -> web.Response:
        """ start a GET request. """

        if not camera_id or not event_id:
            raise web.HTTPNotFound()

        data: Dict[str, dict] = self.hass.data[DOMAIN]
        base: ReolinkBase = (
            data[camera_id].get(BASE, None) if camera_id in data[camera_id] else None
        )
        if not base:
            _LOGGER.debug("camera %s not found", camera_id)
            raise web.HTTPNotFound()

        thumbnail = f"{base.thumbnail_path}/{event_id}.{EXTENSION}"
        return web.FileResponse(thumbnail)


# def _move_thumbnails(source: str, target: str):
#     for thumb in os.listdir(source):
#         os.rename(thumb, target)


@callback
def async_parse_identifier(
    item: MediaSourceItem,
) -> Tuple[str, str, Optional[str]]:
    """Parse identifier."""
    if not item.identifier:
        return "events", "", None

    source, path = item.identifier.lstrip("/").split("/", 1)

    if source != "events":
        raise Unresolvable("Unknown source directory.")

    if "/" in path:
        camera_id, event_id = path.split("/", 1)

        return source, camera_id, event_id

    return source, path, None
