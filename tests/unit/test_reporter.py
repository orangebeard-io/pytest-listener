import pytest
from orangebeard.entity.Attribute import Attribute
from orangebeard.entity.LogFormat import LogFormat
from orangebeard.entity.LogLevel import LogLevel
from orangebeard.entity.OrangebeardParameters import OrangebeardParameters
from orangebeard.entity.TestStatus import TestStatus as Status

from orangebeard_pytest.config import Settings
from orangebeard_pytest.reporter import OrangebeardReporter
from tests.fakes import FakeOrangebeardClient


@pytest.fixture
def client():
    return FakeOrangebeardClient()


@pytest.fixture
def reporter(client):
    params = OrangebeardParameters(token='t', endpoint='e', project='p', testset='my set', description='desc',
                                   attributes=[Attribute('k', 'v')])
    return OrangebeardReporter(client, Settings(params=params))


def test_start_run_uses_testset_description_and_attributes(reporter, client):
    reporter.start_run()
    run, _ = client.of('start_test_run')[0]
    assert run.testSetName == 'my set'
    assert run.description == 'desc'
    assert [(a.key, a.value) for a in run.attributes] == [('k', 'v')]


def test_suites_are_created_lazily_as_one_chain(reporter, client):
    reporter.start_run()
    reporter.start_test('pkg/test_m.py::TestA::test_one')
    suite, uuids = client.of('start_suite')[0]
    assert suite.suiteNames == ['pkg', 'test_m.py', 'TestA']
    assert suite.parentSuiteUUID is None
    test, _ = client.of('start_test')[0]
    assert test.suiteUUID == uuids[-1] and test.testName == 'test_one'


def test_existing_suites_are_reused_and_only_new_levels_started(reporter, client):
    reporter.start_run()
    reporter.start_test('pkg/test_m.py::TestA::test_one')
    reporter.finish_test(Status.PASSED)
    reporter.start_test('pkg/test_m.py::TestA::test_two')
    reporter.finish_test(Status.PASSED)
    reporter.start_test('pkg/test_m.py::TestB::test_three')
    reporter.finish_test(Status.PASSED)
    reporter.start_test('pkg/test_n.py::test_four')

    suites = client.of('start_suite')
    assert [s.suiteNames for s, _ in suites] == [['pkg', 'test_m.py', 'TestA'], ['TestB'], ['test_n.py']]
    module_uuid = suites[0][1][1]
    assert suites[1][0].parentSuiteUUID == module_uuid  # TestB hangs under the existing module suite
    assert suites[2][0].parentSuiteUUID == suites[0][1][0]  # test_n.py under the existing 'pkg' suite


def test_test_gets_description_and_attributes(reporter, client):
    reporter.start_run()
    reporter.start_test('t.py::test_x', description='docs', attributes=[Attribute(None, 'smoke')])
    test, _ = client.of('start_test')[0]
    assert test.description == 'docs'
    assert [(a.key, a.value) for a in test.attributes] == [(None, 'smoke')]


def test_steps_nest_and_finish_with_status(reporter, client):
    reporter.start_run()
    reporter.start_test('t.py::test_x')
    outer = reporter.start_step('outer')
    inner = reporter.start_step('inner')
    reporter.finish_step(Status.PASSED)
    reporter.finish_step(Status.FAILED)

    outer_req, inner_req = [p for p, _ in client.of('start_step')]
    assert outer_req.parentStepUUID is None
    assert inner_req.parentStepUUID == outer
    finished = [(u, f.status) for u, f in (p for p, _ in client.of('finish_step'))]
    assert finished == [(inner, Status.PASSED), (outer, Status.FAILED)]


def test_logs_attach_to_current_step_or_test(reporter, client):
    reporter.start_run()
    reporter.start_test('t.py::test_x')
    reporter.log('at test level')
    step = reporter.start_step('s')
    reporter.log('in step', LogLevel.WARN)
    reporter.finish_step(Status.PASSED)
    reporter.log('back at test level')

    logs = client.logs()
    assert [l.message for l in logs] == ['at test level', 'in step', 'back at test level']
    assert logs[0].stepUUID is None and logs[1].stepUUID == step and logs[2].stepUUID is None
    assert logs[1].logLevel == LogLevel.WARN
    assert logs[0].logFormat == LogFormat.PLAIN_TEXT


def test_attachment_creates_a_log_first_and_links_it(reporter, client):
    reporter.start_run()
    reporter.start_test('t.py::test_x')
    step = reporter.start_step('s')
    reporter.attach('shot.png', b'png-bytes')

    log, log_uuid = client.of('log')[0]
    assert 'shot.png' in log.message and log.stepUUID == step
    attachment, _ = client.of('send_attachment')[0]
    assert attachment.AttachmentMetaData.logUUID == log_uuid
    assert attachment.AttachmentMetaData.stepUUID == step
    assert attachment.AttachmentFile.name == 'shot.png'
    assert attachment.AttachmentFile.content == b'png-bytes'
    assert client.names().index('log') < client.names().index('send_attachment')


def test_oversized_attachments_are_skipped_with_a_warning(client):
    params = OrangebeardParameters(token='t', endpoint='e', project='p', testset='s')
    reporter = OrangebeardReporter(client, Settings(params=params, max_attachment_bytes=4))
    reporter.start_run()
    reporter.start_test('t.py::test_x')
    reporter.attach('big.bin', b'12345')
    assert client.of('send_attachment') == []
    assert any(l.logLevel == LogLevel.WARN and 'big.bin' in l.message for l in client.logs())


