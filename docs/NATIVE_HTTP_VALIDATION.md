# Native HTTP client validation

The experimental HTTP/1 POST adapter passed the native suite on Linux x86-64
with AddressSanitizer, UndefinedBehaviorSanitizer and leak detection enabled on
2026-09-29. The existing HTTP suite also passed after the response decoder
extraction. These are correctness and interoperability results, not performance
measurements or a security audit.

## Tested revisions and environment

| Component | Revision or version |
| --- | --- |
| zen-http | `d031daa423d11317929741ad43add9751ac97d97` |
| zen-crypto | `ba29487346be89dc299e870bdee64941d957bed6` |
| Zen compiler and std | `f506c9cbf22cf1c2367f5be78d642aac27c81e92` |
| Compiler executable SHA-256 | `a7ff87fdb092ca8f3baf6ed220960e89e037882d0a067ab145b0f4f332854986` |
| Kernel | Linux 6.8.0-139-generic, x86-64 |
| C compiler | Ubuntu Clang 18.1.3 |
| Python | 3.12.3 |
| Test-only Python cryptography | 41.0.7 |
| Baseline Go toolchain | 1.27.0 |
| Baseline linked OpenSSL | 3.5.4 |
| Python ssl backend | OpenSSL 3.0.13 |

The isolated HTTP checkout was
`/home/ubuntu/zen-readiness-http-validation-20260928/zen-http`. Compiler and
crypto sources came from sibling checkouts under
`/home/ubuntu/zen-native-crypto-validation-20260928`. All three source revisions
were checked before testing; the HTTP checkout was updated by fast-forward.

## Native suite

Run from zen-http, with Python's `cryptography` installed for the independent
TLS peer:

```sh
ZEN_COMPILER=/home/ubuntu/zen-native-crypto-validation-20260928/zen/zen \
ZEN_STD=/home/ubuntu/zen-native-crypto-validation-20260928/zen/src \
ZEN_CRYPTO=/home/ubuntu/zen-native-crypto-validation-20260928/zen-crypto \
SANITIZERS=address,undefined ASAN_OPTIONS=detect_leaks=1 \
python3 scripts/check-native-http.py
```

The script exited zero. It checked:

- 207 parser cases spanning read boundaries for content-length, chunked and
  close-delimited responses, plus eight rejection cases.
- Eight real encrypted-session scenarios: content-length, chunked and
  authenticated close-delimited responses; premature authenticated close;
  conflicting framing; tampered ciphertext; raw EOF; and rejection of an HTTP
  URL without sending request bytes.
- HTTP responses fragmented across individual TLS records, with the Python
  peer independently verifying the emitted POST and TLS Finished messages.
- A caller-issued close notification using the next client sequence number
  after POST, demonstrating mutation of the original borrowed session.
- Exactly two session allocations and two frees, including repeated abort and
  scope cleanup. HTTP buffers use a separate allocator in this probe.
- A source tree without `tls.zen` and an executable without unresolved
  OpenSSL/libsodium crypto symbols. The tested executable contains both
  `__asan_init` and `__ubsan_handle_type_mismatch_v1_abort`.

The remote log is `build/native-http-linux-asan.log`, SHA-256
`90ef50bd0e9d0f6ee3aada6d51c930734f412e3cab7618079382391185e46880`.
Python cryptography is an oracle dependency, not a native client dependency.
The native script remains separate from the baseline suite.

## Existing HTTP compatibility suite

```sh
ZEN_COMPILER=/home/ubuntu/zen-native-crypto-validation-20260928/zen/zen \
ZEN_STD=/home/ubuntu/zen-native-crypto-validation-20260928/zen/src \
GO_BIN=/home/ubuntu/.local/go/bin/go PYTHON=python3 \
sh scripts/check.sh
```

The full baseline passed, including its HTTP/1 and HTTP/2 checks, OpenSSL-backed
HTTPS behavior, malformed requests, fragmentation, pipelining, slow readers and
abrupt disconnect survival. Its sanitizer targets use UBSan; the ASan result
above belongs specifically to the native HTTP suite. The remote baseline log
is `build/native-http-linux-baseline.log`, SHA-256
`f9be62c9e6a8c0c6d15ad675766069989eace23b4c3d12e6f38b10763bb77121`.

An initial launch stopped because noninteractive SSH did not include Go in
PATH. A complete run with Go 1.23.4 also passed; the reported environment uses
the repeated run with the project's Go 1.27.0 toolchain.

## Scope

The adapter borrows an already authenticated PSK session and performs one
HTTP/1 POST. The caller supplies peer identity, socket policy, entropy and
session cleanup. It requires an `https` URL and has no plaintext fallback.
The parser may prefetch past a response boundary, so this adapter does not
promise reusable HTTP connections. Streaming sinks can receive an authenticated
body prefix before a later framing or transport failure.

These tests do not establish certificate validation, forward secrecy, HTTP/2
over native TLS, a native HTTPS server, side-channel resistance, or superiority
to uWebSockets. The existing OpenSSL-backed HTTPS client remains the default.
