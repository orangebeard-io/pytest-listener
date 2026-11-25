"""Pure mapping functions between pytest concepts and Orangebeard concepts."""
import logging
from typing import Dict, List, Tuple

from orangebeard.entity.Attribute import Attribute
from orangebeard.entity.LogLevel import LogLevel
from orangebeard.entity.TestStatus import TestStatus

# markers that carry pytest behaviour rather than meaning for a human reader
BUILTIN_MARKERS = {'parametrize', 'skip', 'skipif', 'xfail', 'usefixtures', 'filterwarnings'}


def split_nodeid(nodeid: str) -> Tuple[List[str], str]:
    """'pkg/test_m.py::TestA::test_x[p]' -> (['pkg', 'test_m.py', 'TestA'], 'test_x[p]')

    Parametrize ids (everything from the first '[') may contain '/' or '::' and are never split.
    """
    bracket = nodeid.find('[')
    base, params = (nodeid, '') if bracket < 0 else (nodeid[:bracket], nodeid[bracket:])
    path, *rest = base.split('::')
    suites = [part for part in path.split('/') if part]
    if not rest:
        return suites[:-1], suites[-1] + params if suites else params
    return suites + rest[:-1], rest[-1] + params


def phase_status(outcome: str) -> TestStatus:
    return {'passed': TestStatus.PASSED, 'failed': TestStatus.FAILED, 'skipped': TestStatus.SKIPPED}.get(
        outcome, TestStatus.FAILED)


def test_status(reports: Dict[str, object]) -> TestStatus:
    """Overall status from the setup/call/teardown reports of one test.

    Any failure (setup error, test failure, teardown error, strict xpass) fails the test. Skips and xfails are
    reported as SKIPPED. A non strict xpass counts as passed.
    """
    if any(r.outcome == 'failed' for r in reports.values()):
        return TestStatus.FAILED
    for phase in ('setup', 'call'):
        report = reports.get(phase)
        if report is not None and report.outcome == 'skipped':
            return TestStatus.SKIPPED
    return TestStatus.PASSED


test_status.__test__ = False  # not a test, despite its name


def log_level(levelno: int) -> LogLevel:
    if levelno >= logging.ERROR:
        return LogLevel.ERROR
    if levelno >= logging.WARNING:
        return LogLevel.WARN
    if levelno >= logging.INFO:
        return LogLevel.INFO
    return LogLevel.DEBUG


def normalize_level(level) -> LogLevel:
    """Accept LogLevel members or loose strings such as 'warn', 'WARNING', 'critical'."""
    if isinstance(level, LogLevel):
        return level
    name = str(level).strip().upper()
    if name in ('WARN', 'WARNING'):
        return LogLevel.WARN
    if name in ('ERROR', 'CRITICAL', 'FATAL'):
        return LogLevel.ERROR
    if name == 'DEBUG':
        return LogLevel.DEBUG
    return LogLevel.INFO


def parse_level(value: str) -> int:
    """'INFO' / 'warning' / '15' -> logging level number."""
    value = str(value).strip()
    if value.isdigit():
        return int(value)
    number = logging.getLevelName(value.upper())
    if not isinstance(number, int):
        raise ValueError(f'Unknown log level: {value!r}')
    return number


def marker_attributes(item) -> List[Attribute]:
    """Custom markers become value-only attributes (tags)."""
    seen, attributes = set(), []
    for marker in item.iter_markers():
        if marker.name in BUILTIN_MARKERS or marker.name in seen:
            continue
        seen.add(marker.name)
        attributes.append(Attribute(None, marker.name))
    return attributes
