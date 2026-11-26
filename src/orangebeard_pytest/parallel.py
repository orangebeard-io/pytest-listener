"""pytest-xdist: the main process owns the test run, the workers report their tests into it."""
import warnings

import pytest

from orangebeard_pytest.reporter import OrangebeardReporter

RUN_KEY = 'orangebeard_testrun_uuid'  # in a worker's input: the run it reports into
PROBLEMS_KEY = 'orangebeard_problems'  # in a worker's output: what went wrong while it was reporting


def is_worker(config) -> bool:
    return hasattr(config, 'workerinput')


def is_distributing(config) -> bool:
    """Mirrors xdist's own check: this process hands the tests to workers instead of running them."""
    return (config.getoption('dist', 'no') != 'no' and bool(config.getoption('tx', None))
            and not config.getoption('collectonly', False))


class RunController:
    """Registered in the main process instead of the reporting plugin: it reports no tests itself.

    A run given with ORANGEBEARD_TESTRUN_UUID is only passed on; otherwise the run is started before the workers
    and finished after them.
    """

    def __init__(self, config, settings, create_client):
        self.settings = settings
        self.create_client = create_client
        self.run_uuid = settings.params.testrun_uuid
        self.reporter = None  # only when the run is started, and therefore finished, here
        self.problems = []
        if config.getini('orangebeard_watch_dirs') and len(config.getoption('tx')) > 1:
            self.problems.append('orangebeard_watch_dirs is ignored with several workers: '
                                 'a new file cannot be traced to one test')

    def pytest_sessionstart(self, session):  # runs before xdist (trylast) starts the workers
        if self.run_uuid:
            return
        try:
            client = self.create_client(self.settings.params, self.settings)
        except Exception as error:
            warnings.warn(f'Orangebeard reporting disabled, could not create the client: {error}')
            return
        self.reporter = OrangebeardReporter(client, self.settings)
        self.reporter.problems = self.problems
        self.reporter.start_run(shared=True)
        self.run_uuid = self.reporter.shared_run_uuid
        if self.run_uuid is None:
            self.problems.append('could not start the test run; nothing is reported')

    @pytest.hookimpl(optionalhook=True)
    def pytest_configure_node(self, node):
        if self.run_uuid:
            node.workerinput[RUN_KEY] = self.run_uuid

    @pytest.hookimpl(optionalhook=True)
    def pytest_testnodedown(self, node, error):
        self.problems.extend(getattr(node, 'workeroutput', {}).get(PROBLEMS_KEY, []))

    @pytest.hookimpl(trylast=True)  # after xdist has waited for the workers, which send all they have before exiting
    def pytest_sessionfinish(self, session):
        if self.reporter is not None:
            self.reporter.finish_run()

    def pytest_terminal_summary(self, terminalreporter):
        if self.reporter is None and not self.run_uuid:
            return
        terminalreporter.write_sep('-', 'Orangebeard')
        if self.run_uuid:
            terminalreporter.write_line(f'Orangebeard: results reported to {self.settings.report_url}')
        for problem in self.problems:
            terminalreporter.write_line(f'Orangebeard: problem while reporting - {problem}', yellow=True)
