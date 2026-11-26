"""Vercel entrypoint.

Vercel serves this file as a serverless function and routes every /api/* request
to it, with the original path intact. The FastAPI app declares its routes as
/ask, /documents and so on, with no prefix, because in development Vite strips
/api before forwarding. So the prefix is stripped here too and both environments
see identical paths.

Doing it in ASGI rather than with FastAPI's root_path keeps app/main.py free of
any knowledge of where it happens to be deployed.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app as _fastapi_app  # noqa: E402


class StripApiPrefix:
    """Remove a leading /api from the request path before the app sees it."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            path = scope.get("path", "")
            if path == "/api" or path.startswith("/api/"):
                scope = dict(scope)
                scope["path"] = path[4:] or "/"
                raw = scope.get("raw_path")
                if raw:
                    scope["raw_path"] = raw.replace(b"/api", b"", 1) or b"/"
        await self.inner(scope, receive, send)


app = StripApiPrefix(_fastapi_app)
