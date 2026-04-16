"""Verify bluepython package is importable."""


def test_import_bluepython():
    import bluepython  # noqa: F401


def test_bluepython_has_version():
    from importlib.metadata import version

    v = version("bluerock")
    assert v, "bluerock must have a version"
