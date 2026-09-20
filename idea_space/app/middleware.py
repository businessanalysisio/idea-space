import base64
import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

UNPROTECTED_PATHS = {"/health"}


class SitePasswordMiddleware(BaseHTTPMiddleware):
    """Gate the whole app behind one shared password via HTTP Basic Auth.

    No-ops when SITE_PASSWORD isn't set, so local dev and tests are
    unaffected. This app has no per-user login (multi-user is a future
    slice) — this is a single shared secret meant to keep a public
    deployment from being wide open, not a real auth system.
    """

    async def dispatch(self, request: Request, call_next):
        expected_password = os.environ.get("SITE_PASSWORD")
        if not expected_password or request.url.path in UNPROTECTED_PATHS:
            return await call_next(request)

        if _has_valid_credentials(request, expected_password):
            return await call_next(request)

        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Idea Space"'},
        )


def _has_valid_credentials(request: Request, expected_password: str) -> bool:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Basic "):
        return False

    try:
        decoded = base64.b64decode(auth_header[len("Basic "):]).decode("utf-8")
    except Exception:
        return False

    _, _, password = decoded.partition(":")
    return secrets.compare_digest(password, expected_password)
