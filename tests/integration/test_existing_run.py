"""Several processes reporting into one run that is started and finished outside pytest (orangebeard-cli)."""
RUN = '44444444-4444-4444-4444-444444444444'

TESTS = '''
    import logging

    def test_a():
        logging.getLogger("x").info("from a")

    def test_b():
        pass
'''


def test_tests_are_reported_into_the_given_run_without_starting_or_finishing_it(pytester, server, monkeypatch):
    monkeypatch.setenv('ORANGEBEARD_TESTRUN_UUID', RUN)
    pytester.makepyfile(TESTS)
    pytester.runpytest_subprocess().assert_outcomes(passed=2)

    assert not server.of('/test-run/start')
    assert not server.of('/test-run/finish')
    starts = server.of('/test/start')
    assert [r['body']['testName'] for r in starts] == ['test_a', 'test_b']
    assert {r['body']['testRunUUID'] for r in starts} == {RUN}
    assert {r['body']['testRunUUID'] for r in server.of('/suite/start')} == {RUN}
    # everything is sent before the process ends, so the run can be finished right after it
    assert len(server.of('/test/finish/')) == 2
    assert 'from a' in str([r['body'] for r in server.of('/log')])


def test_a_value_that_is_no_uuid_switches_reporting_off_with_a_warning(pytester, server, monkeypatch):
    monkeypatch.setenv('ORANGEBEARD_TESTRUN_UUID', 'None')  # what a failed `orangebeard-cli -x start` prints
    pytester.makepyfile(TESTS)
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=2, warnings=1)
    result.stdout.fnmatch_lines(['*ORANGEBEARD_TESTRUN_UUID*None*'])
    assert not server.requests


def test_a_value_that_is_no_uuid_is_an_error_when_reporting_is_forced(pytester, server, monkeypatch):
    monkeypatch.setenv('ORANGEBEARD_TESTRUN_UUID', 'None')
    pytester.makepyfile(TESTS)
    result = pytester.runpytest_subprocess('--orangebeard')
    assert result.ret != 0
    result.stderr.fnmatch_lines(['*ORANGEBEARD_TESTRUN_UUID*'])
    assert not server.requests
