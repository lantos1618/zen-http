# HTTP/1 server hardening

The server remains a bounded HTTP/1.1 prototype. This change adds scheduling
bounds and parser regressions; it does not establish RFC compliance, resistance
to every denial-of-service pattern, or production readiness.

## Scheduling

One connection can complete at most eight responses or execute 64 state-machine
steps per scheduling round, whichever limit occurs first. A step can perform
one transport I/O call or invoke the synchronous handler. This bounds work items,
not elapsed CPU time: a slow application handler can still block the event loop.
A listener readiness event admits at most 16 new connections.

Budget exhaustion keeps the connection in an explicit userspace runnable set.
The next reactor poll uses a zero timeout when that set is nonempty. Readiness
events are coalesced into the same set, then each runnable slot is visited once.
This matters for pipelined request bytes and decrypted TLS data: neither must
wait for another kernel event after a scheduling yield. A transport would-block
result clears local readiness and returns control to the reactor.

The implementation scans the fixed 256-slot table each round. The integrated server was measured in the latest
[hardening run](../bench/results/2026-09-28/hardening.md), but that run does not
isolate the scan cost from the parser, transport and client changes. Earlier
benchmark results describe earlier code. There is no fairness
latency guarantee or configurable handler time budget.

## Request validation

The parser accepts HTTP/1.1 origin-form requests with token methods and field
names. Header blocks are limited to 8192 bytes, including the closing CRLF, and
64 fields. Bodies and handler response bodies are limited to 65536 bytes. Those
limits are fixed rather than configurable.

Exactly one nonempty Host is required. Whitespace, non-ASCII bytes, commas,
userinfo and path/query/fragment delimiters are rejected in Host. This is not a
complete authority parser: DNS, port and bracketed IPv6 syntax are not fully
validated. Field values reject NUL and other disallowed control bytes while
allowing horizontal tabs. Duplicate Content-Length, malformed/oversized lengths,
ambiguous Transfer-Encoding and Expect are rejected by closing the connection.
A single chunked coding is now supported as described in [chunked requests](HTTP1_CHUNKED.md).

Chunk extensions, most trailers, HTTP/1.0, CONNECT authority-form, OPTIONS asterisk-form, upgrades,
streaming handlers and graceful shutdown remain unsupported. There is a
10-second inactivity timeout, but no absolute request deadline: a peer sending
occasional bytes can retain a slot. Application responses do not expose arbitrary
headers or statuses, and method-specific response semantics need further work.

## Regression coverage

`tests/check.py` exercises ordinary and fragmented echo bodies, pipelining,
connection close and delayed response readers over plaintext and TLS. New cases
send 256 requests before reading responses, then finish a fragmented tail; this
exercises repeated scheduling yields and TLS/userspace wakeup preservation.
Another case checks an independent peer makes progress while a pipeline is
queued. It is a liveness regression, not a statistical fairness benchmark.

Parser cases cover token punctuation, interior tabs, exact header-count and
byte boundaries, missing/duplicate/invalid Host, duplicate/comma/signed/overflow
lengths, control bytes and unsupported framing. These are targeted cases, not
fuzzing or a complete conformance suite. Runtime pass/fail evidence belongs in
the integration report after running the changed binaries.
