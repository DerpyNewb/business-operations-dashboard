import csv
from datetime import datetime, timedelta, timezone
import io
from pathlib import Path
import tempfile
import unittest

from engine import Engine


ROOT = Path(__file__).parent
NOW = datetime(2026, 10, 13, 2, tzinfo=timezone.utc)


def rows(kind):
    return list(csv.DictReader((ROOT / 'samples' / f'{kind}.csv').read_text().splitlines()))


def export(data):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=list(data[0]))
    writer.writeheader()
    writer.writerows(data)
    return output.getvalue()


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.current = NOW
        self.path = Path(self.temp.name) / 'operations.sqlite'
        self.engine = Engine(self.path, clock=lambda: self.current)

    def load(self, kind='maintenance'):
        result = self.engine.import_csv(kind, export(rows(kind)))
        self.assertEqual(result['status'], 'accepted')
        return result

    def request(self, **patch):
        return {'record_id': 'MNT-NEW', 'property': 'Fictional Unit 7',
                'summary': 'Broken window latch', 'priority': 'urgent',
                'due_at': '2026-10-12T09:00:00Z', 'reported_by': 'Demo colleague', **patch}

    def test_import_aggregates_exact_money_and_derives_assigned_tasks(self):
        for kind in ('maintenance', 'leasing', 'finance'):
            self.load(kind)
        state = self.engine.snapshot()
        self.assertEqual(state['metrics'], {'open_requests': 2, 'urgent_requests': 1,
            'overdue_tasks': 1, 'active_leasing': 2, 'income_cents': 8000000,
            'expense_cents': 850000, 'net_cents': 7150000})
        self.assertEqual(len(state['tasks']), 3)
        self.assertEqual(state['tasks'][0]['owner'], 'Duty manager')
        self.assertTrue(state['tasks'][0]['urgent_review'])

    def test_identical_import_is_noop_and_bom_is_supported(self):
        self.load()
        result = self.engine.import_csv('maintenance', '\ufeff' + export(rows('maintenance')))
        self.assertEqual(result['changed'], 0)
        self.assertEqual(len(self.engine.snapshot()['maintenance']), 3)

    def test_new_revision_changes_task_and_does_not_delete_missing_records(self):
        self.load()
        revised = rows('maintenance')[0]
        revised.update(version='2', status='completed', updated_at='2026-10-13T01:00:00Z', updated_by='Demo supervisor')
        self.assertEqual(self.engine.import_csv('maintenance', export([revised]))['changed'], 1)
        state = self.engine.snapshot()
        self.assertEqual(len(state['maintenance']), 3)
        self.assertEqual(state['tasks'][0]['status'], 'completed')
        self.assertEqual(state['metrics']['overdue_tasks'], 0)

    def test_one_invalid_row_preserves_entire_source_and_reports_rejection(self):
        self.load()
        revised = rows('maintenance')
        revised[0].update(version='2', summary='Would otherwise change', updated_at='2026-10-13T01:00:00Z')
        revised[1]['priority'] = 'maybe'
        self.assertEqual(self.engine.import_csv('maintenance', export(revised))['status'], 'rejected')
        state = self.engine.snapshot()
        self.assertEqual(state['maintenance'][0]['summary'], 'Kitchen pipe leak')
        source = next(s for s in state['sources'] if s['kind'] == 'maintenance')
        self.assertEqual(source['status'], 'rejected')
        self.assertIsNotNone(source['last_success_at'])
        self.assertIn('priority', source['error'])

    def test_conflicting_skipped_and_stale_versions_reject_atomically(self):
        self.load()
        for patch in [{'summary': 'Same version conflict'}, {'version': '3'},
                      {'version': '0'}, {'version': '2', 'updated_at': '2026-10-11T00:00:00Z'}]:
            data = rows('maintenance')
            data[0].update(patch)
            self.assertEqual(self.engine.import_csv('maintenance', export(data))['status'], 'rejected')
        revision = rows('maintenance')[0]
        revision.update(version='2', updated_at='2026-10-13T01:00:00Z')
        self.assertEqual(self.engine.import_csv('maintenance', export([revision]))['status'], 'accepted')
        self.assertEqual(self.engine.import_csv('maintenance', export(rows('maintenance')))['status'], 'rejected')

    def test_rejects_duplicate_ids_headers_empty_files_and_large_sources(self):
        data = rows('maintenance')
        cases = [export([data[0], data[0]]), 'record_id,record_id\nA,B\n',
                 (ROOT / 'templates/maintenance.csv').read_text(), '', 'x' * (512 * 1024 + 1)]
        for raw in cases:
            self.assertEqual(self.engine.import_csv('maintenance', raw)['status'], 'rejected')
        self.assertEqual(self.engine.snapshot()['maintenance'], [])

    def test_rejects_invalid_money_dates_and_timestamps(self):
        for field, value in [('amount_php', 'NaN'), ('amount_php', '1.001'),
                             ('amount_php', '-1'), ('amount_php', '1e3'),
                             ('period', '2026-13'), ('version', '2'),
                             ('updated_at', '2099-01-01T00:00:00Z'),
                             ('updated_at', '2026-10-12')]:
            data = rows('finance')
            data[0][field] = value
            self.assertEqual(self.engine.import_csv('finance', export(data))['status'], 'rejected')

    def test_finance_small_decimal_sums_do_not_use_binary_floats(self):
        data = rows('finance')[:2]
        data[0]['amount_php'], data[1]['amount_php'] = '0.10', '0.20'
        self.assertEqual(self.engine.import_csv('finance', export(data))['status'], 'accepted')
        self.assertEqual(self.engine.snapshot()['metrics']['income_cents'], 30)

    def test_refresh_sources_independently_and_retains_failed_source(self):
        self.load('finance')
        folder = Path(self.temp.name) / 'files'
        folder.mkdir()
        (folder / 'maintenance.csv').write_text(export(rows('maintenance')))
        (folder / 'finance.csv').write_text('invalid')
        result = self.engine.refresh(folder)
        self.assertEqual(result['status'], 'partial')
        state = self.engine.snapshot()
        self.assertEqual(len(state['maintenance']), 3)
        self.assertEqual(state['metrics']['income_cents'], 8000000)
        self.assertEqual(len(state['failures']), 2)

    def test_intake_default_assignment_replay_and_conflict(self):
        first = self.engine.create_request(self.request())
        self.assertEqual(first['status'], 'created')
        self.assertEqual(self.engine.create_request(self.request())['status'], 'duplicate')
        with self.assertRaises(ValueError):
            self.engine.create_request(self.request(summary='Different request'))
        self.engine.create_request(self.request(record_id='MNT-NORMAL', priority='normal'))
        state = self.engine.snapshot()
        owners = {t['record_id']: t['owner'] for t in state['tasks']}
        self.assertEqual(owners, {'MNT-NEW': 'Duty manager', 'MNT-NORMAL': 'Maintenance team'})

    def test_notifications_are_daily_idempotent_and_use_manila_day(self):
        self.load()
        self.assertEqual(self.engine.run_automations()['created'], 2)
        self.assertEqual(self.engine.run_automations()['created'], 0)
        self.current = datetime(2026, 10, 13, 16, 1, tzinfo=timezone.utc)
        self.assertEqual(self.engine.run_automations()['created'], 2)
        state = self.engine.snapshot()
        self.assertEqual(len(state['notifications']), 4)
        self.assertTrue(any('2026-10-14' in n['id'] for n in state['notifications']))

    def test_completed_tasks_never_get_new_reminders_and_source_becomes_stale(self):
        self.load()
        data = rows('maintenance')
        data[0].update(version='2', status='completed', updated_at='2026-10-13T01:00:00Z')
        self.engine.import_csv('maintenance', export(data))
        self.engine.run_automations()
        self.assertEqual([n['kind'] for n in self.engine.snapshot()['notifications']], ['daily_summary'])
        self.current += timedelta(days=2)
        self.assertTrue(next(s for s in self.engine.snapshot()['sources'] if s['kind'] == 'maintenance')['stale'])
        restarted = Engine(self.path, clock=lambda: self.current)
        self.assertEqual(len(restarted.snapshot()['maintenance']), 3)

    def test_malformed_csv_header_cannot_abort_other_source_refreshes(self):
        folder = Path(self.temp.name) / 'malformed'
        folder.mkdir()
        for kind in ('maintenance', 'leasing', 'finance'):
            (folder / f'{kind}.csv').write_text(export(rows(kind)))
        (folder / 'maintenance.csv').write_text('"unterminated header')
        self.assertEqual(self.engine.refresh(folder)['status'], 'partial')
        state = self.engine.snapshot()
        self.assertEqual(len(state['leasing']), 3)
        self.assertEqual(state['metrics']['income_cents'], 8000000)
        self.assertEqual(len(state['failures']), 1)

    def test_timestamp_utc_overflow_is_rejected_as_bad_input(self):
        data = rows('maintenance')
        data[0]['due_at'] = '0001-01-01T00:00:00+08:00'
        self.assertEqual(self.engine.import_csv('maintenance', export(data))['status'], 'rejected')
        self.assertEqual(self.engine.snapshot()['maintenance'], [])


if __name__ == '__main__':
    unittest.main()
