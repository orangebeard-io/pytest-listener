import logging
from types import SimpleNamespace

from orangebeard.entity.LogLevel import LogLevel
from orangebeard.entity.TestStatus import TestStatus as Status

from orangebeard_pytest import mapping


def test_suite_chain_for_function_in_module():
    assert mapping.split_nodeid('test_a.py::test_x') == (['test_a.py'], 'test_x', '')


def test_suite_chain_includes_directories_and_classes():
    suites, test, _ = mapping.split_nodeid('pkg/sub/test_mod.py::TestThing::test_x')
    assert suites == ['pkg', 'sub', 'test_mod.py', 'TestThing']
    assert test == 'test_x'


def test_suite_chain_supports_nested_classes():
    suites, test, _ = mapping.split_nodeid('test_mod.py::Outer::Inner::test_x')
    assert suites == ['test_mod.py', 'Outer', 'Inner']


def test_parametrize_ids_are_never_part_of_the_test_name_and_may_contain_separators():
    suites, test, params = mapping.split_nodeid('pkg/test_mod.py::TestA::test_x[a/b::c-1]')
    assert suites == ['pkg', 'test_mod.py', 'TestA']
    assert test == 'test_x'
    assert params == 'a/b::c-1'


def test_huge_parametrize_id_does_not_leak_into_the_name():
    suites, test, params = mapping.split_nodeid('test_m.py::test_boundary[' + 'x' * 5000 + ']')
    assert test == 'test_boundary' and params == 'x' * 5000


def test_names_are_clipped_to_the_orangebeard_limit():
    assert len(mapping.clip('y' * 5000, 1024)) == 1024
    assert mapping.clip('short', 1024) == 'short'
    assert mapping.clip('y' * 20, 10).endswith('…')


def report(when, outcome, wasxfail=None):
    r = SimpleNamespace(when=when, outcome=outcome)
    if wasxfail is not None:
        r.wasxfail = wasxfail
    return r


def test_status_passed():
    reports = {'setup': report('setup', 'passed'), 'call': report('call', 'passed'),
               'teardown': report('teardown', 'passed')}
    assert mapping.test_status(reports) == Status.PASSED


def test_status_failed_in_call():
    reports = {'setup': report('setup', 'passed'), 'call': report('call', 'failed'),
               'teardown': report('teardown', 'passed')}
    assert mapping.test_status(reports) == Status.FAILED


def test_status_failed_in_setup_is_failed():
    reports = {'setup': report('setup', 'failed'), 'teardown': report('teardown', 'passed')}
    assert mapping.test_status(reports) == Status.FAILED


def test_status_error_in_teardown_is_failed_even_when_call_passed():
    reports = {'setup': report('setup', 'passed'), 'call': report('call', 'passed'),
               'teardown': report('teardown', 'failed')}
    assert mapping.test_status(reports) == Status.FAILED


def test_status_skipped_in_setup():
    reports = {'setup': report('setup', 'skipped'), 'teardown': report('teardown', 'passed')}
    assert mapping.test_status(reports) == Status.SKIPPED


def test_status_xfail_is_skipped():
    reports = {'setup': report('setup', 'passed'), 'call': report('call', 'skipped', wasxfail='bug'),
               'teardown': report('teardown', 'passed')}
    assert mapping.test_status(reports) == Status.SKIPPED


def test_status_non_strict_xpass_is_passed():
    reports = {'setup': report('setup', 'passed'), 'call': report('call', 'passed', wasxfail='bug'),
               'teardown': report('teardown', 'passed')}
    assert mapping.test_status(reports) == Status.PASSED


def test_status_strict_xpass_is_failed():
    reports = {'setup': report('setup', 'passed'), 'call': report('call', 'failed', wasxfail='bug'),
               'teardown': report('teardown', 'passed')}
    assert mapping.test_status(reports) == Status.FAILED


def test_phase_status_from_outcome():
    assert mapping.phase_status('passed') == Status.PASSED
    assert mapping.phase_status('failed') == Status.FAILED
    assert mapping.phase_status('skipped') == Status.SKIPPED


def test_log_level_mapping():
    assert mapping.log_level(logging.DEBUG) == LogLevel.DEBUG
    assert mapping.log_level(logging.INFO) == LogLevel.INFO
    assert mapping.log_level(logging.WARNING) == LogLevel.WARN
    assert mapping.log_level(logging.ERROR) == LogLevel.ERROR
    assert mapping.log_level(logging.CRITICAL) == LogLevel.ERROR
    assert mapping.log_level(5) == LogLevel.DEBUG


def test_parse_level_name():
    assert mapping.parse_level('info') == logging.INFO
    assert mapping.parse_level('WARNING') == logging.WARNING
    assert mapping.parse_level('10') == 10


def test_marker_attributes_skip_builtin_markers():
    item = SimpleNamespace(iter_markers=lambda: iter([
        SimpleNamespace(name='smoke'), SimpleNamespace(name='parametrize'), SimpleNamespace(name='skipif'),
        SimpleNamespace(name='usefixtures'), SimpleNamespace(name='smoke'), SimpleNamespace(name='slow')]))
    attrs = mapping.marker_attributes(item)
    assert [(a.key, a.value) for a in attrs] == [(None, 'smoke'), (None, 'slow')]


def test_iterations_number_every_case_of_a_function_that_runs_more_than_once():
    ids = ['t.py::test_a[x]', 't.py::test_b', 't.py::test_a[y]', 't.py::TestC::test_a[x]', 't.py::test_a[z]']
    assert mapping.iteration_numbers(ids) == {
        't.py::test_a[x]': 1, 't.py::test_a[y]': 2, 't.py::test_a[z]': 3}


def test_a_single_parametrized_case_gets_no_iteration():
    assert mapping.iteration_numbers(['t.py::test_a[only]', 't.py::test_b']) == {}


def test_iterations_are_per_function_and_class():
    ids = ['t.py::TestA::test_x[1]', 't.py::TestB::test_x[1]', 't.py::TestA::test_x[2]']
    assert mapping.iteration_numbers(ids) == {'t.py::TestA::test_x[1]': 1, 't.py::TestA::test_x[2]': 2}


def test_params_containing_brackets_still_group_by_function():
    ids = ['t.py::test_a[[1, 2]]', 't.py::test_a[[3]]']
    assert mapping.iteration_numbers(ids) == {'t.py::test_a[[1, 2]]': 1, 't.py::test_a[[3]]': 2}
