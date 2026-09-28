"""Compile and run pure-Zen server state tests; no network server is implied."""
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
COMPILER = Path(os.environ.get('ZEN_COMPILER', ROOT.parent / 'zen-actor-runtime/zen'))
ENV = dict(os.environ, ZEN_STD=os.environ.get('ZEN_STD', str(ROOT.parent / 'zen-actor-runtime/src')))
SOURCE = ROOT / 'build/h2-server-state-source'
SOURCE.mkdir(parents=True, exist_ok=True)
module = SOURCE / 'http'
if module.is_symlink():
    module.unlink()
module.mkdir(exist_ok=True)
state = module / 'http2_server_state.zen'
if not state.exists():
    state.symlink_to(ROOT / 'src/http/http2_server_state.zen')
for test in sorted((ROOT / 'tests/http2').glob('server*.zen')):
    entry = SOURCE / test.name
    if entry.is_symlink():
        entry.unlink()
    entry.symlink_to(test)
    output = ROOT / 'build' / ('h2_state_' + test.stem)
    subprocess.run([str(COMPILER), 'build', str(SOURCE), '--entry', entry.name,
                    '--emit-c', '-o', str(output) + '.c'], env=ENV, check=True)
    subprocess.run(['clang', '-O2', '-g', '-fsanitize=undefined',
                    '-fno-sanitize-recover=all', str(output) + '.c', '-o', str(output)], check=True)
    result = subprocess.run([str(output)], capture_output=True, text=True, check=True, timeout=40)
    assert result.stdout == test.with_suffix('.expected').read_text(), (test, result.stdout)
    print(test.stem + ' PASS (UBSan)', flush=True)
