# Changelog

All code packages in the dpdpkit release train share one version number. This package joins the train with its
first working release.

## Unreleased

### Added
- Django admin (registered when `django.contrib.admin` is installed): a request queue with a per-request SLA
  countdown (overdue and ceiling-breach flags), read-only consent and audit ledger viewers, a retention monitor
  (upcoming erasures, schedules needing attention) and a legal-hold list. All of it is read-only.
- `PersonalDataRegistry` (and the project-wide `dpdpkit.django.registry.registry`): register models with a
  per-field strategy of `delete`, `anonymise` (default placeholder or your own `callable(row)`) or `retain_legal`
  (needs a `retain_reason`), or delete whole rows. `erase(principal, purposes)` runs atomically and returns a report
  per model; `attach(kit)` makes the kit's retention runs and erasure requests use it; `describe()` lists the
  registered fields.
- `@requires_consent(*purposes)` for function views (sync or async) and `RequiresConsentMixin` for class-based
  views. A caller who is not signed in gets 401 `unauthenticated`; one without consent gets 403 `consent_required`
  with the purpose in `details`. Pass `on_denied=` (or override `consent_denied`) to answer differently, for example
  with a redirect.
- Django app `dpdpkit.django` (app label `dpdpkit`) with models and an initial migration for the consent ledger,
  audit trail, notices, rights requests, nominees, erasure schedules, legal holds, activity and deliveries. Table
  names match dpdpkit-fastapi's.
- `DjangoRepository`, an implementation of dpdpkit-core's `Repository` on the Django ORM. It joins the app's
  transactions, raises `SequenceConflict` on a duplicate ledger sequence, and supports `USE_TZ = False` and
  multiple databases (`DjangoRepository(using="alias")`).
- The dpdpkit REST contract as URLs and views: `include("dpdpkit.django.urls")` serves the same endpoints and error
  bodies as dpdpkit-fastapi. It uses a Django REST framework `ViewSet` when `rest_framework` is installed and plain
  JSON views otherwise (override with `DPDPKIT["DRF"]`). Both share one set of handlers. DRF is the optional extra
  `dpdpkit-django[drf]`.
- Configuration through `settings.DPDPKIT`: `CONFIG` or `POLICY` to build the kit, plus `PRINCIPAL_RESOLVER`,
  `ADMIN_GUARD`, `CSRF_EXEMPT` and others. By default the principal is the signed-in user and staff users get the
  handler role (superusers get admin).

## 0.0.1a0 - 2026-11-01

### Added
- Placeholder pre-release that reserves the package name on PyPI. It contains no functionality yet.
