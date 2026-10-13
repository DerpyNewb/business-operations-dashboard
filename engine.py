from contextlib import contextmanager
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import io
import json
from pathlib import Path
import re
import sqlite3


KINDS = ('maintenance', 'leasing', 'finance')
COMMON = ['record_id', 'property', 'version', 'updated_at', 'updated_by']
FIELDS = {'maintenance': COMMON + ['summary', 'priority', 'status', 'owner', 'due_at'],
          'leasing': COMMON + ['applicant', 'stage', 'monthly_rent_php', 'owner'],
          'finance': COMMON + ['period', 'category', 'amount_php', 'status']}
OPEN = ('open', 'in_progress')
MANILA = timezone(timedelta(hours=8), 'Asia/Manila')
MAX_CSV = 512 * 1024


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def text(value, field, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or '\x00' in value:
        raise ValueError(f'{field}: supply nonempty text of at most {limit} characters')
    return value.strip()


def identifier(value):
    value = text(value, 'record_id', 100)
    if not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError('record_id: use ASCII letters, digits, underscore, or hyphen')
    return value


def iso(value, field):
    value = text(value, field, 50)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or 'T' not in value:
            raise ValueError()
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError):
        raise ValueError(f'{field}: supply an ISO timestamp with timezone') from None


def choice(value, field, options):
    if value not in options:
        raise ValueError(f'{field}: expected {", ".join(options)}')
    return value


def money(value, field):
    value = text(value, field, 30)
    if not re.fullmatch(r'\d+(?:\.\d{1,2})?', value, flags=re.ASCII):
        raise ValueError(f'{field}: use a nonnegative plain decimal with at most two decimal places')
    amount = Decimal(value)
    if amount > Decimal('1000000000'):
        raise ValueError(f'{field}: amount exceeds the supported small-business limit')
    return int(amount * 100)


