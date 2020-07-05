<h2 align="center">
  <a href="https://reolink.com"><img src="./logo.png" alt="Reolink logotype" width="200"></a>
  <br>
  <i>Home Assistant Reolink addon</i>
  <br>
</h2>

<p align="center">
  <a href="https://github.com/custom-components/hacs"><img src="https://img.shields.io/badge/HACS-Custom-orange.svg"></a>
  <img src="https://img.shields.io/github/v/release/fwestenberg/reolink" alt="Current version">
</p>

<p align="center">
  <img src="./Lovelace%20Card.PNG?raw=true" alt="Example Lovelace card">
</p>

## Table of contents

- [Installation](#-installation)
- [Configuration](#-configuration)
- [Usage](#-usage)
- [Unsupported models](#-unsupported-models)
- [Troubleshooting](#-troubleshooting)

---


## Installation

### Manual install

```bash
# Download a copy of this repository
$ wget https://github.com/fwestenberg/reolink/archive/master.zip

# Unzip the archive
$ unzip master.zip

# Move the reolink_dev directory into your custom_components directory in your Home Assistant install
$ mv reolink-master/custom_components/reolink_dev <home-assistant-install-directory>/config/custom_components/
```


### HACS install

  1. Click on HACS in the Home Assistant menu
  2. Click on `Integrations`
  3. Click the top right menu (the three dots)
  4. Select `Custom repositories`
  5. Paste the repository URL (`https://github.com/fwestenberg/reolink`) in the dialog box
  6. Select category `Integration`
  7. Click `Add`
  8. Click `Install` on the Reolink IP camera box that has now appeared


## Configuration

1. Add the following to your `configuration.yaml`:
```yaml
camera:
- platform: reolink_dev
  host: IP_ADDRESS
  username: admin
  password: YOUR_PASSWORD
  name: frontdoor (optional, default Reolink Camera)
  stream: main or sub (optional, default main)
  protocol: rtmp or rtsp (optional, default rtmp)
  channel: NVR camera channel (optional, default 0)
  scan_interval: 5 (optional, default 30s)

binary_sensor:
  platform: template
  sensors:
    motion_frontdoor:
      friendly_name: Camera frontdoor
      device_class: motion
      entity_id: camera.frontdoor
      value_template: "{{ is_state('camera.frontdoor', 'motion') }}"
      delay_off: 
          seconds: 30

switch:
  - platform: template
    switches:
      camera_frontdoor_email:
        value_template: "{{ is_state_attr('camera.frontdoor', 'email_enabled', true) }}"
        turn_on:
          service: camera.enable_email
          data:
            entity_id: camera.frontdoor
        turn_off:
          service: camera.disable_email
          data:
            entity_id: camera.frontdoor
        icon_template: >-
          {% if is_state_attr('camera.frontdoor', 'email_enabled', true) %}
            mdi:email
          {% else %}
            mdi:email-outline
          {% endif %}
            
      camera_frontdoor_ftp:
        value_template: "{{ is_state_attr('camera.frontdoor', 'ftp_enabled', true) }}"
        turn_on:
          service: camera.enable_ftp
          data:
            entity_id: camera.frontdoor
        turn_off:
          service: camera.disable_ftp
          data:
            entity_id: camera.frontdoor
        icon_template: >-
          {% if is_state_attr('camera.frontdoor', 'ftp_enabled', true) %}
            mdi:filmstrip
          {% else %}
            mdi:filmstrip-off
          {% endif %}
          
      camera_frontdoor_ir_lights:
        value_template: "{{ is_state_attr('camera.frontdoor', 'ir_lights_enabled', true) }}"
        turn_on:
          service: camera.enable_ir_lights
          data:
            entity_id: camera.frontdoor
        turn_off:
          service: camera.disable_ir_lights
          data:
            entity_id: camera.frontdoor
        icon_template: >-
          {% if is_state_attr('camera.frontdoor', 'ir_lights_enabled', true) %}
            mdi:flashlight
          {% else %}
            mdi:flashlight-off
          {% endif %}

      camera_motion_detection:
        value_template: "{{ is_state_attr('camera.frontdoor', 'motion_detection_enabled', true) }}"
        turn_on:
          service: camera.enable_motion_detection
          data:
            entity_id: camera.frontdoor
        turn_off:
          service: camera.disable_motion_detection
          data:
            entity_id: camera.frontdoor
        icon_template: >-
          {% if is_state_attr('camera.frontdoor', 'motion_detection_enabled', true) %}
            mdi:motion-sensor
          {% else %}
            mdi:motion-sensor-off
          {% endif %}
```
2. Restart Home Assistant.


## Usage

In your Home Assistant Lovelace, add a new card with the following:

```yaml
type: picture-glance
title: frontdoor
camera_image: camera.frontdoor
entities:
  - switch.camera_frontdoor_ir_lights
  - switch.camera_frontdoor_email
  - switch.camera_frontdoor_ftp
  - binary_sensor.motion_frontdoor
```

Now you will have a card the looks like this (notice the buttons and motion icon):

![Example Lovelace card](/Lovelace%20Card.PNG?raw=true)


## Unsupported models

- B800
- B400
- D400
- E1
- E1 Pro
- Battery-powered camera's


## Troubleshooting

- If the buttons are not working on the Lovelace card, make sure that the user that you configured in the Reolink camera is an **administrator**.