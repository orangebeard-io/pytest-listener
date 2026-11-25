"""Translates the pytest lifecycle into Orangebeard calls. Knows nothing about pytest hooks; never raises."""
import functools
from datetime import datetime
from typing import List, Optional

from orangebeard.entity.Attachment import Attachment, AttachmentFile, AttachmentMetaData
from orangebeard.entity.FinishStep import FinishStep
from orangebeard.entity.FinishTest import FinishTest
from orangebeard.entity.FinishTestRun import FinishTestRun
from orangebeard.entity.Log import Log
from orangebeard.entity.LogFormat import LogFormat
from orangebeard.entity.LogLevel import LogLevel
from orangebeard.entity.StartStep import StartStep
from orangebeard.entity.StartSuite import StartSuite
from orangebeard.entity.StartTest import StartTest
from orangebeard.entity.StartTestRun import StartTestRun
from orangebeard.entity.TestStatus import TestStatus
from orangebeard.entity.TestType import TestType

from orangebeard_pytest import mapping
from orangebeard_pytest.config import Settings


MAX_PARAMS_IN_DESCRIPTION = 500


def _now() -> datetime:
    return datetime.now().astimezone()


def _safe(method):
    """Reporting problems must never fail or break a test run: remember them for the terminal summary."""

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except Exception as error:
            self.problems.append(f'{method.__name__}: {error}')
            return None

    return wrapper


class OrangebeardReporter:
    def __init__(self, client, settings: Settings):
        self.client = client
        self.settings = settings
        self.problems: List[str] = []
        self.run_uuid = None
        self.test_uuid = None
        self._suites = {}
        self._steps: list = []

    @property
    def in_test(self) -> bool:
        return self.run_uuid is not None and self.test_uuid is not None

    @property
    def current_step(self):
        return self._steps[-1] if self._steps else None

    # ------------------------------------------------------------------ run

    @_safe
    def start_run(self):
        params = self.settings.params
        self.run_uuid = self.client.start_test_run(
            StartTestRun(params.testset, _now(), params.description, list(params.attributes or [])))

    @_safe
    def finish_run(self):
        if self.run_uuid is not None:
            self.client.finish_test_run(self.run_uuid, FinishTestRun(_now()))
        self.client.close()

    # ------------------------------------------------------------------ test

    @_safe
    def start_test(self, nodeid: str, description: Optional[str] = None, attributes=None,
                   iteration: Optional[int] = None):
        if self.run_uuid is None:
            return None
        suites, name, params = mapping.split_nodeid(nodeid)
        if iteration is not None:  # same function, different data: must not look like a retry
            suffix = f' - iteration #{iteration}'
            name = mapping.clip(name, mapping.MAX_NAME_LENGTH - len(suffix)) + suffix
        suite_uuid = self._ensure_suites(suites)
        if params:  # the parameters are data, not identity: description (clipped) + full value as a log
            summary = f'Parameters: {mapping.clip(params, MAX_PARAMS_IN_DESCRIPTION)}'
            description = f'{description}\n\n{summary}' if description else summary
        self.test_uuid = self.client.start_test(
            StartTest(self.run_uuid, suite_uuid, name, _now(), TestType.TEST, description, attributes or None))
        self._steps = []
        if params:
            self.log(f'Parameters: {params}')
        return self.test_uuid

    def _ensure_suites(self, suites: List[str]):
        known = 0
        for depth in range(len(suites), 0, -1):
            if tuple(suites[:depth]) in self._suites:
                known = depth
                break
        if known < len(suites):
            parent = self._suites.get(tuple(suites[:known]))
            uuids = self.client.start_suite(StartSuite(self.run_uuid, suites[known:], parent))
            for offset, suite_uuid in enumerate(uuids):
                self._suites[tuple(suites[:known + offset + 1])] = suite_uuid
        return self._suites[tuple(suites)]

    @_safe
    def finish_test(self, status: TestStatus):
        if not self.in_test:
            return
        self.close_open_steps(status)
        self.client.finish_test(self.test_uuid, FinishTest(self.run_uuid, status, _now()))
        self.test_uuid = None
        self._steps = []

    # ------------------------------------------------------------------ steps

    @_safe
    def start_step(self, name: str, description: Optional[str] = None):
        if not self.in_test:
            return None
        step_uuid = self.client.start_step(
            StartStep(self.run_uuid, self.test_uuid, name, _now(), self.current_step, description))
        self._steps.append(step_uuid)
        return step_uuid

    @_safe
    def finish_step(self, status: TestStatus):
        if self._steps:
            step_uuid = self._steps.pop()
            self.client.finish_step(step_uuid, FinishStep(self.run_uuid, status, _now()))

    def close_open_steps(self, status: TestStatus):
        while self._steps:
            self.finish_step(status)

    # ------------------------------------------------------------------ logs and attachments

    @_safe
    def log(self, message: str, level=LogLevel.INFO, fmt: LogFormat = LogFormat.PLAIN_TEXT):
        if not self.in_test:
            return
        self.client.log_batch(Log(self.run_uuid, self.test_uuid, message, mapping.normalize_level(level), fmt,
                                  self.current_step, _now()))

    @_safe
    def attach(self, name: str, content: bytes, description: Optional[str] = None, content_type: str = None):
        if not self.in_test:
            return
        if len(content) > self.settings.max_attachment_bytes:
            self.log(f'Attachment {name} skipped: {len(content)} bytes exceeds orangebeard_max_attachment_mb',
                     LogLevel.WARN)
            return
        step = self.current_step
        # an attachment hangs on a log entry, which needs an id: use the non-batched log call
        log_uuid = self.client.log(Log(self.run_uuid, self.test_uuid, f'Attachment: {description or name}',
                                       LogLevel.INFO, LogFormat.PLAIN_TEXT, step, _now()))
        attachment_file = AttachmentFile(name, content)
        if content_type:
            attachment_file.contentType = content_type
        self.client.send_attachment(
            Attachment(attachment_file, AttachmentMetaData(self.run_uuid, self.test_uuid, log_uuid, step)))
