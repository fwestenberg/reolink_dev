# Reolink IP camera
Home Assistant Reolink addon


__Unsupported models__
- B800
- B400
- D400
- E1
- E1 Pro


__SETUP__
1. Clone this project into your config/custom_components directory
2. In your configuration.yaml add the following lines:

```text
camera:
- platform: reolink_dev
  host: IP_ADDRESS
  username: admin
  password: YOUR_PASSWORD
  name: camera (optional, default Reolink Camera)
  stream: main or sub (optional, default main)
  protocol: rtmp or rtsp (optional, default rtmp)
  channel: NVR camera channel (optional, default 0)
  scan_interval: 5 (optional, default 30s)
```
  
3. Create a binary sensor for the motion detection, add this to your binary_sensors.yaml:

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

4. Create email, FTP upload and infrared light buttons:
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
```

5. Now restart Home Assistant.

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

![alt text](https://github.com/fwestenberg/reolink/blob/master/Lovelace%20Card.PNG)

