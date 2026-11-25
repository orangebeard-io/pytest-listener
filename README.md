# orangebeard-pytest

[Orangebeard](https://orangebeard.io) reporting plugin for [pytest](https://pytest.org), including
[pytest-playwright](https://github.com/microsoft/playwright-pytest).

* Suites, tests and steps: directories, modules and classes become nested suites; every test has `setup`, `call` and
  `teardown` steps, fixtures become sub steps, and you can add your own nested steps.
* Logs: `logging` records, captured stdout/stderr, failure details, skip and xfail reasons.
* Attachments: anything you attach, plus the screenshots, traces and videos pytest-playwright produces.
* Never gets in the way: when Orangebeard is not configured the plugin does nothing, and reporting problems never
  fail your tests.

## Install

```shell
pip install orangebeard-pytest
```

The plugin is picked up automatically by pytest (entry point `pytest11`).

## Configure

Configuration is shared with the other Orangebeard listeners. Environment variables or an `orangebeard.json`
(searched from the pytest rootdir upwards):

```json
{
  "endpoint": "https://app.orangebeard.io/{your-organization}",
  "token": "00000000-0000-0000-0000-000000000000",
  "project": "my-project",
  "testset": "nightly",
  "description": "Nightly regression",
  "attributes": [{"key": "env", "value": "acceptance"}, {"value": "smoke"}]
}
```

| Setting          | Environment variable    | pytest option / ini                       |
|------------------|-------------------------|-------------------------------------------|
| Endpoint         | `ORANGEBEARD_ENDPOINT`  | `--ob-endpoint`                           |
| Access token     | `ORANGEBEARD_TOKEN`     | (environment or `orangebeard.json` only)  |
| Project          | `ORANGEBEARD_PROJECT`   | `--ob-project`, `orangebeard_project`     |
| Test set         | `ORANGEBEARD_TESTSET`   | `--ob-testset`, `orangebeard_testset`     |
| Description      | `ORANGEBEARD_DESCRIPTION` | `--ob-description`, `orangebeard_description` |
| Attributes       | `ORANGEBEARD_ATTRIBUTES` (`key:value;tag`) | `--ob-attribute key:value` (repeatable) |
| Existing run     | `ORANGEBEARD_TESTRUN_UUID` | (report into an announced run; finish it with the Orangebeard CLI) |

Precedence: command line, then ini file, then environment / `orangebeard.json`. The test set defaults to the name of
the rootdir. Reporting is active as soon as endpoint, token and project are known.

Other options:

| Option                                  | Meaning                                                           |
|-----------------------------------------|-------------------------------------------------------------------|
| `--orangebeard`                         | Fail with a clear error when the configuration is incomplete      |
| `--ob-no-report`                        | Switch reporting off                                              |
| `orangebeard_log_level` (default INFO)  | Minimum `logging` level that is reported                          |
| `orangebeard_report_fixtures`           | `user` (default), `all` or `none`: fixtures reported as steps      |
| `orangebeard_max_attachment_mb` (50)    | Larger attachments are skipped (with a warning log)               |
| `orangebeard_watch_dirs`                | Extra directories; files a test creates there are attached        |

## Steps, logs and attachments in your tests

```python
import orangebeard_pytest as ob

def test_checkout(page):
    with ob.step("Add item to cart"):
        page.click("#add")
        with ob.step("Verify badge"):
            assert page.inner_text("#badge") == "1"
    ob.log("cart looks fine", level="info")
    ob.attach(b"{...}", name="cart.json")        # bytes need a name
    ob.attach("reports/summary.html")            # or a path

@ob.step("Log in")                               # also usable as a decorator
def login(page): ...
```

The same functions are available through the `orangebeard` fixture. Outside an Orangebeard run they do nothing, so
your tests also work without the plugin configured.

## Playwright

Nothing to configure. Everything pytest-playwright writes to its `--output` directory while a test runs (screenshots,
`trace.zip`, videos) is attached to that test, honouring `--screenshot`, `--tracing` and `--video`:

```shell
pytest --screenshot only-on-failure --tracing retain-on-failure --video retain-on-failure
```

Open a downloaded trace with `playwright show-trace trace.zip`.

## How it is reported

```
suite  tests            (directory)
 └ suite  test_cart.py  (module)
    └ suite  TestCart   (class)
       └ test  test_checkout - iteration #1   (when parametrized)
          ├ step  setup
          │  └ step  fixture: my_database
          ├ step  call
          │  └ step  Add item to cart
          │     └ step  Verify badge
          └ step  teardown
```

Parametrized tests: the parameter id can hold arbitrary data and a changing name would break a test's history, so it
never becomes part of the name. A function that runs more than once with different data is reported as
`test_checkout - iteration #1`, `... #2`, ... (Orangebeard treats identical names as retries of one test). The
numbers follow the collection order and do not change with `-k`/`-m`; a function with a single case keeps its plain
name. The parameters are added to the description (clipped to 2000 characters) and logged in full. Descriptions are
clipped to Orangebeard's 4096 character limit and names to 1024. Selecting one case by node id
(`pytest file.py::test_x[a]`) collects only that case, so it is reported without an iteration number.

A test fails on any setup error, test failure, teardown error or strict xpass. Skipped and xfailed tests are
`SKIPPED`.

## Limitations

* `pytest-xdist` (`-n`) is not supported yet; reporting is disabled with a warning when it is used.
* Fixture finalizers are not reported as separate steps; their output ends up in the `teardown` step.
* While a phase runs the root logger level is lowered to `orangebeard_log_level` so records reach the reporter.

## Development

```shell
pip install -e ".[test]"
python -m pytest
```

The Playwright tests need a browser: `playwright install chromium`.

The suite reports itself to Orangebeard (`orangebeard.json`: project `listeners`) when `ORANGEBEARD_TOKEN` is set,
locally via a git-ignored `.env` (see `.env.example`), in GitHub Actions via the `ORANGEBEARD_TOKEN` secret.
Without a token nothing is reported.

## License

Apache-2.0
