""" Typing declarations for strongly typed dictionaries """

from dataclasses import dataclass, field
from typing import Dict, Optional, TypedDict, Union
from datetime import datetime


@dataclass
class ReolinkMediaSourceVodEntry:
    """ Camera search result representing a recorded video """

    start: datetime
    end: Optional[datetime] = None
    file: Optional[str] = None
    thumbnail: Optional[Union[str, bytes]] = None
    token: Optional[str] = None

    @property
    def incomplete(self):
        """ check if entry if complete """
        return self.end is None or self.file is None


@dataclass
class ReolinkMediaSourceCacheEntry:
    """ entry in the media source cache for a camera instance """

    entry_id: str
    thumbnail_path: Optional[str] = None
    events: Dict[str, ReolinkMediaSourceVodEntry] = field(default_factory=dict)


class ReolinkMediaSourceConfigEntry(TypedDict, total=False):
    """ Dynamic configuration entry """

    thumbnail_path: str


class ReolinkMediaSourceConfig(TypedDict, total=False):
    """ Dynamic configuration entries for storage """

    configs: Dict[str, ReolinkMediaSourceConfigEntry]


class ReolinkMediaSourceHelper:
    """ stub entries to ducktype MediaSource functions in other modules """

    async def async_motion_snapshot(self, system_now: datetime, base):
        """ generate a snapshot of the current motion event """
        raise NotImplementedError()

    async def async_synchronize_thumbnails(
        self,
        camera_id: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ):
        """ Synchronize in memory thumbnails with VoDs """
        raise NotImplementedError()
