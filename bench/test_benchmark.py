"""Offline harness contract tests; no sockets or server processes."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import run
import report


def result():
    return dict(tls=False, connections=1, body=64, requests=100,
                elapsed_s=2., rps=50., p50_us=10., p95_us=20., p99_us=30.)


def document():
    rows = []
    for trial in range(2):
        for name in ('zen', 'uws'):
            rows.append(dict(result(), server=name, trial=trial, status='ok'))
    return dict(schema_version=2, status='complete',
                config=dict(trials=2, tls=[False], connections=[1], sizes=[64]), rows=rows)


class BenchmarkTests(unittest.TestCase):
    def test_bad_arguments(self):
        for args in (['--seconds', 'nan'], ['--seconds', 'inf'], ['--trials', '0'],
                     ['--sizes', '-1'], ['--connections', '201'], ['--sizes', '1', '1']):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                run.arguments(args)

    def test_affinity_contract(self):
        with mock.patch.object(run.os, 'sched_getaffinity', return_value={0,1,2}, create=True):
            args=run.arguments(['--server-cpu','0','--client-cpus','1','2'])
            self.assertEqual(args.client_cpus,[1,2])
            for extra in (['--server-cpu','0'],['--server-cpu','0','--client-cpus','0'],['--server-cpu','3','--client-cpus','1'],['--server-cpu','0','--client-cpus','1','1']):
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    run.arguments(extra)

    def test_linux_resource_accounting(self):
        fields=['S']+['0']*10+['120','30']
        with mock.patch.object(run.sys,'platform','linux'), mock.patch.object(run.Path,'read_text',side_effect=['42 (name with ) spaces) '+ ' '.join(fields), 'Name: server\nVmHWM: 8192 kB\n']), mock.patch.object(run.os,'sysconf',return_value=100), mock.patch.object(run.os,'sched_getaffinity',return_value={2},create=True):
            self.assertEqual(run.linux_process_stats(42), {'cpu_s_including_startup_warmup':1.5,'peak_rss_kib_including_startup_warmup':8192,'observed_cpu_affinity':[2]})
        data=document()
        for row in data['rows']:
            row['server_resources']={'cpu_s_including_startup_warmup':1.5,'peak_rss_kib_including_startup_warmup':8192}
        self.assertIn('1.500 | 8,192',report.render(data))
        data['rows'][0]['status']='failed'
        self.assertNotIn('1.500 | 8,192',report.render(data))

    def test_invalid_metrics(self):
        expected = dict(result(), seconds=2)
        run.validate_result(result(), expected)
        for key, value in [('rps', float('nan')), ('requests', 0), ('rps', 51),
                           ('p50_us', 99), ('tls', 0), ('elapsed_s', .1)]:
            data = dict(result(), **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                run.validate_result(data, expected)

    def test_complete_and_paired_ratio(self):
        data = document()
        data['rows'][0]['rps'] = 100
        data['rows'][2]['rps'] = 300
        data['rows'][3]['rps'] = 100
        text = report.render(data)
        self.assertIn('2.500 [2.000–3.000]', text)
        self.assertIn('2/2', text)

    def test_incomplete_suppresses_comparison(self):
        for mode in ('missing', 'failed', 'interrupted'):
            data = document()
            if mode == 'missing': data['rows'].pop()
            else: data['rows'][-1]['status'] = mode
            text = report.render(data)
            self.assertIn('INCOMPLETE: no comparison', text)
            self.assertNotIn('1.000 [', text)

    def test_entire_missing_cell_visible(self):
        data = document()
        data['config']['sizes'].append(512)
        self.assertIn('| 512 | 0/2 |', report.render(data))

    def test_duplicates_rejected(self):
        data = document()
        data['rows'].append(copy.copy(data['rows'][0]))
        with self.assertRaises(ValueError): report.render(data)

    def test_failed_and_interrupted_runs_saved(self):
        for failure in (RuntimeError('cannot start'), KeyboardInterrupt()):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'build').mkdir()
                for name in ('zen-server', 'uws-server', 'load'):
                    (root / 'build' / name).write_bytes(b'test executable')
                with mock.patch.object(run, 'ROOT', root), mock.patch.object(run, 'server', side_effect=failure), contextlib.redirect_stdout(io.StringIO()):
                    args = ['--trials', '1', '--sizes', '64', '--connections', '1']
                    if isinstance(failure, KeyboardInterrupt):
                        with self.assertRaises(KeyboardInterrupt): run.main(args)
                    else:
                        self.assertEqual(run.main(args), 1)
                saved = json.loads((root / 'build/results.json').read_text())
                self.assertIn(saved['status'], ('failed', 'interrupted'))
                self.assertTrue(saved['rows'])
                self.assertTrue(all(r['status'] != 'ok' for r in saved['rows']))
                self.assertIn('INCOMPLETE', report.render(saved))
                # Existing evidence cannot be overwritten.
                with mock.patch.object(run, 'ROOT', root), self.assertRaises(FileExistsError):
                    run.main(args)

    def test_legacy_caveat(self):
        self.assertIn('no planned workload manifest', report.render(document()['rows']))


if __name__ == '__main__':
    unittest.main()
