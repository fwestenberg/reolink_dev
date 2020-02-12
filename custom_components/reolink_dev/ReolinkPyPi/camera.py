"""
Reolink Camera API
"""
import requests
import datetime
import json
import logging

_LOGGER = logging.getLogger(__name__)

class ReolinkApi(object):
    def __init__(self, ip, channel):
        self._url = "http://" + ip + "/cgi-bin/api.cgi"
        self._ip = ip
        self._channel = channel
        self._token = None
        self._motion_state = False
        self._last_motion = 0
        self._device_info = None
        self._motion_state = None
        self._ftp_state = None
        self._email_state = None
        self._ir_state = None
        self._rtspport = None
        self._rtmpport = None
        self._ptzpresets = dict()

    def session_active(self):
        return self._token is not None

    def status(self):
        if self._token is None:
            return

        param_channel = {"channel": self._channel}
        body = [{"cmd": "GetDevInfo", "action":1, "param": param_channel},
            {"cmd": "GetNetPort", "action": 1, "param": param_channel},
            {"cmd": "GetFtp", "action": 1, "param": param_channel},
            {"cmd": "GetEmail", "action": 1, "param": param_channel},
            {"cmd": "GetIrLights", "action": 1, "param": param_channel},
            {"cmd": "GetPtzPreset", "action": 1, "param": param_channel}]

        param = {"token": self._token}
        response = self.send(body, param)

        try:
            json_data = json.loads(response.text)
        except:
            _LOGGER.error(f"Error translating response to json")
            self._token = None
            return

        for data in json_data:
            try:
                if data["cmd"] == "GetDevInfo": 
                    self._device_info = data

                elif data["cmd"] == "GetNetPort":
                    self._netport_settings = data
                    self._rtspport = data["value"]["NetPort"]["rtspPort"]
                    self._rtmpport = data["value"]["NetPort"]["rtmpPort"]

                elif data["cmd"] == "GetFtp": 
                    self._ftp_settings = data
                    if (data["value"]["Ftp"]["schedule"]["enable"] == 1):
                        self._ftp_state = True
                    else:
                        self._ftp_state = False

                elif data["cmd"] == "GetEmail":
                    self._email_settings = data
                    if (data["value"]["Email"]["schedule"]["enable"] == 1):
                        self._email_state = True
                    else:
                        self._email_state = False
                        
                elif data["cmd"] == "GetIrLights":
                    self._ir_settings = data
                    if (data["value"]["IrLights"]["state"] == "Auto"):
                        self._ir_state = True
                    else:
                        self._ir_state = False

                elif data["cmd"] == "GetPtzPreset":
                    self._ptzpresets_settings = data
                    for preset in data["value"]["PtzPreset"]:
                        if int(preset["enable"]) == 1:
                            preset_name = preset["name"]
                            preset_id = int(preset["id"])
                            self._ptzpresets[preset_name] = preset_id
                            _LOGGER.debug(f"Got preset {preset_name} with ID {preset_id}")
                        else:
                            _LOGGER.debug(f"Preset is not enabled: {preset}")
            except:
                continue    

    @property
    def motion_state(self):
        body = [{"cmd": "GetMdState", "action": 0, "param":{"channel":self._channel}}]
        param = {"token": self._token}
        
        response = self.send(body, param)

        try:
            json_data = json.loads(response.text)

            if json_data is None:
                _LOGGER.error(f"Unable to get Motion detection state at IP {self._ip}")
                self._motion_state = False
                return self._motion_state

            if json_data[0]["value"]["state"] == 1:
                self._motion_state = True 
                self._last_motion = datetime.datetime.now()
            else:
                self._motion_state = False
        except:
            self._motion_state = False

        return self._motion_state
    
    @property
    def still_image(self):
        response = self.send(None, f"?cmd=Snap&channel={self._channel}&token={self._token}", stream=True)
        if response is None:
            return

        response.raw.decode_content = True
        return response.raw

    @property
    def snapshot(self):
        response = self.send(None, f"?cmd=Snap&channel={self._channel}&token={self._token}", stream=False)
        if response is None:
            return

        return response.content

    @property
    def ftp_state(self):
        return self._ftp_state

    @property
    def email_state(self):
        return self._email_state

    @property
    def ir_state(self):
        return self._ir_state

    @property
    def rtmpport(self):
        return self._rtmpport

    @property
    def rtspport(self):
        return self._rtspport

    @property
    def last_motion(self):
        return self._last_motion

    @property
    def ptzpresets(self):
        return self._ptzpresets

    def login(self, username, password):
        body = [{"cmd": "Login", "action": 0, "param": {"User": {"userName": username, "password": password}}}]
        param = {"cmd": "Login", "token": "null"}
        
        response = self.send(body, param)

        try:
            json_data = json.loads(response.text)
        except:
            _LOGGER.error(f"Error translating login response to json")
            return

        if json_data is not None:
            if json_data[0]["code"] == 0:
                self._token = json_data[0]["value"]["Token"]["name"]
                _LOGGER.info(f"Reolink camera logged in at IP {self._ip}")
            else:
                _LOGGER.error(f"Failed to login at IP {self._ip}. No token available")
        else:
            _LOGGER.error(f"Failed to login at IP {self._ip}. Connection error.")

    def logout(self):
        body = [{"cmd":"Logout","action":0,"param":{}}]
        param = {"cmd": "Logout", "token": self._token}

        self.send(body, param)

    def set_ftp(self, enabled):
        self.status()

        if not self._ftp_settings:
            _LOGGER.error("Error while fetching current FTP settings")
            return

        if enabled == True:
            newValue = 1
        else:
            newValue = 0

        body = [{"cmd":"SetFtp","action":0,"param": self._ftp_settings["value"] }]
        body[0]["param"]["Ftp"]["schedule"]["enable"] = newValue

        response = self.send(body, {"cmd": "SetFtp", "token": self._token} )
        try:
            json_data = json.loads(response.text)
            if json_data[0]["value"]["rspCode"] == 200:
                return True
            else:
                return False
        except:
            _LOGGER.error(f"Error translating FTP response to json")
            return False

    def set_email(self, enabled):
        self.status()

        if not self._email_settings:
            _LOGGER.error("Error while fetching current email settings")
            return

        if enabled == True:
            newValue = 1
        else:
            newValue = 0

        body = [{"cmd":"SetEmail","action":0,"param": self._email_settings["value"] }]
        body[0]["param"]["Email"]["schedule"]["enable"] = newValue

        response = self.send(body, {"cmd": "SetEmail", "token": self._token} )
        try:
            json_data = json.loads(response.text)
            if json_data[0]["value"]["rspCode"] == 200:
                return True
            else:
                return False
        except:
            _LOGGER.error(f"Error translating Email response to json")
            return False

    def set_ir_lights(self, enabled):
        self.status()

        if not self._ir_settings:
            _LOGGER.error("Error while fetching current IR light settings")
            return

        if enabled == True:
            newValue = "Auto"
        else:
            newValue = "Off"

        body = [{"cmd":"SetIrLights","action":0,"param": self._ir_settings["value"] }]
        body[0]["param"]["IrLights"]["state"] = newValue

        response = self.send(body, {"cmd": "SetIrLights", "token": self._token} )
        try:
            json_data = json.loads(response.text)
            if json_data[0]["value"]["rspCode"] == 200:
                return True
            else:
                return False
        except requests.exceptions.RequestException:
            _LOGGER.error(f"Error translating IR Lights response to json")
            return False

    def send(self, body, param, stream=False):
        try:
            if (self._token is None and 
                (body is None or body[0]["cmd"] != "Login")):
                _LOGGER.info(f"Reolink camera at IP {self._ip} is not logged in")
                return                

            if body is None:
                response = requests.get(self._url, params=param, stream=stream, timeout=10)
            else:
                response = requests.post(self._url, data=json.dumps(body), params=param, timeout=10)
            
            return response
        except requests.exceptions.RequestException: 
            _LOGGER.error(f"Exception while calling Reolink camera API at ip {self._ip}")
            return None
