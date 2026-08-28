"""
Passenger entry point for cPanel.

Two things this file must never do, both learned the hard way:

  1. It must not import `imp`. That module was removed in Python 3.12 and
     was the root cause of an entire deployment's worth of opaque 500s.
     `importlib` is the replacement and has been since 3.4.

  2. It must not swallow the boot error. If the app cannot start, Passenger
     should see the traceback in stderr, not serve a blank 500 that gives
     you nothing to debug from a shared host with no shell.

cPanel setup (Setup Python App):
    Application root       : /home/<cpuser>/sofia
    Application URL        : your domain or subdomain
    Application startup    : passenger_wsgi.py
    Entry point            : application
    Python version         : 3.11.x
"""

import os
import sys

# Make the project importable regardless of Passenger's working directory.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app  # noqa: E402

application = create_app()

# Some Passenger configurations look for `app` instead.
app = application
