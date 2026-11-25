"""Pure mapping functions between pytest concepts and Orangebeard concepts."""
import logging
from typing import Dict, List, Tuple

from orangebeard.entity.Attribute import Attribute
from orangebeard.entity.LogLevel import LogLevel
from orangebeard.entity.TestStatus import TestStatus

# markers that carry pytest behaviour rather than meaning for a human reader
BUILTIN_MARKERS = {'parametrize', 'skip', 'skipif', 'xfail', 'usefixtures', 'filterwarnings'}


MAX_NAME_LENGTH = 1024  # Orangebeard rejects suite/test names longer than this


def clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 1] + '…'


def split_nodeid(nodeid: str) -> Tuple[List[str], str, str]:
    """'pkg/test_m.py::TestA::test_x[p]' -> (['pkg', 'test_m.py', 'TestA'], 'test_x', 'p')

    The parametrize id (between the first '[' and the final ']') is returned separately and never becomes part of
    the test name: it can hold arbitrary data (long strings, changing values), and a changing name breaks the
    history of a test. It may contain '/' or '::' and is never split.
    """
    bracket = nodeid.find('[')
    base, params = (nodeid, '') if bracket < 0 else (nodeid[:bracket], nodeid[bracket + 1:])
    if params.endswith(']'):
        params = params[:-1]
    path, *rest = base.split('::')
    suites = [part for part in path.split('/') if part]
    if not rest:
        return [clip(s, MAX_NAME_LENGTH) for s in suites[:-1]], clip(suites[-1] if suites else '', MAX_NAME_LENGTH), params
    return [clip(s, MAX_NAME_LENGTH) for s in suites + rest[:-1]], clip(rest[-1], MAX_NAME_LENGTH), params


def iteration_numbers(nodeids: List[str]) -> Dict[str, int]:
    """Number (from 1) the cases of a test function that is collected more than once (parametrized).

    Orangebeard treats identically named tests as retries of each other, so different data needs different names.
    Functions that occur once are not included. Pass the full collection (before -k/-m deselection) so that the
    numbers do not depend on what is selected.
    """
    groups: Dict[str, List[str]] = {}
    for nodeid in nodeids:
        bracket = nodeid.find('[')
        groups.setdefault(nodeid if bracket < 0 else nodeid[:bracket], []).append(nodeid)
    return {nodeid: number for members in groups.values() if len(members) > 1
            for number, nodeid in enumerate(members, start=1)}


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
