from pathlib import Path

import pytest

from orangebeard_pytest import config as ob_config

TOKEN = '22222222-2222-2222-2222-222222222222'

ENV = ['ORANGEBEARD_ENDPOINT', 'ORANGEBEARD_TOKEN', 'ORANGEBEARD_PROJECT', 'ORANGEBEARD_TESTSET',
       'ORANGEBEARD_DESCRIPTION', 'ORANGEBEARD_ATTRIBUTES', 'ORANGEBEARD_REF_URL', 'ORANGEBEARD_TESTRUN_UUID']


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV:
        monkeypatch.delenv(name, raising=False)


class Opts:
    """Minimal stand-in for what the config module reads from pytest's config."""

    def __init__(self, tmp_path, cli=None, ini=None):
        self.rootpath = tmp_path
        self._cli = cli or {}
        self._ini = ini or {}

    def getoption(self, name, default=None):
        return self._cli.get(name, default)

    def getini(self, name):
        return self._ini.get(name, '')


def test_inert_when_nothing_is_configured(tmp_path):
    assert ob_config.resolve(Opts(tmp_path)) is None


def test_active_when_env_is_complete(tmp_path, monkeypatch):
    monkeypatch.setenv('ORANGEBEARD_ENDPOINT', 'https://ob.example')
    monkeypatch.setenv('ORANGEBEARD_TOKEN', TOKEN)
    monkeypatch.setenv('ORANGEBEARD_PROJECT', 'proj')
    settings = ob_config.resolve(Opts(tmp_path))
    assert settings.params.endpoint == 'https://ob.example'
    assert settings.params.project == 'proj'
    assert settings.params.testset == tmp_path.name  # defaults to the rootdir name


def test_orangebeard_json_in_rootdir_is_used(tmp_path):
    (tmp_path / 'orangebeard.json').write_text(
        '{"endpoint": "https://json.example", "token": "%s", "project": "jsonproj", "testset": "from json"}' % TOKEN)
    settings = ob_config.resolve(Opts(tmp_path))
    assert settings.params.endpoint == 'https://json.example'
    assert settings.params.testset == 'from json'


def test_precedence_cli_over_ini_over_env(tmp_path, monkeypatch):
    monkeypatch.setenv('ORANGEBEARD_ENDPOINT', 'https://ob.example')
    monkeypatch.setenv('ORANGEBEARD_TOKEN', TOKEN)
    monkeypatch.setenv('ORANGEBEARD_PROJECT', 'env-project')
    monkeypatch.setenv('ORANGEBEARD_TESTSET', 'env-set')
    opts = Opts(tmp_path, cli={'ob_testset': 'cli-set'},
                ini={'orangebeard_project': 'ini-project', 'orangebeard_testset': 'ini-set'})
    settings = ob_config.resolve(opts)
    assert settings.params.testset == 'cli-set'
    assert settings.params.project == 'ini-project'


def test_cli_attributes_are_added(tmp_path, monkeypatch):
    monkeypatch.setenv('ORANGEBEARD_ENDPOINT', 'https://ob.example')
    monkeypatch.setenv('ORANGEBEARD_TOKEN', TOKEN)
    monkeypatch.setenv('ORANGEBEARD_PROJECT', 'proj')
    settings = ob_config.resolve(Opts(tmp_path, cli={'ob_attribute': ['env:ci', 'plain']}))
    pairs = [(a.key, a.value) for a in settings.params.attributes]
    assert ('env', 'ci') in pairs and (None, 'plain') in pairs


def test_no_report_flag_disables_even_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv('ORANGEBEARD_ENDPOINT', 'https://ob.example')
    monkeypatch.setenv('ORANGEBEARD_TOKEN', TOKEN)
    monkeypatch.setenv('ORANGEBEARD_PROJECT', 'proj')
    assert ob_config.resolve(Opts(tmp_path, cli={'ob_no_report': True})) is None


def test_forced_but_incomplete_is_a_usage_error(tmp_path):
    with pytest.raises(pytest.UsageError, match='ORANGEBEARD_TOKEN'):
        ob_config.resolve(Opts(tmp_path, cli={'orangebeard': True}))


@pytest.mark.parametrize('source', ['env', 'orangebeard.json'])
def test_the_deprecated_test_run_uuid_is_ignored(tmp_path, monkeypatch, source):
    # the client would leave the run unfinished; announced runs are claimed by test set name instead
    monkeypatch.setenv('ORANGEBEARD_ENDPOINT', 'https://ob.example')
    monkeypatch.setenv('ORANGEBEARD_TOKEN', TOKEN)
    monkeypatch.setenv('ORANGEBEARD_PROJECT', 'proj')
    if source == 'env':
        monkeypatch.setenv('ORANGEBEARD_TESTRUN_UUID', TOKEN)
    else:
        (tmp_path / 'orangebeard.json').write_text('{"testrun_uuid": "%s"}' % TOKEN)
    assert ob_config.resolve(Opts(tmp_path)).params.testrun_uuid is None


def test_tuning_options_have_defaults_and_can_be_overridden(tmp_path, monkeypatch):
    monkeypatch.setenv('ORANGEBEARD_ENDPOINT', 'https://ob.example')
    monkeypatch.setenv('ORANGEBEARD_TOKEN', TOKEN)
    monkeypatch.setenv('ORANGEBEARD_PROJECT', 'proj')
    settings = ob_config.resolve(Opts(tmp_path))
    assert settings.log_level == 20  # INFO
    assert settings.report_fixtures == 'user'
    assert settings.max_attachment_bytes == 50 * 1024 * 1024
    settings = ob_config.resolve(Opts(tmp_path, ini={'orangebeard_log_level': 'DEBUG',
                                                     'orangebeard_report_fixtures': 'none',
                                                     'orangebeard_max_attachment_mb': '1'}))
    assert settings.log_level == 10
    assert settings.report_fixtures == 'none'
    assert settings.max_attachment_bytes == 1024 * 1024


def test_parameter_logging_is_on_by_default_and_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setenv('ORANGEBEARD_ENDPOINT', 'https://ob.example')
    monkeypatch.setenv('ORANGEBEARD_TOKEN', TOKEN)
    monkeypatch.setenv('ORANGEBEARD_PROJECT', 'proj')
    assert ob_config.resolve(Opts(tmp_path)).log_parameters is True
    for off in ('false', 'False', '0', 'no', 'off'):
        assert ob_config.resolve(Opts(tmp_path, ini={'orangebeard_log_parameters': off})).log_parameters is False
