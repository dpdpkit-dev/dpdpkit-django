"""ASGI entry point. With ``DPDPKIT_CONFORMANCE=1`` it also creates the tables, for the conformance suite."""

import os
from typing import Any

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school.settings")

from django.core.asgi import get_asgi_application

django_application = get_asgi_application()


async def application(scope: dict[str, Any], receive: Any, send: Any) -> None:
    """Django's handler, plus the lifespan protocol (which Django does not speak) for the test client."""
    if scope["type"] != "lifespan":
        await django_application(scope, receive, send)
        return
    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            if os.environ.get("DPDPKIT_CONFORMANCE") == "1":
                from asgiref.sync import sync_to_async
                from django.core.management import call_command

                await sync_to_async(call_command)("migrate", interactive=False, verbosity=0)
            await send({"type": "lifespan.startup.complete"})
        elif message["type"] == "lifespan.shutdown":
            await send({"type": "lifespan.shutdown.complete"})
            return
