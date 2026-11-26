"""One test per way of naming parametrized cases, see
https://docs.pytest.org/en/stable/example/parametrize.html#different-options-for-test-ids
"""


def run(pytester, *args):
    return pytester.runpytest_inprocess('-p', 'no:cacheprovider', *args)


def names(client):
    return [t.testName for t, _ in client.of('start_test')]


def test_ids_list_with_gaps(pytester, fake_client):
    pytester.makepyfile(test_mod='''
        import pytest

        @pytest.mark.parametrize("user", ["a@x", "b@x", "c@x"], ids=["admin", None, "guest"])
        def test_login(user):
            pass
    ''')
    run(pytester).assert_outcomes(passed=3)
    assert names(fake_client) == ['test_login[admin]', 'test_login - iteration #2', 'test_login[guest]']


def test_ids_function(pytester, fake_client):
    pytester.makepyfile(test_mod='''
        import datetime
        import pytest

        def idfn(val):
            if isinstance(val, datetime.date):
                return val.strftime("%Y%m%d")

        @pytest.mark.parametrize("day,count", [(datetime.date(2001, 12, 12), 1), (datetime.date(2001, 12, 11), 2)],
                                 ids=idfn)
        def test_days(day, count):
            pass
    ''')
    run(pytester).assert_outcomes(passed=2)
    assert names(fake_client) == ['test_days[20011212]', 'test_days[20011211]']


def test_pytest_param_ids(pytester, fake_client):
    pytester.makepyfile(test_mod='''
        import pytest

        @pytest.mark.parametrize("n", [pytest.param(1, id="small"), pytest.param(10 ** 9, id="huge"), 5])
        def test_size(n):
            pass
    ''')
    run(pytester).assert_outcomes(passed=3)
    assert names(fake_client) == ['test_size[small]', 'test_size[huge]', 'test_size - iteration #3']


def test_values_used_as_ids_by_pytest_are_not_names(pytester, fake_client):
    pytester.makepyfile(test_mod='''
        import pytest

        @pytest.mark.parametrize("text", ["alpha", "bravo"])
        def test_text(text):
            pass
    ''')
    run(pytester)
    assert names(fake_client) == ['test_text - iteration #1', 'test_text - iteration #2']


def test_scenarios_from_pytest_generate_tests(pytester, fake_client):
    pytester.makepyfile(test_mod='''
        def pytest_generate_tests(metafunc):
            idlist, argvalues = [], []
            for scenario in metafunc.cls.scenarios:
                idlist.append(scenario[0])
                items = scenario[1].items()
                argnames = [x[0] for x in items]
                argvalues.append([x[1] for x in items])
            metafunc.parametrize(argnames, argvalues, ids=idlist, scope="class")

        scenario1 = ("basic", {"attribute": "value"})
        scenario2 = ("advanced", {"attribute": "value2"})

        class TestSampleWithScenarios:
            scenarios = [scenario1, scenario2]

            def test_demo(self, attribute):
                assert isinstance(attribute, str)
    ''')
    run(pytester).assert_outcomes(passed=2)
    assert names(fake_client) == ['test_demo[basic]', 'test_demo[advanced]']


def test_fixture_params_with_and_without_ids(pytester, fake_client):
    pytester.makepyfile(test_mod='''
        import pytest

        @pytest.fixture(params=["pg://host/db", "sqlite://"], ids=["postgres", "sqlite"])
        def database(request):
            return request.param

        @pytest.fixture(params=[1, 2])
        def number(request):
            return request.param

        def test_db(database):
            pass

        def test_number(number):
            pass
    ''')
    run(pytester).assert_outcomes(passed=4)
    assert sorted(names(fake_client)) == ['test_db[postgres]', 'test_db[sqlite]',
                                          'test_number - iteration #1', 'test_number - iteration #2']


def test_stacked_parametrize_mixed(pytester, fake_client):
    pytester.makepyfile(test_mod='''
        import pytest

        @pytest.mark.parametrize("n", [1, 2])
        @pytest.mark.parametrize("role", ["r1", "r2"], ids=["admin", "guest"])
        def test_stack(role, n):
            pass
    ''')
    run(pytester).assert_outcomes(passed=4)
    got = names(fake_client)
    assert len(set(got)) == 4
    assert sorted(n.split(' - ')[0] for n in got) == ['test_stack[admin]'] * 2 + ['test_stack[guest]'] * 2
    assert sorted(n.split('#')[1] for n in got) == ['1', '2', '3', '4']


