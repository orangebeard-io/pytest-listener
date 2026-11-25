import pytest
from orangebeard.entity.LogLevel import LogLevel
from orangebeard.entity.TestStatus import TestStatus as Status


def run(pytester, *args):
    return pytester.runpytest_inprocess('-p', 'no:cacheprovider', *args)


def test_plugin_is_inert_without_configuration(pytester, monkeypatch):
    def must_not_be_called(params, settings):
        raise AssertionError('client created although Orangebeard is not configured')

    monkeypatch.setattr('orangebeard_pytest.plugin.create_client', must_not_be_called)
    pytester.makepyfile('def test_a():\n    assert True\n')
    result = run(pytester)
    result.assert_outcomes(passed=1)


def test_no_report_flag_disables_reporting(pytester, fake_client):
    pytester.makepyfile('def test_a():\n    assert True\n')
    run(pytester, '--ob-no-report').assert_outcomes(passed=1)
    assert fake_client.calls == []


def test_run_lifecycle_and_structure(pytester, fake_client):
    pytester.makepyfile(**{
        'pkg/__init__': '',
        'pkg/test_mod': '''
            import pytest

            def test_pass():
                assert True

            def test_fail():
                assert 1 == 2

            @pytest.mark.skip(reason="not now")
            def test_skip():
                pass

            @pytest.mark.xfail(reason="known bug")
            def test_xfail():
                assert False

            @pytest.mark.parametrize("n", [1, 2])
            def test_param(n):
                assert n

            class TestGroup:
                def test_in_class(self):
                    assert True
        ''',
    })
    result = run(pytester, '--ob-testset', 'My Set')
    result.assert_outcomes(passed=4, failed=1, skipped=1, xfailed=1)

    names = fake_client.names()
    assert names[0] == 'start_test_run' and names[-1] in ('finish_test_run', 'close')
    assert fake_client.of('start_test_run')[0][0].testSetName == 'My Set'
    assert 'finish_test_run' in names

    suites = [s.suiteNames for s, _ in fake_client.of('start_suite')]
    assert suites[0] == ['pkg', 'test_mod.py']
    assert ['TestGroup'] in suites

    assert fake_client.finish_status_of_test('test_pass') == Status.PASSED
    assert fake_client.finish_status_of_test('test_fail') == Status.FAILED
    assert fake_client.finish_status_of_test('test_skip') == Status.SKIPPED
    assert fake_client.finish_status_of_test('test_xfail') == Status.SKIPPED
    assert fake_client.finish_status_of_test('test_param[1]') == Status.PASSED
    assert fake_client.finish_status_of_test('test_param[2]') == Status.PASSED
    assert fake_client.finish_status_of_test('test_in_class') == Status.PASSED


def test_phases_are_steps_under_the_test(pytester, fake_client):
    pytester.makepyfile('def test_a():\n    assert True\n')
    run(pytester)
    reqs = [p for p, _ in fake_client.of('start_step')]
    assert [r.stepName for r in reqs] == ['setup', 'call', 'teardown']
    test_uuid = fake_client.test_uuid('test_a')
    assert all(r.testUUID == test_uuid and r.parentStepUUID is None for r in reqs)
    for r_uuid in [u for _, u in fake_client.of('start_step')]:
        assert fake_client.finish_status_of_step(r_uuid) == Status.PASSED


def test_user_fixtures_become_steps_below_setup(pytester, fake_client):
    pytester.makepyfile('''
        import pytest

        @pytest.fixture
        def my_database():
            return "db"

        def test_a(my_database, tmp_path):
            assert my_database
    ''')
    run(pytester)
    assert 'fixture: my_database' in fake_client.step_names()
    assert 'fixture: tmp_path' not in fake_client.step_names()  # builtin noise is filtered by default
    fixture_req = next(p for p, _ in fake_client.of('start_step') if p.stepName == 'fixture: my_database')
    assert fixture_req.parentStepUUID == fake_client.step_uuid('setup')


