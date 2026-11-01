"""Django signals for app-specific hooks, fed by the kit's event bus.

* :data:`consent_withdrawn`: a principal withdrew consent for a purpose.
* :data:`erasure_due`: a scheduled erasure has come due (sent just before the erasure handlers run).
* :data:`request_opened`: a data principal opened a rights request.

Receivers get ``sender`` (the :class:`~dpdpkit.Kit` class), ``event`` (the core
:class:`~dpdpkit.events.Event`), ``tenant_id`` and the event's data as keyword arguments: ``principal`` and
``purpose`` for the first two, ``principal``, ``request_id`` and ``kind`` for the last. A failing receiver is
logged and never blocks the others or the state change::

    @receiver(consent_withdrawn)
    def stop_marketing(sender, principal, purpose, **kwargs): ...

The kit built from ``settings.DPDPKIT`` (or passed to :func:`~dpdpkit.django.conf.set_kit`) is connected
automatically; call :func:`connect_kit` for any other kit.
"""

from __future__ import annotations

import logging

from django.dispatch import Signal
from dpdpkit import Kit
from dpdpkit.events import CONSENT_WITHDRAWN, ERASURE_DUE, REQUEST_OPENED, Event, Handler

log = logging.getLogger("dpdpkit.django")

consent_withdrawn = Signal()
erasure_due = Signal()
request_opened = Signal()

_BY_EVENT = {
    CONSENT_WITHDRAWN: consent_withdrawn,
    ERASURE_DUE: erasure_due,
    REQUEST_OPENED: request_opened,
}


def _forward(signal: Signal) -> Handler:
    def handler(event: Event) -> None:
        for receiver, result in signal.send_robust(Kit, event=event, tenant_id=event.tenant_id, **event.data):
            if isinstance(result, Exception):
                log.error("%s receiver %r failed: %r", event.type, receiver, result, exc_info=result)

    return handler


def connect_kit(kit: Kit) -> None:
    """Send the signals for ``kit``'s events. Connecting the same kit twice has no effect."""
    if getattr(kit, "_dpdpkit_django_signals", False):
        return
    for event_type, signal in _BY_EVENT.items():
        kit.events.subscribe(event_type, _forward(signal))
    kit._dpdpkit_django_signals = True  # type: ignore[attr-defined]
