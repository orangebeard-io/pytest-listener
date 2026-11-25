"""A recording stand-in for orangebeard.OrangebeardClient (same method names and signatures)."""
import uuid


class FakeOrangebeardClient:
    def __init__(self):
        self.calls = []  # list of (method_name, payload, result)

    def _record(self, name, payload, result=None):
        self.calls.append((name, payload, result))
        return result

    def of(self, name):
        return [(payload, result) for n, payload, result in self.calls if n == name]

    def names(self):
        return [n for n, _, _ in self.calls]

    # --- client API --------------------------------------------------------
    def start_test_run(self, start_test_run, direct=False):
        return self._record('start_test_run', start_test_run, uuid.uuid4())

    def start_suite(self, start_suite):
        return self._record('start_suite', start_suite, [uuid.uuid4() for _ in start_suite.suiteNames])

    def start_test(self, start_test):
        return self._record('start_test', start_test, uuid.uuid4())

    def finish_test(self, test_uuid, finish_test):
        self._record('finish_test', (test_uuid, finish_test))

    def start_step(self, start_step):
        return self._record('start_step', start_step, uuid.uuid4())

    def finish_step(self, step_uuid, finish_step):
        self._record('finish_step', (step_uuid, finish_step))

    def log(self, log):
        return self._record('log', log, uuid.uuid4())

    def log_batch(self, log):
        self._record('log_batch', log)

    def send_attachment(self, attachment):
        return self._record('send_attachment', attachment, uuid.uuid4())

    def finish_test_run(self, test_run_uuid, finish_test_run, direct=False):
        self._record('finish_test_run', (test_run_uuid, finish_test_run))

    def flush_logs(self, timeout=None):
        self._record('flush_logs', None)

    def close(self):
        self._record('close', None)

    # --- convenience for assertions -----------------------------------------
    def logs(self):
        """All log messages (batched or not) in order."""
        return [p for n, p, _ in self.calls if n in ('log', 'log_batch')]

    def step_names(self):
        return [p.stepName for p, _ in self.of('start_step')]

    def step_uuid(self, step_name):
        return next(r for p, r in self.of('start_step') if p.stepName == step_name)

    def finish_status_of_step(self, step_uuid):
        return next(f.status for u, f in (p for p, _ in self.of('finish_step')) if u == step_uuid)

    def test_uuid(self, test_name):
        return next(r for p, r in self.of('start_test') if p.testName == test_name)

    def finish_status_of_test(self, test_name):
        u = self.test_uuid(test_name)
        return next(f.status for t, f in (p for p, _ in self.of('finish_test')) if t == u)
