import http.client
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest

from app import make_server

TOKEN = 'local-test-token-' + 'x' * 32


class EngineFixture:
    def snapshot(self):
        return {'metrics': {'open_requests': 2}}

    def import_csv(self, kind, csv_text):
        if csv_text == '__raise__':
            raise RuntimeError('private engine detail')
        return {'status': 'rejected', 'error': 'row 2 invalid', 'kind': kind}

    def refresh(self, folder):
        return {'folder': str(folder), 'sources': [{'status': 'rejected', 'error': 'missing file'}]}

    def create_request(self, payload):
        if payload['summary'] == '__raise__':
            raise RuntimeError('private engine detail')
        return {'status': 'accepted', 'record_id': payload['record_id']}

    def run_automations(self):
        return {'recorded': 1}


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.gettempdir()) / 'operations-api-test-files'
        self.server = make_server(EngineFixture(), TOKEN, self.folder)
        self.assertIsNotNone(self.server, 'loopback HTTP server must be implemented')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port

    def tearDown(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join()

    def request(self, path='/api/state', method='GET', body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        defaults = {'Authorization': 'Bearer ' + TOKEN}
        if body is not None:
            defaults['Content-Type'] = 'application/json'
            if isinstance(body, dict):
                body = json.dumps(body)
        defaults.update(headers or {})
        connection.request(method, path, body, defaults)
        response = connection.getresponse()
        raw = response.read()
        status, response_headers = response.status, dict(response.getheaders())
        connection.close()
        return status, raw, response_headers

    def raw_request(self, headers, body=b'', path='/api/automations'):
        with socket.create_connection(('127.0.0.1', self.port), timeout=5) as connection:
            connection.sendall((f'POST {path} HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nAuthorization: Bearer {TOKEN}\r\n' + headers + '\r\n').encode() + body)
            connection.shutdown(socket.SHUT_WR)
            data = b''
            while chunk := connection.recv(65536):
                data += chunk
        return int(data.split(b' ', 2)[1])

    def test_auth_hosts_and_origins(self):
        self.assertEqual(self.request()[0], 200)
        self.assertEqual(self.request(headers={'Authorization': ''})[0], 401)
        self.assertEqual(self.request(headers={'Authorization': 'Bearer wrong'})[0], 401)
        for host in ('evil.example', f'evil.example:{self.port}', f'127.0.0.1:{self.port + 1}'):
            self.assertEqual(self.request(headers={'Host': host})[0], 403)
        for origin in ('null', 'https://evil.example', f'http://localhost:{self.port}', f'http://127.0.0.1:{self.port}/'):
            self.assertEqual(self.request(headers={'Origin': origin})[0], 403)
        self.assertEqual(self.request(headers={'Origin': f'http://127.0.0.1:{self.port}'})[0], 200)
        self.assertEqual(self.request(headers={'Host': f'localhost:{self.port}', 'Origin': f'http://localhost:{self.port}'})[0], 200)

    def test_routes_and_fields(self):
        self.assertEqual(self.request('/api/state', 'POST', {})[0], 405)
        self.assertEqual(self.request('/api/automations', 'GET')[0], 405)
        self.assertEqual(self.request('/api/unknown')[0], 404)
        self.assertEqual(self.request('/api/automations', 'POST', {'extra': True})[0], 400)
        self.assertEqual(self.request('/api/import', 'POST', {'kind': 'maintenance'})[0], 400)
        self.assertEqual(self.request('/api/import', 'POST', {'kind': 'bad', 'csv_text': 'x'})[0], 400)
        self.assertEqual(self.request('/api/import', 'POST', {'kind': 'maintenance', 'csv_text': 7})[0], 400)
        self.assertEqual(self.request('/api/maintenance', 'POST', {})[0], 400)
        payload = dict(record_id='TEST-1', property='A', summary='Leak', priority='normal', due_at='2026-10-15T00:00:00Z', reported_by='Tester')
        status, raw, _ = self.request('/api/maintenance', 'POST', payload)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)['record_id'], 'TEST-1')
        status, raw, _ = self.request('/api/maintenance', 'POST', {**payload, 'summary': '__raise__'})
        self.assertEqual(status, 500)
        self.assertNotIn(b'private engine detail', raw)

    def test_source_results_and_configured_folder(self):
        status, raw, _ = self.request('/api/import', 'POST', {'kind': 'maintenance', 'csv_text': 'invalid'})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)['error'], 'row 2 invalid')
        status, raw, _ = self.request('/api/refresh', 'POST', {})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)['folder'], str(self.folder))
        self.assertEqual(self.request('/api/refresh', 'POST', {'folder': '../private'})[0], 400)
        self.assertEqual(self.request('/api/automations', 'POST', {})[0], 200)
        status, raw, _ = self.request('/api/import', 'POST', {'kind': 'maintenance', 'csv_text': '__raise__'})
        self.assertEqual(status, 500)
        self.assertNotIn(b'private engine detail', raw)

    def test_strict_json_and_body_limits(self):
        for body in ('{"x":1,"x":2}', '{"x":NaN}', '[]', '{', '{"x":Infinity}'):
            self.assertEqual(self.request('/api/automations', 'POST', body)[0], 400)
        self.assertEqual(self.request('/api/automations', 'POST', b'\xff')[0], 400)
        self.assertEqual(self.request('/api/automations', 'POST', '{}', {'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.request('/api/import', 'POST', {'kind': 'finance', 'csv_text': 'x' * (512 * 1024 + 1)})[0], 413)
        self.assertEqual(self.raw_request(f'Content-Length: {1024 * 1024 + 1}\r\nContent-Type: application/json\r\n'), 413)

    def test_http_framing(self):
        self.assertEqual(self.raw_request('Content-Type: application/json\r\n'), 411)
        self.assertEqual(self.raw_request('Content-Length: 2\r\nContent-Length: 2\r\nContent-Type: application/json\r\n', b'{}'), 400)
        self.assertEqual(self.raw_request('Content-Length: -1\r\nContent-Type: application/json\r\n'), 400)
        self.assertEqual(self.raw_request('Transfer-Encoding: chunked\r\nContent-Type: application/json\r\n', b'0\r\n\r\n'), 400)
        self.assertEqual(self.raw_request('Content-Length: 9\r\nContent-Type: application/json\r\n', b'{}'), 400)
        self.assertEqual(self.raw_request('Content-Length: 2\r\nContent-Type: application/json\r\nContent-Type: application/json\r\n', b'{}'), 415)

    def test_static_paths_are_fixed_public_assets(self):
        for route, file_name in (('/', 'index.html'), ('/app.js', 'app.js'), ('/style.css', 'style.css')):
            status, raw, headers = self.request(route, headers={'Authorization': ''})
            if (Path(__file__).parent / 'static' / file_name).exists():
                self.assertEqual(status, 200)
                self.assertTrue(raw)
                self.assertNotIn(TOKEN.encode(), raw)
                self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
            else:
                self.assertEqual(status, 404)
        for route in ('/engine.py', '/.env', '/../engine.py', '/static/../engine.py', '/%2e%2e/engine.py', '/app.js?file=.env'):
            self.assertEqual(self.request(route)[0], 404)

    def test_favicon_is_public_empty_and_protected_by_host_origin(self):
        for method in ('GET', 'HEAD'):
            status, raw, headers = self.request('/favicon.ico', method, headers={'Authorization': ''})
            self.assertEqual(status, 204)
            self.assertEqual(raw, b'')
            self.assertNotIn('Content-Type', headers)
        self.assertEqual(self.request('/favicon.ico', headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.request('/favicon.ico', headers={'Origin': 'https://evil.example'})[0], 403)

    def test_token_validation(self):
        for token in ('short', 'x' * 31, 'x' * 32 + '\n', 'x' * 32 + 'é', None):
            with self.assertRaises(ValueError):
                make_server(EngineFixture(), token, self.folder)

    def test_real_engine_import_refresh_and_retained_records(self):
        from engine import Engine
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(Path(directory) / 'test.sqlite')
            self.server.shutdown()
            self.server.server_close()
            self.thread.join()
            self.server = make_server(engine, TOKEN, Path(__file__).parent / 'samples')
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            self.port = self.server.server_port
            status, raw, _ = self.request('/api/refresh', 'POST', {})
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(raw)['status'], 'accepted')
            before = json.loads(self.request()[1])
            self.assertTrue(before['maintenance'])
            status, raw, _ = self.request('/api/import', 'POST', {'kind': 'maintenance', 'csv_text': 'bad'})
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(raw)['status'], 'rejected')
            after = json.loads(self.request()[1])
            self.assertEqual(after['maintenance'], before['maintenance'])
            self.assertTrue(after['failures'])

    def test_maintenance_conflict_is_actionable_but_parse_errors_stay_generic(self):
        from engine import Engine
        with tempfile.TemporaryDirectory() as directory:
            engine = Engine(Path(directory) / 'test.sqlite')
            self.server.shutdown()
            self.server.server_close()
            self.thread.join()
            self.server = make_server(engine, TOKEN, self.folder)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            self.port = self.server.server_port
            payload = dict(record_id='INTAKE-1', property='A', summary='Leak', priority='normal', due_at='2026-10-15T00:00:00Z', reported_by='Tester')
            self.assertEqual(self.request('/api/maintenance', 'POST', payload)[0], 200)
            status, raw, _ = self.request('/api/maintenance', 'POST', {**payload, 'summary': 'Different issue'})
            self.assertEqual(status, 400)
            self.assertIn('versioned CSV', json.loads(raw)['error'])
            self.assertLessEqual(len(json.loads(raw)['error']), 300)
            status, raw, _ = self.request('/api/maintenance', 'POST', {**payload, 'priority': 'invalid'})
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(raw)['error'], 'priority: expected normal, urgent')
            for body in ('{', '{"priority":NaN}', '{"record_id":1,"record_id":2}'):
                status, raw, _ = self.request('/api/maintenance', 'POST', body)
                self.assertEqual(status, 400)
                self.assertEqual(json.loads(raw)['error'], 'Invalid request')
            status, raw, _ = self.request('/api/maintenance', 'POST', {**payload, 'record_id': 'INTAKE-2', 'summary': '\ud800'})
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(raw)['error'], 'Invalid request')
            self.assertEqual(self.raw_request('Content-Length: 2\r\nContent-Length: 2\r\nContent-Type: application/json\r\n', b'{}', '/api/maintenance'), 400)


