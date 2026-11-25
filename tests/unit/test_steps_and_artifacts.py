import os
import time

import pytest
from orangebeard.entity.OrangebeardParameters import OrangebeardParameters
from orangebeard.entity.TestStatus import TestStatus as Status

import orangebeard_pytest as ob
from orangebeard_pytest import artifacts, context
from orangebeard_pytest.config import Settings
from orangebeard_pytest.reporter import OrangebeardReporter
from tests.fakes import FakeOrangebeardClient


@pytest.fixture
def client():
    return FakeOrangebeardClient()


@pytest.fixture
def active(client):
    reporter = OrangebeardReporter(client, Settings(params=OrangebeardParameters(token='t', endpoint='e',
                                                                                 project='p', testset='s')))
    reporter.start_run()
    reporter.start_test('t.py::test_x')
    token = context.activate(reporter)
    yield reporter
    context.deactivate(token)


def test_step_context_manager_nests_and_passes(active, client):
    with ob.step('outer'):
        with ob.step('inner', description='details'):
            pass
    assert client.step_names() == ['outer', 'inner']
    outer, inner = [r for _, r in client.of('start_step')]
    assert client.finish_status_of_step(inner) == Status.PASSED
    assert client.finish_status_of_step(outer) == Status.PASSED
    assert client.of('start_step')[1][0].description == 'details'


def test_step_marks_failed_logs_error_and_reraises(active, client):
    with pytest.raises(ValueError):
        with ob.step('boom'):
            raise ValueError('bad value')
    assert client.finish_status_of_step(client.step_uuid('boom')) == Status.FAILED
    assert any('bad value' in l.message and l.logLevel == 'ERROR' for l in client.logs())


def test_step_skip_exception_is_skipped_not_failed(active, client):
    with pytest.raises(pytest.skip.Exception):
        with ob.step('skipping'):
            pytest.skip('nope')
    assert client.finish_status_of_step(client.step_uuid('skipping')) == Status.SKIPPED


def test_step_works_as_decorator_with_default_name(active, client):
    @ob.step()
    def do_the_thing():
        return 42

    @ob.step('custom name')
    def other():
        return 1

    assert do_the_thing() == 42 and other() == 1
    assert client.step_names() == ['do_the_thing', 'custom name']


def test_step_is_a_noop_without_an_active_reporter():
    with ob.step('nothing happens'):
        ob.log('ignored')
        ob.attach(b'x', name='a.txt')


def test_public_log_and_attach_use_the_active_reporter(active, client):
    ob.log('hello', level='warn')
    ob.attach(b'content', name='note.txt')
    assert client.logs()[0].message == 'hello' and client.logs()[0].logLevel == 'WARN'
    assert client.of('send_attachment')[0][0].AttachmentFile.name == 'note.txt'


def test_attach_accepts_a_path(active, client, tmp_path):
    f = tmp_path / 'report.html'
    f.write_bytes(b'<html/>')
    ob.attach(f)
    attachment = client.of('send_attachment')[0][0]
    assert attachment.AttachmentFile.name == 'report.html'
    assert attachment.AttachmentFile.content == b'<html/>'
    assert attachment.AttachmentFile.contentType == 'text/html'


def test_attach_bytes_requires_a_name(active):
    with pytest.raises(ValueError):
        ob.attach(b'no name')


# ---- artifact discovery (Playwright output directory) ------------------------------------------

def test_watcher_reports_new_and_changed_files_only(tmp_path):
    out = tmp_path / 'test-results'
    (out / 'old').mkdir(parents=True)
    old = out / 'old' / 'keep.png'
    old.write_bytes(b'1')
    changed = out / 'old' / 'changed.zip'
    changed.write_bytes(b'1')

    watcher = artifacts.DirectoryWatcher(out)
    before = watcher.snapshot()

    time.sleep(0.02)
    changed.write_bytes(b'22')
    new_dir = out / 'tests-foo-chromium'
    new_dir.mkdir()
    (new_dir / 'trace.zip').write_bytes(b'zip')
    (new_dir / 'test-failed-1.png').write_bytes(b'png')

    found = sorted(p.name for p in watcher.new_files(before))
    assert found == ['changed.zip', 'test-failed-1.png', 'trace.zip']


def test_watcher_handles_missing_directory(tmp_path):
    watcher = artifacts.DirectoryWatcher(tmp_path / 'does-not-exist')
    assert watcher.snapshot() == {}
    assert watcher.new_files({}) == []


def test_artifact_labels_make_playwright_files_recognisable():
    assert 'show-trace' in artifacts.describe(artifacts.Path('x/trace.zip'))
    assert artifacts.describe(artifacts.Path('x/video.webm')).lower().startswith('video')
    assert artifacts.describe(artifacts.Path('x/test-failed-1.png')).lower().startswith('screenshot')
    assert artifacts.describe(artifacts.Path('x/other.bin')) == 'other.bin'
