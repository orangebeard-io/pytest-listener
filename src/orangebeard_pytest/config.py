"""Resolve the Orangebeard configuration. Precedence: command line > ini file > env vars / orangebeard.json."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from uuid import UUID

import pytest
from orangebeard.config import AutoConfig
from orangebeard.entity.Attribute import Attribute
from orangebeard.entity.OrangebeardParameters import OrangebeardParameters

from orangebeard_pytest import mapping

REPORT_FIXTURE_MODES = ('all', 'user', 'none')

INI_OPTIONS = [
    ('orangebeard_project', 'string', 'Orangebeard project name'),
    ('orangebeard_testset', 'string', 'Orangebeard test set name (default: name of the rootdir)'),
    ('orangebeard_description', 'string', 'Description of the test run'),
    ('orangebeard_log_level', 'string', 'Minimum logging level reported as logs (default: INFO)'),
    ('orangebeard_report_fixtures', 'string', 'Report fixtures as steps: all, user (default) or none'),
    ('orangebeard_max_attachment_mb', 'string', 'Attachments larger than this are skipped (default: 50)'),
    ('orangebeard_watch_dirs', 'linelist', 'Extra directories whose new files are attached to the test'),
    ('orangebeard_log_parameters', 'string', 'Send the values of test parameters (default: true)'),
]


@dataclass
class Settings:
    params: OrangebeardParameters
    log_level: int = 20  # logging.INFO
    report_fixtures: str = 'user'
    max_attachment_bytes: int = 50 * 1024 * 1024
    watch_dirs: List[Path] = field(default_factory=list)
    log_parameters: bool = True

    @property
    def report_url(self) -> str:
        return f'{(self.params.endpoint or "").rstrip("/")}/p/{self.params.project}/test-results'


def add_options(parser) -> None:
    group = parser.getgroup('orangebeard', 'Orangebeard reporting')
    group.addoption('--orangebeard', action='store_true', dest='orangebeard', default=False,
                    help='Force reporting to Orangebeard (error when the configuration is incomplete).')
    group.addoption('--ob-no-report', action='store_true', dest='ob_no_report', default=False,
                    help='Do not report to Orangebeard, even when it is configured.')
    group.addoption('--ob-endpoint', dest='ob_endpoint', default=None, help='Orangebeard endpoint URL.')
    group.addoption('--ob-project', dest='ob_project', default=None, help='Orangebeard project name.')
    group.addoption('--ob-testset', dest='ob_testset', default=None, help='Orangebeard test set name.')
    group.addoption('--ob-description', dest='ob_description', default=None, help='Test run description.')
    group.addoption('--ob-attribute', dest='ob_attribute', action='append', default=None,
                    help="Test run attribute 'key:value' or 'tag' (repeatable).")
    for name, kind, help_text in INI_OPTIONS:
        parser.addini(name, help_text, type=kind, default=[] if kind == 'linelist' else '')


def _enabled(value: str) -> bool:
    return str(value).strip().lower() not in ('false', '0', 'no', 'off')


def _is_uuid(text: str) -> bool:
    try:
        UUID(text)
    except ValueError:
        return False
    return True


def _parse_attribute(text: str) -> Attribute:
    key, sep, value = text.partition(':')
    return Attribute(key, value) if sep else Attribute(None, text)


def resolve(config) -> Optional[Settings]:
    """Return Settings when reporting is active, None when the plugin should stay inert."""
    if config.getoption('ob_no_report', False):
        return None

    rootpath = Path(config.rootpath)
    params = AutoConfig.get_config(str(rootpath))

    for option, ini, attr in (('ob_endpoint', None, 'endpoint'), ('ob_project', 'orangebeard_project', 'project'),
                              ('ob_testset', 'orangebeard_testset', 'testset'),
                              ('ob_description', 'orangebeard_description', 'description')):
        value = config.getoption(option, None) or (config.getini(ini) if ini else '')
        if value:
            setattr(params, attr, value)

    attributes = list(params.attributes or [])
    attributes.extend(_parse_attribute(a) for a in (config.getoption('ob_attribute', None) or []))
    params.attributes = attributes

    required = {'endpoint': 'ORANGEBEARD_ENDPOINT', 'token': 'ORANGEBEARD_TOKEN', 'project': 'ORANGEBEARD_PROJECT'}
    missing = [env for attr, env in required.items() if not getattr(params, attr)]
    if missing:
        if config.getoption('orangebeard', False):
            raise pytest.UsageError(
                f'--orangebeard was given, but the configuration is incomplete. Missing: {", ".join(missing)} '
                '(set the environment variables or add them to orangebeard.json).')
        return None

    if not params.testset:
        params.testset = rootpath.name

    # a run that is started and finished elsewhere (e.g. `orangebeard-cli` around several CI jobs)
    run_uuid = str(params.testrun_uuid or '').strip()
    if run_uuid and not _is_uuid(run_uuid):
        # reporting into a run of our own instead would scatter the results over several runs
        problem = f"ORANGEBEARD_TESTRUN_UUID is not a UUID: '{run_uuid}'"
        if config.getoption('orangebeard', False):
            raise pytest.UsageError(problem)
        config.issue_config_time_warning(
            pytest.PytestConfigWarning(f'Orangebeard reporting disabled. {problem}'), stacklevel=2)
        return None
    params.testrun_uuid = run_uuid or None

    report_fixtures = (config.getini('orangebeard_report_fixtures') or 'user').strip().lower()
    if report_fixtures not in REPORT_FIXTURE_MODES:
        raise pytest.UsageError(f'orangebeard_report_fixtures must be one of {", ".join(REPORT_FIXTURE_MODES)}')
    try:
        log_level = mapping.parse_level(config.getini('orangebeard_log_level') or 'INFO')
    except ValueError as error:
        raise pytest.UsageError(f'orangebeard_log_level: {error}')
    max_mb = float(config.getini('orangebeard_max_attachment_mb') or 50)

    watch_dirs = [rootpath / line.strip() for line in (config.getini('orangebeard_watch_dirs') or []) if line.strip()]
    playwright_output = config.getoption('output', None)  # added by pytest-playwright
    if playwright_output:
        invocation = getattr(getattr(config, 'invocation_params', None), 'dir', rootpath)
        watch_dirs.append(Path(invocation) / playwright_output)

    return Settings(params=params, log_level=log_level, report_fixtures=report_fixtures,
                    max_attachment_bytes=int(max_mb * 1024 * 1024), watch_dirs=watch_dirs,
                    log_parameters=_enabled(config.getini('orangebeard_log_parameters')))
