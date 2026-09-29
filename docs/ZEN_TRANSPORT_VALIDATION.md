# Zen transport lifecycle validation

The published migration passed the full `scripts/check.sh` suite on the isolated
Linux dev-box checkout on 2026-09-29. Exit status was 0. Listener/accepted-socket
lifecycle and H2 readiness ownership run in Zen; the certificate TLS backend in
this suite remains OpenSSL. This is correctness evidence, not a throughput or
native TLS performance claim.

## Exact inputs

| Component | Revision/version |
| --- | --- |
| zen-http | `109351f8005a6bce228ad8833a9820825a0c20e6` |
| zen-openssl | `0ea91ad665d3ae85a5f37d0b0b648510ee3a3ba4` |
| Zen compiler and std | `f506c9cbf22cf1c2367f5be78d642aac27c81e92` |
| Kernel/platform | Linux 6.8.0-139-generic, x86_64 |
| C compiler | Ubuntu Clang 18.1.3 (1ubuntu1) |
| Python | 3.12.3, TLS 1.3 enabled |
| Go | 1.27.0 linux/amd64 |
| OpenSSL | 3.5.4 |

The HTTP and OpenSSL checkouts were clean before and after the run and updated
using `fetch origin main` followed by `merge --ff-only FETCH_HEAD`. The existing
isolated compiler was reused; the user's other compiler checkout was untouched.
Its executable SHA-256 was
`a7ff87fdb092ca8f3baf6ed220960e89e037882d0a067ab145b0f4f332854986`.

## Reproduction

Run from `/home/ubuntu/zen-readiness-http-validation-20260928/zen-http` with
previously built dependencies:

```sh
ZEN_COMPILER=/home/ubuntu/zen-native-crypto-validation-20260928/zen/zen \
ZEN_STD=/home/ubuntu/zen-native-crypto-validation-20260928/zen/src \
GO_BIN=/home/ubuntu/.local/go/bin/go \
PYTHON=python3 sh scripts/check.sh > ../zen-transport-linux.log 2>&1
```

## Results

- Benchmark harness Python tests (10) and Go tests passed. No performance
  measurement was run.
- Transport tests passed listener allocation failure, accepted-socket cleanup,
  descriptor flags, 128 pooled connections, retry, backpressure, recovery and EOF.
- HTTP/1 plaintext and certificate TLS passed echo, fragmentation, pipelining,
  close, slow-reader and rejection checks; abrupt disconnect survival passed.
  The uWebSockets correctness comparisons also passed.
- H2 primitives, HPACK/request validation, server state and flow-control tests
  passed, including their existing UBSan checks.
- Independent H2 peers passed plaintext and certificate TLS/ALPN, multiplexed
  streams, continuation/padding, 64 KiB transfers, reset/ping, zero-window
  isolation, malformed frames/headers, and the 128-request GOAWAY limit.
- H2 readiness cleanup passed 24 invalid-preface failures and 24 established
  disconnects per mode, with unchanged server descriptor counts. Both the normal
  and UBSan H2 binaries passed this check.
- UBSan HTTP/1 plaintext and TLS regressions and disconnect survival passed.

Full remote log:
`/home/ubuntu/zen-readiness-http-validation-20260928/zen-transport-linux.log`.
SHA-256: `6585a1488c747f512077a121dbfdcc0e513d690798a4da95e106f9b3071e405f`.
Clang emitted generated-C parentheses warnings; no sanitizer failure was reported.
This run did not use ASan, prove leak freedom for every failure path, or change
H2's existing single-active-connection scheduling limitation.
