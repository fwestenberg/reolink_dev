A Home Assistant integration for your Reolink security cameras which enables you to detect motion, control the IR lights, recording and the sending of emails.

*Configuration guide can be found [here](https://github.com/fwestenberg/reolink_dev/blob/master/README.md).*


{% if installed %}

#### Changes from version {{ version_installed }}

{% if version_installed == version_available  %}
*You already have the latest released version installed.*
{% endif %}

{% if version_installed.replace("v", "") | float < 0.10  %}
**New features:**
- RTSP support from options menu

**Bug fixes:**
- Change logging to debug for most of the errors
- Truncate password at 31 characters (#104)
- Improved exception handling
- Increased default timeout (30s default)
- Restore options after reboot

{% if version_installed.replace("v", "") | float < 0.8  %}
**New features:**
- Integration flow
- Binary sensor for motion events, real time push
- Switches instead of events
- Services: SET_SENSITIVITY, SET_DAYNIGHT, PTZ_CONTROL
- Camera settings can be changed from the options menu

**Bugfixes:**
- Motion detection not working (#85)
- Error that is only fixed by rebooting the camera (#83)
- Interfering with Blink (#79
- Infrared switch (#78)
- url does not include port (#70)
- HA Requires Reboot if the camera does not respond during start up (#66)
- Camera on port 82 instead of 80 (#65)
- PTZ position control (#64)
- Add availability sensor (#53)
- Snapshot requires login first (#52)
- Camera Pan & Tilt (#23)
{% endif %}

{% if version_installed.replace("v", "") | float < 0.3  %}
**Bugfix:**  Change duplicate disable_ir_lights to disable_recording.
{% endif %}

{% if version_installed.replace("v", "") | float < 0.2  %}
**New feature:** Recording added.
{% endif %}

{% if version_installed.replace("v", "") | float < 0.1  %}
**Bugfix:** Async handling: aiohttp.
{% endif %}

{% endif %}
