"""Recognise Markdown in log messages, so Orangebeard can render it.

Deliberately conservative: rendering plain output (tracebacks, shell output, code) as Markdown mangles it, which is
worse than showing Markdown source. Only constructs that rarely occur by accident count. All patterns are bounded or
linear, as log messages can be large.
"""
import re

_FENCE = re.compile(r'^ {0,3}```', re.MULTILINE)
# the |---|:--:| line under a table header
_TABLE_DELIMITER = re.compile(r'^ {0,3}\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)*\|?[ \t]*$')
_SUB_HEADING = re.compile(r'^ {0,3}#{2,6} +\S', re.MULTILINE)
# **bold**, but not 2**8, **kwargs, src/**/*.py or rows of asterisks
_BOLD = re.compile(r'(?<![\w*/])\*\*(?=[^\s*/])[^*\n]{0,200}?(?<=[^\s*/])\*\*(?![\w*/])')
_LINK = re.compile(r'\[[^\[\]\n]{1,200}\]\(https?://[^\s()]{1,2000}\)')
# a single '#' is usually a comment: it only counts together with a list
_TOP_HEADING = re.compile(r'^ {0,3}# +\S', re.MULTILINE)
_LIST_ITEM = re.compile(r'^ {0,3}(?:[-*+]|\d{1,9}\.) +\S', re.MULTILINE)


def _has_table(text: str) -> bool:
    if '|' not in text:
        return False
    lines = text.splitlines()
    return any('|' in line and '|' in header and _TABLE_DELIMITER.match(line)
               for header, line in zip(lines, lines[1:]))


def looks_like_markdown(text: str) -> bool:
    return bool(
        len(_FENCE.findall(text)) >= 2
        or _has_table(text)
        or _SUB_HEADING.search(text)
        or _BOLD.search(text)
        or _LINK.search(text)
        or (_TOP_HEADING.search(text) and _LIST_ITEM.search(text))
    )


_LINE_END = re.compile(r'(\r\n|\r|\n)')
_FENCE_OPEN = re.compile(r' {0,3}(`{3,}(?=[^`]*$)|~{3,})')
_ANY_LIST_ITEM = re.compile(r' {0,3}(?:[-*+]|\d{1,9}[.)])(?:[ \t]|$)')
# what may start code or raw HTML; '<' followed by anything else ('a < b') is just text
_BACKTICKS_OR_TAG = re.compile(r'`+|<(?=[A-Za-z/!?])')
_BACKTICKS = re.compile(r'`+')
# <https://...> and <user@host> are links: their text survives rendering
_AUTOLINK = re.compile(r'<(?:[A-Za-z][A-Za-z0-9+.-]{1,31}:[^\s<>]*|[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255})>')


def _is_escaped(line: str, position: int) -> bool:
    start = position
    while start and line[start - 1] == '\\':
        start -= 1
    return (position - start) % 2 == 1


def _end_of_code_span(line: str, position: int, length: int) -> int:
    """The position after the closing backticks, or `position` when the span is never closed."""
    for run in _BACKTICKS.finditer(line, position):
        if len(run.group()) == length:
            return run.end()
    return position


def _escape_line(line: str) -> str:
    parts, copied, position = [], 0, 0
    while True:
        match = _BACKTICKS_OR_TAG.search(line, position)
        if match is None:
            return ''.join(parts) + line[copied:]
        start, position = match.start(), match.end()
        escaped = _is_escaped(line, start)
        if match.group() != '<':
            length = len(match.group()) - escaped  # an escaped backtick is literal text
            if length:
                position = _end_of_code_span(line, position, length)
        elif not escaped:
            link = _AUTOLINK.match(line, start)
            if link:
                position = link.end()
            else:
                parts.append(line[copied:start] + '\\')
                copied = start


def escape_html(text: str) -> str:
    """Escape what Markdown would treat as HTML. Orangebeard drops unknown tags, and with them text like
    <Locator selector='#a'>. Code is left alone. Code spans are only recognised within one line: when in doubt a
    bracket is escaped, as a visible backslash is better than lost text.
    """
    if '<' not in text:
        return text
    pieces = _LINE_END.split(text)  # lines at the even positions, their line ends at the odd ones
    fence = None  # the backticks or tildes that opened the current fenced block
    blank_before, in_indented_code, in_list = True, False, False
    for number in range(0, len(pieces), 2):
        line = pieces[number]
        if fence:
            closing = line.strip()
            if len(line) - len(line.lstrip(' ')) <= 3 and closing.startswith(fence) and not closing.strip(fence[0]):
                fence = None
            continue
        if not line.strip():
            blank_before = True
            continue
        indented = line.startswith(('    ', '\t'))
        in_indented_code = indented and not in_list and (blank_before or in_indented_code)
        opening = _FENCE_OPEN.match(line)
        if opening:
            fence = opening.group(1)
        elif not in_indented_code:
            if _ANY_LIST_ITEM.match(line):
                in_list = True
            elif blank_before and not line[0].isspace():
                in_list = False
            pieces[number] = _escape_line(line)
        blank_before = False
    return ''.join(pieces)


def code_block(text: str) -> str:
    """Wrap text in a fence that is longer than any run of backticks inside it."""
    longest = max((len(run) for run in re.findall(r'`+', text)), default=0)
    fence = '`' * max(3, longest + 1)
    return f'{fence}\n{text}\n{fence}'
