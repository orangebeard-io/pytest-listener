# Changelog

## 0.3.0

* Log messages containing Markdown (tables, bold text, headings, code fences, links) are sent in Markdown format.
  A failure message written in Markdown is also shown rendered, next to the traceback.
  Text like `<Locator ...>` is escaped in these messages, so rendering does not drop it as HTML.
* Fixed: captured stdout/stderr was logged again with every later phase (output of the test showed up twice).

## 0.2.0

**Test names of parametrized tests change** (Orangebeard history starts anew for the renamed tests).

* Ids you give (`ids=[...]`, an `ids` function, `pytest.param(id=...)`, scenario ids from `pytest_generate_tests`,
  fixture `ids`, the `pytest_make_parametrize_id` hook) are used in the test name, pytest style: `test_login[admin]`.
  pytest-playwright's browser is included: `test_login[chromium]`.
* ` - iteration #n` is only added where cases have no usable id (or duplicate ids). `n` no longer depends on how tests
  are selected, also not when selecting one case by node id.
* The real parameter values (`user='alice', retries=3`) are logged and added to the description instead of pytest's
  id. New ini option `orangebeard_log_parameters` (default `true`) switches that off.

## 0.1.1

* Parametrize ids are no longer part of the test name (long or changing data was rejected by Orangebeard and broke
  test history). The parameters are in the description (clipped to 2000 characters) and in full as a log entry.
* A function that runs more than once with different data is reported as `name - iteration #n` (n from 1, following
  the collection order, independent of -k/-m) so Orangebeard does not mistake the cases for retries.
* Suite, test and step names are clipped to Orangebeard's 1024 character limit, and all descriptions (test, step, run)
  to its 4096 character limit; the parameters stay visible even with a very long docstring.

## 0.1.0

* Initial release: suites/tests/steps, logs, attachments, pytest-playwright artifacts.
