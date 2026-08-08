"""Smoke tests for demo_json_pkg."""

def test_import():
    import demo_json_pkg
    assert demo_json_pkg.__version__ == "0.2.0"
