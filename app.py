"""Loopback-only operations dashboard and authenticated JSON API."""

import argparse
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import sys

MAX_BODY = 1024 * 1024
MAX_CSV = 512 * 1024
STATIC = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
ROUTES = {'/api/state', '/api/import', '/api/refresh', '/api/maintenance', '/api/automations'}


def require_token(token):
    if not isinstance(token, str) or len(token) < 32 or not re.fullmatch(r'[!-~]+', token):
        raise ValueError('OPERATIONS_API_TOKEN must contain at least 32 printable ASCII characters without spaces')
    return token


def strict_json(raw):
    def reject_constant(value):
        raise ValueError('Invalid JSON constant')

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON field')
            result[key] = value
        return result

    return json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique_object)


def make_server(engine, token, folder, port=0):
    token = require_token(token)
    folder = Path(folder)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)
            self.body_read = False

        def log_message(self, format, *args):
            pass

        def send_error(self, code, message=None, explain=None):
            self.respond(code, {'error': 'Invalid HTTP request'})

        def respond(self, status, value=None, content=None, mime='application/json'):
            lengths = self.headers.get_all('Content-Length', []) if hasattr(self, 'headers') else []
            if (not self.body_read and len(lengths) == 1 and re.fullmatch(r'[0-9]{1,12}', lengths[0])
                    and int(lengths[0]) <= MAX_BODY and self.headers.get('Transfer-Encoding') is None):
                # Drain bounded rejected bodies to preserve error responses on Windows.
                self.body_read = True
                try:
                    self.rfile.read(int(lengths[0]))
                except OSError:
                    pass
            raw = content if content is not None else json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
            self.send_response(status)
            if status != 204:
                self.send_header('Content-Type', mime + '; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.send_header('Connection', 'close')
            self.end_headers()
            self.close_connection = True
            if self.command != 'HEAD':
                self.wfile.write(raw)

        def handle_route(self):
            hosts = self.headers.get_all('Host', [])
            port = self.server.server_port
            if len(hosts) != 1 or hosts[0] not in (f'127.0.0.1:{port}', f'localhost:{port}'):
                self.respond(403, {'error': 'Invalid Host'})
                return
            origins = self.headers.get_all('Origin', [])
            if origins and (len(origins) != 1 or origins[0] != 'http://' + hosts[0]):
                self.respond(403, {'error': 'Invalid Origin'})
                return
            if self.path == '/favicon.ico':
                if self.command in ('GET', 'HEAD'):
                    self.respond(204, content=b'')
                else:
                    self.respond(405, {'error': 'Method not allowed'})
                return
            if self.path in STATIC:
                if self.command not in ('GET', 'HEAD'):
                    self.respond(405, {'error': 'Method not allowed'})
                    return
                file_name, mime = STATIC[self.path]
                try:
                    raw = (Path(__file__).parent / 'static' / file_name).read_bytes()
                except OSError:
                    self.respond(404, {'error': 'Asset unavailable'})
                    return
                self.respond(200, content=raw, mime=mime)
                return
            auth = self.headers.get_all('Authorization', [])
            if len(auth) != 1 or not hmac.compare_digest(auth[0].encode(), ('Bearer ' + token).encode()):
                self.respond(401, {'error': 'Unauthorized'})
                return
            if self.path not in ROUTES:
                self.respond(404, {'error': 'Unknown route'})
                return
            expected = 'GET' if self.path == '/api/state' else 'POST'
            if self.command != expected:
                self.respond(405, {'error': 'Method not allowed'})
                return
            try:
                if self.command == 'GET':
                    if self.headers.get('Transfer-Encoding') is not None or self.headers.get_all('Content-Length', []) not in ([], ['0']):
                        raise ValueError('State request must not have a body')
                    result = engine.snapshot()
                else:
                    if self.headers.get('Transfer-Encoding') is not None:
                        self.respond(400, {'error': 'Transfer encoding is unsupported'})
                        return
                    lengths = self.headers.get_all('Content-Length', [])
                    if not lengths:
                        self.respond(411, {'error': 'Content-Length required'})
                        return
                    if len(lengths) != 1 or not re.fullmatch(r'[0-9]{1,12}', lengths[0]):
                        raise ValueError('Invalid Content-Length')
                    length = int(lengths[0])
                    if length > MAX_BODY:
                        self.respond(413, {'error': 'JSON body exceeds 1 MiB'})
                        return
                    types = self.headers.get_all('Content-Type', [])
                    if len(types) != 1 or types[0].split(';')[0].strip().lower() != 'application/json':
                        self.respond(415, {'error': 'Content-Type must be application/json'})
                        return
                    self.body_read = True
                    raw = self.rfile.read(length)
                    if len(raw) != length:
                        raise ValueError('Incomplete body')
                    body = strict_json(raw.decode('utf-8'))
                    if not isinstance(body, dict):
                        raise ValueError('JSON body must be an object')
                    result = self.execute(body)
                    if result is None:
                        return
                self.respond(200, result)
            except TimeoutError:
                self.respond(408, {'error': 'Request body timeout'})
            except (ValueError, UnicodeError, RecursionError):
                self.respond(400, {'error': 'Invalid request'})
            except Exception:
                self.respond(500, {'error': 'Internal server error'})

        def execute(self, body):
            allowed, required = {
                '/api/import': ({'kind', 'csv_text'}, {'kind', 'csv_text'}),
                '/api/refresh': (set(), set()),
                '/api/automations': (set(), set()),
                '/api/maintenance': ({'record_id', 'property', 'summary', 'priority', 'owner', 'due_at', 'reported_by'},
                                     {'record_id', 'property', 'summary', 'priority', 'due_at', 'reported_by'})
            }[self.path]
            if not required <= body.keys() or body.keys() - allowed:
                raise ValueError('Unexpected or missing fields')
            if self.path == '/api/import':
                if not isinstance(body['kind'], str) or body['kind'] not in ('maintenance', 'leasing', 'finance') or not isinstance(body['csv_text'], str):
                    raise ValueError('Invalid import fields')
                if len(body['csv_text'].encode('utf-8')) > MAX_CSV:
                    self.respond(413, {'error': 'CSV exceeds 512 KiB'})
                    return None
                return engine.import_csv(body['kind'], body['csv_text'])
            if self.path == '/api/refresh':
                return engine.refresh(folder)
            if self.path == '/api/maintenance':
                try:
                    return engine.create_request(body)
                except UnicodeError:
                    raise
                except ValueError as exc:
                    message = ''.join(char for char in str(exc) if char.isprintable())[:300]
                    self.respond(400, {'error': message or 'Invalid request'})
                    return None
            return engine.run_automations()

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = handle_route

    # ponytail: serialized local requests; leased jobs before multi-worker throughput.
    return HTTPServer(('127.0.0.1', port), Handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('serve', 'refresh', 'automations', 'state'):
        command = commands.add_parser(name)
        command.add_argument('--db', type=Path, default=Path(__file__).parent / 'output' / 'operations.sqlite')
        command.add_argument('--files', type=Path, default=Path(__file__).parent / 'samples')
        if name == 'serve':
            command.add_argument('--port', type=int, default=8766)
    args = parser.parse_args(argv)
    try:
        from engine import Engine
        token = require_token(os.environ.get('OPERATIONS_API_TOKEN', '')) if args.command == 'serve' else None
        engine = Engine(args.db)
        if args.command == 'serve':
            with make_server(engine, token, args.files, args.port) as server:
                print(f'Operations dashboard listening on http://127.0.0.1:{server.server_port}', flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
        else:
            result = engine.refresh(args.files) if args.command == 'refresh' else engine.run_automations() if args.command == 'automations' else engine.snapshot()
            print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except (OSError, ValueError, UnicodeError, RecursionError):
        print('Check token configuration, input folder, database path, and port.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
