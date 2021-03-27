""" Storage Extensions """

from collections import deque
from json.encoder import JSONEncoder
import logging
import os
import tempfile
from typing import (
    Any,
    Dict,
    Optional,
    Type,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.exceptions import HomeAssistantError
from homeassistant.loader import bind_hass

BLOB_PREFIX = ".blob:"

_LOGGER = logging.getLogger(__name__)


class WriteError(HomeAssistantError):
    """Error writing the data."""


class ReadError(HomeAssistantError):
    """Error reading the data."""


@bind_hass
class BytesStore(Store):
    """ blob aware storage """

    def __init__(
        self,
        hass: HomeAssistant,
        version: int,
        key: str,
        private: bool = False,
        *,
        encoder: Optional[Type[JSONEncoder]] = None,
    ):
        super().__init__(hass, version, key, private=private, encoder=encoder)

    @property
    def blob_path(self):
        """ sub-path for blob data """
        return f"{self.path}.blobs"

    async def _async_read_dict_blobs(self, path: str, data: dict):
        for key in data:
            if isinstance(data[key], str) and data[key].startswith(BLOB_PREFIX):
                data[key] = await self._async_read_blob(
                    path, data[key][len(BLOB_PREFIX) :]
                )
            else:
                await self._async_do_read_blobs(path, data[key])

    async def _async_read_list_blobs(self, path: str, data: list):
        for i, value in enumerate(data):
            if isinstance(value, str) and value.startswith(BLOB_PREFIX):
                data[i] = await self._async_read_blob(path, value[len(BLOB_PREFIX) :])
            else:
                await self._async_do_read_blobs(path, value)

    async def _async_do_read_blobs(self, path: str, data: Any):
        if isinstance(data, list):
            await self._async_read_list_blobs(path, data)
        elif isinstance(data, dict):
            await self._async_read_dict_blobs(path, data)

    async def _async_read_blob(self, path: str, filename: str):
        await self.hass.async_add_executor_job(_read_blob, path, filename)

    async def _async_load_data(self):
        data = await super()._async_load_data()
        await self._async_do_read_blobs(self.blob_path, data)
        return data

    def _write_dict_blobs(self, path: str, data: dict):
        for key in data:
            if isinstance(data[key], bytes):
                filename = _write_blob(path, self._private, data[key])
                data[key] = BLOB_PREFIX + filename
            else:
                self._do_write_blobs(path, data[key])

    def _write_list_blobs(self, path: str, data: list):
        for i, value in enumerate(data):
            if isinstance(value, bytes):
                filename = _write_blob(path, self._private, value)
                data[i] = BLOB_PREFIX + filename
            else:
                self._do_write_blobs(path, value)

    def _do_write_blobs(self, path: str, data: Any):
        if isinstance(data, list):
            self._write_list_blobs(path, data)
        elif isinstance(data, dict):
            self._write_dict_blobs(path, data)

    def _write_data(self, path: str, data: Dict):
        if "data" in data:
            self._do_write_blobs(self.blob_path, data["data"])
        return super()._write_data(path, data)

    async def async_remove(self):
        try:
            await self.hass.async_add_executor_job(_remove_blobs, self.blob_path)
        except FileNotFoundError:
            pass
        return await super().async_remove()

    async def _async_migrate_func(self, old_version, old_data):
        """Migrate to the new version."""
        raise NotImplementedError


def _remove_blobs(path: str):
    if not os.path.isdir(path):
        return

    for dirpath, _, filenames in os.walk(path, topdown=False):
        for filename in filenames:
            os.unlink(os.path.join(dirpath, filename))
        os.rmdir(dirpath)


def _write_blob(path: str, private: bool, data: bytes):
    if not os.path.isdir(path):
        os.makedirs(path)

    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path, delete=False) as fdesc:
            temp_filename = fdesc.name
            fdesc.write(data)
        if not private:
            os.chmod(temp_filename, 0o644)
    except OSError as error:
        _LOGGER.exception("Saving BLOB failed: %s", temp_filename)
        raise WriteError(error) from error
    return os.path.basename(temp_filename)


def _read_blob(path: str, filename: str):
    filename = os.path.join(path, filename)
    try:
        with open(filename, mode="rb") as fdesc:
            return fdesc.read()
    except OSError as error:
        _LOGGER.exception("Reading BLOB failed: %s", filename)
        raise ReadError(error) from error
