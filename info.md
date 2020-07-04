A Home Assistant integration for your Reolink security cameras which enables you to detect motion, control the IR lights, recording and the sending of emails.

*Configuration guide can be found [here](https://github.com/fwestenberg/reolink/blob/master/README.md).*


{% if installed %}

#### Changes from version {{ version_installed }}

{% if version_installed == version_available  %}
*You already have the latest released version installed.*
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