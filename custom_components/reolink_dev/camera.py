"""This component provides basic support for Reolink IP cameras."""
import logging
import asyncio
import voluptuous as vol
# import aiohttp
import datetime

from homeassistant.components.camera import Camera, PLATFORM_SCHEMA, SUPPORT_STREAM, ENTITY_IMAGE_URL
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_USERNAME, CONF_PASSWORD, ATTR_ENTITY_ID, EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers import config_validation as cv
from haffmpeg.camera import CameraMjpeg
from homeassistant.components.ffmpeg import DATA_FFMPEG
from custom_components.reolink_dev.ReolinkPyPi.camera import ReolinkApi

_LOGGER = logging.getLogger(__name__)

STATE_MOTION = "motion"
STATE_NO_MOTION = "no_motion"
STATE_IDLE = "idle"

DEFAULT_NAME = "Reolink Camera"
DOMAIN = "camera"
SERVICE_ENABLE_FTP = 'enable_ftp'
SERVICE_DISABLE_FTP = 'disable_ftp'
SERVICE_ENABLE_EMAIL = 'enable_email'
SERVICE_DISABLE_EMAIL = 'disable_email'
SERVICE_ENABLE_IR_LIGHTS = 'enable_ir_lights'
SERVICE_DISABLE_IR_LIGHTS = 'disable_ir_lights'
# SERVICE_SET_STREAM_PROTOCOL = 'set_stream_protocol'
# SERVICE_SET_STREAM_SOURCE = 'set_stream_source'
DEFAULT_BRAND = 'Reolink'
DOMAIN_DATA = 'reolink_devices'


from homeassistant.helpers.aiohttp_client import (
    async_aiohttp_proxy_stream,
    async_aiohttp_proxy_web,
    async_get_clientsession,
)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string
    }
)

