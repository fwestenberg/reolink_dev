<h2 align="center">
  <a href="https://reolink.com"><img src="./logo.png" alt="Reolink logotype" width="200"></a>
  <br>
  <i>Home Assistant Reolink addon</i>
  <br>
</h2>

<p align="center">
  <a href="https://github.com/custom-components/hacs"><img src="https://img.shields.io/badge/HACS-Custom-orange.svg"></a>
  <img src="https://img.shields.io/github/v/release/fwestenberg/reolink_dev" alt="Current version">
</p>

The `reolink` implementation allows you to integrate your [Reolink](https://www.reolink.com/) devices in Home Assistant.

## Installation

### Manual install

```bash
# Download a copy of this repository
$ wget https://github.com/fwestenberg/reolink_dev/archive/master.zip

# Unzip the archive
$ unzip master.zip

# Move the reolink_dev directory into your custom_components directory in your Home Assistant install
$ mv reolink_dev-master/custom_components/reolink_dev <home-assistant-install-directory>/config/custom_components/
```


### HACS install

  1. Click on HACS in the Home Assistant menu
  2. Click on `Integrations`
  3. Click the top right menu (the three dots)
  4. Select `Custom repositories`
  5. Paste the repository URL (`https://github.com/fwestenberg/reolink_dev`) in the dialog box
  6. Select category `Integration`
  7. Click `Add`
  8. Click `Install` on the Reolink IP camera box that has now appeared
  

> :warning: **After executing one of the above installation methods, restart Home Assistant. Also clear your browser cache before proceeding to the next step, as the integration may not be visible otherwise.**


In your Home Assistant installation go to: Configuration > Integrations, click the button Add Integration > Reolink IP camera
Enter the details for your camera. The camera and other sensors will now be available as an entity. 

For the motion detection to work, Home Assistant must be reachable via http from your local network. So when using https internally, motion detection will not work at this moment.

For the services and switch entities of this integration to work, you need a camera user of type "Administrator". Users of type "Guest" can only view the switch states but cannot change them and cannot call the services. Users are created and managed through the web interface of the camera (Device Settings / Cog icon -> User) or through the app (Device Settings / Cog icon -> Advanced -> User Management).

### Hints during setup
* Make sure you have set up the `Internal URL` in Home Assistant to the correct IP address and port (do not use the mDNS name)
* Make sure ONVIF is enabled on your camera/NVR. It might be disabled by default and can only be enabled when you have a screen connected to the NVR, not via webb or app clients.

## Services

The Reolink integration supports all default camera [services](https://www.home-assistant.io/integrations/camera/#services) and additionally provides the following services:

### Service `reolink_dev.set_sensitivity`

Set the motion detection sensitivity of the camera. Either all time schedule presets can be set at once, or a specific preset can be specified.

| Service data attribute  | Optional  | Description  |
| :---------------------- | :-------- | :----------- |
| `entity_id`             | no        | The camera to control.
| `sensitivity`           | no        | The sensitivity to set, a value between 1 (low sensitivity) and 50 (high sensitivity).
| `preset`                | yes       | The time schedule preset to set. Presets can be found in the Web UI of the camera.

### Service `reolink_dev.set_backlight`

Optimizing brightness and contrast levels to compensate for differences between dark and bright objects using either BLC or WDR mode. 
This may improve image clarity in high contrast situations, but it should be tested at different times of the day and night to ensure there is no negative effect.

| Service data attribute  | Optional  | Description  |
| :---------------------- | :-------- | :----------- |
| `entity_id`             | no        | The camera to control.
| `mode`                  | no        | The backlight parameter supports the following values: `BACKLIGHTCONTROL`: use Backlight Control `DYNAMICRANGECONTROL`: use Dynamic Range Control `OFF`: no optimization
### Service `reolink_dev.set_daynight`

Set the day and night mode parameter of the camera.  

| Service data attribute  | Optional  | Description  |
| :---------------------- | :-------- | :----------- |
| `entity_id`             | no        | The camera to control.
| `mode`                  | no        | The day and night mode parameter supports the following values: `AUTO` Auto switch between black & white mode `COLOR` Always record videos in color mode `BLACKANDWHITE` Always record videos in black & white mode.

### Service `reolink_dev.ptz_control`

Control the PTZ (Pan Tilt Zoom) movement of the camera.

| Service data attribute  | Optional  | Description  |
| :---------------------- | :-------- | :----------- |
| `entity_id`             | no        | The camera to control.
| `command`               | no        | The command to execute. Possibe values are: `AUTO`, `DOWN`, `FOCUSDEC`, `FOCUSINC`, `LEFT`, `LEFTDOWN`, `LEFTUP`, `RIGHT`, `RIGHTDOWN`, `RIGHTUP`, `STOP`, `TOPOS`, `UP`, `ZOOMDEC` and `ZOOMINC`.
| `preset`                | yes       | In case of the command `TOPOS`, pass the preset ID here. The possible presets are listed as attribute on the camera.
| `speed`                 | yes       | The speed at which the camera moves. Not applicable for the commands: `STOP` and `AUTO`.

**The camera keeps moving until the `STOP` command is passed to the service.**

## Camera

This integration creates a camera entity, providing a live-stream configurable from the integrations page. In the options menu, the following parameters can be configured:

| Parameter               | Description                                                                                                 |
| :-------------------    | :---------------------------------------------------------------------------------------------------------- |
| Stream                  | Switch between Sub or Main camera stream.                                                                   |
| Stream format           | Switch between h264 and h256 stream formats.                                                                |
| Protocol                | Switch between the RTMP or RTSP streaming protocol.                                                         |
| Channel                 | When using a single camera, choose stream 0. When using a NVR, switch between the different camera streams. |

## Binary Sensor

When the camera supports motion detection events, a binary sensor is created for real-time motion detection. The time to switch motion detection off can be configured via the options menu, located at the integrations page. Please notice: for using the motion detection, your Homa Assistant should be reachable (within you local network) over http (not https).

| Parameter               | Description                                                                                                 |
| :-------------------    | :---------------------------------------------------------------------------------------------------------- |
| Motion sensor off delay | Control how many seconds it takes (after the last motion detection) for the binary sensor to switch off.    |

When the camera supports AI objects detection, a binary sensor is created for each type of object (person, vehicle, pet)

## Switch

Depending on the camera, the following switches are created:

| Switch               | Description |
| :------------------- | :------------------------------------------------------------ |
| Email                | Switch email alerts from the camera when motion is detected.  |
| FTP                  | Switch FTP upload of photo and video when motion is detected. |
| IR lights            | Switch the infrared lights to auto or off.                    |
| Record audio         | Record auto or mute. This also implies the live-stream.       |
| Push notifications   | Enable or disable push notifications to Android/IOS.          |
| Recording            | Switch recording to the SD card.                              |

## Unsupported models

The following models are not to be supported:

- E1
- E1 Pro
- Battery-powered cameras
- B800: Only with NVR
- B400: Only with NVR
- D400: Only with NVR
- Lumus
