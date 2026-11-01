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
plain JSON views otherwise), configured through `settings.DPDPKIT`.

Planned:

- `@requires_consent` decorator and class mixin
- Django admin: rights-request queue with SLA, read-only ledger viewer, retention monitor
- Celery tasks and management commands (`dpdp_run_retention`, `dpdp_verify_ledger`, `dpdp_export`)

Until then, use [`dpdpkit-fastapi`](https://github.com/dpdpkit-dev/dpdpkit-fastapi) or the core library
[`dpdpkit-core`](https://github.com/dpdpkit-dev/dpdpkit-core). Documentation:
https://dpdpkit-dev.github.io/dpdpkit-docs/dev/

## License

Apache-2.0. See [LICENSE](LICENSE). Contributions need a DCO sign-off; see [CONTRIBUTING.md](CONTRIBUTING.md).