def test_fixture_reporting_can_be_switched_off_or_widened(pytester, fake_client):
    pytester.makepyfile('''
        import pytest

        @pytest.fixture
        def mine():
            return 1

        def test_a(mine, tmp_path):
            pass
    ''')
    pytester.makeini('[pytest]\norangebeard_report_fixtures = none\n')
    run(pytester)
    assert not [n for n in fake_client.step_names() if n.startswith('fixture:')]

    fake_client.calls.clear()
    pytester.makeini('[pytest]\norangebeard_report_fixtures = all\n')
    run(pytester)
    assert 'fixture: mine' in fake_client.step_names() and 'fixture: tmp_path' in fake_client.step_names()


def test_user_steps_nest_under_the_call_step(pytester, fake_client):
    pytester.makepyfile('''
        import orangebeard_pytest as ob

        def test_a():
            with ob.step("Open page"):
                with ob.step("Click button"):
                    pass
    ''')
    run(pytester)
    reqs = {p.stepName: p for p, _ in fake_client.of('start_step')}
    assert reqs['Open page'].parentStepUUID == fake_client.step_uuid('call')
    assert reqs['Click button'].parentStepUUID == fake_client.step_uuid('Open page')


def test_logging_is_reported_at_mapped_levels_inside_the_current_step(pytester, fake_client):
    pytester.makepyfile('''
        import logging
        log = logging.getLogger("my.app")

        def test_a():
            log.debug("debug hidden")
            log.info("info shown")
            log.warning("warn shown")
            log.error("error shown")
    ''')
    run(pytester)
    by_msg = {l.message: l for l in fake_client.logs()}
    assert 'debug hidden' not in by_msg
    assert by_msg['info shown'].logLevel == LogLevel.INFO
    assert by_msg['warn shown'].logLevel == LogLevel.WARN
    assert by_msg['error shown'].logLevel == LogLevel.ERROR
    assert by_msg['info shown'].stepUUID == fake_client.step_uuid('call')


def test_log_level_can_be_lowered(pytester, fake_client):
    pytester.makepyfile('''
        import logging

        def test_a():
            logging.getLogger("x").debug("now visible")
    ''')
    pytester.makeini('[pytest]\norangebeard_log_level = DEBUG\n')
    run(pytester)
    assert any(l.message == 'now visible' for l in fake_client.logs())


def test_stdout_stderr_and_failure_details_are_logged(pytester, fake_client):
    pytester.makepyfile('''
        import sys

        def test_a():
            print("hello stdout")
            print("hello stderr", file=sys.stderr)
            assert 1 == 2, "the numbers differ"
    ''')
    run(pytester)
    logs = fake_client.logs()
    assert any('hello stdout' in l.message and l.logLevel == LogLevel.INFO for l in logs)
    assert any('hello stderr' in l.message and l.logLevel == LogLevel.WARN for l in logs)
    failure = [l for l in logs if l.logLevel == LogLevel.ERROR and 'the numbers differ' in l.message]
    assert failure
    assert failure[0].stepUUID == fake_client.step_uuid('call')
    assert fake_client.finish_status_of_step(fake_client.step_uuid('call')) == Status.FAILED


def test_setup_error_fails_the_test_and_skips_call(pytester, fake_client):
    pytester.makepyfile('''
        import pytest

        @pytest.fixture
        def broken():
            raise RuntimeError("fixture exploded")

        def test_a(broken):
            pass
    ''')
    result = run(pytester)
    result.assert_outcomes(errors=1)
    assert 'call' not in fake_client.step_names()
    assert fake_client.finish_status_of_test('test_a') == Status.FAILED
    assert fake_client.finish_status_of_step(fake_client.step_uuid('fixture: broken')) == Status.FAILED
    assert any('fixture exploded' in l.message for l in fake_client.logs())


