# Vercel Python serverless entry: serves the same Flask app as Docker.
import os
import sys
from urllib.parse import parse_qsl, urlencode

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app import create_app  # noqa: E402

app = create_app()


class RestoreApiPath:
    """vercel.json rewrites every /api/* request to this single function and passes
    the original path in the `__path` query parameter. Put it back, so Flask routes
    /api/health, /api/feed, ... exactly as it does locally and in Docker."""

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        pairs = parse_qsl(environ.get("QUERY_STRING", ""), keep_blank_values=True)
        original = [v for k, v in pairs if k == "__path"]
        if original:
            environ["PATH_INFO"] = "/api/" + original[0].lstrip("/")
            environ["QUERY_STRING"] = urlencode([(k, v) for k, v in pairs if k != "__path"])
        return self.wsgi_app(environ, start_response)


app.wsgi_app = RestoreApiPath(app.wsgi_app)