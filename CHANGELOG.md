# Changelog

## 0.1.1

* Parametrize ids are no longer part of the test name (long or changing data was rejected by Orangebeard and broke
  test history). The parameters are in the description (clipped to 500 characters) and in full as a log entry.
* A function that runs more than once with different data is reported as `name - iteration #n` (n from 1, following
  the collection order, independent of -k/-m) so Orangebeard does not mistake the cases for retries.
* Suite and test names are clipped to Orangebeard's 1024 character limit.

## 0.1.0

* Initial release: suites/tests/steps, logs, attachments, pytest-playwright artifacts.
