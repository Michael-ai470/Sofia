"""Generic WSGI entry point — gunicorn, uwsgi, or `python wsgi.py` for local dev."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app  # noqa: E402

application = create_app()
app = application

if __name__ == "__main__":
    from config import Config
    application.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=Config.DEBUG,
    )
