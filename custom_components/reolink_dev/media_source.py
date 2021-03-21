"""Reolink Camera Media Source Implementation."""
from urllib import parse
import secrets
import datetime as dt
import logging
import os
from typing import List, Optional, Tuple
from aiohttp import web
import asyncio

from haffmpeg.tools import IMAGE_JPEG

from dateutil import relativedelta

from homeassistant.core import HomeAssistant, callback

import homeassistant.util.dt as dt_utils

from homeassistant.components.http import HomeAssistantView

# from homeassistant.components.http.auth import async_sign_path
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
from homeassistant.components.ffmpeg import DATA_FFMPEG

from custom_components.reolink_dev.base import ReolinkBase

from . import typings

from .const import BASE, DEFAULT_THUMBNAIL_OFFSET, DOMAIN

_LOGGER = logging.getLogger(__name__)
# MIME_TYPE = "rtmp/mp4"
# MIME_TYPE = "video/mp4"
MIME_TYPE = "application/x-mpegURL"

NAME = "Reolink IP Camera"

STORAGE_DIR = ".storage"


class IncompatibleMediaSource(MediaSourceError):
    """Incompatible media source attributes."""


async def async_get_media_source(hass: HomeAssistant):
    """Set up Reolink media source."""
    _LOGGER.debug("Creating REOLink Media Source")
    source = ReolinkSource(hass)
    hass.http.register_view(ReolinkSourceThumbnailView(hass, source))
    return source