@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Set up a Reolink IP Camera."""
    async_add_devices([ReolinkCamera(hass, config)], update_before_add=True)

# Event enable FTP
    def handler_enable_ftp(call):
        component = hass.data.get(DOMAIN)
        entity = component.get_entity(call.data.get(ATTR_ENTITY_ID))

        if entity:
            entity.enable_ftp_upload()
    hass.services.async_register(DOMAIN, SERVICE_ENABLE_FTP, handler_enable_ftp)

# Event disable FTP
    def handler_disable_ftp(call):
        component = hass.data.get(DOMAIN)
        entity = component.get_entity(call.data.get(ATTR_ENTITY_ID))

        if entity:
            entity.disable_ftp_upload()

    hass.services.async_register(DOMAIN, SERVICE_DISABLE_FTP, handler_disable_ftp)

# Event enable email
    def handler_enable_email(call):
        component = hass.data.get(DOMAIN)
        entity = component.get_entity(call.data.get(ATTR_ENTITY_ID))

        if entity:
            entity.enable_email()
    hass.services.async_register(DOMAIN, SERVICE_ENABLE_EMAIL, handler_enable_email)

# Event disable email
    def handler_disable_email(call):
        component = hass.data.get(DOMAIN)
        entity = component.get_entity(call.data.get(ATTR_ENTITY_ID))

        if entity:
            entity.disable_email()

    hass.services.async_register(DOMAIN, SERVICE_DISABLE_EMAIL, handler_disable_email)

# Event enable ir lights
    def handler_enable_ir_lights(call):
        component = hass.data.get(DOMAIN)
        entity = component.get_entity(call.data.get(ATTR_ENTITY_ID))

        if entity:
            entity.enable_ir_lights()
    hass.services.async_register(DOMAIN, SERVICE_ENABLE_IR_LIGHTS, handler_enable_ir_lights)

# Event disable ir lights
    def handler_disable_ir_lights(call):
        component = hass.data.get(DOMAIN)
        entity = component.get_entity(call.data.get(ATTR_ENTITY_ID))

        if entity:
            entity.disable_ir_lights()

    hass.services.async_register(DOMAIN, SERVICE_DISABLE_IR_LIGHTS, handler_disable_ir_lights)


class ReolinkCamera(Camera):
    """An implementation of a Reolink IP camera."""

    def __init__(self, hass, config):
        """Initialize a Reolink camera."""
        super().__init__()
        self._host = config.get(CONF_HOST)
        self._username = config.get(CONF_USERNAME)
        self._password = config.get(CONF_PASSWORD)
        self._name = config.get(CONF_NAME)
        self._reolinkSession = None
        self._hass = hass
        self._manager = self._hass.data[DATA_FFMPEG]

        self._stream = None 
        self._protocol = None
        self._last_update = 0
        self._last_image = None
        self._last_motion = 0
        self._ftp_state = None
        self._email_state = None
        self._ir_state = None
        self._state = STATE_IDLE

        if not self._stream:
            self._stream = 'main'

        if not self._protocol:
            self._protocol = 'rtmp'

        self._reolinkSession = ReolinkApi(self._host)
        self._reolinkSession.login(self._username, self._password)
        self._hass.bus.async_listen(EVENT_HOMEASSISTANT_STOP, self.disconnect)

    @property
    def state_attributes(self):
        """Return the camera state attributes."""
        attrs = {"access_token": self.access_tokens[-1]}

        if self._last_motion:
            attrs["last_motion"] = self._last_motion
        
        if self._last_update:
            attrs["last_update"] = self._last_update

        attrs["ftp_enabled"] = self._ftp_state
        attrs["email_enabled"] = self._email_state
        attrs["ir_lights_enabled"] = self._ir_state

        return attrs

    @property
    def supported_features(self):
        """Return supported features."""
        return SUPPORT_STREAM

    @property
    def name(self):
        """Return the name of this camera."""
        return self._name

    @property
    def should_poll(self):
        """Polling needed for the device status."""
        return True

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def ftp_state(self):
        """Camera Motion recording Status."""
        return self._ftp_state

    @property
    def email_state(self):
        """Camera email Status."""
        return self._email_state

    async def stream_source(self):
        """Return the source of the stream."""
        if self._protocol == 'rtsp':
            stream_source = "rtsp://{}:{}@{}:{}/h264Preview_01_{}".format(
                self._username,
                self._password,
                self._host,
                self._reolinkSession.rtspPort,
                self._stream )
        else:
            stream_source = "rtmp://{}:{}/bcs/channel0_{}.bcs?channel=0&stream=0&user={}&password={}".format(
                self._host,
                self._reolinkSession.rtmpport,
                self._stream,
                self._username,
                self._password )

        return stream_source

    async def handle_async_mjpeg_stream(self, request):
        """Generate an HTTP MJPEG stream from the camera."""
        stream_source = "rtmp://{}:{}/bcs/channel0_{}.bcs?channel=0&stream=0&user={}&password={}".format(
            self._host,
            self._reolinkSession.rtmpport,
            self._stream,
            self._username,
            self._password )

        stream = CameraMjpeg(self._manager.binary, loop=self._hass.loop)
        await stream.open_camera(stream_source)

        try:
            stream_reader = await stream.get_reader()
            return await async_aiohttp_proxy_stream(
                self._hass,
                request,
                stream_reader,
                self._manager.ffmpeg_stream_content_type,
            )
        finally:
            await stream.close()

    def camera_image(self):
        """Return bytes of camera image."""
        return asyncio.run_coroutine_threadsafe(self.async_camera_image(), self._hass.loop).result()

    async def async_camera_image(self):
        """Return a still image response from the camera."""
        return self._reolinkSession.still_image

    def enable_ftp_upload(self):
        """Enable motion recording in camera."""
        if self._reolinkSession.set_ftp(True):
            self._ftp_state = True
            self._hass.states.set(self.entity_id, self.state, self.state_attributes)

    def disable_ftp_upload(self):
        """Disable motion recording."""
        if self._reolinkSession.set_ftp(False):
            self._ftp_state = False
            self._hass.states.set(self.entity_id, self.state, self.state_attributes)

    def enable_email(self):
        """Enable email motion detection in camera."""
        if self._reolinkSession.set_email(True):
            self._email_state = True
            self._hass.states.set(self.entity_id, self.state, self.state_attributes)

    def disable_email(self):
        """Disable email motion detection."""
        if self._reolinkSession.set_email(False):
            self._email_state = False
            self._hass.states.set(self.entity_id, self.state, self.state_attributes)

    def enable_ir_lights(self):
        """Enable IR lights."""
        if self._reolinkSession.set_ir_lights(True):
            self._ir_state = True
            self._hass.states.set(self.entity_id, self.state, self.state_attributes)

    def disable_ir_lights(self):
        """Disable IR lights."""
        if self._reolinkSession.set_ir_lights(False):
            self._ir_state = False
            self._hass.states.set(self.entity_id, self.state, self.state_attributes)   

    async def update_motion_state(self):
        if self._reolinkSession.motion_state == True:
            self._state = STATE_MOTION
            self._last_motion = self._reolinkSession.last_motion
        else:
            self._state = STATE_NO_MOTION
    
    async def update_status(self):
        self._reolinkSession.status()

        self._last_update = datetime.datetime.now()
        self._ftp_state = self._reolinkSession.ftp_state
        self._email_state = self._reolinkSession.email_state
        self._ir_state = self._reolinkSession.ir_state

    def update(self):
        """Update the data from the camera."""
        try:
            self._hass.loop.create_task(self.update_motion_state())

            if (self._last_update == 0 or
               (datetime.datetime.now() - self._last_update).total_seconds() >= 30):
                self._hass.loop.create_task(self.update_status())

        except Exception as ex:
            _LOGGER.error("Got exception while fetching the state: %s", ex)

    def disconnect(self, event):
        _LOGGER.info("Disconnecting from Reolink camera")
        self._reolinkSession.logout()
