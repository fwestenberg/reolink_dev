import json
import requests

class APIHandler(object):

    def __init__(self, ip):
        self.url = "http://" + ip + "/cgi-bin/api.cgi"
        self.token = None

    # Token

    def login(self, username, password):
        """
        Get login token
        Must be called first, before any other operation can be performed
        :param username:
        :param password:
        :return:
        """
        try:
            body = [{"cmd": "Login", "action": 0, "param": {"User": {"userName": username, "password": password}}}]
            param = {"cmd": "Login", "token": "null"}
            
            response = requests.post(self.url, data=json.dumps(body), params=param)     

            if response is not None:
                data = json.loads(response.text)[0]
                code = data["code"]

                if int(code) == 0:
                    self.token = data["value"]["Token"]["name"]
                    print("Login success")
                    print(self.token)
                else:
                    print("Failed to login\nStatus Code:", response.status_code)
            else:
                print("Failed to login\nStatus Code:", response.status_code)
        except Exception as e:
            print("Error Login\n", e)
            raise

    def logout(self):
        try:
            body = [{"cmd":"Logout","action":0,"param":{}}]
            param = {"cmd": "Logout", "token": self.token}
            
            response = requests.post(self.url, data=json.dumps(body), params=param)

            if response is not None:

                data = json.loads(response.text)[0]
                if int(data["code"]) != 0:
                    print("Failed to logout\nStatus Code:", response.status_code)
        except Exception as e:
            print("Error Logout\n", e)
            raise


    ###########
    # SETTERS
    ###########
    def set_ftp(self, enabled):

        current_settings = self.get_ftp()

        if not current_settings:
            print("Error while fetching current FTP settings")
            return

        if enabled == True:
            newValue = 1
        else:
            newValue = 0

        # Copy the body data into the new body data, so no settings will change
        body = [{"cmd":"SetFtp","action":0,"param": current_settings[0]["value"] }]
        # Change the FTP enable setting
        body[0]["param"]["Ftp"]["schedule"]["enable"] = newValue

        return self.call(body, {"cmd": "SetFtp", "token": self.token} )

    def set_email(self, enabled):

        current_settings = self.get_email()

        if not current_settings:
            print("Error while fetching current email settings")
            return

        if enabled == True:
            newValue = 1
        else:
            newValue = 0

        # Copy the body data into the new body data, so no settings will change
        body = [{"cmd":"SetEmail","action":0,"param": current_settings[0]["value"] }]
        # Change the Email enable setting
        body[0]["param"]["Email"]["schedule"]["enable"] = newValue

        return self.call(body, {"cmd": "SetEmail", "token": self.token} )

    def set_ir_lights(self, enabled):

        current_settings = self.get_ir_lights()

        if not current_settings:
            print("Error while fetching current IR light settings")
            return

        if enabled == True:
            newValue = "Auto"
        else:
            newValue = "Off"

        # Copy the body data into the new body data, so no settings will change
        body = [{"cmd":"SetIrLights","action":0,"param": current_settings[0]["value"] }]
        # Change the Email enable setting
        body[0]["param"]["IrLights"]["state"] = newValue

        return self.call(body, {"cmd": "SetIrLights", "token": self.token} )

    ###########
    # GETTERS
    ###########
    def get_net_ports(self):
        return self.call([{"cmd": "GetNetPort", "action": 1, "param": {}}],
                         {"token": self.token})

    def get_ftp(self):
        return self.call([{"cmd": "GetFtp", "action": 0, "param": {}}], 
                         {"token": self.token})
    
    def get_device_info(self):
        return self.call([{"cmd":"GetDevInfo","action":0,"param":{}}], 
                         {"token": self.token})

    def get_email(self):
        return self.call([{"cmd":"GetEmail","action":1,"param":{}}], 
                         {"token": self.token})

    def get_ir_lights(self):
        return self.call([{"cmd":"GetIrLights","action":1,"param":{}}], 
                         {"token": self.token})    

    def call(self, body, param):
        try:
            if self.token is None:
                raise ValueError("Login first")
            
            response = requests.post(self.url, data=json.dumps(body), params=param)
            
            return json.loads(response.text)
        except Exception as e:
            print(body[0]["cmd"], e)


class Camera(APIHandler):
    def __init__(self, ip="", username="admin", password=""):
        APIHandler.__init__(self, ip)
        self.ip = ip
        self.username = username
        self.password = password
        super(Camera, self).login(self.username, self.password)