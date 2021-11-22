#TROUBLESHOOTING GUIDE

## Checklist

- Is your hardware compatible with this integration?
- Are you using an up-to-date firmware?
- Did you check the Frequent Issue section of this document?
- Open a support ticket and provide useful logs (Look at sections below to enable debug logging)

## Enable debugging of Reolink components in HA
Edit your configuration yaml file to insert/edit the logger section and then restart your Core services:
```yaml
logger:
  default: warning
  logs:
    custom_components.reolink_dev: debug
    custom_components.reolink_dev.base.data: warning
    reolink: debug
```
Copy and Paste all logs after you have clicked on "LOAD FULL HOMEASSISTANT LOG" button.

## Frequent issues

### Motion sensors remains unavailable or never trigger

- If you are using a NVR, you must first enable ONVIF protocol via a menu which is only available via
a HDMI screen connected to the NVR, without this then HA cannot be aware of a motion detection event.
- HomeAssistant must have an internal URL configured and:
  - IT MUST NOT USE HTTPS : Reolink doesn't support HTTPS based Webhooks.
  - URL also should not be using a DNS name but an ip address instead unless you have a solid DNS setup 
  your camera is probably not able to resolve your address