class WorkflowTests(unittest.TestCase):
    def test_inactive_graphs_credentials_and_forwarding_expressions(self):
        root = Path(__file__).parent
        self.assertTrue((root / 'n8n-maintenance.json').exists(), 'maintenance workflow required')
        intake = json.loads((root / 'n8n-maintenance.json').read_text())
        refresh = json.loads((root / 'n8n-refresh.json').read_text())
        for workflow in (intake, refresh):
            self.assertFalse(workflow['active'])
            self.assertEqual(workflow['settings']['timezone'], 'Asia/Manila')
            nodes = workflow['nodes']
            self.assertEqual(len({n['id'] for n in nodes}), len(nodes))
            self.assertFalse(any(n.get('credentials') for n in nodes))
            names = {n['name'] for n in nodes}
            for source, channels in workflow['connections'].items():
                self.assertIn(source, names)
                for output in channels['main']:
                    for edge in output:
                        self.assertIn(edge['node'], names)
            for node in nodes:
                if node['type'] == 'n8n-nodes-base.httpRequest':
                    self.assertEqual(node['parameters']['authentication'], 'genericCredentialType')
                    self.assertEqual(node['parameters']['genericAuthType'], 'httpHeaderAuth')
                    self.assertTrue(node['parameters']['url'].startswith('http://127.0.0.1:8766/api/'))
        webhook, forward, response = [next(n for n in intake['nodes'] if n['name'] == name) for name in ('Maintenance intake', 'Create request', 'Return API result')]
        self.assertEqual(webhook['parameters']['authentication'], 'headerAuth')
        self.assertEqual(webhook['parameters']['responseMode'], 'responseNode')
        for workflow, chain in ((intake, ('Maintenance intake', 'Create request', 'Return API result')),
                                (refresh, ('Hourly Manila schedule', 'Refresh configured CSV files', 'Require all sources accepted', 'Record reminders and daily summary'))):
            self.assertEqual(set(workflow['connections']), set(chain[:-1]))
            for source, target in zip(chain, chain[1:]):
                self.assertEqual(workflow['connections'][source], {'main': [[{'node': target, 'type': 'main', 'index': 0}]]})
        schedule = next(n for n in refresh['nodes'] if n['type'] == 'n8n-nodes-base.scheduleTrigger')
        self.assertEqual(schedule['parameters']['rule']['interval'], [{'field': 'hours', 'hoursInterval': 1, 'triggerAtMinute': 5}])
        requests = [n for n in refresh['nodes'] if n['type'] == 'n8n-nodes-base.httpRequest']
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(n['parameters']['options']['response']['response']['neverError'] is False for n in requests))
        fixture = {'body': {'record_id': 'TEST-1', 'summary': 'Leak "quoted"', 'owner': 'Team'}}
        expressions = [forward['parameters']['jsonBody'], response['parameters']['responseBody'], response['parameters']['options']['responseCode']]
        gate = next(n for n in refresh['nodes'] if n['type'] == 'n8n-nodes-base.code')['parameters']['jsCode']
        script = '''const expressions = JSON.parse(process.argv[1]);
const fixture = JSON.parse(process.argv[2]);
function evaluate(expression, $json) {return Function('$json', 'return (' + expression.slice(3, -2).trim() + ')')($json);}
if (JSON.parse(evaluate(expressions[0], fixture)).summary !== fixture.body.summary) throw Error('forward');
for (const statusCode of [200, 400, 401, 500]) {
  const input = {statusCode, body:{error:'fixture'}};
  if (evaluate(expressions[2], input) !== statusCode || JSON.parse(evaluate(expressions[1], input)).error !== 'fixture') throw Error('response');
}
const gate = Function('$json', '$input', JSON.parse(process.argv[3]));
const accepted = {status:'accepted',sources:[1,2,3].map(() => ({status:'accepted'}))};
if (gate(accepted,{all:()=>[{json:accepted}]}).length !== 1) throw Error('gate success');
for (const input of [{status:'partial',sources:accepted.sources},{status:'accepted',sources:[]},{status:'accepted',sources:[{status:'rejected'},{status:'accepted'},{status:'accepted'}]}]) {
  let rejected = false; try {gate(input,{all:()=>[{json:input}]});} catch {rejected=true;} if(!rejected) throw Error('gate rejection');
}'''
        result = subprocess.run(['node', '-e', script, json.dumps(expressions), json.dumps(fixture), json.dumps(gate)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
