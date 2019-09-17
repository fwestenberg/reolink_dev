# reolink
Home Assistant Reolink addon

SETUP
1. Clone this project into your config/custom_components directory
2. In your configuration.yaml add the following lines:

camera:
- platform: reolink 
  name: Garden
  host: 192.168.1.20
  username: admin
  password: !secret reolink
  
3. For push notifications, login to your camera web UI. Navigate to the Device Settings, tab Network -> Advanced -> E-mail.
Add the following configuration here:

SMTP Server: 192.168.1.100 --> Your Home Assistant IP
SMTP Port: 1026 --> Can be changed to something else
Sender Address: hass@hass.io --> Just something
Receipient Address 1: garden@reolink.com --> This should match the camera device name in Home Assistant (before the @)
Attachment: No Attachment
Interval: 30 Seconds

Enable the checkbox under Schedule and press OK.

4. Now restart Home Assistant, the local SMTP server should be setup (see HA's logfile). When Home Assistant is fully started, hit the E-Mail Test button in the camera's UI. Home assistant should detect motion! But... there is one limitation (tested on my RLC-420 and RLC-430. The Test button immediately sends the email to HA. But the motion detection to email takes about 25 seconds. I already had contact about this with the Reolink support desk, but this seems to be normal behaviour:

"I have confirmed with our senior engineers that it's normal. When you test email, it's just your sender address to send an email to the recipient address, which is very quick. When the camera detects a movement, it'll pre-record, write video to the SD card, send email and all the other settings. So it'll deal with a lot of things at the same time. Then it won't communicate to your email server that quick to send an email notification."
