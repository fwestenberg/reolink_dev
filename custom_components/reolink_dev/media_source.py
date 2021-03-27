"""Reolink Camera Media Source Implementation."""
import tempfile
from urllib import parse
import secrets
import datetime as dt
import logging
import os
from typing import Dict, Optional, Tuple, cast
from aiohttp import web

from dateutil import relativedelta
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_HOMEASSISTANT_STOP

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

import homeassistant.util.dt as dt_utils

from homeassistant.components.http import HomeAssistantView

# from homeassistant.components.http.auth import async_sign_path
from homeassistant.components.camera import DEFAULT_CONTENT_TYPE
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

from .storage import BytesStore

from .base import ReolinkBase, Api

from . import typings

from .const import BASE, DOMAIN, DOMAIN_DATA, MEDIA_SOURCE

_LOGGER = logging.getLogger(__name__)
# MIME_TYPE = "rtmp/mp4"
# MIME_TYPE = "video/mp4"
MIME_TYPE = "application/x-mpegURL"
EXTENSION = ".jpg"

NAME = "Reolink IP Camera"

THUMBNAIL_URL = "/api/" + DOMAIN + "/media_proxy/{camera_id}/{event_id}"
STORAGE_VERSION = 1


class IncompatibleMediaSource(MediaSourceError):
    """Incompatible media source attributes."""


async def async_get_media_source(hass: HomeAssistant):
    """Set up Reolink media source."""

    source: ReolinkMediaSource = cast(dict, hass.data[DOMAIN]).get(MEDIA_SOURCE, None)
    if not source:
        _LOGGER.debug("Creating REOLink Media Source")
        source = hass.data[DOMAIN][MEDIA_SOURCE] = ReolinkMediaSource(hass)
        hass.http.register_view(ReolinkSourceThumbnailView(hass))

    return source


