#!/usr/bin/env python3
"""Native TLS HTTP client: shared framing, authenticated records, no OpenSSL link."""
import ast
import hashlib
import hmac
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
ROOT = Path(__file__).resolve().parents[1]
CRYPTO = Path(os.environ.get('ZEN_CRYPTO', ROOT.parent / 'zen-crypto')).resolve()
ZEN = Path(os.environ.get('ZEN_COMPILER', ROOT.parent / 'zen-crypto-numeric/zen')).resolve()
STD = Path(os.environ.get('ZEN_STD', ROOT.parent / 'zen-crypto-numeric/src')).resolve()
WORK = ROOT / 'build/native-http-check'
STAGE = WORK / 'source'
(STAGE / 'http').mkdir(parents=True, exist_ok=True)
for name in ['response_types', 'response_decode', 'client_request', 'native_client']:
    (STAGE / 'http' / (name + '.zen')).write_text((ROOT / 'src/http' / (name + '.zen')).read_text())
for path in CRYPTO.joinpath('src').glob('*.zen'):
    (STAGE / path.name).write_text(path.read_text())
assert not (STAGE / 'tls.zen').exists()
# Reuse test-only independent TLS peer operations without executing its suite.
helper = ast.parse((CRYPTO / 'scripts/check-tls13-session.py').read_text())
names = {'extract', 'label', 'finished', 'hs', 'plain', 'encrypted', 'receive_exact', 'receive_record', 'decrypt', 'handshake'}
exec(compile(ast.Module(body=[n for n in helper.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[]), '<TLS oracle>', 'exec'))
PSK = bytes(range(32))
def build(source):
    (STAGE / 'main.zen').write_text(source)
    with (WORK / 'compile.log').open('w') as log:
        subprocess.run([str(ZEN), 'build', str(STAGE), '--std', str(STD), '--emit-c', '-o', str(WORK / 'client.c')], check=True, stdout=log, stderr=log)
        subprocess.run([os.environ.get('CC','clang'), '-O2', '-Wno-parentheses-equality', '-fsanitize=' + os.environ.get('SANITIZERS', 'undefined'), '-fno-sanitize-recover=all', str(WORK / 'client.c'), '-o', str(WORK / 'client')], check=True, stdout=log, stderr=log)
    symbols = subprocess.check_output(['nm', '-u', str(WORK / 'client')], text=True)
    assert not re.search(r'\b_?(?:SSL_|OPENSSL_|EVP_|sodium_|crypto_|randombytes)', symbols), symbols
    return WORK / 'client'
def run(binary):
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
    return result.stdout
# No TLS session is needed to sweep all byte boundaries of the actual parser.
print(run(build((ROOT / 'tests/native/response.zen').read_text())), end='')
for mode in range(8):
    server = socket.socket(); server.bind(('127.0.0.1',0)); server.listen(1); server.settimeout(20)
    source = (ROOT / 'tests/native/session.zen').read_text().replace('TEST_PORT', str(server.getsockname()[1])).replace('MODE', str(mode))
    source = source.replace('// RANDOM', '\n'.join(f'random.write({i}, {b});' for i,b in enumerate(os.urandom(32))))
    binary = build(source)
    errors = []
    def peer():
        try:
            with server, server.accept()[0] as conn:
                conn.settimeout(15)
                client, secret = handshake(conn)
                if mode == 7:
                    assert conn.recv(1) == b'', "insecure URL sent bytes"
                    return
                request = decrypt(client,0,receive_record(conn))
                assert request == b'POST /native HTTP/1.1\r\nHost: example.test\r\nContent-Length: 11\r\n\r\nnative post\x17', request
                responses = [b'HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nhello', b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n2\r\nhe\r\n3\r\nllo\r\n0\r\n\r\n', b'HTTP/1.1 200 OK\r\n\r\nhello', b'HTTP/1.1 200 OK\r\nContent-Length: 6\r\n\r\nhello', b'HTTP/1.1 200 OK\r\nContent-Length: 5\r\nContent-Length: 6\r\n\r\nhello', b'HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nhello']
                wire = responses[3 if mode == 6 else mode]
                if mode == 5:
                    record = bytearray(encrypted(secret,0,wire,23)); record[-1] ^= 1; conn.sendall(record)
                else:
                    # Every HTTP byte boundary is also a TLS record boundary.
                    conn.sendall(b''.join(encrypted(secret,i,bytes([b]),23) for i,b in enumerate(wire)))
                    if mode in (2,3): conn.sendall(encrypted(secret,len(wire),b'\x01\x00',21))
                if mode < 3:
                    assert decrypt(client,1,receive_record(conn)) == b'\x01\x00\x15'
        except Exception as error:
            errors.append(error)
    thread = threading.Thread(target=peer); thread.start()
    output = run(binary); thread.join(20)
    assert not thread.is_alive() and not errors, errors
    assert 'session behavior: true alignment and release: true' in output, output
    label_name = ['content length', 'chunked', 'authenticated close-delimited', 'short content length', 'conflicting framing', 'tampered ciphertext', 'raw EOF', 'insecure URL sends nothing'][mode]
    print(f'PASS native HTTP TLS: {label_name}; exactly-once session release')
print('PASS UBSan, native-only symbols, mutable borrowed session sequence continuity')
