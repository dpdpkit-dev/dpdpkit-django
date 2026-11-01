"""Template tags for server-rendered sites::

    {% load dpdpkit %}
    {% dpdp_notice %}
    {% dpdp_notice locale="hi" %}
    {% dpdp_preferences action="/privacy/preferences/" %}

``dpdp_preferences`` renders the signed-in user's consent choices as a form (nothing pre-ticked) that posts
``purpose`` checkboxes, ``notice_version`` and ``locale`` to ``action``; handle the post with
:func:`dpdpkit.django.consent.record_preferences`. Override ``dpdpkit/notice.html`` and
``dpdpkit/preferences.html`` to restyle either tag.
"""

from __future__ import annotations

from typing import Any

from django import template
from django.template import Context
from dpdpkit.models import ConsentStatus

from .. import conf

register = template.Library()


@register.inclusion_tag("dpdpkit/notice.html")
def dpdp_notice(locale: str | None = None) -> dict[str, Any]:
    """The current privacy notice in ``locale`` (default: the notice's default locale)."""
    kit = conf.get_kit()
    notice = kit.notices.current(locale or None)
    return {"notice": notice.content, "version": notice.version, "locale": notice.locale}


@register.inclusion_tag("dpdpkit/preferences.html", takes_context=True)
def dpdp_preferences(context: Context, action: str = "", locale: str | None = None) -> dict[str, Any]:
    """A form of consent choices for the signed-in user; an empty result for anonymous visitors."""
    request = context.get("request")
    principal = conf.resolve_principal(request) if request is not None else None
    if principal is None:
        return {"signed_in": False}
    kit = conf.get_kit()
    notice = kit.notices.current(locale or None)
    consent_ids = {p.id for p in kit.registry.consent_purposes()}
    states = {s.purpose: s for s in kit.consent.state(principal)}
    purposes = [
        {
            "id": p.id,
            "title": p.title,
            "description": p.description,
            "required": p.required,
            "granted": p.id in states and states[p.id].status is ConsentStatus.GRANTED,
        }
        for p in notice.content.purposes
        if p.id in consent_ids
    ]
    return {
        "signed_in": True,
        "action": action,
        "purposes": purposes,
        "version": notice.version,
        "locale": notice.locale,
        "csrf_token": context.get("csrf_token", ""),
    }