def test_finish_test_closes_open_steps_and_finish_run_flushes(reporter, client):
    reporter.start_run()
    reporter.start_test('t.py::test_x')
    reporter.start_step('left open')
    reporter.finish_test(Status.FAILED)
    reporter.finish_run()

    assert len(client.of('finish_step')) == 1
    assert client.finish_status_of_test('test_x') == Status.FAILED
    assert client.names()[-1] in ('finish_test_run', 'close')
    assert 'finish_test_run' in client.names()


def test_reporter_never_raises_when_the_client_fails(reporter, client):
    def boom(*_a, **_k):
        raise RuntimeError('network down')

    client.start_test_run = boom
    reporter.start_run()  # must not raise
    reporter.start_test('t.py::test_x')  # nor must dependants
    reporter.log('x')
    reporter.finish_test(Status.PASSED)
    reporter.finish_run()
    assert reporter.problems and 'network down' in reporter.problems[0]


def test_calls_outside_a_test_are_ignored(reporter, client):
    reporter.start_run()
    reporter.log('nobody home')
    assert reporter.start_step('x') is None
    reporter.attach('a.txt', b'x')
    assert client.logs() == [] and client.of('start_step') == []


def test_parametrize_id_stays_out_of_the_test_name(reporter, client):
    huge = 'x' * 3000
    reporter.start_run()
    reporter.start_test(f't.py::test_boundary[{huge}]', description='Checks bounds.')
    test, _ = client.of('start_test')[0]
    assert test.testName == 'test_boundary'
    # description carries a clipped version, the log the full value
    assert test.description.startswith('Checks bounds.\n\nParameters: x')
    assert len(test.description) == len('Checks bounds.\n\nParameters: ') + 2000 and test.description.endswith('…')
    assert any(l.message == f'Parameters: {huge}' for l in client.logs())


def test_display_name_replaces_the_function_name(reporter, client):
    reporter.start_run()
    reporter.start_test('t.py::test_x[1]', display_name='test_x[admin]')
    assert client.of('start_test')[0][0].testName == 'test_x[admin]'


def test_given_parameter_text_is_described_and_logged_instead_of_the_pytest_id(reporter, client):
    reporter.start_run()
    reporter.start_test('t.py::test_x[admin]', parameters="user='alice', retries=3")
    assert client.of('start_test')[0][0].description == "Parameters: user='alice', retries=3"
    assert client.logs()[0].message == "Parameters: user='alice', retries=3"

def test_descriptions_are_clipped_to_the_orangebeard_limit(reporter, client):
    reporter.start_run()
    reporter.start_test('t.py::test_a', description='d' * 10000)
    reporter.start_step('s', description='e' * 10000)
    assert len(client.of('start_test')[0][0].description) == 4096
    assert len(client.of('start_step')[0][0].description) == 4096


def test_parameters_survive_a_huge_docstring(reporter, client):
    reporter.start_run()
    reporter.start_test('t.py::test_a[p1]', description='d' * 10000)
    reporter.start_test('t.py::test_a[p2]', description='d' * 10000)
    first = client.of('start_test')[0][0].description
    assert len(first) <= 4096 and first.endswith('\n\nParameters: p1')


def test_run_description_is_clipped(client):
    params = OrangebeardParameters(token='t', endpoint='e', project='p', testset='s', description='r' * 9000)
    reporter = OrangebeardReporter(client, Settings(params=params))
    reporter.start_run()
    assert len(client.of('start_test_run')[0][0].description) == 4096


def test_markdown_messages_are_sent_as_markdown_and_others_as_plain_text(reporter, client):
    reporter.start_run()
    reporter.start_test('t.py::test_x')
    reporter.log('some **bold** text')
    reporter.log('just text')
    assert [l.logFormat for l in client.logs()] == [LogFormat.MARKDOWN, LogFormat.PLAIN_TEXT]


def test_an_explicit_format_wins_over_detection(reporter, client):
    reporter.start_run()
    reporter.start_test('t.py::test_x')
    reporter.log('some **bold** text', fmt=LogFormat.PLAIN_TEXT)
    assert client.logs()[0].logFormat == LogFormat.PLAIN_TEXT


def test_parameter_values_are_data_and_stay_plain_text(reporter, client):
    reporter.start_run()
    reporter.start_test('t.py::test_x[a]', parameters="text='**bold**'")
    assert client.logs()[0].logFormat == LogFormat.PLAIN_TEXT


def test_html_is_escaped_only_in_detected_markdown(reporter, client):
    reporter.start_run()
    reporter.start_test('t.py::test_x')
    reporter.log('**found** <Page url=x>')
    reporter.log('found <Page url=x>')
    reporter.log('**found** <br>', fmt=LogFormat.MARKDOWN)
    assert [l.message for l in client.logs()] == [
        r'**found** \<Page url=x>', 'found <Page url=x>', '**found** <br>']


def test_an_existing_run_is_used_instead_of_starting_one(client):
    run = '44444444-4444-4444-4444-444444444444'
    params = OrangebeardParameters(token='t', endpoint='e', project='p', testset='s', testrun_uuid=run)
    reporter = OrangebeardReporter(client, Settings(params=params))
    reporter.start_run()
    reporter.start_test('t.py::test_x')
    reporter.finish_test(Status.PASSED)
    reporter.finish_run()
    assert not client.of('start_test_run')
    assert client.of('start_test')[0][0].testRunUUID == run
    # the client knows the run is managed elsewhere: this only sends what is still queued
    assert client.of('finish_test_run')[0][0][0] == run
