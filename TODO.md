# TODO

This file is kept as a lightweight scratchpad.

Current cleanup ideas:

- collapse the remaining auth/config duplication between `shared/config.py` and `shared/runtime.py`
- decide whether `web/order_scheduler.py` should stay cron-based or switch to a simpler schedule model
- split the Flask app creation into a factory if more tests or instances are needed
- remove any remaining legacy compatibility paths once the current CLI and web flows are stable
