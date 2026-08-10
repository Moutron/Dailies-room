# tests/test_smoke.py
def test_imports():
    """Catches syntax errors and broken dependencies early."""
    import agent  # noqa: F401
    import pipeline  # noqa: F401
