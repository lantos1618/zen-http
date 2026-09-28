# Benchmark evidence and validation

The harness measures a fixed-length POST echo over persistent HTTP/1.1 connections, with one outstanding request per connection. TLS trials verify the local certificate and require TLS 1.3 with AES-128-GCM. Each connection warms up for one second before a common measurement start. The final in-flight request may finish after the requested duration; elapsed time includes that drain through the last worker completion. Client aggregation/sorting time is excluded from throughput elapsed time.

This is a closed-loop, same-host test. It includes client overhead and cannot establish open-loop latency under a fixed offered load, remote-network behavior, HTTP/2 performance, or handshake throughput. The client records every successful exchange latency; this consumes memory and adds measurement overhead. Its CPU metric includes setup, warmup, measurement and aggregation through the accounting call. **It is not server CPU usage.** On Linux, the runner records server CPU time and peak RSS over its lifetime through client completion, including startup and warmup. Optional disjoint CPU affinity is checked for the server; no claim of physical-core or host isolation follows.

## Running and retaining evidence

Choose a new output filename for each run; the runner refuses to overwrite an existing result:

```sh
python3 bench/run.py --trials 5 --seconds 5 --sizes 64 512 16384 --connections 1 32 --output build/run-new.json
python3 bench/report.py build/run-new.json --output build/run-new.md
```

Only run when no other task owns loopback port 18080. Build the current binaries first using the project build script. SHA-256 hashes identify the three measured binaries; platform and Python version are recorded. These hashes are not a substitute for recording source revisions, compiler versions/flags, dependency versions and host conditions when publishing measurements.

The version 2 JSON contains the planned workload matrix and trial count. It checkpoints a running row before starting each trial, and saves client output, failure details and newly written server logs afterward. Ordinary trial failures remain in the file and the runner continues the planned matrix, then exits nonzero. Keyboard interruption marks the run and active row interrupted. Abrupt termination may leave the last row marked running; reporting treats it as incomplete. Checkpoint replacement is atomic on the same filesystem, but does not guarantee power-loss durability.

A cell is compared only if **all planned pairs succeed**. Missing, failed and interrupted trials are displayed as incomplete with no performance comparison. Duplicate trial identifiers and invalid numerical metrics are rejected. Do not delete failures or publish only favorable cells. Legacy list-format results remain readable, but cannot establish whether an entire workload was omitted.

Throughput and p99 are trial medians. Throughput brackets give observed trial minimum–maximum; the comparison is the median of per-pair Zen/uWS ratios with its observed range. These ranges are **not confidence intervals**, and a median of trial p99 values is not a pooled p99. Server order alternates each trial; odd trial counts still have one more occurrence of one order. Small differences can be noise.

## Offline validation

```sh
python3 -B -m unittest discover -s bench -p test_benchmark.py
GOCACHE="$PWD/build/go-test-cache" ../zen-bench/build/toolchains/go/bin/go test bench/load.go bench/load_test.go
```

Python tests exercise invalid inputs/metrics, pairing, missing entire cells, duplicate identifiers, failure/interrupt persistence and overwrite protection. Go tests exercise valid responses and negative controls for wrong bodies, status, duplicate/signed/missing content lengths, transfer encoding, truncated bodies and excessive/malformed headers. They use in-memory input, not loopback servers.

These changes alter both timing accounting and client validation overhead. Earlier results remain historical evidence for the earlier harness and binaries; **fresh matched runs are required before making new performance claims**. No new performance measurement is implied by passing these tests.


Linux placement example: append `--server-cpu 2 --client-cpus 4 5 6 7`.
Both arguments are required together; CPUs must be allowed, distinct, and
nonoverlapping. `taskset` is required. Raw rows record observed server affinity,
cumulative server user+system CPU seconds from /proc, and lifetime VmHWM KiB.
Reading occurs after the load generator exits and before terminating the server.
These are not measurement-window-only resource figures. Other host workloads
and virtual CPU scheduling can still affect results.
