# Zen HTTP versus native uWebSockets — 2026-09-28

## Latest Linux run — current implementation

[Full matrix and server resource measurements](bench/results/2026-09-28/linux.md),
[all 48 raw trials](bench/results/2026-09-28/linux.json), and
[build, revision and validation evidence](bench/results/2026-09-28/environment-linux.txt).
All planned trials completed with response validation. This measures `zen-http`
`0a58b71` with `zen-crypto` `3c041cd` and compiler `f1bd2a8`; later documentation
commits do not change the measured binaries.

**Zen does not beat uWebSockets overall in this run.** For 16-KiB plaintext
at 32 connections, the median paired throughput ratio is **1.052x**
(observed range **1.010–1.087x**); median-trial p99 is **899.3 µs versus 975.2 µs**.
For the same workload over TLS, the ratio is **0.789x** (**0.778–0.795x**):
Zen is **21.1% slower** by the paired median, with p99 **2446.2 µs versus
1917.7 µs**. The large-body concurrent TLS path is the clearest profiling target.
Small concurrent plaintext is approximately tied; all four TLS paired medians
are below 1.0. Three short trials cannot establish a universal ranking.

This is Linux x86_64 on a 16-vCPU virtual host, Clang18.1.3 and Go1.23.4,
using the same pinned native uWebSockets/uSockets and OpenSSL3.5.4 revisions
listed below. Each server is pinned to CPU2 and the client to CPUs4–7.
Physical-core isolation and exclusive host use are not asserted. Each trial
uses one second of warmup followed by three seconds of measurement, IPv4
loopback, persistent connections and one outstanding request per connection.
Server order alternates. Server CPU seconds and peak RSS include startup and
warmup; p99 is the median of trial p99s, not a pooled percentile. Observed
minima/maxima are not confidence intervals. Client overhead remains part of
this same-host closed-loop experiment.

The measured implementation includes bounded HTTP/1 chunk decoding, but the
benchmark sends Content-Length requests. HTTP/2 is tested separately and has
**no performance result**. Remote-client, offered-load latency, handshake
throughput, client throughput and production equivalence remain unestablished.
Both macOS and Linux full HTTP package check scripts pass, including the
documented HTTP/2 peer checks, UBSan and abrupt-disconnect regressions. Linux
validation exposed and fixed a TLS SIGPIPE crash before this benchmark.

Reproduce after dependencies and `scripts/check.sh`:

```sh
python3 bench/run.py --trials 3 --seconds 3 --sizes 64 16384 \
  --connections 1 32 --server-cpu 2 --client-cpus 4 5 6 7 \
  --output build/linux-reproduction.json
python3 bench/report.py build/linux-reproduction.json --output build/linux-reproduction.md
```

Choose permitted, disjoint CPU sets for your machine; do not overwrite prior
raw results. The Linux compiler was built from its checked-in bootstrap with
`make build/bootstrap/zen-seed CC=clang CFLAGS='-O2 -std=c99'`, then copied to
`zen`. Full compiler validation was not performed; its focused native socket
regression and the package integration suites passed.

## Previous macOS hardening run (historical)

The following historical results apply only to their recorded source/binary
hashes. They predate the chunked-request and HTTP/2 network implementation.

[Full historical matrix and trial ranges](bench/results/2026-09-28/hardening.md),
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
ranges, not confidence intervals. This historical run did not measure server
CPU/RSS, isolated Linux cores, remote load, offered-load latency or HTTP/2 performance. The changed
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

## What was compared in the historical macOS runs

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
on macOS and epoll on Linux (validated in the latest run above). Completed
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

## Historical validation and limits

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
lifecycle feature set than uWebSockets. At that historical checkpoint it had no
chunked request bodies, upgrades, streaming handlers, graceful shutdown, HTTP/2
or HTTP/3. Current code adds bounded chunked requests and experimental HTTP/2;
see the README for current limitations. The old standard-library
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
Linux run is linked at the top of this document. No HTTP/2 performance
result is claimed.
