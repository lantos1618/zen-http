# Package boundary and performance work

`zen-http` owns HTTP messages, parsing, framing, routing, connection policy and
protocol-specific client/server behavior. `zen-openssl` owns TLS policy, sessions,
certificate verification and OpenSSL integration. `std` retains generic
memory, byte, numeric and OS facilities. Keep existing standard-library consumers
working while replacing their HTTP/TLS imports explicitly in a later migration.
HTTP/2 must migrate with its framing, HPACK, flow control and actor tests, not
with a forwarding alias that still depends on its old implementation.

Next server work, driven by measured bottlenecks:

1. kqueue/epoll readiness adapters and bounded per-connection work are implemented.
   Both macOS and Linux paths pass the current integration suite. Readiness is currently level-triggered;
   an edge-triggered variant must explicitly drain all kernel and TLS input. Add deterministic forced-short-write
   and readiness retry tests, including TLS WANT_READ during writes.
2. Expose caller-chosen connection/buffer budgets, deadlines and graceful drain.
   Test admission exhaustion, stalled handshakes, reconnect churn and cleanup.
3. Separate an incremental HTTP parser from server scheduling. Differential
   fuzz against a mature parser, reject ambiguous framing, and expand RFC
   coverage before broadening methods/headers/streaming support.
4. Bounded chunked request decoding is implemented. Add streaming responses
   and explicit backpressure in the public handler contract without forcing
   one actor per connection.
5. Profile exact optimized binaries and allocation counts. Test a persistent
   TLS client with reusable contexts separately from server steady-state echo.
6. Extend the Linux same-host, disjoint-CPU benchmark to a separate
   load-generator machine and characterize physical isolation, client headroom
   and offered-load latency. Lifetime server CPU/RSS accounting is implemented. Add Cinatra/lithium only after the uWS contract is stable.

Success is a reproducible workload-specific win while preserving correctness.
Do not treat a reduced-feature prototype beating a complete library as proof of
production equivalence, or claim the private implementation in screenshots was
measured when its binary and test contract are unavailable.

## Earlier native Zen / HTTP/2 checkpoint (historical)

Completed: migrated the existing Zen HTTP/2 client, frame codec and HPACK code
into the package; wired it to zen-crypto; added package codec and loopback wire
checks. Moved TLS server policy/context ownership out of C into Zen.

Next: HTTP/2 server with bounded stream state and request header validation;
client multiplexing and receive/send interleaving; independent full H2 peer and
conformance tests; migrate socket/reactor and TLS I/O control to Zen using
header-backed records. Keep cryptographic algorithms in vetted backends until
native implementations meet the crypto project's validation requirements.


## Earlier parallel hardening checkpoint (historical)

Implemented and tested in this batch: bounded HTTP/1 scheduling with preserved
userspace wakeups; parser field/token boundaries; socket/TLS retry policy in Zen;
forced socket backpressure/recovery test; a pure-Zen HTTP/2 server state component;
and benchmark failure retention / incomplete-cell rejection.

Still outstanding: full HTTP/2 request decoding and network server, client
multiplexing, HTTP/1 streaming/chunked handling, configurable server budgets,
absolute request deadlines/graceful drain, Linux execution and broader fuzzing.
See the track-specific documents for exact coverage. No production-readiness
claim follows from this checkpoint.


Validation for this checkpoint: integrated plaintext/TLS correctness and UBSan
passed; two HTTP/2 state programs passed UBSan; eight Python benchmark tests and
Go response-contract cases passed. A fresh 48-trial HTTP/1 comparison is retained
in RESULTS.md, including losses and dispersion. No HTTP/2 network server or
Linux-runtime validation is implied.


## Network protocol checkpoint

The experimental HTTP/2 network path now implements preface/frames, request
HPACK with bounded dynamic table, concurrent streams, basic flow control,
PING/reset/GOAWAY, and TLS1.3 h2 ALPN. Independent hyper-h24.3.0 checks and
UBSan runs passed for the documented cases. It services one TCP connection at
a time, buffers whole bodies, and has incomplete RFC error distinctions.
HTTP/1 now accepts a documented bounded chunked subset, with fragmentation,
pipelining and ambiguity-rejection checks over plaintext/TLS under UBSan.

Immediate next work: a multi-connection HTTP/2 reactor with bounded output
queues/read-write interleaving; precise stream-vs-connection errors and broader
conformance testing; generic streaming handler APIs; configurable limits and
application shutdown. Linux runtime validation now passes. The existing client still
permits only one active request per connection. No new benchmark claim accompanies
this checkpoint. See H2_NETWORK.md, H2_REQUEST.md and HTTP1_CHUNKED.md.


## Public Linux validation checkpoint

`zen-http` and `zen-crypto` are public repositories. The complete HTTP package
check script passes on macOS and Linux, including HTTP/1 and HTTP/2 plaintext/TLS
checks, independent HTTP/2 peer checks, UBSan and abrupt-disconnect regression
tests. Linux testing exposed a real TLS SIGPIPE crash; the crypto adapter now
uses a borrowed socket BIO with `MSG_NOSIGNAL`, without changing the process-wide
signal handler. OpenSSL library placement and the uSockets Clang LTO toolchain
were also corrected for reproducible Linux builds.

The existing `~/zenc` checkout on the validation host was preserved; validation
used an isolated checkout of the published compiler and package revisions.
This validates the documented bounded cases, not full HTTP/2 conformance,
production readiness, cryptographic implementation correctness or ASan safety.
See RESULTS.md for measured performance and exact build evidence.

TLS extraction now lives in the separate `zen-openssl` backend package. Earlier
checkpoint references to zen-crypto describe the layout at those revisions.
Native Zen algorithms remain in zen-crypto; libsodium bindings live in zen-sodium.
