"""Smoke tests for minimal_pkg."""

def test_import():
    import minimal_pkg
    assert minimal_pkg.__version__ == "0.1.0"
