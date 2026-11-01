"""The REST contract from dpdpkit-spec's ``openapi.yaml``, implemented once on dpdpkit-core.

Handlers are plain functions registered with :func:`endpoint`. ``views.py`` serves them as JSON views and
``drf.py`` as Django REST framework viewsets.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from django.http import HttpRequest, HttpResponse, JsonResponse
from dpdpkit import Kit
from dpdpkit._util import as_utc
from dpdpkit.errors import DpdpkitError, ValidationFailed
from dpdpkit.models import (
    ConsentReceipt,
    ConsentState,
    Notice,
    RequestKind,
    RequestStatus,
    RightsRequest,
    Role,
)

from . import conf
from .http import Forbidden, MethodNotAllowed, NotImplementedYet, Unauthenticated, render_dpdpkit_error

B = TypeVar("B", bound=BaseModel)

# --------------------------------------------------------------------------- request bodies


class Decision(BaseModel):
    purpose: str = Field(min_length=1)
    granted: bool


class ConsentDecisionIn(BaseModel):
    notice_version: int | None = None
    locale: str | None = None
    decisions: list[Decision] = Field(min_length=1)


class RequestIn(BaseModel):
    kind: RequestKind
    details: dict[str, Any] = Field(default_factory=dict)


class AdminUpdateIn(BaseModel):
    action: Literal["assign", "start", "verify_identity", "respond", "reject"]
    assignee: str | None = None
    verified: bool | None = None
    method: str | None = None
    message: str | None = None


class ActivityIn(BaseModel):
    principal: str = Field(min_length=1)
    at: dt.datetime | None = None


# --------------------------------------------------------------------------- response shapes


def notice_out(notice: Notice, locales: list[str]) -> dict[str, Any]:
    content = notice.content.model_dump(mode="json")
    return {
        "version": notice.version,
        "locale": notice.locale,
        "content_hash": notice.content_hash,
        "published_at": notice.published_at.isoformat(),
        "available_locales": locales,
        **content,
    }


def state_out(state: ConsentState) -> dict[str, Any]:
    return state.model_dump(mode="json", exclude={"tenant_id", "principal"})


def receipt_out(receipt: ConsentReceipt) -> dict[str, Any]:
    data = receipt.model_dump(mode="json", exclude={"tenant_id"})
    data["consents"] = [state_out(c) for c in receipt.consents]
    return data


def request_out(req: RightsRequest, now: dt.datetime, *, admin: bool = False) -> dict[str, Any]:
    hidden = (
        {"tenant_id", "updated_at"}
        if admin
        else {"tenant_id", "updated_at", "principal", "assignee", "identity_verified"}
    )
    data = req.model_dump(mode="json", exclude=hidden)
    data["overdue"] = req.closed_at is None and now > req.due_at
    return data


# --------------------------------------------------------------------------- call context and registry


@dataclass
class Call:
    """What a handler gets: the kit, the request and who is calling (``who`` for users, ``actor`` for admins)."""

    request: HttpRequest
    kit: Kit
    who: str = ""
    actor: str = ""

    def body(self, model: type[B]) -> B:
        try:
            return model.model_validate(json.loads(self.request.body or b"{}"))
        except json.JSONDecodeError as exc:
            raise ValidationFailed("request body is not valid JSON") from exc
        except PydanticValidationError as exc:
            errors = [
                {"loc": [str(p) for p in e["loc"]], "msg": str(e["msg"]), "type": str(e["type"])} for e in exc.errors()
            ]
            raise ValidationFailed("request body or parameters are invalid", errors=errors) from exc

    def metadata(self) -> dict[str, Any]:
        """Evidence stored with consent events. No IP address or personal data by default."""
        return {"channel": "web", "user_agent_present": "HTTP_USER_AGENT" in self.request.META}


Handler = Callable[..., dict[str, Any] | HttpResponse]
View = Callable[..., HttpResponse]

#: path -> {lowercase method: view}. Paths are Django route strings relative to the include point.
ROUTES: dict[str, dict[str, View]] = {}


def _role_actor(request: HttpRequest, needed: Role) -> str:
    role = conf.resolve_role(request)
    principal = conf.resolve_principal(request)
    if role is None:
        if principal is None:
            raise Unauthenticated("sign in to use this endpoint")
        raise Forbidden("an admin role is required")
    if not role.allows(needed):
        raise Forbidden(f"the {needed.value} role is required", role=role.value)
    return f"{role.value}:{principal}" if principal else role.value


def endpoint(
    method: str, path: str, *, role: Role | None = None, public: bool = False, status: int = 200
) -> Callable[[Handler], View]:
    """Register ``fn(call, **url_kwargs)``. It returns a JSON-able dict, or a ready ``HttpResponse``.

    With ``role`` the caller needs that admin role; unless ``public``, they must be a signed-in principal."""

    def decorate(fn: Handler) -> View:
        def view(request: HttpRequest, **kwargs: Any) -> HttpResponse:
            try:
                call = Call(request, conf.get_kit())
                if role is not None:
                    call.actor = _role_actor(request, role)
                elif not public:
                    who = conf.resolve_principal(request)
                    if who is None:
                        raise Unauthenticated("sign in to use this endpoint")
                    call.who = who
                result = fn(call, **kwargs)
            except DpdpkitError as exc:
                return render_dpdpkit_error(exc)
            if isinstance(result, HttpResponse):
                return result
            return JsonResponse(result, status=status)

        view.__name__ = fn.__name__
        ROUTES.setdefault(path, {})[method] = view
        return view

    return decorate


def method_not_allowed(allowed: list[str]) -> HttpResponse:
    exc = MethodNotAllowed("method not allowed", allowed=sorted(m.upper() for m in allowed))
    response = render_dpdpkit_error(exc)
    response["Allow"] = ", ".join(exc.details["allowed"])
    return response


# --------------------------------------------------------------------------- notices


@endpoint("get", "notices/current", public=True)
def current_notice(c: Call) -> dict[str, Any]:
    notice = c.kit.notices.current(c.request.GET.get("locale") or None)
    return notice_out(notice, c.kit.notices.locales(notice.version))


# --------------------------------------------------------------------------- consents


@endpoint("post", "consents", status=201)
def record_consents(c: Call) -> dict[str, Any]:
    body = c.body(ConsentDecisionIn)
    decisions = {d.purpose: d.granted for d in body.decisions}
    if len(decisions) != len(body.decisions):
        raise ValidationFailed("each purpose may appear only once")
    states = c.kit.consent.record(
        c.who,
        decisions,
        notice_version=body.notice_version,
        locale=body.locale,
        source="api",
        metadata=c.metadata(),
    )
    return {"consents": [state_out(s) for s in states]}


@endpoint("post", "consents/<str:purpose>/withdraw")
def withdraw(c: Call, purpose: str) -> dict[str, Any]:
    return state_out(c.kit.consent.withdraw(c.who, purpose, source="api", metadata=c.metadata()))


@endpoint("get", "consents/me")
def my_consents(c: Call) -> dict[str, Any]:
    return {"consents": [state_out(s) for s in c.kit.consent.state(c.who)]}


@endpoint("get", "consents/me/receipt")
def my_receipt(c: Call) -> dict[str, Any]:
    return receipt_out(c.kit.consent.receipt(c.who))


# --------------------------------------------------------------------------- rights


@endpoint("post", "requests", status=201)
def open_request(c: Call) -> dict[str, Any]:
    body = c.body(RequestIn)
    return request_out(c.kit.rights.open(c.who, body.kind, body.details), c.kit.now())


@endpoint("get", "requests")
def my_requests(c: Call) -> dict[str, Any]:
    now = c.kit.now()
    return {"items": [request_out(r, now) for r in c.kit.rights.list_requests(principal=c.who)]}


@endpoint("get", "requests/<str:request_id>")
def get_request(c: Call, request_id: str) -> dict[str, Any]:
    return request_out(c.kit.rights.get(request_id, principal=c.who), c.kit.now())


@endpoint("get", "me/export")
def my_export(c: Call) -> HttpResponse:
    fmt = c.request.GET.get("format", "json")
    if fmt == "html":
        return HttpResponse(c.kit.export.principal_html(c.who), content_type="text/html; charset=utf-8")
    if fmt != "json":
        raise ValidationFailed("format must be json or html")
    return JsonResponse(c.kit.export.principal(c.who))


# --------------------------------------------------------------------------- admin


@endpoint("get", "admin/requests", role=Role.VIEWER)
def admin_requests(c: Call) -> dict[str, Any]:
    raw = c.request.GET.get("status")
    try:
        status = RequestStatus(raw) if raw else None
    except ValueError as exc:
        raise ValidationFailed("unknown status", status=raw) from exc
    only_open = c.request.GET.get("open", "").lower() in {"1", "true", "yes"}
    now = c.kit.now()
    reqs = c.kit.rights.list_requests(statuses=[status] if status else None, open_only=only_open)
    return {"items": [request_out(r, now, admin=True) for r in reqs]}


@endpoint("get", "admin/requests/<str:request_id>", role=Role.VIEWER)
def admin_request(c: Call, request_id: str) -> dict[str, Any]:
    return request_out(c.kit.rights.get(request_id), c.kit.now(), admin=True)


@endpoint("patch", "admin/requests/<str:request_id>", role=Role.HANDLER)
def admin_update(c: Call, request_id: str) -> dict[str, Any]:
    body = c.body(AdminUpdateIn)
    rights, actor = c.kit.rights, c.actor
    if body.action == "assign":
        if not body.assignee:
            raise ValidationFailed("assignee is required")
        req = rights.assign(request_id, body.assignee, actor=actor)
    elif body.action == "start":
        req = rights.start(request_id, actor=actor)
    elif body.action == "verify_identity":
        if body.verified is None:
            raise ValidationFailed("verified is required")
        req = rights.verify_identity(request_id, body.verified, actor=actor, method=body.method)
    elif body.action == "respond":
        req = rights.respond(request_id, body.message or "", actor=actor)
    else:
        req = rights.reject(request_id, body.message or "", actor=actor)
    return request_out(req, c.kit.now(), admin=True)


@endpoint("get", "admin/retention/preview", role=Role.VIEWER)
def retention_preview(c: Call) -> dict[str, Any]:
    try:
        hours = int(c.request.GET.get("hours", 168))
    except ValueError:
        hours = 0
    if hours < 1:
        raise ValidationFailed("hours must be a positive integer")
    items = c.kit.retention.preview(horizon=dt.timedelta(hours=hours))
    return {
        "items": [i.model_dump(mode="json") for i in items],
        "needs_attention": [
            {"schedule_id": s.id, "principal": s.principal, "purpose": s.purpose, "reason": s.attention_reason}
            for s in c.kit.retention.needs_attention()
        ],
    }


@endpoint("get", "admin/incidents", role=Role.VIEWER)
def list_incidents(c: Call) -> dict[str, Any]:
    raise NotImplementedYet("the incident register ships in v0.5 (task CORE-24)")


@endpoint("post", "admin/incidents", role=Role.HANDLER)
def create_incident(c: Call) -> dict[str, Any]:
    raise NotImplementedYet("the incident register ships in v0.5 (task CORE-24)")


@endpoint("get", "admin/incidents/<str:incident_id>/report", role=Role.HANDLER)
def incident_report(c: Call, incident_id: str) -> dict[str, Any]:
    raise NotImplementedYet("incident report drafts ship in v0.5 (task CORE-24)")


@endpoint("get", "admin/audit/export", role=Role.ADMIN)
def audit_export(c: Call) -> HttpResponse:
    stamp = c.kit.now().strftime("%Y%m%dT%H%M%SZ")
    response = HttpResponse(c.kit.export.evidence_pack(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="dpdpkit-evidence-{stamp}.zip"'
    return response


@endpoint("post", "admin/ledger/verify", role=Role.VIEWER)
def verify_ledger(c: Call) -> dict[str, Any]:
    return c.kit.ledger.verify_report().model_dump(mode="json", exclude={"tenant_id"})


# --------------------------------------------------------------------------- events


@endpoint("post", "events/activity", role=Role.HANDLER, status=202)
def activity(c: Call) -> dict[str, Any]:
    body = c.body(ActivityIn)
    c.kit.retention.record_activity(body.principal, as_utc(body.at) if body.at else None)
    return {"accepted": True}
