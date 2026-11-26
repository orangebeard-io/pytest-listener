"""pytest hooks. Thin by design: everything of substance lives in reporter/mapping/artifacts."""
import inspect
import logging
import threading
import warnings
from typing import Optional

import pytest
from orangebeard.entity.LogFormat import LogFormat
from orangebeard.entity.LogLevel import LogLevel
from orangebeard.entity.TestStatus import TestStatus

from orangebeard_pytest import artifacts, config as ob_config, context, ids, mapping
from orangebeard_pytest.reporter import OrangebeardReporter
from orangebeard_pytest.steps import OrangebeardApi

PHASES = ('setup', 'call', 'teardown')
# loggers whose records come from the reporting machinery itself: never report them (feedback loop)
IGNORED_LOGGERS = ('orangebeard', 'aiohttp', 'asyncio')


def create_client(params, settings):
    """Factory for the Orangebeard client (replaced in the plugin's own tests)."""
    from orangebeard.OrangebeardClient import OrangebeardClient
    return OrangebeardClient(orangebeard_config=params)


def pytest_addoption(parser):
    ob_config.add_options(parser)


def pytest_configure(config):
    config.addinivalue_line('markers', 'orangebeard: reserved for Orangebeard specific markers')
    if hasattr(config, 'workerinput'):  # pytest-xdist worker: not supported (yet)
        return
    settings = ob_config.resolve(config)
    if settings is None:
        return
    if getattr(config.option, 'numprocesses', None):
        warnings.warn('orangebeard-pytest does not support pytest-xdist (-n) yet; reporting is disabled.',
                      stacklevel=1)
        return
    config.pluginmanager.register(OrangebeardPlugin(config, settings), 'orangebeard-reporter')


@pytest.fixture
def orangebeard():
    """Gives tests step(), log() and attach() (same as `import orangebeard_pytest`)."""
    return OrangebeardApi()


class _PhaseLogHandler(logging.Handler):
    def __init__(self, reporter: OrangebeardReporter, level: int):
        super().__init__(level)
        self.reporter = reporter
        self.thread = threading.get_ident()
        self._busy = False

    def emit(self, record: logging.LogRecord) -> None:
        if self._busy or threading.get_ident() != self.thread or record.name.startswith(IGNORED_LOGGERS):
            return
        self._busy = True
        try:
            message = record.getMessage()
            if record.exc_info:
                message += '\n' + logging.Formatter().formatException(record.exc_info)
            self.reporter.log(message, mapping.log_level(record.levelno))
        except Exception:
            pass
        finally:
            self._busy = False


def _is_user_fixture(fixturedef) -> bool:
    func = getattr(fixturedef, 'func', None)
    if (getattr(func, '__module__', '') or '').startswith('_pytest'):
        return False
    filename = getattr(getattr(func, '__code__', None), 'co_filename', '') or ''
    return not any(part in filename for part in ('site-packages', 'dist-packages'))


