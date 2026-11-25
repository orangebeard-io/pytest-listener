# Changelog

## 0.1.1

* Parametrize ids are no longer part of the test name (long or changing data was rejected by Orangebeard and broke
  test history). All parametrized cases share the function name; the parameters are in the description (clipped to
  500 characters) and in full as a log entry.
* Suite and test names are clipped to Orangebeard's 1024 character limit.

## 0.1.0

* Initial release: suites/tests/steps, logs, attachments, pytest-playwright artifacts.
