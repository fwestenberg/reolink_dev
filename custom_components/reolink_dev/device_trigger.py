""" Additional triggers for ReoLink Camera """

import logging

import voluptuous as vol

from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_PLATFORM,
    CONF_TYPE,
    DEVICE_CLASS_TIMESTAMP,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceRegistry
from homeassistant.helpers import entity_registry
from homeassistant.helpers.typing import ConfigType

from homeassistant.components.automation import AutomationActionType
from homeassistant.components.device_automation import TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import state as state_trigger
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN

from .const import DOMAIN

VOD_NO_THUMB_TRIGGER = "vod_without_thumbnail"

TRIGGER_TYPES = {VOD_NO_THUMB_TRIGGER}

TRIGGER_SCHEMA = TRIGGER_BASE_SCHEMA.extend(
    {vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES)}
)

_LOGGER = logging.getLogger(__name__)


async def async_get_triggers(hass: HomeAssistant, device_id: str):
    """ List of device triggers """

    registry = await entity_registry.async_get_registry(hass)
    device_registry: DeviceRegistry = (
        await hass.helpers.device_registry.async_get_registry()
    )
    device = device_registry.async_get(device_id)

    triggers = []

    if not device:
        return triggers

    sensor = next(
        (
            entry
            for entry in entity_registry.async_entries_for_device(registry, device_id)
            if entry.domain == SENSOR_DOMAIN
            and entry.device_class == DEVICE_CLASS_TIMESTAMP
        )
    )
    if sensor:
        triggers.append(
            {
                CONF_PLATFORM: "device",
                CONF_DOMAIN: DOMAIN,
                CONF_DEVICE_ID: device_id,
                CONF_TYPE: VOD_NO_THUMB_TRIGGER,
            }
        )

    return triggers


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: AutomationActionType,
    automation_info: dict,
):
    """ Attach a trigger """

    registry = await entity_registry.async_get_registry(hass)
    device_registry: DeviceRegistry = (
        await hass.helpers.device_registry.async_get_registry()
    )
    device = device_registry.async_get(config[CONF_DEVICE_ID])

    if not device:
        _LOGGER.debug("no device")
        return

    if config[CONF_TYPE] == VOD_NO_THUMB_TRIGGER:
        sensor = next(
            (
                entry
                for entry in entity_registry.async_entries_for_device(
                    registry, device.id
                )
                if entry.domain == SENSOR_DOMAIN
                and entry.device_class == DEVICE_CLASS_TIMESTAMP
            )
        )
        if not sensor:
            _LOGGER.debug("no sensor")
            return

        vod_config = state_trigger.TRIGGER_SCHEMA(
            {
                CONF_PLATFORM: "state",
                CONF_ENTITY_ID: sensor.entity_id,
                state_trigger.CONF_ATTRIBUTE: "has_thumbnail",
                state_trigger.CONF_TO: "false",
            }
        )
        _LOGGER.debug("vod_config: %s", vod_config)
        _LOGGER.debug("action: %s", action)
        _LOGGER.debug("automation_info: %s", automation_info)
        return await state_trigger.async_attach_trigger(
            hass,
            vod_config,
            action,
            automation_info,
            platform_type=config[CONF_PLATFORM],
        )
