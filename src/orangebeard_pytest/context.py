"""Process wide pointer to the active reporter, so test code can use step()/log()/attach() without wiring."""
_active = None


def activate(reporter):
    """Make `reporter` the active one; returns a token for deactivate()."""
    global _active
    previous, _active = _active, reporter
    return previous


def deactivate(token) -> None:
    global _active
    _active = token


def current():
    return _active
