# Zen HTTP versus native uWebSockets — 2026-09-28

The subsequent chunked-request and HTTP/2 network implementation has not been
benchmarked. All results below apply to their recorded source/binary hashes,
not automatically to the current checkout.

## Latest measured hardening run

[Full current matrix and trial ranges](bench/results/2026-09-28/hardening.md),
[all 48 raw trials](bench/results/2026-09-28/hardening.json), and
[build/source evidence](bench/results/2026-09-28/environment-hardening.txt).
Three paired trials per cell, 64-byte / 16-KiB bodies, 1 / 32 connections,
plaintext / TLS 1.3. All planned trials completed and validated.

This run includes the bounded scheduler, stricter parser, Zen transport I/O
policy and revised load-client validation/timing. The median paired ratio for
16-KiB plaintext at 32 connections was **1.220x**, with a **1.029–1.239x**
observed range. Single-connection plaintext paired medians were **0.973x**
(64 bytes) and **0.979x** (16 KiB). TLS paired ratios straddled 1.0 in every
cell: this run does not establish a consistent TLS throughput advantage. For
32-connection 16-KiB TLS, median-trial p99 was **1435.6 µs for Zen versus
1380.1 µs for uWS**, despite a slightly higher throughput median.

The same-host desktop environment has substantial dispersion. These are observed
ranges, not confidence intervals. Server CPU/RSS, isolated Linux cores, remote
load, offered-load latency and HTTP/2 performance remain unmeasured. The changed
client timing means direct before/after rates do not isolate server regressions.

## Earlier run (historical)

The earlier prototype recorded a local advantage for the 16 KiB echo workload
at 32 persistent connections: **19.3% more requests/sec over plain HTTP** and
**5.8% more over TLS 1.3**. All three Zen trials in each of those two cells exceeded
all three uWS trials. Small concurrent workloads are approximately tied; their
sub-1.2% median differences are too small to establish a useful ranking here.
At one connection with a 16 KiB plain HTTP body, Zen is **3.8% slower**.

This is a workload-specific result from a development Mac, not a claim of
production equivalence or world-leading performance. No measurement of the
private implementation shown in the reference screenshots was possible.

## Historical matrix

Median of three trials per cell. `Zen/uWS > 1` means greater Zen throughput.
Latency columns are medians of each trial's p99, not pooled percentiles.

| Protocol | Connections | Body bytes | Zen req/s | uWS req/s | Zen/uWS | Zen p99 µs | uWS p99 µs |
|---|---:|---:|---:|---:|---:|---:|---:|
| HTTP | 1 | 64 | 54,159 | 51,523 | 1.051× | 39.2 | 44.6 |
| HTTP | 1 | 512 | 53,066 | 52,823 | 1.005× | 41.0 | 42.2 |
| HTTP | 1 | 16,384 | 34,969 | 36,337 | 0.962× | 57.5 | 53.5 |
| HTTP | 32 | 64 | 143,922 | 142,908 | 1.007× | 447.9 | 444.9 |
| HTTP | 32 | 512 | 140,285 | 138,753 | 1.011× | 450.5 | 449.6 |
| HTTP | 32 | 16,384 | 104,167 | 87,333 | 1.193× | 608.2 | 757.2 |
| TLS 1.3 | 1 | 64 | 42,039 | 39,775 | 1.057× | 51.4 | 55.3 |
| TLS 1.3 | 1 | 512 | 39,072 | 37,481 | 1.042× | 52.0 | 52.0 |
| TLS 1.3 | 1 | 16,384 | 21,792 | 20,890 | 1.043× | 75.4 | 78.2 |
| TLS 1.3 | 32 | 64 | 121,692 | 120,785 | 1.008× | 520.9 | 524.2 |
| TLS 1.3 | 32 | 512 | 114,814 | 114,359 | 1.004× | 551.0 | 551.0 |
| TLS 1.3 | 32 | 16,384 | 52,489 | 49,629 | 1.058× | 1182.8 | 1253.5 |

The strongest plain HTTP cell also reduces median-trial p99 from **757.2 µs to
608.2 µs**. The corresponding TLS p99 changes from **1253.5 µs to 1182.8 µs**.
All individual p50/p95/p99, request counts, durations and throughput values remain
in [the raw final trials](bench/results/2026-09-28/final.json).