class OrangebeardPlugin:
    """Registered only when Orangebeard is configured."""

    def __init__(self, config, settings: ob_config.Settings):
        self.config = config
        self.settings = settings
        self.reporter: Optional[OrangebeardReporter] = None
        self.reports = {}
        self.watchers = [artifacts.DirectoryWatcher(path) for path in settings.watch_dirs]
        self._previous_context = None
        self.recorder = ids.ParametrizeRecorder(config)
        self.names = {}  # item nodeid -> test name, for parametrized items

    # ------------------------------------------------------------------ collection

    @pytest.hookimpl(wrapper=True, tryfirst=True)
    def pytest_generate_tests(self, metafunc):
        return (yield from self.recorder.recording(metafunc))

    @pytest.hookimpl(tryfirst=True)
    def pytest_collection_modifyitems(self, session, config, items):
        # before -k/-m deselect anything, so that the fallback numbering does not depend on the selection
        fallback = mapping.iteration_numbers([item.nodeid for item in items])
        for item in items:
            try:
                name = self._name(item, fallback.get(item.nodeid))
            except Exception:  # keep the plain function name
                continue
            if name:
                self.names[item.nodeid] = name

    def _name(self, item, fallback_number: Optional[int]) -> Optional[str]:
        function_name = mapping.split_nodeid(item.nodeid)[1]
        dimensions = self.recorder.dimensions(item)
        if dimensions is not None:
            return mapping.display_name(function_name, dimensions)
        if fallback_number is not None:
            unknown = mapping.Dimension(size=max(fallback_number, 2), index=fallback_number - 1)
            return mapping.display_name(function_name, [unknown])
        return None

    # ------------------------------------------------------------------ run

    def pytest_sessionstart(self, session):
        try:
            client = create_client(self.settings.params, self.settings)
        except Exception as error:
            warnings.warn(f'Orangebeard reporting disabled, could not create the client: {error}')
            return
        self.reporter = OrangebeardReporter(client, self.settings)
        self.reporter.start_run()
        self._previous_context = context.activate(self.reporter)

    def pytest_sessionfinish(self, session):
        if self.reporter is None:
            return
        self.reporter.finish_run()
        context.deactivate(self._previous_context)

    def pytest_terminal_summary(self, terminalreporter):
        if self.reporter is None:
            return
        terminalreporter.write_sep('-', 'Orangebeard')
        terminalreporter.write_line(f'Orangebeard: results reported to {self.settings.report_url}')
        for problem in self.reporter.problems:
            terminalreporter.write_line(f'Orangebeard: problem while reporting - {problem}', yellow=True)

    # ------------------------------------------------------------------ test

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_protocol(self, item, nextitem):
        reporter = self.reporter
        if reporter is None:
            return (yield)
        parameters = ids.parameter_text(item) if self.settings.log_parameters else None
        reporter.start_test(item.nodeid, self._description(item), self._attributes(item),
                            self.names.get(item.nodeid), parameters)
        self.reports = {}
        before = [watcher.snapshot() for watcher in self.watchers]
        try:
            return (yield)
        finally:
            for watcher, snapshot in zip(self.watchers, before):
                for path in watcher.new_files(snapshot):
                    self._attach_file(path)
            reporter.finish_test(mapping.test_status(self.reports) if self.reports else TestStatus.FAILED)

    @staticmethod
    def _description(item):
        try:
            return inspect.getdoc(getattr(item, 'obj', None)) or None
        except Exception:
            return None

    @staticmethod
    def _attributes(item):
        try:
            return mapping.marker_attributes(item)
        except Exception:
            return []

    def _attach_file(self, path):
        try:
            self.reporter.attach(path.name, path.read_bytes(), description=artifacts.describe(path))
        except OSError as error:
            self.reporter.problems.append(f'attach {path}: {error}')

    # ------------------------------------------------------------------ phases

    def _phase(self, name):
        reporter = self.reporter
        if reporter is None:
            return (yield)
        reporter.start_step(name)
        handler = _PhaseLogHandler(reporter, self.settings.log_level)
        root = logging.getLogger()
        previous_level = root.level
        if root.level > self.settings.log_level:
            root.setLevel(self.settings.log_level)
        root.addHandler(handler)
        try:
            return (yield)
        finally:
            root.removeHandler(handler)
            root.setLevel(previous_level)

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_setup(self, item):
        return (yield from self._phase('setup'))

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_call(self, item):
        return (yield from self._phase('call'))

    @pytest.hookimpl(wrapper=True)
    def pytest_runtest_teardown(self, item, nextitem):
        return (yield from self._phase('teardown'))

    def pytest_runtest_logreport(self, report):
        reporter = self.reporter
        if reporter is None or report.when not in PHASES:
            return
        self.reports[report.when] = report
        for title, content in report.sections:
            if title.startswith('Captured stdout'):
                reporter.log(content, LogLevel.INFO)
            elif title.startswith('Captured stderr'):
                reporter.log(content, LogLevel.WARN)
        if report.failed:
            reporter.log(f'```\n{report.longreprtext}\n```', LogLevel.ERROR, LogFormat.MARKDOWN)
        elif report.skipped:
            reason = getattr(report, 'wasxfail', None)
            if reason is not None:
                reporter.log(f'xfailed: {reason}', LogLevel.INFO)
            else:
                longrepr = report.longrepr
                reporter.log(str(longrepr[2] if isinstance(longrepr, tuple) else longrepr), LogLevel.INFO)
        reporter.close_open_steps(mapping.phase_status(report.outcome))

    # ------------------------------------------------------------------ fixtures

    def _wants_fixture(self, fixturedef) -> bool:
        mode = self.settings.report_fixtures
        return mode == 'all' or (mode == 'user' and _is_user_fixture(fixturedef))

    @pytest.hookimpl(wrapper=True)
    def pytest_fixture_setup(self, fixturedef, request):
        reporter = self.reporter
        if reporter is None or not reporter.in_test or not self._wants_fixture(fixturedef):
            return (yield)
        reporter.start_step(f'fixture: {fixturedef.argname}')
        try:
            result = yield
        except BaseException as error:
            skipped = isinstance(error, pytest.skip.Exception)
            reporter.finish_step(TestStatus.SKIPPED if skipped else TestStatus.FAILED)
            raise
        reporter.finish_step(TestStatus.PASSED)
        return result
