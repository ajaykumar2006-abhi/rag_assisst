"""Shared FastAPI dependencies.

The service container is created once during application startup and stored on
``app.state``. Tests replace it with a container pointed at a temporary data
directory, which is why every dependency reads from ``request.app.state`` rather
than from a module-level global.
"""

from __future__ import annotations

from fastapi import Request

from ..services.container import ServiceContainer


def get_container(request: Request) -> ServiceContainer:
    container = getattr(request.app.state, "container", None)
    if container is None:  # pragma: no cover - only if startup was skipped
        raise RuntimeError("The service container has not been initialised.")
    return container
