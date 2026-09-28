#!/usr/bin/env python3
"""Loopback contract tests. Every server is a child owned by this runner."""
import argparse
import contextlib
import os
from pathlib import Path
import socket
import ssl
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]

@contextlib.contextmanager
def server(name, tls=False, command_prefix=()):
    env = dict(os.environ)
    env.pop('BENCH_TLS', None)
    args = [str(ROOT / 'build' / (name + '-server'))]
    if tls:
        if name == 'uws': env['BENCH_TLS'] = '1'
        else: args.append('--tls')
    # Fail on an already occupied port; never benchmark a foreign process.
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(('127.0.0.1', 18080))
    with open(ROOT / 'build' / (name + '-server.log'), 'w') as log:
        process = subprocess.Popen([*command_prefix, *args], cwd=ROOT, env=env, stdout=log, stderr=log)
        try:
            for _ in range(1000):
                if process.poll() is not None: raise RuntimeError(f'{name} exited: {process.returncode}; see log')
                try:
                    with socket.create_connection(('127.0.0.1', 18080), .1): pass
                    break
                except OSError: time.sleep(.03)
            else: raise RuntimeError('server did not listen')
            yield process
        finally:
            if process.poll() is None: process.terminate()
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired: process.kill(); process.wait()

def connect(tls=False):
    conn = socket.create_connection(('127.0.0.1', 18080), 3)
    conn.settimeout(4)
    if tls:
        context = ssl.create_default_context(cafile=str(ROOT / 'build/cert.pem'))
        context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_3
        conn = context.wrap_socket(conn, server_hostname='localhost')
        assert conn.cipher()[0] == 'TLS_AES_128_GCM_SHA256'
    return conn

def request(body=b'', extra=b'', path=b'/echo'):
    return b'POST ' + path + b' HTTP/1.1\r\nHost: localhost\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n' + extra + b'\r\n' + body

def response(stream, expected, status=200):
    line = stream.readline()
    assert line.startswith(f'HTTP/1.1 {status} '.encode()), line
    headers = {}
    for _ in range(64):
        line = stream.readline()
        if line == b'\r\n': break
        assert line and b':' in line, line
        key, value = line.split(b':', 1)
        headers[key.lower()] = value.strip()
    else: raise AssertionError('too many headers')
    assert int(headers[b'content-length']) == len(expected), headers
    actual = stream.read(len(expected))
    assert actual == expected, f'echo mismatch: got {len(actual)} expected {len(expected)}, first mismatch {next((i for i, (a,b) in enumerate(zip(actual, expected)) if a != b), None)}'
    assert headers[b'content-type'] == b'application/octet-stream'
    assert len(headers[b'date']) == 29


