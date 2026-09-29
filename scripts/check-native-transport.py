#!/usr/bin/env python3
"""Focused native adapter ownership/OS failure gate; real loopback, no OpenSSL."""
import os
from pathlib import Path
import shutil
import subprocess
ROOT = Path(__file__).resolve().parents[1]
compiler = Path(os.environ.get('ZEN_COMPILER', ROOT.parent / 'zen-crypto-numeric/zen')).resolve()
std = Path(os.environ.get('ZEN_STD', ROOT.parent / 'zen-crypto-numeric/src')).resolve()
work = ROOT / 'build/native-transport-check'
stage = work / 'source'
(stage / 'http').mkdir(parents=True, exist_ok=True)
for name in ('native_transport', 'socket_setup', 'server_core', 'chunked'):
    shutil.copy(ROOT / f'src/http/{name}.zen', stage / f'http/{name}.zen')
crypto = Path(os.environ.get('ZEN_CRYPTO', ROOT.parent / 'zen-crypto')).resolve()
for path in (crypto / 'src').glob('*.zen'):
    shutil.copy(path, stage / path.name)
shutil.copy(ROOT / 'tests/native_transport.zen', stage / 'main.zen')
subprocess.run([str(compiler), 'build', str(stage), '--std', str(std), '--emit-c', '-o', str(work / 'test.c')], check=True)
subprocess.run([os.environ.get('CC', 'clang'), '-O2', '-g', '-fsanitize='+os.environ.get('SANITIZERS', 'undefined'), '-fno-sanitize-recover=all',
                '-Werror=parentheses-equality', '-I', str(ROOT / 'src'), '-I', str(ROOT / 'tests'),
                '-I', str(std / 'std/net'), '-include', str(ROOT / 'tests/native_transport_probe.h'),
                str(work / 'test.c'), '-o', str(work / 'test')], check=True)
symbols = subprocess.check_output(['nm', '-u', str(work / 'test')], text=True)
assert not any(name in symbols for name in ('SSL_', 'OPENSSL_', 'EVP_', 'sodium_', 'crypto_')), symbols
subprocess.run([str(work / 'test')], check=True, timeout=30)
print('PASS native adapter sanitizer checks and no external crypto linkage')
