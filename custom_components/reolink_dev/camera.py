"""This component provides basic support for Reolink IP cameras."""
import logging
import asyncio
import voluptuous as vol
import aiohttp
import async_timeout
import datetime

from homeassistant.components.camera import Camera, PLATFORM_SCHEMA, SUPPORT_STREAM, ENTITY_IMAGE_URL
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_USERNAME, CONF_PASSWORD, ATTR_ENTITY_ID, EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import Throttle
from requests.auth import HTTPDigestAuth

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
    reolinkCameraDevice = ReolinkCamera(hass, config)
    async_add_devices([reolinkCameraDevice])

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
        from custom_components.reolink.ReolinkCamera import Camera

        super().__init__()
        self._host = config.get(CONF_HOST)
        self._username = config.get(CONF_USERNAME)
        self._password = config.get(CONF_PASSWORD)
        self._name = config.get(CONF_NAME)
        self._hass = hass

        self._auth = aiohttp.BasicAuth(self._username, password=self._password)
        self._stream = None 
        self._protocol = None
        self._reolink_session = Camera(self._host, self._username, self._password)
        self._last_update = 0
        self._last_image = None
        self._last_motion = 0
        self._ftp = None
        self._email = None
        self._ir_lights = None
        self._device_info = None
        self._netports = None
        self._state = STATE_IDLE
        self._emailHandler = None
        self._smtp_server = None
        self._smtp_port = None

        hass.bus.async_listen(EVENT_HOMEASSISTANT_STOP, self.disconnect)

        hass.loop.create_task(self.connect())

    @property
    def state_attributes(self):
        """Return the camera state attributes."""
        attrs = {"access_token": self.access_tokens[-1]}

        if self.model:
            attrs["model_name"] = self.model

        if self.brand:
            attrs["brand"] = self.brand

        if self.sw_version:
            attrs["sw_version"] = self.sw_version

        if self.motion_detection_enabled:
            attrs["motion_detection"] = self.motion_detection_enabled

        if self._last_motion:
            attrs["last_motion"] = self._last_motion
        
        if self._last_update:
            attrs["last_update"] = self._last_update

        attrs["ftp_enabled"] = self._ftp_enabled
        attrs["email_enabled"] = self._email_enabled
        attrs["ir_lights_enabled"] = self._ir_lights_enabled

        return attrs

    @property
    def supported_features(self):
        """Return supported features."""
        return SUPPORT_STREAM

    @property
    def brand(self):
        """Return the camera brand."""
        return DEFAULT_BRAND

    @property
    def model(self):
        """Return the camera model."""
        return self._device_info[0]["value"]["DevInfo"]["model"]

    @property
    def sw_version(self):
        """Return the camera model."""
        return self._device_info[0]["value"]["DevInfo"]["firmVer"]

    async def connect(self):
        await self.get_camera_settings()

    async def stream_source(self):
        """Return the source of the stream."""
        if self._protocol == 'rtsp':
            stream_source = "rtsp://{}:{}@{}:{}/h264Preview_01_{}".format(
                self._username,
                self._password,
                self._host,
                self._rtspport,
                self._stream )
        else:
            stream_source = "rtmp://{}:{}@{}:{}/bcs/channel0_{}.bcs?channel=0&stream=0".format(
                self._username,
                self._password,
                self._host,
                self._rtmpport,
                self._stream )
        return stream_source

    async def get_motion_state(self):
            motion_state = self._reolink_session.get_motion_state()

            if (motion_state != None and
                motion_state[0]["value"]["state"] == 1):
                self._state = STATE_MOTION
                self._last_motion = datetime.datetime.now()
            else:
                self._state = STATE_NO_MOTION

    async def get_camera_settings(self):
        self._ftp = self._reolink_session.get_ftp()
        self._email = self._reolink_session.get_email()
        self._device_info = self._reolink_session.get_device_info()
        self._netports = self._reolink_session.get_net_ports()
        self._ir_lights = self._reolink_session.get_ir_lights()

        if self._ftp == None:
            _LOGGER.error("Error retrieving FTP settings for Reolink camera" + self._name)
            return False

        if self._email == None:
            _LOGGER.error("Error retrieving email settings for Reolink camera" + self._name)
            return False

        if self._device_info == None:
            _LOGGER.error("Error retrieving device info for Reolink camera" + self._name)
            return False

        if self._netports == None:
            _LOGGER.error("Error retrieving port settings for Reolink camera" + self._name)
            return False

        if self._ir_lights == None:
            _LOGGER.error("Error retrieving IR light settings for Reolink camera" + self._name)
            return False

        if (self._ftp[0]["value"]["Ftp"]["schedule"]["enable"] == 1):
            self._ftp_enabled = True
        else:
            self._ftp_enabled = False

        if (self._email[0]["value"]["Email"]["schedule"]["enable"] == 1):
            self._email_enabled = True
        else:
            self._email_enabled = False

        if (self._ir_lights[0]["value"]["IrLights"]["state"] == "Auto"):
            self._ir_lights_enabled = True
        else:
            self._ir_lights_enabled = False

        self._rtspport = self._netports[0]["value"]["NetPort"]["rtspPort"]
        self._rtmpport = self._netports[0]["value"]["NetPort"]["rtmpPort"]

        self.smtp_server = self._email[0]["value"]["Email"]["smtpServer"]
        self.smtp_port = self._email[0]["value"]["Email"]["smtpPort"]

        if not self._stream:
            self._stream = 'main'

        if not self._protocol:
            self._protocol = 'rtsp'

        self._last_update = datetime.datetime.now()

        return True

    def camera_image(self):
        """Return bytes of camera image."""
        return asyncio.run_coroutine_threadsafe(self.async_camera_image(), self._hass.loop).result()

    async def async_camera_image(self):
        """Return a still image response from the camera."""
        still_image_url = "http://{}/cgi-bin/api.cgi?cmd=Snap&channel=0&user={}&password={}".format(
            self._host,
            self._username,
            self._password )

        try:
            websession = async_get_clientsession(self._hass, verify_ssl=False)
            with async_timeout.timeout(10):
                response = await websession.get(still_image_url, auth=self._auth)
            self._last_image = await response.read()
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout getting image from: %s", self._name)
            return self._last_image
        except aiohttp.ClientError as err:
            _LOGGER.error("Error getting new camera image: %s", err)
            return self._last_image

        return self._last_image

    @property
    def ftp_upload_enabled(self):
        """Camera Motion recording Status."""
        return self._ftp_enabled

    @property
    def email_enabled(self):
        """Camera email Status."""
        return self._email_enabled

    def enable_ftp_upload(self):
        """Enable motion recording in camera."""
        if self._reolink_session.set_ftp(True):
            self._ftp_enabled = True
            self._hass.states.set(self.entity_id, self.state, self.state_attributes)

    def disable_ftp_upload(self):
        """Disable motion recording."""
        if self._reolink_session.set_ftp(False):
            self._ftp_enabled = False
            self._hass.states.set(self.entity_id, self.state, self.state_attributes)

    def enable_email(self):
        """Enable email motion detection in camera."""
        if self._reolink_session.set_email(True):
            self._email_enabled = True
            self._hass.states.set(self.entity_id, self.state, self.state_attributes)

    def disable_email(self):
        """Disable email motion detection."""
        if self._reolink_session.set_email(False):
            self._email_enabled = False
            self._hass.states.set(self.entity_id, self.state, self.state_attributes)

    def enable_ir_lights(self):
        """Enable IR lights."""
        if self._reolink_session.set_ir_lights(True):
            self._ir_lights_enabled = True
            self._hass.states.set(self.entity_id, self.state, self.state_attributes)

    def disable_ir_lights(self):
        """Disable IR lights."""
        if self._reolink_session.set_ir_lights(False):
            self._ir_lights_enabled = False
            self._hass.states.set(self.entity_id, self.state, self.state_attributes)   

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

    def update(self):
        """Update the data from the camera."""
        self._hass.loop.create_task(self.get_motion_state())

        if (self._last_update == 0 or
            (datetime.datetime.now() - self._last_update).total_seconds() >= 30):
            self._hass.loop.create_task(self.get_camera_settings())

    def disconnect(self, event):
        _LOGGER.info("Disconnecting from Reolink camera")
        self._reolink_session.logout()