class ReolinkMediaSource(MediaSource):
    """Provide Reolink camera recordings as media sources."""

    name: str = NAME

    def __init__(self, hass: HomeAssistant):
        """Initialize Reolink source."""
        super().__init__(DOMAIN)
        self.hass = hass
        self._cache: Dict[str, typings.ReolinkMediaSourceCacheEntry] = cast(
            dict, hass.data.setdefault(DOMAIN_DATA, {})
        ).setdefault(MEDIA_SOURCE, {})
        self._config_store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.media")
        self._motion_store = BytesStore(hass, STORAGE_VERSION, f"{DOMAIN}.motion")
        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._on_stop)
        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, self._init)

    def _create_cache_entry(self, camera_id: str):
        for entry_id in self.hass.data[DOMAIN]:
            if (
                not isinstance(self.hass.data[DOMAIN][entry_id], dict)
                or not BASE in self.hass.data[DOMAIN][entry_id]
            ):
                continue
            base: ReolinkBase = self.hass.data[DOMAIN][entry_id][BASE]
            if base.unique_id != camera_id:
                continue
            return self._cache.setdefault(
                camera_id, self._create_new_cache_entry(entry_id, base)
            )
        return None

    def _get_or_create_cache_entry(self, camera_id: str):
        return typings.try_get_or_create_item(
            self._cache, camera_id, self._create_cache_entry
        )

    async def _init(self, event):
        data: Dict[str, Dict[str, bytes]] = await self._motion_store.async_load()
        if data:
            _LOGGER.debug("Loading saved motion thumbnails... %s", data)
            for camera_id in data:
                cache = self._get_or_create_cache_entry(camera_id)

                for event_id in data[camera_id]:
                    start = dt.datetime.fromtimestamp(
                        float(event_id), dt_utils.now().tzinfo
                    )
                    cache.events[event_id] = typings.ReolinkMediaSourceVodEntry(
                        start, thumbnail=data[camera_id][event_id]
                    )

        await self._motion_store.async_remove()
        config: typings.ReolinkMediaSourceConfig = await self._config_store.async_load()

        if config:
            for camera_id in config["configs"]:
                cconfig = config["configs"][camera_id]
                cache = self._get_or_create_cache_entry(camera_id)
                cache.thumbnail_path = cconfig["thumbnail_path"]

    async def _on_stop(self, event):
        data: Optional[Dict[str, Dict[str, bytes]]] = None
        for camera_id in self._cache:
            for event_id in self._cache[camera_id].events:
                event = self._cache[camera_id].events[event_id]
                if not event.incomplete or not isinstance(event.thumbnail, bytes):
                    continue
                if not data:
                    data = {}
                cdata = data.setdefault(camera_id, {})
                cdata[event_id] = event.thumbnail

        if data:
            self._motion_store.async_delay_save(lambda: data)
        config: typings.ReolinkMediaSourceConfig = None
        for camera_id in self._cache:
            cache = self._cache[camera_id]
            if cache.thumbnail_path:
                if not config:
                    config = {}
                cconfig = config.setdefault("configs", {}).setdefault(camera_id, {})
                cconfig["thumbnail_path"] = cache.thumbnail_path

        if config:
            self._config_store.async_delay_save(lambda: config)
        else:
            await self._config_store.async_remove()

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve a media item to a playable item."""
        _, camera_id, event_id = async_parse_identifier(item)

        cache = self._cache.get(camera_id, None)
        base: ReolinkBase = (
            cast(dict, self.hass.data[DOMAIN].get(cache.entry_id, {})).get(BASE, None)
            if cache
            else None
        )
        event = cache.events[event_id] if cache and event_id in cache.events else None
        url = await base.api.get_vod_source(event.file)
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

        if camera_id and camera_id not in self._cache:
            raise BrowseError("Camera does not exist.")

        if (
            event_id
            and not "/" in event_id
            and event_id not in self._cache[camera_id].events
        ):
            raise BrowseError("Event does not exist.")

        return await self._async_browse_media(source, camera_id, event_id, False)

    def _create_new_cache_entry(self, entry_id: str, base: ReolinkBase):
        return typings.ReolinkMediaSourceCacheEntry(entry_id)

    async def _async_browse_media(
        self, source: str, camera_id: str, event_id: str = None, no_descend: bool = True
    ) -> BrowseMediaSource:
        """ actual browse after input validation """

        cache = (
            self._cache[camera_id] if camera_id and camera_id in self._cache else None
        )
        base: ReolinkBase = (
            self.hass.data[DOMAIN].get(cache.entry_id, {}).get(BASE, None)
            if cache
            else None
        )

        event = None
        start_date = None

        if cache and event_id:
            if event_id in cache.events:
                event = cache.events[event_id]
                end_date = event.end
                start_date = event.start
                time = start_date.time()
                duration = end_date - start_date

                title = f"{time} {duration}"
            else:
                year, *rest = event_id.split("/", 3)
                month = rest[0] if len(rest) > 0 else None
                day = rest[1] if len(rest) > 1 else None

                start_date = dt.datetime.combine(
                    dt.date(
                        int(year), int(month) if month else 1, int(day) if day else 1
                    ),
                    dt.time.min,
                    dt_utils.now().tzinfo,
                )

                title = f"{start_date.date()}"

            path = f"{source}/{camera_id}/{event_id}"
        else:
            if not base:
                camera_id = ""
                title = NAME
            else:
                title = base.name

            path = f"{source}/{camera_id}"

        media_class = MEDIA_CLASS_DIRECTORY if event else MEDIA_CLASS_VIDEO

        media = BrowseMediaSource(
            domain=DOMAIN,
            identifier=path,
            media_class=media_class,
            media_content_type=MEDIA_TYPE_VIDEO,
            title=title,
            can_play=bool(event and event.file),
            can_expand=bool(not event),
        )

        if event and event.thumbnail:
            url = THUMBNAIL_URL.format(camera_id=camera_id, event_id=event_id)

            # TODO : I cannot find a way to get the current user context at this point
            #        so I will have to leave the view as unauthenticated, as a temporary
            #        security measure, I will add a unique token to the event to limit
            #        "exposure"
            # url = async_sign_path(self.hass, None, url, dt.timedelta(minutes=30))
            if not event.token:
                event.token = secrets.token_hex()
            media.thumbnail = f"{url}?token={parse.quote_plus(event.token)}"

        if not media.can_play and not media.can_expand:
            _LOGGER.debug(
                "Camera %s with event %s without media url found", camera_id, event_id
            )
            raise IncompatibleMediaSource

        if not media.can_expand or no_descend:
            return media

        media.children = []

        if not cache:
            for entry_id in self.hass.data[DOMAIN]:
                entry = self.hass.data[DOMAIN][entry_id]
                if not isinstance(entry, dict) or not BASE in entry:
                    continue
                base = entry[BASE]
                camera_id = base.unique_id
                cache = self._cache.get(camera_id, None)
                if not cache:
                    cache = self._cache[camera_id] = self._create_new_cache_entry(
                        entry_id, base
                    )

                child = await self._async_browse_media(source, camera_id)
                media.children.append(child)
            return media

        # TODO: the cache is one way so over time it can grow and have invalid
        #       records, the code should be expanded to invalidate/expire
        #       entries

        if not base:
            raise BrowseError("Camera does not exist.")

        if not start_date:
            end_date = dt_utils.now()
            start_date = dt.datetime.combine(end_date.date(), dt.time.min)
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
                                child = await self._async_browse_media(
                                    source, camera_id, f"{year}/{month}/{day}"
                                )
                                media.children.append(child)
                    media.children.reverse()

            return media

        end_date = dt.datetime.combine(
            start_date.date(), dt.time.max, start_date.tzinfo
        )

        _, files = await base.api.send_search(start_date, end_date)

        if not files is None:
            events = cache.events

            for file in files:
                dto = file["EndTime"]
                end_date = dt.datetime(
                    dto["year"],
                    dto["mon"],
                    dto["day"],
                    dto["hour"],
                    dto["min"],
                    dto["sec"],
                    0,
                    end_date.tzinfo,
                )
                dto = file["StartTime"]
                start_date = dt.datetime(
                    dto["year"],
                    dto["mon"],
                    dto["day"],
                    dto["hour"],
                    dto["min"],
                    dto["sec"],
                    0,
                    end_date.tzinfo,
                )
                event_id = str(start_date.timestamp())
                event = events.setdefault(
                    event_id, typings.ReolinkMediaSourceVodEntry(start_date)
                )
                if event.incomplete:
                    event.start = start_date
                    event.end = end_date
                    event.file = file["name"]
                    # Merge any incomplete events (snapshots) that are in the start/stop
                    # range of this event
                    delkeys = []
                    for _event_id in events:
                        if not events[_event_id].incomplete:
                            continue
                        _event = events[_event_id]
                        if event.start <= _event.start and event.end >= _event.start:
                            event.thumbnail = _event.thumbnail
                            delkeys.append(_event_id)
                    if delkeys:
                        for _event_id in delkeys:
                            events.pop(_event_id)
                    if event.thumbnail:
                        self.hass.async_add_executor_job(
                            self._save_thumbnail, camera_id, event_id
                        )

                if not event.thumbnail and base.playback_thumbnails:
                    thumbnail = os.path.join(cache.thumbnail_path, event_id) + EXTENSION
                    if os.path.isfile(thumbnail):
                        event.thumbnail = thumbnail

                child = await self._async_browse_media(source, camera_id, event_id)
                media.children.append(child)

            media.children.reverse()

        return media

    async def async_motion_snapshot(self, system_now: dt.datetime, base: ReolinkBase):
        """ internal method to sync motion events with snapshots """

        start = system_now.astimezone(dt_utils.now().tzinfo)
        _LOGGER.debug("Motion capture for %s", base.unique_id)
        cache = self._cache.setdefault(base.unique_id, None)
        if not cache:
            for entry_id in self.hass.data[DOMAIN]:
                entry = self.hass.data[DOMAIN][entry_id]
                if isinstance(entry, dict) and BASE in entry:
                    cache = self._cache[base.unique_id] = self._create_new_cache_entry(
                        entry_id, base
                    )
                    break

        event = typings.ReolinkMediaSourceVodEntry(start)
        event_id = str(event.start.timestamp())
        cache.events[event_id] = event
        event.thumbnail = await base.api.get_snapshot()

    def _save_thumbnail(self, camera_id: str, event_id: str):
        cache = self._cache.get(camera_id, None)
        event = cache.events.get(event_id, None) if cache else None

        if not event or not event.thumbnail or not isinstance(event.thumbnail, bytes):
            return

        if not cache.thumbnail_path:
            cache.thumbnail_path = os.path.join(
                os.path.dirname(self._config_store.path),
                f"{DOMAIN}.pbthumbs",
                camera_id,
            )

        if not os.path.isdir(cache.thumbnail_path):
            os.makedirs(cache.thumbnail_path)

        temp_filename = ""
        filename = os.path.join(cache.thumbnail_path, event_id + EXTENSION)
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=cache.thumbnail_path, delete=False
            ) as fdesc:
                temp_filename = fdesc.name
                fdesc.write(event.thumbnail)
            os.chmod(temp_filename, 0o644)
            os.replace(temp_filename, filename)
            event.thumbnail = filename
        finally:
            if os.path.exists(temp_filename):
                try:
                    os.remove(temp_filename)
                except OSError as err:
                    _LOGGER.error("Thumbnail replacement cleanup failed: %s", err)


class ReolinkSourceThumbnailView(HomeAssistantView):
    """ Thumbnial view handler """

    url = "/api/" + DOMAIN + "/media_proxy/{camera_id}/{event_id}"
    name = "api:" + DOMAIN + ":image"
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

        _LOGGER.debug("thumbnail %s, %s", camera_id, event_id)

        if isinstance(event.thumbnail, str):
            # TODO : determine storage
            return web.FileResponse(event.thumbnail)

        if event.thumbnail:
            return web.Response(body=event.thumbnail, content_type=DEFAULT_CONTENT_TYPE)

        raise web.HTTPInternalServerError()


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
