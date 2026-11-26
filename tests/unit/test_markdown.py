import pytest

from orangebeard_pytest.markdown import code_block, escape_html, looks_like_markdown

MARKDOWN = {
    'table': '| name | status |\n|------|--------|\n| a    | ok     |',
    'table without outer pipes': 'name | status\n:--- | ---:\na | ok',
    'bold': 'The **expected** value differs',
    'bold phrase': '**Call log:**\n  waiting for locator',
    'heading': '## Summary\nall good',
    'playwright debug banner': ('\n### The test is currently paused at the start\n\n### Debugging Instructions\n'
                                '- Run `python -m playwright cli attach tw-1` to attach to this test\n'),
    'fenced code': 'Snapshot:\n```yaml\n- heading "Hello"\n```',
    'link': 'See [the report](https://example.com/report) for details',
    'single hash heading with a list': '# Results\n\n- first\n- second',
}

PLAIN = {
    'empty': '',
    'sentence': 'Clicked the submit button',
    'traceback': ('Traceback (most recent call last):\n  File "x.py", line 1, in <module>\n    f(**kwargs)\n'
                  '    ^^^^^^\nValueError: bad'),
    'kwargs': 'def f(*args, **kwargs): return g(**a, **b)',
    'power': 'result = 2**8 + 3**2',
    'globs': 'include = src/**/*.py, tests/**/data/**',
    'masked value': 'password=********',
    'star banner': '**************** START ****************\n** WARNING **',
    'shell comments': '# install\n# configure\npip install x',
    'single hash line': '# of retries: 3',
    'plain list': 'Items:\n- apple\n- pear',
    'pipes without a delimiter row': 'cat file | grep x | wc -l',
    'psql table': ' id | name\n----+------\n  1 | a',
    'separator lines': 'Results\n-------\nok\n=======',
    'index access': 'value = data[0](x)',
    'indented heading is code': '    ## not a heading',
    'unclosed fence': '``` oops',
}


@pytest.mark.parametrize('text', MARKDOWN.values(), ids=MARKDOWN.keys())
def test_markdown_is_recognised(text):
    assert looks_like_markdown(text)


@pytest.mark.parametrize('text', PLAIN.values(), ids=PLAIN.keys())
def test_plain_text_stays_plain(text):
    assert not looks_like_markdown(text)


def test_detection_is_fast_on_large_hostile_input():
    for text in ('**a ' * 50000, '| ' * 100000, '[' * 100000, '#' * 100000, '```\n' + 'x\n' * 100000):
        looks_like_markdown(text)  # must return promptly (no catastrophic backtracking)


def test_code_block_wraps_text():
    assert code_block('boom') == '```\nboom\n```'


def test_code_block_survives_fences_inside_the_text():
    block = code_block('before\n```yaml\nx: 1\n```\nafter')
    assert block.startswith('````\n') and block.endswith('\n````')


# the UI treats <...> in Markdown as HTML and drops what it does not allow
ESCAPED = {
    'tag': ('<Locator selector="#a"> not found', r'\<Locator selector="#a"> not found'),
    'closing tag and comment': ('</div> <!-- note --> <?php', r'\</div> \<!-- note --> \<?php'),
    'after inline code': ('`<a>` and <b>', r'`<a>` and \<b>'),
    'after double backtick code': ('``x ` <a>`` <b>', r'``x ` <a>`` \<b>'),
    'unmatched backtick': ('a ` quote <a>', r'a ` quote \<a>'),
    'escaped backticks are no code': (r'\` <a> \`', r'\` \<a> \`'),
    'backticks on different lines': ('one ` two\n<a> three `', 'one ` two\n\\<a> three `'),
    'backticks around a carriage return': ('one ` two\r<a> three `', 'one ` two\r\\<a> three `'),
    'after a fence': ('```\n<a>\n```\n<b>', '```\n<a>\n```\n\\<b>'),
    'indented paragraph continuation': ('text\n    <a>', 'text\n    \\<a>'),
    'indented list continuation': ('- item\n\n    <a>', '- item\n\n    \\<a>'),
    'after indented code': ('x\n\n    <a>\n<b>', 'x\n\n    <a>\n\\<b>'),
    'after a literal backslash': (r'\\<a>', r'\\\<a>'),
    'windows line ends': ('<a>\r\n<b>\r\n', '\\<a>\r\n\\<b>\r\n'),
}

UNTOUCHED = {
    'comparisons and arrows': 'a < b, x <= 3, <- here, << and <>',
    'python repr': '<__main__.User object at 0x1>',
    'already escaped': r'\<a>',
    'inline code': 'use `List<String>` here',
    'fence': '```html\n<a href="x">\n```',
    'tilde fence': '~~~\n<a>\n~~~',
    'shorter fence inside a fence': '````\n```\n<a>\n```\n````',
    'unclosed fence': '```\n<a>',
    'fence with windows line ends': '```\r\n<a>\r\n```\r\n',
    'indented code': 'x\n\n    <a>\n\n    <b>',
    'indented code at the start': '    <a>',
    'autolinks': '<https://example.com/a?b=1> <user@example.com>',
}


@pytest.mark.parametrize('text, expected', ESCAPED.values(), ids=ESCAPED.keys())
def test_html_outside_code_is_escaped(text, expected):
    assert escape_html(text) == expected


@pytest.mark.parametrize('text', UNTOUCHED.values(), ids=UNTOUCHED.keys())
def test_code_and_harmless_brackets_are_not_escaped(text):
    assert escape_html(text) == text


def test_escaping_is_fast_on_large_hostile_input():
    unmatched = ' '.join('`' * n for n in range(1, 600))
    for text in ('<' * 100000, '\\' * 100000, '<a:' * 50000, '<a@' * 50000, unmatched, '<a>\n' * 50000):
        escape_html(text)  # must return promptly