class Engine:
    def __init__(self, db_path, clock=None):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        with self.database() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS records (
                    kind TEXT NOT NULL, record_id TEXT NOT NULL, data TEXT NOT NULL,
                    PRIMARY KEY(kind,record_id));
                CREATE TABLE IF NOT EXISTS sources (
                    kind TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'never',
                    last_success_at TEXT, last_attempt_at TEXT, error TEXT);
                CREATE TABLE IF NOT EXISTS failures (
                    id INTEGER PRIMARY KEY, kind TEXT, attempted_at TEXT, error TEXT);
                CREATE TABLE IF NOT EXISTS notifications (id TEXT PRIMARY KEY, data TEXT NOT NULL);
            ''')
            db.executemany('INSERT OR IGNORE INTO sources(kind) VALUES (?)', [(k,) for k in KINDS])

    @contextmanager
    def database(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def current(self):
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ValueError('clock must return an aware datetime')
        return value.astimezone(timezone.utc)

    def row(self, kind, raw, current):
        value = {k: text(raw.get(k), k) for k in ('property', 'updated_by')}
        value['record_id'] = identifier(raw.get('record_id'))
        version = text(raw.get('version'), 'version', 10)
        if not re.fullmatch(r'[1-9][0-9]*', version):
            raise ValueError('version: supply a positive integer')
        value['version'] = int(version)
        value['updated_at'] = iso(raw.get('updated_at'), 'updated_at')
        if datetime.fromisoformat(value['updated_at']) > current:
            raise ValueError('updated_at: future timestamps are not accepted')
        if kind == 'maintenance':
            value.update(summary=text(raw.get('summary'), 'summary', 2000),
                         priority=choice(raw.get('priority'), 'priority', ('normal', 'urgent')),
                         status=choice(raw.get('status'), 'status', OPEN + ('completed', 'cancelled')),
                         owner=text(raw.get('owner'), 'owner'), due_at=iso(raw.get('due_at'), 'due_at'))
        elif kind == 'leasing':
            value.update(applicant=text(raw.get('applicant'), 'applicant'),
                         stage=choice(raw.get('stage'), 'stage', ('inquiry', 'viewing', 'application', 'leased', 'lost')),
                         owner=text(raw.get('owner'), 'owner'),
                         monthly_rent_cents=money(raw.get('monthly_rent_php'), 'monthly_rent_php'))
        else:
            period = text(raw.get('period'), 'period', 7)
            if not re.fullmatch(r'[0-9]{4}-(?:0[1-9]|1[0-2])', period) or period.startswith('0000'):
                raise ValueError('period: use a valid YYYY-MM value')
            value.update(period=period, category=choice(raw.get('category'), 'category', ('income', 'expense')),
                         amount_cents=money(raw.get('amount_php'), 'amount_php'),
                         status=choice(raw.get('status'), 'status', ('posted', 'void')))
        return value

    def parse_csv(self, kind, raw, current):
        if not isinstance(raw, str) or len(raw.encode('utf-8')) > MAX_CSV:
            raise ValueError('CSV must be UTF-8 text no larger than 512 KiB')
        reader = csv.DictReader(io.StringIO(raw.lstrip('\ufeff'), newline=''), strict=True)
        values, ids = [], set()
        try:
            if not reader.fieldnames or len(reader.fieldnames) != len(FIELDS[kind]) or set(reader.fieldnames) != set(FIELDS[kind]):
                raise ValueError('CSV headers must match the source template exactly without duplicates')
            for number, raw_row in enumerate(reader, 2):
                if number > 1001:
                    raise ValueError('CSV exceeds 1,000 records')
                if None in raw_row or any(v is None for v in raw_row.values()):
                    raise ValueError(f'row {number}: column count does not match headers')
                try:
                    value = self.row(kind, raw_row, current)
                except ValueError as exc:
                    raise ValueError(f'row {number}: {exc}') from None
                if value['record_id'] in ids:
                    raise ValueError(f'row {number}: duplicate record_id {value["record_id"]}')
                ids.add(value['record_id'])
                values.append(value)
        except csv.Error:
            raise ValueError('Malformed CSV quoting; export a valid UTF-8 CSV') from None
        if not values:
            raise ValueError('CSV contains no records; an empty export does not clear stored data')
        return values

    def reject(self, kind, error, current):
        error = str(error)[:500]
        stamp = current.isoformat()
        with self.database() as db:
            db.execute("UPDATE sources SET status='rejected',last_attempt_at=?,error=? WHERE kind=?", (stamp, error, kind))
            db.execute('INSERT INTO failures(kind,attempted_at,error) VALUES(?,?,?)', (kind, stamp, error))
        return {'kind': kind, 'status': 'rejected', 'changed': 0, 'error': error}

    def import_csv(self, kind, csv_text):
        if kind not in KINDS:
            raise ValueError('unknown source kind')
        current = self.current()
        try:
            values = self.parse_csv(kind, csv_text, current)
            with self.database() as db:
                db.execute('BEGIN IMMEDIATE')
                changed = 0
                for value in values:
                    row = db.execute('SELECT data FROM records WHERE kind=? AND record_id=?', (kind, value['record_id'])).fetchone()
                    if row:
                        old = json.loads(row['data'])
                        if old == value:
                            continue
                        if value['version'] != old['version'] + 1:
                            raise ValueError(f'{value["record_id"]}: version conflict; stored version is {old["version"]}, submit its next revision')
                        if value['updated_at'] < old['updated_at']:
                            raise ValueError(f'{value["record_id"]}: updated_at cannot move backward')
                    elif value['version'] != 1:
                        raise ValueError(f'{value["record_id"]}: new records must start at version 1')
                    db.execute('INSERT INTO records VALUES(?,?,?) ON CONFLICT(kind,record_id) DO UPDATE SET data=excluded.data',
                               (kind, value['record_id'], encode(value)))
                    changed += 1
                stamp = current.isoformat()
                db.execute("UPDATE sources SET status='accepted',last_success_at=?,last_attempt_at=?,error=NULL WHERE kind=?", (stamp, stamp, kind))
            return {'kind': kind, 'status': 'accepted', 'changed': changed, 'unchanged': len(values) - changed}
        except (ValueError, UnicodeError) as exc:
            return self.reject(kind, exc, current)

    def refresh(self, folder):
        results = []
        for kind in KINDS:
            try:
                with (Path(folder) / f'{kind}.csv').open('rb') as source:
                    raw = source.read(MAX_CSV + 1)
                if len(raw) > MAX_CSV:
                    raise ValueError('CSV exceeds 512 KiB')
                results.append(self.import_csv(kind, raw.decode('utf-8-sig')))
            except (OSError, UnicodeError, ValueError):
                results.append(self.reject(kind, f'{kind}.csv is missing, unreadable, oversized, or not UTF-8', self.current()))
        accepted = sum(r['status'] == 'accepted' for r in results)
        return {'status': 'accepted' if accepted == 3 else 'partial' if accepted else 'rejected', 'sources': results}

    def create_request(self, payload):
        if not isinstance(payload, dict):
            raise ValueError('request must be an object')
        allowed = {'record_id', 'property', 'summary', 'priority', 'owner', 'due_at', 'reported_by'}
        if payload.keys() - allowed:
            raise ValueError('unexpected request fields')
        current = self.current()
        owner = payload.get('owner')
        if owner is None or owner == '':
            owner = 'Duty manager' if payload.get('priority') == 'urgent' else 'Maintenance team'
        raw = {**payload, 'owner': owner, 'version': '1', 'status': 'open',
               'updated_at': current.isoformat(), 'updated_by': payload.get('reported_by')}
        value = self.row('maintenance', raw, current)
        with self.database() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute("SELECT data FROM records WHERE kind='maintenance' AND record_id=?", (value['record_id'],)).fetchone()
            if existing:
                old = json.loads(existing['data'])
                fields = ('property', 'summary', 'priority', 'owner', 'due_at', 'updated_by')
                if not all(old[k] == value[k] for k in fields):
                    raise ValueError('record_id already exists with different request details; update through a versioned CSV')
                return {'status': 'duplicate', 'record_id': value['record_id']}
            db.execute("INSERT INTO records VALUES('maintenance',?,?)", (value['record_id'], encode(value)))
        return {'status': 'created', 'record_id': value['record_id'], 'owner': value['owner']}

    def state(self, db, current):
        records = {kind: [] for kind in KINDS}
        for row in db.execute('SELECT kind,data FROM records ORDER BY record_id'):
            records[row['kind']].append(json.loads(row['data']))
        tasks = [{**row, 'urgent_review': row['priority'] == 'urgent' and row['status'] in OPEN,
                  'overdue': row['status'] in OPEN and datetime.fromisoformat(row['due_at']) < current}
                 for row in records['maintenance']]
        posted = [r for r in records['finance'] if r['status'] == 'posted']
        income = sum(r['amount_cents'] for r in posted if r['category'] == 'income')
        expense = sum(r['amount_cents'] for r in posted if r['category'] == 'expense')
        metrics = {'open_requests': sum(t['status'] in OPEN for t in tasks),
                   'urgent_requests': sum(t['urgent_review'] for t in tasks),
                   'overdue_tasks': sum(t['overdue'] for t in tasks),
                   'active_leasing': sum(r['stage'] not in ('leased', 'lost') for r in records['leasing']),
                   'income_cents': income, 'expense_cents': expense, 'net_cents': income - expense}
        sources = []
        for row in db.execute('SELECT * FROM sources ORDER BY kind'):
            source = dict(row)
            source['record_count'] = len(records[source['kind']])
            source['stale'] = not source['last_success_at'] or current - datetime.fromisoformat(source['last_success_at']) > timedelta(hours=24)
            sources.append(source)
        return {'generated_at': current.isoformat(), 'timezone': 'Asia/Manila', 'metrics': metrics,
                **records, 'tasks': tasks, 'sources': sources,
                'notifications': [json.loads(r['data']) for r in db.execute('SELECT data FROM notifications ORDER BY rowid DESC')],
                'failures': [dict(r) for r in db.execute('SELECT * FROM failures ORDER BY id DESC LIMIT 100')]}

    def snapshot(self):
        with self.database() as db:
            db.execute('BEGIN')
            return self.state(db, self.current())

    def run_automations(self):
        current, created = self.current(), 0
        day = current.astimezone(MANILA).date().isoformat()
        with self.database() as db:
            db.execute('BEGIN IMMEDIATE')
            state = self.state(db, current)
            entries = []
            for task in state['tasks']:
                if task['overdue']:
                    entries.append({'id': f'overdue:{task["record_id"]}:{task["owner"]}:{day}',
                                    'kind': 'overdue_reminder', 'created_at': current.isoformat(),
                                    'record_id': task['record_id'], 'owner': task['owner'], 'status': 'recorded',
                                    'message': f'{task["record_id"]}: {task["summary"]} is overdue. Owner: {task["owner"]}.'})
            metrics = state['metrics']
            entries.append({'id': f'summary:{day}', 'kind': 'daily_summary', 'created_at': current.isoformat(),
                            'record_id': None, 'owner': 'Operations manager', 'status': 'recorded',
                            'message': f'{day}: {metrics["open_requests"]} open requests, {metrics["urgent_requests"]} urgent, {metrics["overdue_tasks"]} overdue, {metrics["active_leasing"]} active leasing records.',
                            'metrics': metrics})
            for entry in entries:
                result = db.execute('INSERT OR IGNORE INTO notifications VALUES(?,?)', (entry['id'], encode(entry)))
                created += result.rowcount
        return {'created': created, 'delivery': 'local_log', 'day': day}
