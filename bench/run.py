#!/usr/bin/env python3
"""Alternate paired trials; checkpoint successes, failures, and unfinished work."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from check import server


def arguments(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--trials', type=int, default=3)
    p.add_argument('--seconds', type=float, default=2)
    p.add_argument('--sizes', type=int, nargs='+', default=[32, 64, 256, 512, 16384])
    p.add_argument('--connections', type=int, nargs='+', default=[1, 32])
    p.add_argument('--output', default='build/results.json')
    p.add_argument('--server-cpu', type=int)
    p.add_argument('--client-cpus', type=int, nargs='+')
    args = p.parse_args(argv)
    if not 1 <= args.trials <= 1000:
        p.error('trials must be between 1 and 1000')
    if not math.isfinite(args.seconds) or not 0 < args.seconds <= 3600:
        p.error('seconds must be finite, positive, and at most 3600')
    if any(not 0 <= n <= 65536 for n in args.sizes):
        p.error('sizes must be between 0 and 65536')
    if any(not 1 <= n <= 200 for n in args.connections):
        p.error('connections must be between 1 and 200')
    if len(set(args.sizes)) != len(args.sizes) or len(set(args.connections)) != len(args.connections):
        p.error('duplicate sizes or connections would duplicate trial identifiers')
    if (args.server_cpu is None) != (args.client_cpus is None):
        p.error('supply both server-cpu and client-cpus')
    if args.server_cpu is not None:
        if not hasattr(os, 'sched_getaffinity'):
            p.error('CPU placement requires Linux sched_getaffinity and taskset')
        allowed = os.sched_getaffinity(0)
        if args.server_cpu not in allowed or any(cpu not in allowed for cpu in args.client_cpus):
            p.error('requested CPU is outside the allowed affinity set')
        if args.server_cpu in args.client_cpus or len(set(args.client_cpus)) != len(args.client_cpus):
            p.error('server and client CPUs must be distinct and client CPUs unique')
    return args


def checkpoint(path, document):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(document, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def validate_result(data, expected):
    if not isinstance(data, dict):
        raise ValueError('client result must be an object')
    for key in ('tls', 'connections', 'body'):
        if type(data.get(key)) is not type(expected[key]) or data[key] != expected[key]:
            raise ValueError(f'client {key} differs from requested workload')
    if type(data.get('requests')) is not int or data['requests'] <= 0:
        raise ValueError('client must report positive completed requests')
    for key in ('elapsed_s', 'rps', 'p50_us', 'p95_us', 'p99_us'):
        value = data.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'invalid client metric: {key}')
    if not data['p50_us'] <= data['p95_us'] <= data['p99_us']:
        raise ValueError('client quantiles are unordered')
    if not math.isclose(data['requests'] / data['elapsed_s'], data['rps'], rel_tol=1e-6):
        raise ValueError('client throughput does not match count / elapsed')
    if data['elapsed_s'] < expected['seconds'] * .95:
        raise ValueError('client measurement ended too early')


def linux_process_stats(pid):
    """Cumulative server CPU and lifetime peak RSS, including startup/warmup."""
    if sys.platform != 'linux':
        return None
    stat = Path(f'/proc/{pid}/stat').read_text()
    # comm can contain spaces or parentheses; fields after its final ')' start at3.
    fields = stat[stat.rfind(')') + 2:].split()
    ticks = int(fields[11]) + int(fields[12])
    status = Path(f'/proc/{pid}/status').read_text().splitlines()
    peak = next(int(line.split()[1]) for line in status if line.startswith('VmHWM:'))
    return {'cpu_s_including_startup_warmup': ticks / os.sysconf('SC_CLK_TCK'),
            'peak_rss_kib_including_startup_warmup': peak,
            'observed_cpu_affinity': sorted(os.sched_getaffinity(pid))}


def main(argv=None):
    args = arguments(argv)
    path = ROOT / args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    # Refuse accidental destruction of earlier evidence, including interrupted runs.
    with path.open('x') as output:
        output.write('{}\n')
    document = {
        'schema_version': 2, 'status': 'running',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'environment': {'platform': platform.platform(), 'machine': platform.machine(),
                        'python': platform.python_version()},
        'config': {'trials': args.trials, 'seconds': args.seconds,
                   'sizes': args.sizes, 'connections': args.connections, 'tls': [False, True],
                   'server_cpu': args.server_cpu, 'client_cpus': args.client_cpus},
        'binaries_sha256': {}, 'rows': [],
    }
    checkpoint(path, document)
    try:
        for name in ('zen-server', 'uws-server', 'load'):
            document['binaries_sha256'][name] = hashlib.sha256((ROOT / 'build' / name).read_bytes()).hexdigest()
        checkpoint(path, document)
        for encrypted in [False, True]:
            for connections in args.connections:
                for size in args.sizes:
                    for trial in range(args.trials):
                        order = ['zen', 'uws'] if trial % 2 == 0 else ['uws', 'zen']
                        for position, name in enumerate(order):
                            row = dict(server=name, tls=encrypted, connections=connections,
                                       body=size, trial=trial, seconds=args.seconds,
                                       order=position, status='running')
                            document['rows'].append(row)
                            checkpoint(path, document)
                            command = [str(ROOT / 'build/load'), '-body', str(size),
                                       '-connections', str(connections), '-seconds', str(args.seconds)]
                            if encrypted:
                                command += ['-tls']
                            server_prefix = []
                            if args.server_cpu is not None:
                                server_prefix = ['taskset', '-c', str(args.server_cpu)]
                                command = ['taskset', '-c', ','.join(map(str,args.client_cpus)), *command]
                            log = ROOT / 'build' / (name + '-server.log')
                            previous_log = log.stat() if log.exists() else None
                            try:
                                with server(name, encrypted, command_prefix=server_prefix) as process:
                                    result = subprocess.run(command, cwd=ROOT, capture_output=True,
                                                            text=True, timeout=args.seconds + 20)
                                    row.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
                                    if result.returncode:
                                        raise RuntimeError(f'load client exited {result.returncode}')
                                    data = json.loads(result.stdout)
                                    validate_result(data, row)
                                    if process.poll() is not None:
                                        raise RuntimeError('server exited during trial')
                                    stats = linux_process_stats(process.pid)
                                    if stats is not None:
                                        row['server_resources'] = stats
                                        if args.server_cpu is not None and stats['observed_cpu_affinity'] != [args.server_cpu]:
                                            raise RuntimeError('server affinity changed during trial')
                                # Only accept metrics after both client validation and server cleanup.
                                row.update({k: data[k] for k in ('requests', 'elapsed_s', 'rps', 'p50_us', 'p95_us', 'p99_us')})
                                if 'client_cpu_s_including_warmup' in data:
                                    row['client_cpu_s_including_warmup'] = data['client_cpu_s_including_warmup']
                                row['status'] = 'ok'
                            except Exception as exc:
                                row.update(status='failed', error=f'{type(exc).__name__}: {exc}')
                                if isinstance(exc, subprocess.TimeoutExpired):
                                    row['stdout'] = (exc.stdout or b'').decode(errors='replace') if isinstance(exc.stdout, bytes) else (exc.stdout or '')
                                    row['stderr'] = (exc.stderr or b'').decode(errors='replace') if isinstance(exc.stderr, bytes) else (exc.stderr or '')
                            finally:
                                if log.exists() and log.stat() != previous_log:
                                    row['server_log'] = log.read_text(errors='replace')
                                checkpoint(path, document)
                            print(f'{name} tls={encrypted} c={connections} body={size} trial={trial}: {row["status"]}', flush=True)
        document['status'] = 'complete' if all(r['status'] == 'ok' for r in document['rows']) else 'failed'
    except BaseException as exc:
        document.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
                        error=f'{type(exc).__name__}: {exc}')
        for row in document['rows']:
            if row['status'] == 'running':
                row['status'] = 'interrupted'
        raise
    finally:
        checkpoint(path, document)
    print(f'Saved {path}; status={document["status"]}. Use bench/report.py to report complete cells.')
    return 0 if document['status'] == 'complete' else 1


if __name__ == '__main__':
    sys.exit(main())
