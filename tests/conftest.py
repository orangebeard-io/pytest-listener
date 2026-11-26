import pytest

from tests.fake_server import FakeOrangebeardServer
from tests.fakes import FakeOrangebeardClient

pytest_plugins = ['pytester']

ORANGEBEARD_ENV = ['ORANGEBEARD_ENDPOINT', 'ORANGEBEARD_TOKEN', 'ORANGEBEARD_PROJECT', 'ORANGEBEARD_TESTSET',
                   'ORANGEBEARD_DESCRIPTION', 'ORANGEBEARD_ATTRIBUTES', 'ORANGEBEARD_REF_URL',
                   'ORANGEBEARD_TESTRUN_UUID']


@pytest.fixture(autouse=True)
def isolated_orangebeard_env(monkeypatch):
    for name in ORANGEBEARD_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def server(monkeypatch):
    """A fake Orangebeard over HTTP, configured through env vars (which subprocesses inherit)."""
    fake = FakeOrangebeardServer().start()
    monkeypatch.setenv('ORANGEBEARD_ENDPOINT', fake.url)
    monkeypatch.setenv('ORANGEBEARD_TOKEN', '33333333-3333-3333-3333-333333333333')
    monkeypatch.setenv('ORANGEBEARD_PROJECT', 'demo')
    yield fake
    fake.stop()


@pytest.fixture
def fake_client(monkeypatch):
    """Configure the plugin through env vars and inject a recording fake instead of the real client."""
    client = FakeOrangebeardClient()
    monkeypatch.setenv('ORANGEBEARD_ENDPOINT', 'https://orangebeard.test')
    monkeypatch.setenv('ORANGEBEARD_TOKEN', '33333333-3333-3333-3333-333333333333')
    monkeypatch.setenv('ORANGEBEARD_PROJECT', 'demo')
    monkeypatch.setattr('orangebeard_pytest.plugin.create_client', lambda params, settings: client)
    return client
