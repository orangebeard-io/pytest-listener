"""A tiny in-process fake of the Orangebeard listener API (v3), for tests that run pytest in subprocesses.

The recording FakeOrangebeardClient cannot see what other processes do; this lets the real client talk HTTP.
"""
import asyncio
import json
import threading
import uuid

from aiohttp import web


class FakeOrangebeardServer:
    def __init__(self):
        self.requests = []  # dicts: method, path, body, response - in the order they arrived
        self.reject_run_start = False
        self.url = None
        self._loop = None
        self._runner = None
        self._thread = None

    # --- request handling -------------------------------------------------
    async def _handle(self, request: web.Request):
        raw = await request.read()
        body = json.loads(raw) if raw and request.content_type == 'application/json' else raw
        record = {'method': request.method, 'path': request.path, 'body': body, 'response': None}
        self.requests.append(record)
        path = request.path
        if path.endswith('/test-run/start'):
            if self.reject_run_start:  # no UUID in the answer (an error status would make the client retry for long)
                return web.Response(status=204)
            record['response'] = str(uuid.uuid4())
        elif path.endswith(('/test/start', '/step/start', '/log')):
            record['response'] = str(uuid.uuid4())
        elif path.endswith('/suite/start'):
            record['response'] = [{'suiteUUID': str(uuid.uuid4())} for _ in body['suiteNames']]
        elif path.endswith('/attachment'):
            return web.Response(text=str(uuid.uuid4()))
        else:
            return web.Response(status=204)  # finish calls and log batches
        return web.json_response(record['response'])

    # --- lifecycle --------------------------------------------------------
    def start(self):
        ready = threading.Event()

        def run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            app = web.Application(client_max_size=50 * 1024 ** 2)
            app.router.add_route('*', '/{tail:.*}', self._handle)
            self._runner = web.AppRunner(app)
            self._loop.run_until_complete(self._runner.setup())
            site = web.TCPSite(self._runner, '127.0.0.1', 0)
            self._loop.run_until_complete(site.start())
            self.url = f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
            ready.set()
            self._loop.run_forever()

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        assert ready.wait(10), 'fake Orangebeard server did not start'
        return self

    def stop(self):
        asyncio.run_coroutine_threadsafe(self._runner.cleanup(), self._loop).result(10)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(5)

    # --- helpers ----------------------------------------------------------
    def of(self, *parts: str):
        """Requests whose path contains the given text, e.g. of('/test-run/start')."""
        return [r for r in self.requests if all(part in r['path'] for part in parts)]

    def index_of(self, record) -> int:
        return self.requests.index(record)

    def attachments_by_test(self):
        """Test name -> sorted descriptions of the attachments (every attachment gets a log entry saying so)."""
        names = {r['response']: r['body']['testName'] for r in self.of('/test/start')}
        found = {name: [] for name in names.values()}
        for request in self.of('/log'):
            entries = request['body'] if isinstance(request['body'], list) else [request['body']]
            for entry in entries:
                if entry['message'].startswith('Attachment: '):
                    found[names[entry['testUUID']]].append(entry['message'].removeprefix('Attachment: '))
        return {name: sorted(files) for name, files in found.items()}
