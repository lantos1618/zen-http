# Native implementation and standard-library migration

The compiler removal is tracked in [Zen PR #12](https://github.com/lantos1618/zen/pull/12).
The removal statements below describe that revision; older compiler checkouts
still contain the std APIs.

The public packages should own one maintained HTTP/TLS protocol implementation.
The standard library should own generally useful allocation, bytes, sockets,
clocks and readiness primitives. Publishing a package is not a reason to copy
its implementation back into `std`: two independently edited copies drift.

The current package split keeps native Zen algorithms in `zen-crypto`, OpenSSL
TLS integration in `zen-openssl`, and libsodium bindings in `zen-sodium`.
The default zen-http client, event-driven server and HTTP/2 use zen-openssl.
The explicit `http.native_client` module instead borrows a native zen-crypto
TLS session, with no OpenSSL linkage. It currently requires external PSK
authentication; it does not implement certificate verification or ALPN.
Both client backends share the same response decoder. The source inventory below is historical
and retains its original repository names and revisions.

## What is actually Zen

At HTTP commit `1463e2d` and crypto commit `3c041cd`, physical lines under `src`
(including blanks/comments, excluding builds, tests and dependencies) were:

| Package | Zen | Handwritten C headers |
|---|---:|---:|
| zen-http | 3,579 | 155 |
| zen-crypto | 531 | 113 |

These are source inventories, not percentages of runtime work, safety or
independence from C. Zen currently compiles to C. OpenSSL and libsodium were
excluded from this historical table and supplied its cryptographic primitives.
Current zen-crypto separately implements native Zen primitives and a bounded
TLS 1.3 PSK/PSK-DHE client plus PSK-DHE server. See its TLS documentation for
current tests and limits; this old inventory does not describe that work. A Zen
binding is not a native Zen implementation of encryption or TLS records.

Zen owns HTTP parsing/framing, buffers, scheduling, HPACK/Huffman, HTTP/2 stream
and flow-control state, certificate-verification policy, ALPN protocol selection
and nonblocking TLS retry decisions. The first follow-up conversion moves client TLS
context construction and the server's selected-ALPN check into Zen; borrowed
OpenSSL accessors remain ABI glue. No throughput gain follows from that change.

The listener/connection records, allocation, socket setup, failure cleanup,
OpenSSL session construction and H2 readiness ownership now live in Zen.
The server uses std pool allocation for transport storage because a caller arena
may not reclaim individual frees. `src/reactor.h` has been removed. Remaining handwritten package C includes
an IPv4 address-field accessor, errno access and HTTP date/time helpers, OpenSSL const/callback ABI adapters,
and the Linux MSG_NOSIGNAL socket BIO. The BIO still contains allocation,
retry and lifetime logic; it is not merely a declaration. Its disconnect
protections must survive a future conversion. Generic std readiness still
uses a platform header for kqueue/epoll layouts and syscall macros.

Moving OpenSSL setup into `.zen` does not make its cryptography native Zen.
The separate native PSK path and its security limits remain unchanged.

See [migration validation](ZEN_TRANSPORT_VALIDATION.md) for the macOS/Linux
integration results, allocation-failure tests and descriptor cleanup checks.

## Implementation rule

Write allocation, cleanup, retry policy, state transitions and protocol logic
in `.zen`. A handwritten C helper needs a concrete platform ABI or compiler
limitation, documented beside it. Do not add a C implementation merely to make
a Zen wrapper shorter. Existing exceptions, particularly the Linux OpenSSL BIO
and date cache, remain migration work and must be described as such.

The current IPv4 accessors accommodate OS-dependent family-field widths and
unsupported nested-native-record addresses. OS readiness still bridges native
kqueue/epoll layouts and macros. Generated C emitted by the Zen compiler is a
separate build artifact, not a reason to keep handwritten policy in headers.

## Standard-library boundary

HTTP/1 and HTTP/2 implementations, their std exports and `env.net.http()` have
been removed from the compiler's standard library. Applications explicitly
import `zen-http`; there is no std compatibility facade or automatic package
fetch. [The migration guide](STD_HTTP_MIGRATION.md) lists the replacement imports
and all seven preserved client/actor corpus fixtures.

`std.net.tls` remains a separate compatibility implementation. Its
`Stream`/`TlsError` names differ from package `Transport`/`TlsFault`, so the HTTP
removal does not imply that TLS callers can replace imports blindly.

The package uses sibling paths in `build.zen`. Public repositories do not by
themselves provide versioned package installation. Reproducible dependency
resolution remains work to do; no package-to-std-to-package import cycle was
introduced to preserve old HTTP names.

Generic nonblocking sockets, readiness, clocks and memory can continue to be
upstreamed independently. HTTP status, headers, ALPN choices and connection
limits remain package policy. Package tests now own HTTP client/actor coverage,
alongside plain/TLS, certificate rejection, H2, allocation-failure and cleanup
checks. The experimental H2 server and native PSK HTTP client have not become
default standard-library APIs.

Validation of this conversion: the full macOS HTTP package check script passes,
including trusted/untrusted TLS clients, h2 ALPN acceptance/rejection, HTTP/2
independent peer tests, UBSan and abrupt-disconnect survival. No new benchmark
was run for this change; earlier measurements retain their recorded revisions.
