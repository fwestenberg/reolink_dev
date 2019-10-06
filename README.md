# Reolink IP camera
Home Assistant Reolink addon

__SETUP__
1. Clone this project into your config/custom_components directory
2. In your configuration.yaml add the following lines:

```text
camera:
- platform: reolink 
  name: frontdoor
  host: 192.168.1.20
  username: admin
  password: !secret reolink
```
  
3. For push notifications, login to your camera web UI. 
Navigate to the Device Settings, tab Network -> Advanced -> E-mail.
Add the following configuration here:

```text
SMTP Server: 192.168.1.100 --> Your Home Assistant IP
SMTP Port: 1026 --> Can be changed to something else
Sender Address: hass@hass.io --> Just something
Receipient Address 1: frontdoor@reolink.com --> This should match the camera device name in Home Assistant (before the @)
Attachment: No Attachment
Interval: 30 Seconds
```

Enable the checkbox under Schedule and press OK.

4. Of course you want to have a binary sensor for the motion detection now, so add this to your binary_sensors.yaml:

```text
platform: template
sensors:
  motion_frontdoor:
    friendly_name: Camera frontdoor
    device_class: motion
    entity_id: camera.frontdoor
    value_template: "{{ is_state('camera.frontdoor', 'motion') }}"
    delay_off: 
        seconds: 30
```

5. Next you can create those fancy buttons:
```text
platform: template
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
        mdi:bell
      {% else %}
        mdi:bell-off
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
```

6. Now restart Home Assistant, the local SMTP server should be setup (see HA's logfile). When Home Assistant is fully started, hit the E-Mail Test button in the camera's UI. Home assistant should detect motion! But... there is one limitation (tested on my RLC-420 and RLC-430. The Test button immediately sends the email to HA. But the motion detection to email takes about 25 seconds. I already had contact about this with the Reolink support desk, but this seems to be normal behaviour:

_"I have confirmed with our senior engineers that it's normal. When you test email, it's just your sender address to send an email to the recipient address, which is very quick. When the camera detects a movement, it'll pre-record, write video to the SD card, send email and all the other settings. So it'll deal with a lot of things at the same time. Then it won't communicate to your email server that quick to send an email notification."_

__USAGE__
In your Home Assistant Lovelace, add a new card with the following:

```text
camera_image: camera.frontdoor
entities:
  - switch.camera_frontdoor_ir_lights
  - switch.camera_frontdoor_email
  - switch.camera_frontdoor_ftp
  - binary_sensor.motion_frontdoor
title: frontdoor
type: picture-glance
```

Now you will have card like this (notice the buttons and motion icon):

![alt text](https://github.com/fwestenberg/reolink/blob/master/Lovelace%20Card.png)

