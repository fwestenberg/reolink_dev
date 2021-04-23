""" custom helper actions """

import logging

from typing import Optional
import voluptuous as vol

from homeassistant.helpers.device_registry import DeviceRegistry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_TYPE,
    DEVICE_CLASS_TIMESTAMP,
)
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_registry

from homeassistant.components.camera import DOMAIN as CAMERA_DOMAIN, SERVICE_SNAPSHOT
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN

from .const import DOMAIN

VOD_THUMB_CAP_ACTION = "capture_vod_thumbnail"

ACTION_TYPES = {VOD_THUMB_CAP_ACTION}

ACTION_SCHEMA = cv.DEVICE_ACTION_BASE_SCHEMA.extend(
    {vol.Required(CONF_TYPE): vol.In(ACTION_TYPES)}
)

_LOGGER = logging.getLogger(__name__)


async def async_get_actions(hass: HomeAssistant, device_id: str):
    """List device actions for devices."""

    registry = await entity_registry.async_get_registry(hass)
    device_registry: DeviceRegistry = (
        await hass.helpers.device_registry.async_get_registry()
    )
    device = device_registry.async_get(device_id)

    actions = []

    if not device:
        return actions

    entries = entity_registry.async_entries_for_device(registry, device_id)
    sensor = next(
        (
            entry
            for entry in entries
            if entry.domain == SENSOR_DOMAIN
            and entry.device_class == DEVICE_CLASS_TIMESTAMP
        )
    )
    camera = next((entry for entry in entries if entry.domain == CAMERA_DOMAIN))

    if sensor and camera:
        actions.append(
            {
                CONF_DOMAIN: DOMAIN,
                CONF_DEVICE_ID: device_id,
                CONF_TYPE: VOD_THUMB_CAP_ACTION,
            }
        )

    _LOGGER.debug("actions: %s", actions)
    return actions


async def async_call_action_from_config(
    hass: HomeAssistant, config: dict, variables: dict, context: Optional[Context]
):
    """Execute a device action."""

    registry = await entity_registry.async_get_registry(hass)
    device_registry: DeviceRegistry = (
        await hass.helpers.device_registry.async_get_registry()
    )
    device = device_registry.async_get(config[CONF_DEVICE_ID])

    if not device:
        _LOGGER.debug("no device")
        return

    if config[CONF_TYPE] == VOD_THUMB_CAP_ACTION:
        entries = entity_registry.async_entries_for_device(registry, device.id)
        sensor = next(
            (
                entry
                for entry in entries
                if entry.domain == SENSOR_DOMAIN
                and entry.device_class == DEVICE_CLASS_TIMESTAMP
            )
        )
        camera = next((entry for entry in entries if entry.domain == CAMERA_DOMAIN))

        if not sensor and camera:
            _LOGGER.debug("no sensor or camera")
            return

        sensor_state = hass.states.get(sensor.entity_id)

        service_data = {
            ATTR_ENTITY_ID: camera.entity_id,
            "filename": sensor_state.attributes.get("thumbnail_path"),
        }
        _LOGGER.debug("service_data: %s", service_data)
        _LOGGER.debug("variables: %s", variables)
        return await hass.services.async_call(
            CAMERA_DOMAIN,
            SERVICE_SNAPSHOT,
            service_data,
            blocking=True,
            context=context,
        )
