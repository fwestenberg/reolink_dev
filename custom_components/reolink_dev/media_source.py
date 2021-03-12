"""Reolink Camera Media Source Implementation."""
import asyncio
from os import environ
from re import split
from homeassistant.config_entries import ConfigEntry

from homeassistant.helpers.config_validation import datetime
from custom_components.reolink_dev.base import ReolinkBase
import homeassistant.util.dt as dt_utils
import datetime as dt
from dateutil import relativedelta
import logging
from typing import Optional, Tuple

from . import typings

from calendar import c, month_name

from homeassistant.components.media_player.const import (
    MEDIA_CLASS_DIRECTORY,
    MEDIA_CLASS_VIDEO,
    MEDIA_TYPE_VIDEO,
)
from homeassistant.components.media_player.errors import BrowseError
from homeassistant.components.media_source.const import MEDIA_MIME_TYPES
from homeassistant.components.media_source.error import MediaSourceError, Unresolvable
from homeassistant.components.media_source.models import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
)
from homeassistant.core import Event, HomeAssistant, callback

from homeassistant.components.stream import create_stream
from homeassistant.components.stream.const import FORMAT_CONTENT_TYPE, OUTPUT_FORMATS
from homeassistant.components.ffmpeg import async_get_image

from .const import BASE, DOMAIN

_LOGGER = logging.getLogger(__name__)
# MIME_TYPE = "rtmp/mp4"
# MIME_TYPE = "video/mp4"
MIME_TYPE = "application/x-mpegURL"

NAME = "Reolink IP Camera"


class IncompatibleMediaSource(MediaSourceError):
    """Incompatible media source attributes."""


async def async_get_media_source(hass: HomeAssistant):
    """Set up Reolink media source."""
    _LOGGER.debug("Creating REOLink Media Source")
    return ReolinkSource(hass)


class ReolinkSource(MediaSource):
    """Provide Reolink camera recordings as media sources."""

    name: str = NAME

    def __init__(self, hass: HomeAssistant):
        """Initialize Reolink source."""
        super().__init__(DOMAIN)
        self.hass = hass
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

        # if not event is None and "thumbnail" in event:
        #    media.thumbnail = event["thumbnail"]

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

                entries.sort()
            else:
                entries = cache["playback_day_entries"]

            for date in cache["playback_day_entries"]:
                child = await self._async_browse_media(
                    source, camera_id, f"{date.year}/{date.month}/{date.day}"
                )
                media.children.append(child)

            return media

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
                if (
                    "playback_thumbs" in cache
                    and cache["playback_thumbs"]
                    and not "thumbnail" in event
                ):
                    event["thumbail"] = await async_get_image(
                        self.hass, await base.api.get_vod_source(file["name"])
                    )

                child = await self._async_browse_media(source, camera_id, event_id)
                media.children.append(child)

        return media


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