def test_class_level_generator_ids_are_shared_between_methods(pytester, fake_client):
    pytester.makepyfile(test_mod='''
        import itertools
        import pytest

        @pytest.mark.parametrize("n", [1, 2], ids=(f"case{i}" for i in itertools.count()))
        class TestShared:
            def test_one(self, n):
                pass

            def test_two(self, n):
                pass
    ''')
    run(pytester).assert_outcomes(passed=4)
    assert sorted(names(fake_client)) == ['test_one[case0]', 'test_one[case1]', 'test_two[case0]', 'test_two[case1]']


def test_make_parametrize_id_hook(pytester, fake_client):
    pytester.makeconftest('''
        def pytest_make_parametrize_id(config, val, argname):
            if isinstance(val, complex):
                return f"point{int(val.imag)}"
    ''')
    pytester.makepyfile(test_mod='''
        import pytest

        @pytest.mark.parametrize("p", [1j, 2j])
        def test_point(p):
            pass
    ''')
    run(pytester).assert_outcomes(passed=2)
    assert names(fake_client) == ['test_point[point1]', 'test_point[point2]']


def test_long_ids_are_data_and_fall_back_to_numbers(pytester, fake_client):
    pytester.makepyfile(test_mod='''
        import pytest

        @pytest.mark.parametrize("text", ["x" * 3000, "y" * 3000], ids=str)
        def test_long(text):
            pass
    ''')
    run(pytester).assert_outcomes(passed=2)
    assert names(fake_client) == ['test_long - iteration #1', 'test_long - iteration #2']


def test_duplicate_ids_stay_distinct(pytester, fake_client):
    pytester.makepyfile(test_mod='''
        import pytest

        @pytest.mark.parametrize("n", [1, 2, 3], ids=["same", "same", "other"])
        def test_dup(n):
            pass
    ''')
    run(pytester).assert_outcomes(passed=3)
    assert names(fake_client) == ['test_dup[same] - iteration #1', 'test_dup[same] - iteration #2', 'test_dup[other]']


def test_names_do_not_depend_on_selection(pytester, fake_client):
    pytester.makepyfile(test_mod='''
        import pytest

        @pytest.mark.parametrize("n", [1, 2, 3])
        def test_data(n):
            pass
    ''')
    run(pytester, 'test_mod.py::test_data[2]').assert_outcomes(passed=1)
    assert names(fake_client) == ['test_data - iteration #2']
    fake_client.calls.clear()
    run(pytester, '-k', '3').assert_outcomes(passed=1)
    assert names(fake_client) == ['test_data - iteration #3']


def test_real_parameter_values_are_logged_and_described(pytester, fake_client):
    pytester.makepyfile(test_mod='''
        import pytest

        @pytest.mark.parametrize("user,retries", [("alice", 3)], ids=["admin"])
        def test_login(user, retries):
            pass
    ''')
    run(pytester)
    test = fake_client.of('start_test')[0][0]
    assert test.testName == 'test_login[admin]'
    assert test.description == "Parameters: user='alice', retries=3"
    assert any(l.message == "Parameters: user='alice', retries=3" for l in fake_client.logs())


def test_parameter_values_can_be_switched_off(pytester, fake_client):
    pytester.makepyfile(test_mod='''
        import pytest

        @pytest.mark.parametrize("password", ["s3cret"], ids=["admin"])
        def test_login(password):
            pass
    ''')
    pytester.makeini("""
        [pytest]
        orangebeard_log_parameters = false
    """)
    run(pytester)
    test = fake_client.of('start_test')[0][0]
    assert test.description == 'Parameters: admin'
    assert not any('s3cret' in l.message for l in fake_client.logs())


def test_a_failing_repr_never_breaks_reporting(pytester, fake_client):
    pytester.makepyfile(test_mod='''
        import pytest

        class Odd:
            def __repr__(self):
                raise RuntimeError("no repr")

        @pytest.mark.parametrize("thing", [Odd()], ids=["odd"])
        def test_odd(thing):
            pass
    ''')
    run(pytester).assert_outcomes(passed=1)
    assert names(fake_client) == ['test_odd[odd]']
    assert 'thing=<unprintable Odd>' in fake_client.of('start_test')[0][0].description


def test_an_ids_function_that_fails_on_the_second_call_does_not_break_collection(pytester, fake_client):
    pytester.makepyfile(test_mod='''
        import pytest

        seen = set()

        def once(val):
            if val in seen:
                raise RuntimeError("called twice")
            seen.add(val)
            return f"id{val}"

        @pytest.mark.parametrize("n", [1, 2], ids=once)
        def test_once(n):
            pass
    ''')
    run(pytester).assert_outcomes(passed=2)
    assert names(fake_client) == ['test_once - iteration #1', 'test_once - iteration #2']