def chunked_checks(tls):
    head = b'POST /echo HTTP/1.1\r\nHost: localhost\r\nTransfer-Encoding: chunked\r\n\r\n'
    wire = head + b'3\r\nabc\r\nA\r\n0123456789\r\n0\r\nX-Checksum: ignored\r\n\r\n'
    # Every split point, including chunk size, data CRLF and trailer terminator.
    for at in range(1, len(wire)):
        with connect(tls) as conn, conn.makefile('rb') as stream:
            conn.sendall(wire[:at]); time.sleep(.001); conn.sendall(wire[at:])
            response(stream, b'abc0123456789')
    with connect(tls) as conn, conn.makefile('rb') as stream:
        conn.sendall(wire + request(b'next') + head + b'0\r\n\r\n' + request(b'last'))
        for body in [b'abc0123456789', b'next', b'', b'last']: response(stream, body)
    with connect(tls) as conn, conn.makefile('rb') as stream:
        body = bytes(i % 251 for i in range(65536))
        conn.sendall(head + b'10000\r\n' + body + b'\r\n0\r\n\r\n' + request(b'after-max'))
        response(stream, body); response(stream, b'after-max')
    with connect(tls) as conn, conn.makefile('rb') as stream:
        conn.sendall(head + b'1\r\nx\r\n' * 5000 + b'0\r\n\r\n')
        response(stream, b'x' * 5000)
    invalid = [
        head + b'10001\r\n', head + b'-1\r\n', head + b'0x1\r\n',
        head + b'1;foo=bar\r\nx\r\n0\r\n\r\n',  # explicit subset rejection
        head + b'1\r\nxXX', head + b'\r\n', head + b'1 \r\n',
        head + b'FFFFFFFFFFFFFFFF\r\n', head + b'x' * 1026,
        head + b'0\r\nContent-Length: 0\r\n\r\n',
        head + b'0\r\nHost: evil\r\n\r\n',
        head + b'0\r\n X-Checksum: x\r\n\r\n',
        head + b'0\r\nX-Checksum: a\x00b\r\n\r\n',
        head + b'0\r\n' + b'X-Checksum: x\r\n' * 65 + b'\r\n',
        head + b'0\r\n' + (b'X-Checksum: ' + b'x' * 1000 + b'\r\n') * 9 + b'\r\n',
        head + b'10000\r\n' + b'x' * 65536 + b'\r\n1\r\nx\r\n0\r\n\r\n',
        head + b'1\r\nx\r\n' * 13000 + b'0\r\n\r\n',  # encoded size bound
        head.replace(b'Transfer-Encoding: chunked', b'Content-Length: 0\r\nTransfer-Encoding: chunked'),
        head.replace(b'Transfer-Encoding: chunked', b'Transfer-Encoding: chunked\r\nContent-Length: 0'),
        head.replace(b'Transfer-Encoding: chunked', b'Transfer-Encoding: chunked\r\nTransfer-Encoding: chunked'),
        head.replace(b'Transfer-Encoding: chunked', b'Transfer-Encoding: gzip, chunked'),
    ]
    for wire in invalid:
        with connect(tls) as conn:
            try:
                conn.sendall(wire)
                assert conn.recv(1) == b'', wire[:150]
            except (ConnectionResetError, BrokenPipeError, ssl.SSLEOFError): pass

