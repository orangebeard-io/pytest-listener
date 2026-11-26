from orangebeard_pytest.mapping import Dimension, display_name


def named(label, size=2, index=0, **kwargs):
    return Dimension(size=size, index=index, label=label, **kwargs)


def unnamed(size=2, index=0):
    return Dimension(size=size, index=index, label=None)


def test_not_parametrized():
    assert display_name('test_x', []) == 'test_x'


def test_named_case_uses_pytest_style():
    assert display_name('test_x', [named('admin')]) == 'test_x[admin]'


def test_a_single_named_case_still_shows_its_name():
    assert display_name('test_x', [named('chromium', size=1)]) == 'test_x[chromium]'


def test_several_named_dimensions_are_joined_like_pytest_does():
    dims = [named('chromium', size=1), named('admin')]
    assert display_name('test_x', dims) == 'test_x[chromium-admin]'


def test_single_unnamed_case_keeps_the_plain_name():
    assert display_name('test_x', [unnamed(size=1)]) == 'test_x'


def test_unnamed_cases_are_numbered_from_one():
    assert display_name('test_x', [unnamed(size=3, index=0)]) == 'test_x - iteration #1'
    assert display_name('test_x', [unnamed(size=3, index=2)]) == 'test_x - iteration #3'


def test_named_and_varying_unnamed_dimensions_are_combined_with_a_number():
    dims = [named('chromium', size=1), unnamed(size=2, index=1)]
    assert display_name('test_x', dims) == 'test_x[chromium] - iteration #2'


def test_an_unnamed_dimension_with_one_case_is_ignored():
    assert display_name('test_x', [named('admin'), unnamed(size=1)]) == 'test_x[admin]'


def test_iteration_number_is_the_position_in_the_full_product():
    # applied in order: first dimension changes slowest, like pytest generates the cases
    assert display_name('t', [unnamed(2, 0), unnamed(3, 2)]) == 't - iteration #3'
    assert display_name('t', [unnamed(2, 1), unnamed(3, 0)]) == 't - iteration #4'
    assert display_name('t', [unnamed(2, 1), unnamed(3, 2)]) == 't - iteration #6'


def test_ambiguous_ids_get_a_number_as_well():
    dims = [named('same', size=2, index=1, ambiguous=True)]
    assert display_name('test_x', dims) == 'test_x[same] - iteration #2'


def test_a_label_that_is_really_data_is_not_used():
    assert display_name('test_x', [named('x' * 101, size=2, index=1)]) == 'test_x - iteration #2'
    assert display_name('test_x', [named('x' * 100)]) == 'test_x[' + 'x' * 100 + ']'
    assert display_name('test_x', [named('x' * 101, size=1)]) == 'test_x'


def test_empty_label_counts_as_unnamed():
    assert display_name('test_x', [named('', size=2)]) == 'test_x - iteration #1'


def test_clipping_keeps_suffix_and_closing_bracket():
    plain = display_name('n' * 2000, [unnamed(20, 11)])
    assert len(plain) == 1024 and plain.endswith(' - iteration #12')
    with_label = display_name('n' * 1000, [named('l' * 90)])
    assert len(with_label) == 1024 and with_label.endswith(']')
    both = display_name('n' * 1000, [named('l' * 90), unnamed(2, 1)])
    assert len(both) == 1024 and both.endswith('] - iteration #2')
