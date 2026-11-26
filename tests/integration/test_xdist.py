"""pytest-xdist: the main process starts and finishes one run, the workers report into it."""
import pytest

pytest.importorskip('xdist')

RUN = '44444444-4444-4444-4444-444444444444'

TESTS = '''
    import logging, os, time
    import pytest

    @pytest.mark.parametrize("n", range(8))
    def test_n(n):
        logging.getLogger("x").info("worker %s", os.environ["PYTEST_XDIST_WORKER"])
        time.sleep(0.05)
'''


def logged_text(server):
    return str([r['body'] for r in server.of('/log')])


def test_one_run_is_started_before_and_finished_after_the_workers(pytester, server):
    pytester.makepyfile(TESTS)
    result = pytester.runpytest_subprocess('-n', '2', '--ob-testset', 'parallel')
    result.assert_outcomes(passed=8)

    [start] = server.of('/test-run/start')
    [finish] = server.of('/test-run/finish/')
    run = start['response']
    assert start['body']['testSetName'] == 'parallel'
    assert finish['path'].endswith(f'/test-run/finish/{run}')

    tests = server.of('/test/start')
    assert sorted(r['body']['testName'] for r in tests) == [f'test_n - iteration #{i}' for i in range(1, 9)]
    assert {r['body']['testRunUUID'] for r in tests} == {run}
    assert 'worker gw0' in logged_text(server) and 'worker gw1' in logged_text(server)

    # nothing arrives after the run has been finished, and everything that was started got finished
    assert server.index_of(finish) == len(server.requests) - 1
    assert len(server.of('/test/finish/')) == 8
    result.stdout.fnmatch_lines(['*Orangebeard: results reported to *'])


def test_workers_report_into_a_given_run_that_is_left_open(pytester, server, monkeypatch):
    monkeypatch.setenv('ORANGEBEARD_TESTRUN_UUID', RUN)
    pytester.makepyfile(TESTS)
    pytester.runpytest_subprocess('-n', '2').assert_outcomes(passed=8)

    assert not server.of('/test-run/start') and not server.of('/test-run/finish')
    assert {r['body']['testRunUUID'] for r in server.of('/test/start')} == {RUN}
    assert len(server.of('/test/finish/')) == 8


def test_tests_still_run_when_the_run_cannot_be_started(pytester, server):
    server.reject_run_start = True
    pytester.makepyfile(TESTS)
    result = pytester.runpytest_subprocess('-n', '2')
    result.assert_outcomes(passed=8)
    result.stdout.fnmatch_lines(['*Orangebeard: problem while reporting*could not start the test run*'])
    assert len(server.requests) == 1  # no worker reports into a run that does not exist


def test_the_run_is_finished_when_a_worker_crashes(pytester, server):
    pytester.makepyfile('''
        import os

        def test_crash():
            os._exit(3)

        def test_other():
            pass
    ''')
    result = pytester.runpytest_subprocess('-n', '2')
    assert result.ret != 0
    assert len(server.of('/test-run/finish/')) == 1


def test_problems_of_workers_are_shown_in_the_summary(pytester, server):
    pytester.makeconftest('''
        from orangebeard.OrangebeardClient import OrangebeardClient

        def broken(self, *args, **kwargs):
            raise RuntimeError("backend exploded")

        OrangebeardClient.start_test = broken
    ''')
    pytester.makepyfile(TESTS)
    result = pytester.runpytest_subprocess('-n', '2')
    result.assert_outcomes(passed=8)
    result.stdout.fnmatch_lines(['*Orangebeard: problem while reporting*backend exploded*'])


def test_nothing_is_reported_when_switched_off(pytester, server):
    pytester.makepyfile(TESTS)
    pytester.runpytest_subprocess('-n', '2', '--ob-no-report').assert_outcomes(passed=8)
    assert not server.requests


def test_distribution_without_n_is_supported(pytester, server):
    pytester.makepyfile(TESTS)
    pytester.runpytest_subprocess('--dist', 'load', '--tx', '2*popen').assert_outcomes(passed=8)
    assert len(server.of('/test-run/start')) == 1 and len(server.of('/test-run/finish/')) == 1
    assert len(server.of('/test/start')) == 8


# pytest-playwright gives every test its own folder in a shared --output directory
TWO_TESTS_WRITING_AT_THE_SAME_TIME = '''
    import pathlib, time
    import pytest

    @pytest.mark.parametrize("name", ["a", "b"], ids=["a", "b"])
    def test_files(output_path, pytestconfig, name):
        folder = pathlib.Path(output_path)
        other = "b" if name == "a" else "a"
        shared = folder.parent
        deadline = time.time() + 20
        while True:  # until both exist; the other worker may still clear the output dir while it starts
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{name}.txt").write_text(name)
            (shared / f"loose-{name}.txt").write_text(name)
            if list(shared.glob(f"*/{other}.txt")) or time.time() > deadline:
                break
            time.sleep(0.05)
        time.sleep(1)
        extra = pathlib.Path(str(pytestconfig.rootpath)) / "reports"
        extra.mkdir(exist_ok=True)
        (extra / f"report-{name}.txt").write_text(name)
'''


def test_parallel_tests_only_get_the_files_from_their_own_output_folder(pytester, server):
    pytester.makeini('[pytest]\norangebeard_watch_dirs = reports\n')
    pytester.makepyfile(TWO_TESTS_WRITING_AT_THE_SAME_TIME)
    result = pytester.runpytest_subprocess('-n', '2')
    result.assert_outcomes(passed=2)

    assert server.attachments_by_test() == {'test_files[a]': ['a.txt'], 'test_files[b]': ['b.txt']}
    result.stdout.fnmatch_lines(['*Orangebeard: problem while reporting*orangebeard_watch_dirs*'])


def test_a_single_worker_attaches_files_like_a_normal_run(pytester, server):
    pytester.makeini('[pytest]\norangebeard_watch_dirs = reports\n')
    pytester.makepyfile('''
        import pathlib

        def test_files(output_path, pytestconfig):
            for folder, name in ((output_path, "own.txt"), (pytestconfig.rootpath / "reports", "report.txt")):
                pathlib.Path(folder).mkdir(parents=True, exist_ok=True)
                (pathlib.Path(folder) / name).write_text("x")
    ''')
    result = pytester.runpytest_subprocess('-n', '1')
    result.assert_outcomes(passed=1)
    assert server.attachments_by_test() == {'test_files': ['own.txt', 'report.txt']}
    assert 'orangebeard_watch_dirs' not in result.stdout.str()
