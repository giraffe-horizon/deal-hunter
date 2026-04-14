"""ASGI middleware registered on the FastAPI app."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

_MUTATING_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})


async def csrf_check(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Require HX-Request or X-Requested-With header on mutating requests.

    Lightweight CSRF defense — browsers won't add either header on a
    vanilla HTML form submit, but HTMX and explicit XHR clients will.
    """
    if request.method in _MUTATING_METHODS:
        has_htmx = request.headers.get("HX-Request")
        has_xhr = request.headers.get("X-Requested-With")
        if not has_htmx and not has_xhr:
            return JSONResponse(
                status_code=403,
                content={
                    "detail": ("CSRF check failed — missing HX-Request or X-Requested-With header")
                },
            )
    return await call_next(request)
