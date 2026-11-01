# Changelog

All code packages in the dpdpkit release train share one version number. This package joins the train with its
first working release.

## Unreleased

### Added
- Django app `dpdpkit.django` (app label `dpdpkit`) with models and an initial migration for the consent ledger,
  audit trail, notices, rights requests, nominees, erasure schedules, legal holds, activity and deliveries. Table
  names match dpdpkit-fastapi's.
- `DjangoRepository`, an implementation of dpdpkit-core's `Repository` on the Django ORM. It joins the app's
  transactions, raises `SequenceConflict` on a duplicate ledger sequence, and supports `USE_TZ = False` and
  multiple databases (`DjangoRepository(using="alias")`).

## 0.0.1a0 - 2026-11-01

### Added
- Placeholder pre-release that reserves the package name on PyPI. It contains no functionality yet.
