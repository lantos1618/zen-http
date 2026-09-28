#!/usr/bin/env python3
"""Report every planned cell; never compare unpaired or failed subsets."""
import argparse
import json
import math
from pathlib import Path
import statistics


def render(document):
    legacy = isinstance(document, list)
    rows = document if legacy else document['rows']
    if legacy:
        cells = sorted({(r['tls'], r['connections'], r['body']) for r in rows})
        # Historical format had no manifest. Require contiguous global trial IDs,
        # but it cannot establish whether an entire workload was omitted.
        count = max((r['trial'] for r in rows), default=-1) + 1
    else:
        if document.get('schema_version') != 2:
            raise ValueError('unsupported result schema')
        config = document['config']
        count = config['trials']
        cells = [(tls, c, size) for tls in config['tls'] for c in config['connections'] for size in config['sizes']]
    if type(count) is not int or count < 1 or not cells:
        raise ValueError('no planned trials')
    indexed = {}
    for row in rows:
        cell = (row['tls'], row['connections'], row['body'])
        if cell not in cells or row['server'] not in ('zen', 'uws') or type(row['trial']) is not int or not 0 <= row['trial'] < count:
            raise ValueError('unexpected workload, server, or trial')
        key = (*cell, row['trial'], row['server'])
        if key in indexed:
            raise ValueError(f'duplicate trial: {key}')
        indexed[key] = row
    lines = ['Throughput and p99 values are medians across trials. Brackets show trial minima–maxima, not confidence intervals. Ratios are medians of paired Zen/uWS throughput ratios.', '']
    if legacy:
        lines += ['Legacy input has no planned workload manifest; entirely missing cells cannot be detected.', '']
    else:
        lines += [f'Run status: {document.get("status", "unknown")}. Planned paired trials per cell: {count}.', '']
    lines += ['| Protocol | Connections | Body bytes | Valid pairs / planned | Zen req/s [min–max] | uWS req/s [min–max] | Paired Zen/uWS [min–max] | Zen p99 µs | uWS p99 µs | Status |',
              '|---|---:|---:|---:|---|---|---|---:|---:|---|']
    for cell in cells:
        tls, connections, size = cell
        valid = []
        issues = []
        for trial in range(count):
            pair = [indexed.get((*cell, trial, name)) for name in ('zen', 'uws')]
            if any(r is None or r.get('status', 'ok') != 'ok' for r in pair):
                issues.append('missing, failed, or interrupted trials')
                continue
            for row in pair:
                if type(row.get('requests')) is not int or row['requests'] <= 0:
                    raise ValueError('invalid request count')
                for field in ('rps', 'p99_us'):
                    value = row.get(field)
                    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                        raise ValueError(f'invalid {field}')
            valid.append(pair)
        prefix = f'| {"TLS 1.3" if tls else "HTTP"} | {connections} | {size:,} | {len(valid)}/{count} |'
        if issues:
            lines.append(prefix + ' — | — | — | — | — | INCOMPLETE: no comparison |')
            continue
        rates = [[pair[i]['rps'] for pair in valid] for i in (0, 1)]
        tails = [statistics.median(pair[i]['p99_us'] for pair in valid) for i in (0, 1)]
        ratios = [pair[0]['rps'] / pair[1]['rps'] for pair in valid]
        def spread(values, decimals):
            return f'{statistics.median(values):,.{decimals}f} [{min(values):,.{decimals}f}–{max(values):,.{decimals}f}]'
        lines.append(prefix + f' {spread(rates[0], 0)} | {spread(rates[1], 0)} | {spread(ratios, 3)} | {tails[0]:.1f} | {tails[1]:.1f} | complete |')
    lines += ['', 'These closed-loop measurements include client overhead and use one outstanding request per connection. They do not measure open-loop tail latency, server CPU/RSS, or handshake throughput.']
    return '\n'.join(lines) + '\n'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('results', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.write_text(render(json.loads(args.results.read_text())))


if __name__ == '__main__':
    main()
