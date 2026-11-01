# dpdpkit-django

Django app for [dpdpkit](https://github.com/dpdpkit-dev). It will add consent, versioned notices, rights requests and retention to your Django project, with tables in your own database.

> **Disclaimer.** dpdpkit is software that helps you implement obligations under India's Digital Personal
> Data Protection Act, 2023 and the DPDP Rules, 2025. It does not provide legal advice and does not
> guarantee compliance. Decisions about notices, purposes, retention and incident reporting must be made
> by you or your counsel.

## Status

**Not usable yet.** Version 0.0.1a0 is an empty pre-release that reserves the name on PyPI. The first working
release is planned for milestone v0.4 (planned for April 2027); the work is tracked as DJ-01 to DJ-10 in the dpdpkit task sheet.

In the repository, unreleased: the `dpdpkit.django` app with models, migrations and `DjangoRepository`, an
implementation of the dpdpkit `Repository` on the Django ORM (Postgres, MySQL, SQLite), and the dpdpkit REST
contract as URLs and views (`include("dpdpkit.django.urls")`; a DRF viewset when `rest_framework` is installed,
plain JSON views otherwise), configured through `settings.DPDPKIT`, and consent checks for views:
`@requires_consent("marketing")` for function views and `RequiresConsentMixin` (`consent_purposes = ("marketing",)`)
for class-based views. With `django.contrib.admin` installed you also get a read-only compliance back-office: a
request queue with SLA countdowns, consent and audit ledger viewers, a retention monitor and a legal-hold list.
Scheduled work runs from cron with the management commands `dpdp_run_retention`, `dpdp_verify_ledger` (exits
non-zero when a ledger chain is broken) and `dpdp_export` (`--principal`, `--evidence-pack`, `--root-file`), or from
Celery beat with the tasks in `dpdpkit.django.tasks` (`pip install "dpdpkit-django[celery]"`). For app-specific hooks
there are the signals `consent_withdrawn`, `erasure_due` and `request_opened` (`dpdpkit.django.signals`), and for
server-rendered sites the template tags `{% dpdp_notice %}` and `{% dpdp_preferences %}` (`{% load dpdpkit %}`).

Until then, use [`dpdpkit-fastapi`](https://github.com/dpdpkit-dev/dpdpkit-fastapi) or the core library
[`dpdpkit-core`](https://github.com/dpdpkit-dev/dpdpkit-core). Documentation:
https://dpdpkit-dev.github.io/dpdpkit-docs/dev/

## License

Apache-2.0. See [LICENSE](LICENSE). Contributions need a DCO sign-off; see [CONTRIBUTING.md](CONTRIBUTING.md).
