import twmarket


def test_import():
    assert twmarket.__version__ == "0.1.1"


def test_public_api_exists():
    for name in ("revenue", "prices", "calendar", "sync"):
        assert callable(getattr(twmarket, name))
