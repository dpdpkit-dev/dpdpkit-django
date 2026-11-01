from __future__ import annotations

from typing import Any

from django import forms
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.core import signing
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from dpdpkit.django.consent import record_preferences, requires_consent
from dpdpkit.errors import DpdpkitError

from . import guardians
from .models import Learner, Progress


class SignupForm(UserCreationForm):  # type: ignore[type-arg]
    full_name = forms.CharField(max_length=120)
    date_of_birth = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    school_grade = forms.CharField(max_length=20, required=False)
    guardian_name = forms.CharField(max_length=120, required=False, label="Parent or guardian's name")
    guardian_email = forms.EmailField(required=False, label="Parent or guardian's email")

    def clean(self) -> dict[str, Any]:
        data: dict[str, Any] = super().clean() or {}
        born = data.get("date_of_birth")
        if born is not None:
            probe = Learner(date_of_birth=born)
            if born > timezone.localdate():
                self.add_error("date_of_birth", "Date of birth is in the future.")
            elif guardians.is_child(probe) and not (data.get("guardian_name") and data.get("guardian_email")):
                self.add_error(None, "Learners under 18 need a parent or guardian's name and email.")
        return data


def index(request: HttpRequest) -> HttpResponse:
    return render(request, "school/index.html")


def signup(request: HttpRequest) -> HttpResponse:
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save()
            learner = Learner.objects.create(
                user=user,
                full_name=form.cleaned_data["full_name"],
                date_of_birth=form.cleaned_data["date_of_birth"],
                school_grade=form.cleaned_data["school_grade"],
                guardian_name=form.cleaned_data["guardian_name"],
                guardian_email=form.cleaned_data["guardian_email"],
            )
        login(request, user)
        link = guardians.send_link(request, learner) if guardians.is_child(learner) else None
        return render(request, "school/welcome.html", {"learner": learner, "child": link is not None, "link": link})
    return render(request, "school/form.html", {"title": "Create a learner account", "form": form})


def _awaiting_guardian(request: HttpRequest, error: DpdpkitError) -> HttpResponse:
    learner = Learner.objects.filter(user=request.user).first()
    child = learner is not None and guardians.is_child(learner)
    return render(request, "school/consent_needed.html", {"child": child}, status=403)


@login_required
@requires_consent("learning", on_denied=_awaiting_guardian)
def course(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        Progress.objects.create(user=request.user, course="Maths 101", score=int(request.POST.get("score", 0) or 0))
        return redirect("course")
    return render(request, "school/course.html", {"progress": Progress.objects.filter(user=request.user)})


@login_required
def preferences(request: HttpRequest) -> HttpResponse:
    """Adults choose for themselves. A child's choices belong to their guardian."""
    learner = Learner.objects.filter(user=request.user).first()
    if learner is not None and guardians.is_child(learner):
        return render(request, "school/consent_needed.html", {"child": True}, status=403)
    if request.method == "POST":
        record_preferences(request)
        return redirect("preferences")
    return render(request, "school/preferences.html")


def guardian_consent(request: HttpRequest, token: str) -> HttpResponse:
    """The page the guardian reaches from the emailed link. No sign-in: the signed link is the proof."""
    try:
        learner = guardians.learner_from_token(token)
    except signing.BadSignature:
        return render(request, "school/guardian_invalid.html", status=400)
    if request.method == "POST":
        guardians.record_guardian_choices(request, learner)
        return redirect("guardian-consent", token=token)
    return render(
        request,
        "school/guardian.html",
        {"learner": learner, "purposes": guardians.offered_purposes(learner), "token": token},
    )