def check(name, tls):
    with server(name, tls):
        if name == 'zen':
            command = [str(ROOT / 'build/client-test')] + (['--tls'] if tls else [])
            env = dict(os.environ)
            env.pop('SSL_CERT_FILE', None)
            env.pop('SSL_CERT_DIR', None)
            if tls:
                subprocess.run(command + ['--reject'], cwd=ROOT, env=env, check=True, timeout=30)
                env['SSL_CERT_FILE'] = str(ROOT / 'build/cert.pem')
            subprocess.run(command, cwd=ROOT, env=env, check=True, timeout=30)
        for size in [0, 1, 32, 64, 256, 512, 16384, 65536]:
            body = bytes(i % 251 for i in range(size))
            with connect(tls) as conn, conn.makefile('rb') as stream:
                conn.sendall(request(body)); response(stream, body)
                conn.sendall(request(body)); response(stream, body)
        payload = request(b'fragmented')
        for at in range(1, len(payload)):
            with connect(tls) as conn, conn.makefile('rb') as stream:
                conn.sendall(payload[:at]); time.sleep(.001); conn.sendall(payload[at:])
                response(stream, b'fragmented')
        with connect(tls) as conn, conn.makefile('rb') as stream:
            bodies = [bytes([i]) * (i * 37) for i in range(32)]
            conn.sendall(b''.join(request(body) for body in bodies))
            for body in bodies: response(stream, body)
        with connect(tls) as conn, conn.makefile('rb') as stream:
            conn.sendall(request(b'closing', b'Connection: close\r\n'))
            response(stream, b'closing')
            assert stream.read(1) == b''
        # Slow reader with enough pipelined responses to exercise backpressure.
        with connect(tls) as conn, conn.makefile('rb') as stream:
            # CPython SSLSocket does not promise concurrent read/write safety.
            # Queue a bounded batch sequentially, then delay draining responses.
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024 * 1024)
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 16384)
            for _ in range(4): conn.sendall(request(b'x' * 65536))
            time.sleep(.1)
            for _ in range(4): response(stream, b'x' * 65536)
        if name.startswith('zen'):
            chunked_checks(tls)
            # More than one scheduler budget, all input sent before any reading.
            # A lost userspace wakeup strands the tail (including TLS pending data).
            with connect(tls) as conn, conn.makefile('rb') as stream:
                bodies = [str(i).encode() for i in range(256)]
                partial = request(b'after-yield')
                conn.sendall(b''.join(request(body) for body in bodies) + partial[:-3])
                for body in bodies: response(stream, body)
                conn.sendall(partial[-3:]); response(stream, b'after-yield')
            # A queued connection must not block a second independently usable peer.
            with connect(tls) as busy, busy.makefile('rb') as queued:
                busy.sendall(request(b'queued') * 256)
                with connect(tls) as probe, probe.makefile('rb') as stream:
                    probe.sendall(request(b'probe')); response(stream, b'probe')
                for _ in range(256): response(queued, b'queued')
            # Legal token punctuation and interior horizontal tabs remain accepted.
            with connect(tls) as conn, conn.makefile('rb') as stream:
                conn.sendall(request(b'tokens', b"X_!#$%&'*+-.^`|~: a\tb\r\n"))
                response(stream, b'tokens')
                conn.sendall(request(b'limit', b'X: y\r\n' * 62))
                response(stream, b'limit')
                # Header byte limit includes the final CRLF, exactly 8192 passes.
                base = request(b'boundary', b'X: \r\n')
                header_len = len(base) - len(b'boundary')
                conn.sendall(request(b'boundary', b'X: ' + b'x' * (8192 - header_len) + b'\r\n'))
                response(stream, b'boundary')
            invalid_requests = [
                b'POST /echo HTTP/1.1\r\nContent-Length: 0\r\n\r\n',
                b'POST /echo HTTP/1.1\r\nHost: a b\r\n\r\n',
                b'POST /echo HTTP/1.1\r\nHost: a,b\r\n\r\n',
                b'POST /echo HTTP/1.1\r\nHost: user@host\r\n\r\n',
                request(extra=b'X: y\r\n' * 63),  # Host + length + 63 > 64
            ]
            for wire in invalid_requests:
                with connect(tls) as conn:
                    conn.sendall(wire)
                    try: assert conn.recv(1) == b''
                    except ConnectionResetError: pass
            with connect(tls) as conn, conn.makefile('rb') as stream:
                conn.sendall(request(path=b'/missing')); response(stream, b'not found', 404)
            bad_headers = [b'Content-Length: -1', b'Content-Length: 65537', b'Content-Length: 999999999999999999999',
                           b'Content-Length: 1\r\nContent-Length: 1', b'Transfer-Encoding: gzip',
                           b'Content-Length: 1x', b' Content-Length: 1', b'Expect: 100-continue',
                           b'Host: duplicate\r\nContent-Length: 0', b'X: a\x00b',
                           b'Content-Length: 0, 0', b'Content-Length: +1',
                           b'X : bad', b'X: a\x7fb']
            for header in bad_headers:
                with connect(tls) as conn:
                    conn.sendall(b'POST /echo HTTP/1.1\r\nHost: localhost\r\n' + header + b'\r\n\r\n')
                    try: assert conn.recv(1) == b''
                    except ConnectionResetError: pass
            with connect(tls) as conn:
                conn.sendall(b'POST /echo HTTP/1.1\r\nX: ' + b'x' * 8192)
                try: assert conn.recv(1) == b''
                except ConnectionResetError: pass
    print(f'PASS {name} {"TLS" if tls else "HTTP"}: echo, fragmentation, pipelining, close, slow reader' + (', rejection' if name.startswith('zen') else ''), flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--server', default='both', choices=['both', 'zen', 'uws', 'zen-sanitized', 'zen-debug'])
    args = parser.parse_args()
    # Demonstrate that payload and framing validation reject a bad peer.
    import io
    try: response(io.BytesIO(b'HTTP/1.1 200 OK\r\nContent-Length: 1\r\n\r\ny'), b'x')
    except AssertionError: pass
    else: raise AssertionError('negative control passed unexpectedly')
    for name in (['zen', 'uws'] if args.server == 'both' else [args.server]):
        for tls in [False, True]: check(name, tls)
