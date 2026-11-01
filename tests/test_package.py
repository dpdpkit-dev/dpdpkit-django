import dpdpkit.consent  # from dpdpkit-core, which owns the dpdpkit package
from dpdpkit import django


def test_version() -> None:
    assert django.__version__ == "0.0.1a0"


def test_installs_alongside_dpdpkit_core() -> None:
    assert dpdpkit.consent.__name__ == "dpdpkit.consent"
