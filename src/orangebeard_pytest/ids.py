"""Find out which parametrize ids were given by the user.

pytest does not remember whether an id was chosen by the user or derived from the value, so every
metafunc.parametrize() call is observed while it happens. That one point covers the parametrize mark, fixture
params, custom pytest_generate_tests hooks and plugins such as pytest-playwright.
"""
import inspect
import itertools
import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

import pytest

from orangebeard_pytest.mapping import Dimension

_HIDDEN = getattr(pytest, 'HIDDEN_PARAM', object())  # pytest 8.4+


@dataclass(frozen=True)
class _Call:
    argnames: Tuple[str, ...]
    labels: Tuple[Optional[str], ...]  # one per case


def _is_parameter_set(value) -> bool:
    return type(value).__name__ == 'ParameterSet' and hasattr(value, 'values') and hasattr(value, 'id')


def _plain_id(value) -> Optional[str]:
    """An explicit id as pytest accepts it; anything else (e.g. pytest.HIDDEN_PARAM) is no name."""
    if value is _HIDDEN or not isinstance(value, (str, int, float, bool, Enum)):
        return None
    return str(value)


class ParametrizeRecorder:
    def __init__(self, config):
        self.config = config
        self._calls: Dict[str, List[_Call]] = {}  # by test function (definition) nodeid
        self._mark_labels: Dict[int, Tuple[Optional[str], ...]] = {}  # for ids pytest reuses between functions
        self._positions: Dict[str, Tuple[str, int]] = {}  # item nodeid -> (function nodeid, position of the case)

    # ------------------------------------------------------------------ recording

    def recording(self, metafunc):
        """Body of a pytest_generate_tests hook wrapper."""
        calls = self._calls[metafunc.definition.nodeid] = []
        original = metafunc.parametrize
        signature = inspect.signature(original)

        def parametrize(*args, **kwargs):
            try:
                bound = signature.bind(*args, **kwargs)
                argnames = bound.arguments['argnames']
                values = list(bound.arguments['argvalues'])
                bound.arguments['argvalues'] = values
                ids = bound.arguments.get('ids')
                mark = bound.arguments.get('_param_mark')
                source = getattr(mark, '_param_ids_from', None)
                reused = source is not None and getattr(source, '_param_ids_generated', None) is not None
                if ids is not None and not callable(ids) and not reused:
                    if hasattr(ids, '__len__'):
                        ids = list(ids)
                    else:  # a one-shot (possibly endless) iterator: read it once, hand pytest the result
                        ids = list(itertools.islice(ids, len(values)))
                        ids += [None] * (len(values) - len(ids))
                    bound.arguments['ids'] = ids
            except Exception:  # unexpected signature or arguments: leave everything to pytest
                return original(*args, **kwargs)

            result = original(*bound.args, **bound.kwargs)

            try:
                if reused:
                    labels = self._mark_labels.get(id(source))
                else:
                    labels = self._labels(argnames, values, ids)
                    if source is not None:
                        self._mark_labels[id(source)] = labels
                names = self._argnames(argnames)
                if labels is not None:
                    calls.append(_Call(names, labels))
            except Exception:  # naming must never break collection
                pass
            return result

        metafunc.parametrize = parametrize
        try:
            result = yield
        finally:
            metafunc.parametrize = original
        self._remember_positions(metafunc)
        return result

    def _remember_positions(self, metafunc) -> None:
        """The generated cases are the product of all calls, the last call varying fastest. Remember where each
        case sits in it. (item.callspec.indices cannot be used: pytest rewrites it afterwards.)"""
        function = metafunc.definition.nodeid
        for position, callspec in enumerate(getattr(metafunc, '_calls', None) or []):
            self._positions[f'{function}[{callspec.id}]'] = (function, position)

    @staticmethod
    def _argnames(argnames) -> Tuple[str, ...]:
        if isinstance(argnames, str):
            return tuple(name.strip() for name in argnames.split(',') if name.strip())
        return tuple(argnames)

    def _labels(self, argnames, values, ids) -> Tuple[Optional[str], ...]:
        names = self._argnames(argnames)
        single = isinstance(argnames, str) and len(names) == 1
        labels = []
        for index, value in enumerate(values):
            given = None
            if _is_parameter_set(value):
                given, case = value.id, tuple(value.values)
            else:
                case = (value,) if single else value
            if given is not None:
                label = _plain_id(given)
            elif isinstance(ids, list) and index < len(ids) and ids[index] is not None:
                label = _plain_id(ids[index])
            else:
                label = self._generated_label(names, case, ids)
                if label is None and names == ('browser_name',):  # pytest-playwright
                    label = str(case[0])
            labels.append(label)
        return tuple(labels)

    def _generated_label(self, names, case, ids) -> Optional[str]:
        """Ids produced by user code: an ids=function or the pytest_make_parametrize_id hook."""
        parts = []
        try:
            for name, value in zip(names, case):
                part = ids(value) if callable(ids) else None
                if part is None:
                    part = self.config.hook.pytest_make_parametrize_id(config=self.config, val=value, argname=name)
                if part is not None:
                    parts.append(str(part))
        except Exception:
            return None
        return '-'.join(parts) or None

    # ------------------------------------------------------------------ per test case

    def dimensions(self, item) -> Optional[List[Dimension]]:
        """The parametrize() calls behind a test item, in the order pytest applied them. None if unknown."""
        function, position = self._positions.get(item.nodeid, (None, None))
        calls = self._calls.get(function)
        if not calls or position >= math.prod(len(call.labels) for call in calls):
            return None
        dimensions = []
        for call in reversed(calls):
            position, index = divmod(position, len(call.labels))
            label = call.labels[index]
            dimensions.append(Dimension(size=len(call.labels), index=index, label=label,
                                        ambiguous=label is not None and call.labels.count(label) > 1))
        return dimensions[::-1]


def _safe_repr(value) -> str:
    try:
        return repr(value)
    except Exception:
        return f'<unprintable {type(value).__name__}>'


def parameter_text(item) -> Optional[str]:
    """The actual parameter values of a test case: "user='alice', retries=3"."""
    callspec = getattr(item, 'callspec', None)
    params = getattr(callspec, 'params', None)
    if not params:
        return None
    return ', '.join(f'{name}={_safe_repr(value)}' for name, value in params.items())