def test_teardown_error_fails_the_test(pytester, fake_client):
    pytester.makepyfile('''
        import pytest

        @pytest.fixture
        def messy():
            yield
            raise RuntimeError("cleanup exploded")

        def test_a(messy):
            pass
    ''')
    run(pytester)
    assert fake_client.finish_status_of_test('test_a') == Status.FAILED
    assert any('cleanup exploded' in l.message for l in fake_client.logs())


def test_skip_reason_is_logged(pytester, fake_client):
    pytester.makepyfile('''
        import pytest

        def test_a():
            pytest.skip("no browser available")
    ''')
    run(pytester)
    assert any('no browser available' in l.message for l in fake_client.logs())
    assert fake_client.finish_status_of_test('test_a') == Status.SKIPPED


def test_markers_and_docstring_become_attributes_and_description(pytester, fake_client):
    pytester.makepyfile('''
        import pytest

        @pytest.mark.smoke
        def test_a():
            """Checks the thing."""
    ''')
    pytester.makeini('[pytest]\nmarkers = smoke: smoke tests\n')
    run(pytester)
    req = fake_client.of('start_test')[0][0]
    assert req.description == 'Checks the thing.'
    assert (None, 'smoke') in [(a.key, a.value) for a in req.attributes]


def test_attach_api_and_fixture(pytester, fake_client):
    pytester.makepyfile('''
        import orangebeard_pytest as ob

        def test_a(orangebeard, tmp_path):
            ob.attach(b"raw", name="raw.txt")
            f = tmp_path / "x.json"
            f.write_text("{}")
            orangebeard.attach(f)
            orangebeard.log("via fixture")
    ''')
    run(pytester)
    names = [a.AttachmentFile.name for a, _ in fake_client.of('send_attachment')]
    assert names == ['raw.txt', 'x.json']
    assert any(l.message == 'via fixture' for l in fake_client.logs())


def test_files_produced_in_the_playwright_output_dir_are_attached(pytester, fake_client):
    """pytest-playwright writes screenshots/traces/videos below --output; we attach what a test produced."""
    pytester.makepyfile('''
        import pathlib

        def test_a(request):
            out = pathlib.Path(request.config.getoption("output")) / "test_a-chromium"
            out.mkdir(parents=True)
            (out / "trace.zip").write_bytes(b"zip")
            (out / "test-failed-1.png").write_bytes(b"png")
    ''')
    run(pytester)
    attachments = {a.AttachmentFile.name: a for a, _ in fake_client.of('send_attachment')}
    assert set(attachments) == {'trace.zip', 'test-failed-1.png'}
    assert attachments['trace.zip'].AttachmentMetaData.testUUID == fake_client.test_uuid('test_a')
    assert any('show-trace' in l.message for l in fake_client.logs())


def test_extra_watch_directories_can_be_configured(pytester, fake_client):
    pytester.makepyfile('''
        import pathlib

        def test_a():
            d = pathlib.Path("my-artifacts")
            d.mkdir()
            (d / "dump.log").write_text("x")
    ''')
    pytester.makeini('[pytest]\norangebeard_watch_dirs = my-artifacts\n')
    run(pytester)
    assert [a.AttachmentFile.name for a, _ in fake_client.of('send_attachment')] == ['dump.log']


def test_backend_failures_never_break_the_test_run(pytester, fake_client):
    def boom(*_a, **_k):
        raise RuntimeError('orangebeard unreachable')

    fake_client.start_test = boom
    fake_client.log_batch = boom
    fake_client.log = boom
    pytester.makepyfile('def test_a():\n    print("x")\n    assert True\n')
    result = run(pytester)
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(['*Orangebeard*unreachable*'])


def test_terminal_summary_mentions_orangebeard(pytester, fake_client):
    pytester.makepyfile('def test_a():\n    pass\n')
    result = run(pytester)
    result.stdout.fnmatch_lines(['*Orangebeard*'])
