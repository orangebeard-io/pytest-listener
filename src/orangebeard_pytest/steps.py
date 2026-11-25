"""Public API for test code: step(), log(), attach(). All of it is a no-op when Orangebeard is not active."""
from contextlib import ContextDecorator
from pathlib import Path
from typing import Optional, Union

import pytest
from orangebeard.entity.LogLevel import LogLevel
from orangebeard.entity.TestStatus import TestStatus

from orangebeard_pytest import context


class step(ContextDecorator):
    """Report a (nested) step. Usable as `with step("name"):` and as `@step("name")` / `@step()`."""

    def __init__(self, name: Optional[str] = None, description: Optional[str] = None):
        self.name = name
        self.description = description
        self._started = False

    def __call__(self, func):
        if self.name is None:
            self.name = func.__name__
        return super().__call__(func)

    def _recreate_cm(self):
        return step(self.name, self.description)  # a fresh instance per call (recursion / concurrency safe)

    def __enter__(self):
        reporter = context.current()
        if reporter is not None:
            self._started = reporter.start_step(self.name or 'step', self.description) is not None
        return self

    def __exit__(self, exc_type, exc, tb):
        reporter = context.current()
        if reporter is None or not self._started:
            return False
        if exc_type is None:
            status = TestStatus.PASSED
        elif issubclass(exc_type, (pytest.skip.Exception, pytest.xfail.Exception)):
            status = TestStatus.SKIPPED
        else:
            status = TestStatus.FAILED
            reporter.log(f'{exc_type.__name__}: {exc}', LogLevel.ERROR)
        reporter.finish_step(status)
        return False


def log(message: str, level: Union[str, LogLevel] = 'info') -> None:
    """Send a log message to the current step (or test)."""
    reporter = context.current()
    if reporter is not None:
        reporter.log(str(message), level)


def attach(source: Union[bytes, str, Path], name: Optional[str] = None, content_type: Optional[str] = None) -> None:
    """Attach a file (path) or raw bytes (give a name) to the current step (or test)."""
    if isinstance(source, (bytes, bytearray)):
        if not name:
            raise ValueError('attach() needs a name when given raw bytes')
        content = bytes(source)
    else:
        path = Path(source)
        name = name or path.name
        content = None
    reporter = context.current()
    if reporter is None:
        return
    if content is None:
        content = path.read_bytes()
    reporter.attach(name, content, content_type=content_type)


class OrangebeardApi:
    """What the `orangebeard` fixture hands to tests."""
    step = staticmethod(step)
    log = staticmethod(log)
    attach = staticmethod(attach)
