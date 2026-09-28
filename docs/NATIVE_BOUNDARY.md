# Native implementation and standard-library migration

The public packages should own one maintained HTTP/TLS protocol implementation.
The standard library should own generally useful allocation, bytes, sockets,
clocks and readiness primitives. Publishing a package is not a reason to copy
its implementation back into `std`: two independently edited copies drift.

The current package split keeps native Zen algorithms in `zen-crypto`, OpenSSL
TLS integration in `zen-openssl`, and libsodium bindings in `zen-sodium`.
zen-http depends on zen-openssl for TLS. The source inventory below is historical
and retains its original repository names and revisions.

## What is actually Zen

At HTTP commit `1463e2d` and crypto commit `3c041cd`, physical lines under `src`
(including blanks/comments, excluding builds, tests and dependencies) were:

| Package | Zen | Handwritten C headers |
|---|---:|---:|
| zen-http | 3,579 | 155 |
| zen-crypto | 531 | 113 |

These are source inventories, not percentages of runtime work, safety or
independence from C. Zen currently compiles to C. OpenSSL and libsodium are
excluded from this table and implement the cryptographic primitives. A Zen
binding is not a native Zen implementation of encryption or TLS records.

Zen owns HTTP parsing/framing, buffers, scheduling, HPACK/Huffman, HTTP/2 stream
and flow-control state, certificate-verification policy, ALPN protocol selection
and nonblocking TLS retry decisions. The first follow-up conversion moves client TLS
context construction and the server's selected-ALPN check into Zen; borrowed
OpenSSL accessors remain ABI glue. No throughput gain follows from that change.

Remaining handwritten native work includes socket setup/accept/cleanup,
kqueue/epoll registration and event extraction, HTTP date formatting/cache,
OpenSSL session setup and the Linux MSG_NOSIGNAL socket BIO. The BIO is functional
I/O code, not merely a declaration. It must retain its disconnect protections
through any conversion. Vetted crypto backends stay in place; replacing them
needs a separate implementation, vector, interoperability and side-channel
validation effort.

## Existing standard-library overlap

`std.net.http`, `std.net.http2` and `std.net.tls` still contain implementations.
`std/std.zen` re-exports their types, and `Env.http` constructs the old
`std.net.http.HttpClient`. Publishing these packages did not migrate those
callers. Package TLS names also differ (`Transport`/`TlsFault` versus
`Stream`/`TlsError`); replacing imports blindly is not a compatibility plan.

The package currently uses sibling paths in `build.zen`. Public Git repositories
are available, but a versioned package install and standard-library dependency
integration are not established by that alone.

## Migration sequence and gates

1. Move portable connection and readiness policy into Zen. Upstream reusable
   nonblocking socket operations, monotonic time and a portable readiness API
   into `std`, backed by the minimum OS ABI bindings. Keep HTTP status, ALPN,
   headers and connection limits out of that generic layer. Remove corresponding
   package adapters only after macOS/Linux backpressure, EOF, descriptor cleanup,
   readiness and disconnect tests pass against the upstream primitive.
2. Make package versions and dependency resolution reproducible without local
   sibling checkout assumptions. Choose a pinned bundled source snapshot if the
   compiler distribution cannot yet resolve packages. Such a snapshot must be
   mechanically synchronized from one canonical source, not edited as a fork.
3. Add compatibility facades for the existing `std.net.http`, `std.net.http2`,
   `std.net.tls`, top-level exports and `Env.http`. Preserve public names, errors,
   ownership/drop behavior and verified TLS defaults. Ensure compiler bootstrap
   builds offline and avoids a package-to-std-to-package import cycle. If those
   constraints cannot be met, retain the existing API until an explicit breaking
   release rather than introducing a hidden network/build dependency.
4. Run existing standard-library client/actor tests through the facades, plus
   package plain/TLS, certificate rejection, H2, allocation-failure and cleanup
   tests. Only then remove the duplicated std implementations. Test upgrades
   from existing caller examples, not just freshly rewritten package examples.

The experimental H2 server (one active TCP connection, bounded streams, incomplete
error distinctions) should not become a default std API yet. HTTP/1 and TLS also
remain experimental. Generic primitives can be upstreamed independently of that
stabilization. This document is the migration design; it does not claim the
compiler repository or `Env.http` has already been changed.

Validation of this conversion: the full macOS HTTP package check script passes,
including trusted/untrusted TLS clients, h2 ALPN acceptance/rejection, HTTP/2
independent peer tests, UBSan and abrupt-disconnect survival. No new benchmark
was run for this change; earlier measurements retain their recorded revisions.
