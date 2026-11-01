"""Consent checks for Django views: the :func:`requires_consent` decorator and :class:`RequiresConsentMixin`.

Both resolve the caller with ``DPDPKIT['PRINCIPAL_RESOLVER']`` and ask the kit's ledger. A caller who is not signed
in gets 401 ``unauthenticated``; a caller without consent for every purpose gets 403 ``consent_required`` with the
purpose in ``details``. Both use the contract's ``{"error": {...}}`` body unless ``on_denied`` supplies a response
(for example a redirect to a consent page).
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any, TypeVar, cast

from asgiref.sync import sync_to_async

from django.http import HttpRequest, HttpResponse
from dpdpkit.errors import ConsentRequired, DpdpkitError
from dpdpkit.models import ConsentState, ConsentStatus

from . import conf
from .http import Unauthenticated, render_dpdpkit_error

F = TypeVar("F", bound=Callable[..., Any])

#: ``on_denied(request, error)`` returns the response sent instead of calling the view.
OnDenied = Callable[[HttpRequest, DpdpkitError], HttpResponse]


def check_consent(request: HttpRequest, purposes: tuple[str, ...]) -> None:
    """Raise :class:`~dpdpkit.django.http.Unauthenticated` or :class:`~dpdpkit.errors.ConsentRequired` unless the
    caller has consented to every purpose. Purposes with a Section 7 legitimate use always pass."""
    principal = conf.resolve_principal(request)
    if principal is None:
        raise Unauthenticated("sign in to use this endpoint")
    consent = conf.get_kit().consent
    for purpose in purposes:
        consent.require(principal, purpose)


def record_preferences(request: HttpRequest) -> list[ConsentState]:
    """Record the form posted by ``{% dpdp_preferences %}`` for the signed-in caller.

    Ticked purposes are granted; unticked ones that were granted are withdrawn, the rest are recorded as denied.
    Raises :class:`~dpdpkit.django.http.Unauthenticated` for anonymous callers."""
    principal = conf.resolve_principal(request)
    if principal is None:
        raise Unauthenticated("sign in to use this endpoint")
    kit = conf.get_kit()
    ticked = set(request.POST.getlist("purpose"))
    notice_version = int(request.POST["notice_version"]) if request.POST.get("notice_version", "").isdigit() else None
    locale = request.POST.get("locale") or None
    current = {s.purpose: s for s in kit.consent.state(principal)}
    shown = {p.id for p in kit.registry.consent_purposes()}
    decisions: dict[str, bool] = {}
    for purpose in sorted(shown):
        state = current.get(purpose)
        granted = state is not None and state.status is ConsentStatus.GRANTED
        if purpose in ticked:
            if not granted:
                decisions[purpose] = True
        elif granted:
            kit.consent.withdraw(principal, purpose, source="web")
        elif state is None:
            decisions[purpose] = False
    if decisions:
        kit.consent.record(principal, decisions, notice_version=notice_version, locale=locale, source="web")
    return kit.consent.state(principal)


def _denied(request: HttpRequest, exc: DpdpkitError, on_denied: OnDenied | None) -> HttpResponse:
    return on_denied(request, exc) if on_denied is not None else render_dpdpkit_error(exc)


def requires_consent(*purposes: str, on_denied: OnDenied | None = None) -> Callable[[F], F]:
    """Decorate a function view (sync or async) so it only runs when the caller has consented to ``purposes``::

    @requires_consent("marketing")
    def send_offer(request): ...
    """
    if not purposes:
        raise ValueError("requires_consent needs at least one purpose")

    def decorate(view: F) -> F:
        if inspect.iscoroutinefunction(view):

            @functools.wraps(view)
            async def async_wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
                try:
                    await sync_to_async(check_consent)(request, purposes)
                except (Unauthenticated, ConsentRequired) as exc:
                    return _denied(request, exc, on_denied)
                return cast(HttpResponse, await view(request, *args, **kwargs))

            return cast(F, async_wrapper)

        @functools.wraps(view)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            try:
                check_consent(request, purposes)
            except (Unauthenticated, ConsentRequired) as exc:
                return _denied(request, exc, on_denied)
            return cast(HttpResponse, view(request, *args, **kwargs))

        return cast(F, wrapper)

    return decorate


class RequiresConsentMixin:
    """Class-based view mixin. List it before the view class and set ``consent_purposes``::

        class OfferView(RequiresConsentMixin, View):
            consent_purposes = ("marketing",)

    Override :meth:`consent_denied` to answer a denial differently."""

    consent_purposes: tuple[str, ...] = ()

    def consent_denied(self, request: HttpRequest, error: DpdpkitError) -> HttpResponse:
        return render_dpdpkit_error(error)

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if not self.consent_purposes:
            raise ValueError(f"{type(self).__name__}.consent_purposes must name at least one purpose")
        try:
            check_consent(request, tuple(self.consent_purposes))
        except (Unauthenticated, ConsentRequired) as exc:
            return self.consent_denied(request, exc)
        parent = cast(Any, super())
        return cast(HttpResponse, parent.dispatch(request, *args, **kwargs))