class ReolinkSource(MediaSource):
    """Provide Reolink camera recordings as media sources."""

    name: str = NAME

    def __init__(self, hass: HomeAssistant):
        """Initialize Reolink source."""
        super().__init__(DOMAIN)
        self.hass = hass
        if DATA_FFMPEG in hass.data:
            ffmpeg = hass.data[DATA_FFMPEG]
            if not ffmpeg is None:
                self._ffmpeg_bin = ffmpeg.binary
        self.cache = {}

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve a media item to a playable item."""
        _, camera_id, event_id = async_parse_identifier(item)
        cache: typings.MediaSourceCacheEntry = self.cache[camera_id]
        event = cache["playback_events"][event_id]
        base: ReolinkBase = self.hass.data[DOMAIN][cache["entry_id"]][BASE]
        url = await base.api.get_vod_source(event["file"])
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

        if camera_id and camera_id not in self.cache:
            raise BrowseError("Camera does not exist.")

        if (
            event_id
            and not "/" in event_id
            and event_id not in self.cache[camera_id]["playback_events"]
        ):
            raise BrowseError("Event does not exist.")

        return await self._async_browse_media(source, camera_id, event_id, False)

    async def _async_browse_media(
        self, source: str, camera_id: str, event_id: str = None, no_descend: bool = True
    ) -> BrowseMediaSource:
        """ actual browse after input validation """
        event: typings.VodEvent = None
        cache: typings.MediaSourceCacheEntry = None
        start_date = None

        if camera_id and camera_id in self.cache:
            cache = self.cache[camera_id]

        if cache and event_id:
            if "playback_events" in cache and event_id in cache["playback_events"]:
                event = cache["playback_events"][event_id]
                end_date = event["end"]
                start_date = event["start"]
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
            if cache is None:
                camera_id = ""
                title = NAME
            else:
                title = cache["name"]

            path = f"{source}/{camera_id}"

        media_class = MEDIA_CLASS_DIRECTORY if event is None else MEDIA_CLASS_VIDEO

        media = BrowseMediaSource(
            domain=DOMAIN,
            identifier=path,
            media_class=media_class,
            media_content_type=MEDIA_TYPE_VIDEO,
            title=title,
            can_play=bool(not event is None and event.get("file")),
            can_expand=event is None,
        )

        if not event is None and cache.get("playback_thumbnails", False):
            url = "/api/" + DOMAIN + f"/media_proxy/{camera_id}/{event_id}"

            # TODO : I cannot find a way to get the current user context at this point
            #        so I will have to leave the view as unauthenticated, as a temporary
            #        security measure, I will add a unique token to the event to limit
            #        "exposure"
            # url = async_sign_path(self.hass, None, url, dt.timedelta(minutes=30))
            if "token" not in event:
                event["token"] = secrets.token_hex()
            media.thumbnail = f"{url}?token={parse.quote_plus(event['token'])}"

        if not media.can_play and not media.can_expand:
            _LOGGER.debug(
                "Camera %s with event %s without media url found", camera_id, event_id
            )
            raise IncompatibleMediaSource

        if not media.can_expand or no_descend:
            return media

        media.children = []

        base: ReolinkBase = None

        if cache is None:
            for entry_id in self.hass.data[DOMAIN]:
                entry = self.hass.data[DOMAIN][entry_id]
                if not isinstance(entry, dict) or not BASE in entry:
                    continue
                base = entry[BASE]
                if base.api.hdd_info is None or len(base.api.hdd_info) < 1:
                    continue
                _LOGGER.debug("%s", base.api.hdd_info)
                camera_id = base.unique_id
                cache = self.cache.get(camera_id, None)
                if cache is None:
                    cache = self.cache[camera_id] = {
                        "entry_id": entry_id,
                        "unique_id": base.unique_id,
                        "playback_events": {},
                    }
                cache["name"] = base.name

                child = await self._async_browse_media(source, camera_id)
                media.children.append(child)
            return media

        base = self.hass.data[DOMAIN][cache["entry_id"]][BASE]

        # TODO: the cache is one way so over time it can grow and have invalid
        #       records, the code should be expanded to invalidate/expire
        #       entries

        if base is None:
            raise BrowseError("Camera does not exist.")

        if not start_date:
            if (
                "playback_day_entries" not in cache
                or cache.get("playback_months", -1) != base.playback_months
            ):
                end_date = dt_utils.now()
                start_date = dt.datetime.combine(end_date.date(), dt.time.min)
                cache["playback_months"] = base.playback_months
                if cache["playback_months"] > 1:
                    start_date -= relativedelta.relativedelta(
                        months=int(cache["playback_months"])
                    )

                entries = cache["playback_day_entries"] = []

                search, _ = await base.api.send_search(start_date, end_date, True)

                if not search is None:
                    for status in search:
                        year = status["year"]
                        month = status["mon"]
                        for day, flag in enumerate(status["table"], start=1):
                            if flag == "1":
                                entries.append(dt.date(year, month, day))

                entries.sort(reverse=True)

                oldest = entries[-1]
                thumb_dir = f"{DOMAIN}/thumbnails/{camera_id}"

                # background directory scan and expired thumbnail cleanup
                self.hass.async_add_executor_job(
                    self._cleanup_expired_thumbnails, thumb_dir, oldest
                )
            else:
                entries = cache["playback_day_entries"]

                # force today to be in the list to ensure
                # entries recorded today are not missed
                today = dt_utils.now().date()
                if today not in entries:
                    entries.insert(0, today)

            for date in cache["playback_day_entries"]:
                child = await self._async_browse_media(
                    source, camera_id, f"{date.year}/{date.month}/{date.day}"
                )
                media.children.append(child)

            return media

        cache["playback_thumbnails"] = (
            base.playback_thumbnails and not self._ffmpeg_bin is None
        )

        end_date = dt.datetime.combine(
            start_date.date(), dt.time.max, start_date.tzinfo
        )

        _, files = await base.api.send_search(start_date, end_date)

        if not files is None:
            events = cache.setdefault("playback_events", {})

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
                event = events.setdefault(event_id, {})
                event["start"] = start_date
                event["end"] = end_date
                event["file"] = file["name"]
                filepath = f"{DOMAIN}/thumbnails/{camera_id}/{event_id}.jpg"
                path = self.hass.config.path(STORAGE_DIR, filepath)
                if os.path.isfile(path):
                    event["thumbnail"] = filepath

                child = await self._async_browse_media(source, camera_id, event_id)
                media.children.append(child)

        return media

    def _cleanup_expired_thumbnails(self, filepath: str, before: dt.date):
        """ cleanup expired thumbnails for camera """

        path = self.hass.config.path(STORAGE_DIR, filepath)
        if not os.path.isdir(path):
            return

        _LOGGER.debug("cleanup of thumbnails older than %s for %s", before, filepath)
        (_, _, filenames) = next(os.walk(path))
        ts = dt.datetime.combine(before, dt.time.min).timestamp()

        for filename in filenames:
            basename = os.path.splitext(filename)[0]
            _LOGGER.debug("got %s", basename)
            try:
                file_ts = float(basename)
            except ValueError:
                continue

            if file_ts < ts:
                os.remove(os.path.join(path, filename))


class ReolinkSourceThumbnailView(HomeAssistantView):
    """ Thumbnial view handler """

    url = "/api/" + DOMAIN + "/media_proxy/{camera_id}/{event_id}"
    name = "api:" + DOMAIN + ":image"
    requires_auth = False
    cors_allowed = True

    def __init__(self, hass: HomeAssistant, source: ReolinkSource):
        """Initialize media view """

        self.hass = hass
        self.source = source
        self._tasks = {}

    async def get(
        self, request: web.Request, camera_id: str, event_id: str
    ) -> web.Response:
        """ start a GET request. """

        if not camera_id or not event_id:
            raise web.HTTPNotFound()

        cache: typings.MediaSourceCacheEntry = self.source.cache.get(camera_id, None)
        if cache is None or "playback_events" not in cache:
            _LOGGER.debug("camera %s not found", camera_id)
            raise web.HTTPNotFound()

        event = cache["playback_events"].get(event_id, None)
        if event is None:
            _LOGGER.debug("camera %s, event %s not found", camera_id, event_id)
            raise web.HTTPNotFound()

        token = request.query.get("token")
        if (token and event.get("token") != token) or (
            not token and not self.requires_auth
        ):
            _LOGGER.debug(
                "invalid or missing token %s for camera %s, event %s",
                token,
                camera_id,
                event_id,
            )
            raise web.HTTPNotFound()

        _LOGGER.debug("thumbnail %s, %s", camera_id, event_id)

        base: ReolinkBase = self.hass.data[DOMAIN][cache["entry_id"]][BASE]

        filepath = f"{DOMAIN}/thumbnails/{camera_id}/{event_id}.jpg"

        image = event.get("thumbnail", None)
        if (
            image is None
            or cache.get("playback_thumbnail_offset", DEFAULT_THUMBNAIL_OFFSET)
            != base.playback_thumbnail_offset
        ):
            cache["playback_thumbnails"] = base.playback_thumbnails
            cache["playback_thumbnail_offset"] = base.playback_thumbnail_offset

            if not cache["playback_thumbnails"]:
                _LOGGER.debug("Thumbnails not allowed on camera %s", camera_id)
                raise web.HTTPInternalServerError()

            extra_cmd: List[str] = None
            if cache["playback_thumbnail_offset"] > 0:
                extra_cmd = ["-ss", str(cache["playback_thumbnail_offset"])]

            tasks = self._tasks.setdefault(base.api.host, {})
            url = await base.api.get_vod_source(event["file"])
            task = tasks.get(url, None)
            if task is None:
                _LOGGER.debug(
                    "queueing thumbnail generation for %s, %s", camera_id, event_id
                )
                tasks[url] = tasks["current"] = task = self.hass.async_create_task(
                    self._async_get_image(
                        url, filepath, extra_cmd, tasks.get("current", None)
                    )
                )

            image = event["thumbnail"] = await task
            tasks.pop(url, None)
            if tasks["current"] == task:
                tasks.pop("current")
            _LOGGER.debug("generated thumbnail for %s, %s", camera_id, event_id)

        if isinstance(image, str):
            return web.FileResponse(self.hass.config.path(STORAGE_DIR, image))
        if image:
            return web.Response(body=image, content_type=IMAGE_JPEG)

        _LOGGER.debug(
            "No thumbnail generated for camera %s, event %s", camera_id, event_id
        )
        raise web.HTTPInternalServerError()

    async def _async_get_image(
        self,
        url: str,
        filepath: str,
        extra_cmd: List[str] = None,
        waitforit=None,
    ):
        if waitforit is not None:
            await waitforit

        path = self.hass.config.path(STORAGE_DIR, filepath)
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))

        cmd = [
            self.source._ffmpeg_bin,  # pylint: disable=protected-access
            "-loglevel",
            "fatal",
            "-i",
            url,
            "-an",
            "-frames:v",
            "1",
            "-c:v",
            IMAGE_JPEG,
        ]

        if not extra_cmd is None:
            cmd.extend(extra_cmd)

        cmd.append(path)

        # async_get_image runs horribly slow on my rPI4 but ffmpeg runs fine from command line
        # so this is a direct call to bypass the pipe issues
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
        )
        _, _ = await proc.communicate()

        # image = await async_get_image(self.hass, url, extra_cmd=extra_cmd)

        return filepath

    async def _async_save_image(self, path: str, event: typings.VodEvent, task):
        image = await task
        if image is None:
            return
        await self.hass.async_add_executor_job(self._save_image, path, image)
        event["thumbnail"] = path

    def _save_image(self, key: str, data):
        path = self.hass.config.path(STORAGE_DIR, key)
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))

        _LOGGER.debug("writing thumbnail to %s", path)
        f = open(path, "wb")
        f.write(data)
        f.close()
        _LOGGER.debug("finished")


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