## What was compared

- Native C++ uWebSockets at `4e7578d175fcb6d2f5b3ae7ad7b13ce14f4309d8`,
  uSockets at `86097c490263ab662d62e8e7b541390bdec7d149`.
- The current Zen compiler candidate and its standard library, generating C.
  Both server builds use Apple Clang 17, `-O3 -flto`; the compiler binary and
  endpoint source/binary hashes are recorded in the environment artifact.
- Both TLS endpoints link the same OpenSSL 3.5.4 archives and use the same
  certificate, TLS 1.3, AES-128-GCM and enabled read-ahead. Certificate verification
  is enabled in the load generator. TLS handshakes are outside measurement.
- One server thread per process on the same Darwin arm64 host; IPv4 loopback,
  matching `POST /echo` binary bodies and response semantics. Each connection has
  one outstanding request. One second of warmup, then two seconds of measurement;
  server order alternates across three trials. Every response is checked.
- The Go 1.27.1 load generator runs on the same machine. This is closed-loop
  latency, not independent offered-load latency. CPU affinity, background load,
  thermal state, client headroom, server RSS and separate-host networking were
  not controlled or fully characterized. Single-connection results visibly vary.

[Full final environment and hashes](bench/results/2026-09-28/environment-final.txt).
The OpenSSL source commit is `c1eeb9406b6142148f267594197d853403d10208`.

## Changes that led to this version

The server began with `poll` and repeated connection scans. It now uses kqueue
on macOS (an epoll adapter exists but has not been run on Linux). Completed
responses return to readiness without an extra speculative socket read. TLS
records already buffered by OpenSSL are drained before waiting. The TLS adapter
in `zen-crypto` enables read-ahead to avoid separate small record-header reads.
HTTP buffers are allocated once and reused, and header/body bytes are coalesced
into a contiguous response buffer.

Earlier complete runs are preserved for inspection:
[poll](bench/results/2026-09-28/poll.json),
[kqueue](bench/results/2026-09-28/kqueue.json), and
[kqueue without redundant reads, before read-ahead](bench/results/2026-09-28/no-extra-read.json).
Each has an adjacent `environment-*.txt` record. These were sequential exploratory
runs with different implementations on a busy desktop, not isolated causal A/B
experiments. Their generated C snapshots remain under ignored `build/` locally.
Only the final source is the maintained implementation.

## Validation and limits

The normal `build.zen` target and matched benchmark builds pass. The full normal
contract suite passes for both servers over HTTP and TLS. Zen's server also
passes that suite with UBSan. Coverage includes body fragmentation, pipelining,
slow readers, connection closure, malformed framing and payload-validation
negative controls. The extracted Zen client passes plain HTTP, trusted TLS and
untrusted-certificate rejection. Existing libsodium known-vector, tamper,
key-exchange, hash/MAC and erasure tests still pass with UBSan.

The combined ASan/UBSan executable from an earlier iteration did not reach
listening state within the 30-second startup allowance. **ASan remains
unverified**, and the UBSan run does not establish leak freedom or complete
memory safety. The crypto backends themselves were not sanitizer-instrumented
by these application builds, and the OpenSSL upstream test suite was not run.

The server reserves **36 MiB for 256 connection buffer pairs**, excluding allocator
and TLS overhead; this is not an RSS measurement. It has a narrower protocol and
lifecycle feature set than uWebSockets: no chunked request bodies, upgrades,
streaming handlers, graceful shutdown, HTTP/2 or HTTP/3. The old standard-library
HTTP/TLS APIs remain for existing callers. See [the package README](README.md)
and [remaining work](docs/PLAN.md) before treating it as a replacement server.

Reproduce from `zen-http` after dependencies and checks:

```sh
python3 bench/run.py --sizes 64 512 16384 --connections 1 32 --trials 3 --seconds 2
python3 bench/report.py build/results.json --output build/table.md
```

Use a Python runtime with TLS 1.3 support. The final local checks used the bundled
Codex Python 3.12 runtime; the Xcode Python on this machine cannot negotiate it.

The historical matrix applies to its recorded source hashes. The latest
hardening run is linked at the top of this document. No HTTP/2 performance
result is claimed.
