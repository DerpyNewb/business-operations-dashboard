import argparse
import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import shutil
import tempfile

from engine import Engine


def csv_text(rows):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def run_demo():
    root = Path(__file__).parent
    reference_time = datetime(2026, 10, 13, 2, tzinfo=timezone.utc)
    steps = []
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory) / 'files'
        shutil.copytree(root / 'samples', folder)
        engine = Engine(Path(directory) / 'operations.sqlite', clock=lambda: reference_time)
        initial = engine.refresh(folder)
        assert initial['status'] == 'accepted'
        assert engine.snapshot()['metrics']['net_cents'] == 7150000
        replay = engine.refresh(folder)
        assert all(source['changed'] == 0 for source in replay['sources'])
        steps.append({'step': 'department refresh and identical replay', 'refresh': initial, 'replay': replay})

        request = {'record_id': 'MNT-DEMO', 'property': 'Fictional Unit 7',
                   'summary': 'Inspect entrance gate latch', 'priority': 'urgent',
                   'due_at': '2026-10-12T12:00:00+08:00', 'reported_by': 'Demo colleague'}
        created = engine.create_request(request)
        assert created['owner'] == 'Duty manager'
        assert engine.create_request(request)['status'] == 'duplicate'
        first = engine.run_automations()
        repeated = engine.run_automations()
        assert first['created'] == 3 and repeated['created'] == 0
        steps.append({'step': 'assigned urgent request and repeat-safe automation', 'request': created,
                      'first_run': first, 'repeated_run': repeated})

        with (folder / 'maintenance.csv').open(newline='') as file:
            rows = list(csv.DictReader(file))
        rows[0].update(version='2', updated_at='2026-10-13T01:00:00Z',
                       updated_by='Demo supervisor', status='completed')
        good = csv_text(rows)
        (folder / 'maintenance.csv').write_text(good, encoding='utf-8')
        revised = engine.refresh(folder)
        assert revised['status'] == 'accepted'
        assert engine.snapshot()['tasks'][0]['status'] == 'completed'
        assert engine.snapshot()['metrics']['overdue_tasks'] == 1
        steps.append({'step': 'staff revision updates dashboard task', 'refresh': revised})

        rows[1]['priority'] = 'invalid'
        (folder / 'maintenance.csv').write_text(csv_text(rows), encoding='utf-8')
        rejected = engine.refresh(folder)
        assert rejected['status'] == 'partial'
        assert engine.snapshot()['maintenance'][0]['status'] == 'completed'
        rows[1]['priority'] = 'normal'
        rows[0]['summary'] = 'Conflicting edit at the same version'
        conflict = engine.import_csv('maintenance', csv_text(rows))
        assert conflict['status'] == 'rejected'
        assert engine.snapshot()['maintenance'][0]['summary'] == 'Kitchen pipe leak'
        steps.append({'step': 'invalid and conflicting updates retain valid data', 'refresh': rejected, 'conflict': conflict})

        recovered = engine.import_csv('maintenance', good)
        assert recovered['status'] == 'accepted' and recovered['changed'] == 0
        state = engine.snapshot()
        assert len(state['tasks']) == 4 and len(state['notifications']) == 3
        assert state['metrics']['net_cents'] == 7150000
        steps.append({'step': 'corrected file clears source rejection', 'import': recovered})
        return {'mode': 'offline_reference', 'fictional_data': True,
                'reference_time': reference_time.isoformat(), 'external_messages_sent': 0,
                'steps': steps, 'state': state}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run the asserted fictional operations walkthrough.')
    parser.add_argument('--output', type=Path, default=Path(__file__).parent / 'output/demo-run.json')
    args = parser.parse_args()
    report = run_demo()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('Offline demo passed: three CSV sources, exact totals, assigned intake, staff revision,')
    print('repeat-safe reminders, invalid/conflicting refresh retention, and recovery.')
    print('External messages sent: 0. Evidence:', args.output)
