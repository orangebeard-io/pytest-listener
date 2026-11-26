"""End-to-end with the real pytest-playwright plugin and a real (headless) browser."""
import os

import pytest

pytest.importorskip('pytest_playwright')

REAL_HOME = os.environ.get('HOME')  # read at import time: the pytester fixture replaces HOME

PAGE_TEST = '''
import orangebeard_pytest as ob
from playwright.sync_api import Page

def test_passes(page: Page):
    with ob.step("Open the page"):
        page.set_content("<h1>Hello</h1>")
    with ob.step("Check the heading"):
        assert page.locator("h1").inner_text() == "Hello"

def test_fails(page: Page):
    page.set_content("<h1>Hello</h1>")
    assert page.locator("h1").inner_text() == "Goodbye"
'''


def run(pytester, *args):
    # the real playwright plugin must be active in the inner run (it is disabled for the outer one)
    return pytester.runpytest_inprocess('-p', 'no:cacheprovider', '-p', 'playwright', *args)


@pytest.fixture
def browser_available(pytester, monkeypatch):
    # on Linux and macOS Playwright looks for its browsers below HOME, which pytester points at a temp dir
    if REAL_HOME:
        monkeypatch.setenv('HOME', REAL_HOME)
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            p.chromium.launch().close()
    except Exception as error:  # browser not installed
        if os.environ.get('CI'):  # CI installs the browser: never skip these tests silently there
            pytest.fail(f'Playwright chromium not available: {error}')
        pytest.skip(f'Playwright chromium not available: {error}')


def test_screenshot_trace_and_video_are_attached(pytester, fake_client, browser_available):
    pytester.makepyfile(PAGE_TEST)
    result = run(pytester, '--screenshot', 'on', '--tracing', 'on', '--video', 'on')
    result.assert_outcomes(passed=1, failed=1)

    by_test = {}
    for attachment, _ in fake_client.of('send_attachment'):
        by_test.setdefault(attachment.AttachmentMetaData.testUUID, []).append(attachment.AttachmentFile.name)

    for test_name in ('test_passes[chromium]', 'test_fails[chromium]'):
        names = by_test[fake_client.test_uuid(test_name)]
        assert 'trace.zip' in names
        assert any(n.endswith('.png') for n in names)
        assert any(n.endswith('.webm') for n in names)

    assert fake_client.finish_status_of_test('test_passes[chromium]').value == 'PASSED'
    assert fake_client.finish_status_of_test('test_fails[chromium]').value == 'FAILED'
    assert 'Open the page' in fake_client.step_names()
    assert any('Goodbye' in l.message for l in fake_client.logs())


def test_only_on_failure_artifacts_follow_the_playwright_options(pytester, fake_client, browser_available):
    pytester.makepyfile(PAGE_TEST)
    run(pytester, '--screenshot', 'only-on-failure')
    names = {(a.AttachmentMetaData.testUUID, a.AttachmentFile.name) for a, _ in fake_client.of('send_attachment')}
    assert any(t == fake_client.test_uuid('test_fails[chromium]') and n.endswith('.png') for t, n in names)
    assert not any(t == fake_client.test_uuid('test_passes[chromium]') for t, _ in names)


def test_playwright_tests_are_named_after_browser_and_user_ids(pytester, fake_client, browser_available):
    pytester.makepyfile('''
        import pytest
        from playwright.sync_api import Page

        @pytest.mark.parametrize("title", ["Admin area", "Guest area"], ids=["admin", "guest"])
        def test_title(page: Page, title):
            page.set_content(f"<h1>{title}</h1>")

        @pytest.mark.parametrize("n", [1, 2])
        def test_numbered(page: Page, n):
            pass
    ''')
    run(pytester).assert_outcomes(passed=4)
    got = sorted(t.testName for t, _ in fake_client.of('start_test'))
    assert got == ['test_numbered[chromium] - iteration #1', 'test_numbered[chromium] - iteration #2',
                   'test_title[chromium-admin]', 'test_title[chromium-guest]']
