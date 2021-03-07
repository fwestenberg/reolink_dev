"""Reolink Camera Media Source Implementation."""
from asyncio import events
from os import environ
from re import split
import homeassistant
from homeassistant.helpers.config_validation import datetime
from custom_components.reolink_dev.base import ReolinkBase
import homeassistant.util.dt as dt_utils
import datetime as dt
import logging
from typing import Optional, Tuple, Union

from . import typings

from calendar import month_name

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
from homeassistant.core import HomeAssistant, callback

from homeassistant.components.stream import Stream, create_stream
from homeassistant.components.stream.const import FORMAT_CONTENT_TYPE, OUTPUT_FORMATS

from .const import BASE, DOMAIN

_LOGGER = logging.getLogger(__name__)
VOD_MIME_TYPE = "video/mp4"
MIME_TYPE = "application/x-mpegURL"

NAME = "Reolink IP Camera"


class IncompatibleMediaSource(MediaSourceError):
    """Incompatible media source attributes."""


async def async_get_media_source(hass: HomeAssistant):
    """Set up Reolink media source."""
    return ReolinkSource(hass)


class ReolinkSource(MediaSource):
    """Provide Reolink camera recordings as media sources."""

    name: str = NAME

    def __init__(self, hass: HomeAssistant):
        """Initialize Reolink source."""
        super().__init__(DOMAIN)
        self.hass = hass
        self.events: dict[str, dict[float, typings.VodEvent]] = {}
        self.statuses: dict[str, dict[int, dict[int, list[int]]]] = {}

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve a media item to a playable item."""
        _, camera_id, event_id = async_parse_identifier(item)
        file = self.events[camera_id][float(event_id)]["file"]
        base: ReolinkBase = self.hass.data[DOMAIN][camera_id][BASE]
        url = await base.api.get_vod_source(file)
        _LOGGER.debug("Load VOD %s", url)
        # stream = create_stream(self.hass, url)
        # stream.add_provider(VOD_MIME_TYPE)
        # url = stream.endpoint_url(VOD_MIME_TYPE)
        # _LOGGER.debug("Proxy %s", url)
        return PlayMedia(url, MIME_TYPE)

    async def _async_browse_media2(
        self, source: str, camera_id: str, event_id: str = None, no_descend: bool = True
    ) -> BrowseMediaSource:
        base: ReolinkBase = None
        year: int = None
        month: int = None
        day: int = None

        _LOGGER.debug("Browsing %s camera %s event %s", source, camera_id, event_id)

        if isinstance(event_id, str) and "/" in event_id:
            year, path = event_id.split("/", 1)
            year = int(year)
            if "/" in path:
                month, day = path.split("/", 1)
                month = int(month)
                day = int(day) if day else None
            else:
                month = int(path) if path else None
            path = f"{source}/{camera_id}/{event_id}"
            title = str(day) if day else month_name[month] if month else str(year)
        elif (
            camera_id
            and camera_id in self.events
            and isinstance(event_id, float)
            and event_id in self.events[camera_id]
        ):
            event: typings.VodEvent = self.events[camera_id][event_id]
            end_date = event["end"]
            start_date = event["start"]
            title = f"{start_date.time()} {end_date - start_date}"
            path = f"{source}/{camera_id}/{event_id}"
        else:
            if camera_id:
                base = self.hass.data[DOMAIN][camera_id][BASE]
                title = base.name
            else:
                title = NAME
            path = f"{source}/{camera_id}"

        media_class = MEDIA_CLASS_DIRECTORY if event_id is None else MEDIA_CLASS_VIDEO

        media = BrowseMediaSource(
            domain=DOMAIN,
            identifier=path,
            media_class=media_class,
            media_content_type=MEDIA_TYPE_VIDEO,
            title=title,
            can_play=bool(
                event_id
                and isinstance(event_id, float)
                and self.events[camera_id][event_id].get("file")
            ),
            can_expand=event_id is None or isinstance(event_id, str),
            thumbnail=None,
        )

        if not media.can_play and not media.can_expand:
            _LOGGER.debug(
                "Camera %s with event %s without media url found", camera_id, event_id
            )
            raise IncompatibleMediaSource

        if not media.can_expand or no_descend:
            return media

        media.children = []
        if not camera_id:
            for entry in self.hass.config_entries.async_entries(DOMAIN):
                child = await self._async_browse_media2(source, entry.entry_id)
                media.children.append(child)
            return media

        if base is None:
            base = self.hass.data[DOMAIN][camera_id][BASE]

        if camera_id and not camera_id in self.statuses:
            statuses = self.statuses[camera_id] = {}
            end_date = dt_utils.now()
            start_date = dt.datetime.combine(end_date.date(), dt.time.min)
            search_statuses, _ = await base.api.send_search(start_date, end_date, True)
            while not search_statuses is None:
                for status in search_statuses:
                    status_year = statuses.setdefault(status["year"], {})
                    status_month = status_year.setdefault(status["mon"], [])
                    for status_day, status_flag in enumerate(status["table"], start=1):
                        if status_flag == "1":
                            status_month.append(status_day)
                break

        statuses = self.statuses[camera_id]

        if not year:
            for year in statuses.keys():
                child = await self._async_browse_media2(source, camera_id, f"{year}/")
                media.children.append(child)
            return media

        status_year = statuses[year]
        if not month:
            for month in status_year.keys():
                child = await self._async_browse_media2(
                    source, camera_id, f"{year}/{month}/"
                )
                media.children.append(child)
            return media

        status_month = status_year[month]
        if not day:
            for day in status_month:
                child = await self._async_browse_media2(
                    source, camera_id, f"{year}/{month}/{day}"
                )
                media.children.append(child)
            return media

        date = dt.date(year, month, day)
        end_date = dt.datetime.combine(date, dt.time.max, dt_utils.now().tzinfo)
        start_date = dt.datetime.combine(date, dt.time.min, end_date.tzinfo)

        _, files = await base.api.send_search(start_date, end_date)

        if not files is None:
            events = self.events.setdefault(camera_id, {})
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
                event_id = start_date.timestamp()
                event = events.setdefault(event_id, {})
                event["start"] = start_date
                event["end"] = end_date
                event["file"] = file["name"]
                child = await self._async_browse_media2(source, camera_id, event_id)
                media.children.append(child)

        return media

    async def _async_browse_media(
        self, source: str, camera_id: str, event_id: str
    ) -> BrowseMediaSource:
        if camera_id and camera_id not in self.hass.data[DOMAIN]:
            raise BrowseError("Camera does not exist.")

        if event_id and not "/" in event_id and event_id not in self.events[camera_id]:
            raise BrowseError("Event does not exist.")

        return await self._async_browse_media2(source, camera_id, event_id, False)

    async def async_browse_media(
        self, item: MediaSourceItem, media_types: Tuple[str] = MEDIA_MIME_TYPES
    ) -> BrowseMediaSource:
        """Browse media."""

        _LOGGER.debug("%s", media_types)

        try:
            source, camera_id, event_id = async_parse_identifier(item)
        except Unresolvable as err:
            raise BrowseError(str(err)) from err

        return await self._async_browse_media(source, camera_id, event_id)


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
