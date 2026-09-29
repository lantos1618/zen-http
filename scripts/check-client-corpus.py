"""HTTP client corpus migrated from std; no network peers are needed."""
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
COMPILER = Path(os.environ.get("ZEN_COMPILER", ROOT.parent / "zen-actor-runtime/zen")).resolve()
STD = Path(os.environ.get("ZEN_STD", ROOT.parent / "zen-actor-runtime/src")).resolve()
SOURCE = ROOT / "build/client-corpus-source"
SOURCE.mkdir(parents=True, exist_ok=True)
for name, target in {
    "http": ROOT / "src/http",
    "tls.zen": ROOT.parent / "zen-openssl/src/tls.zen",
}.items():
    link = SOURCE / name
    if link.is_symlink():
        link.unlink()
    link.symlink_to(target)

cases = sorted((ROOT / "tests/client-corpus").glob("*.zen"))
assert {"http_post", "http2_receiver_protocol"} <= {case.stem for case in cases}, \
    "missing migrated HTTP client corpus"
for test in cases:
    entry = SOURCE / test.name
    if entry.is_symlink():
        entry.unlink()
    entry.symlink_to(test)
    output = ROOT / "build" / ("client-corpus-" + test.stem)
    subprocess.run([
        str(COMPILER), "build", str(SOURCE), "--std", str(STD),
        "--entry", entry.name, "--emit-c", "-o", str(output) + ".c",
    ], check=True)
    subprocess.run([
        os.environ.get("CC", "clang"), "-O2", "-g", "-pthread",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        "-I" + str(ROOT.parent / "zen-openssl/src"),
        "-I" + str(ROOT / "build/openssl/include"), str(output) + ".c",
        str(ROOT / "build/openssl/lib/libssl.a"),
        str(ROOT / "build/openssl/lib/libcrypto.a"), "-o", str(output),
    ], check=True)
    result = subprocess.run([str(output)], capture_output=True, text=True,
                            check=True, timeout=40)
    assert result.stdout == test.with_suffix(".expected").read_text(), (test, result.stdout)
    print(test.stem + " migrated client corpus PASS", flush=True)
