# Native PSK HTTPS reactor

The explicit `http.native_server.serve_psk` entry point serves HTTP/1.1 over
native Zen TLS 1.3 external-PSK/X25519 sessions. It shares HTTP parsing,
framing, response generation, scheduling and readiness with the existing
OpenSSL/plaintext server. It does not authenticate web certificates and is
not browser-compatible HTTPS. The default certificate-backed server and
HTTP/2 still use `zen-openssl`.

## Build and run

Use matching compiler/std sources with `std.entropy`, `std.net.readiness` and
`std.mem.PoolAlloc`, plus sibling `zen-crypto` sources containing
`Tls13ServerHandshake`. The explicit script stages these dependencies without
downloading anything:

```sh
export ZEN_COMPILER=/path/to/zen/zen
export ZEN_STD=/path/to/zen/src
export ZEN_CRYPTO=/path/to/zen-crypto
sh scripts/build-native.sh
# Loopback demonstration only; argv exposes the test PSK to local inspection.
./build/zen-native-server TEST_PSK_HEX PORT
```

The example uses identity `ZenTest` and expects a 32-byte hexadecimal test PSK.
Applications instead import `serve_psk`, `PskOptions` and `Handler` from
`http.native_server`, supply their own secret storage and allocator, and keep
the PSK and identity immutable for the entire serve call. Public handshake
random and ephemeral private-key bytes come from two independent OS entropy
requests per accepted connection. There is no insecure entropy fallback.

The native build needs no OpenSSL/libsodium headers or link libraries. It uses
Zen's generated C backend and the existing POSIX ABI helpers. It builds with
UBSan by default; `SANITIZERS=address,undefined` enables both sanitizers.
This is a validation target, not a benchmark build.

## Ownership and progress

`server_core.zen` contains the common parser/reactor and its transport contract.
`server.zen` supplies the existing certificate/plaintext wrapper;
`native_server.zen` supplies explicit PSK configuration. `socket_setup.zen`
shares nonblocking/CLOEXEC/socket-option setup between backends.

`native_transport.zen` owns stable handshake/session storage. Connection slots
copy only borrowed handles. The handshake receives one bounded fragment or
advances one protocol phase at a time; server flights remain unchanged until
acknowledged. Finished authentication precedes the one-time allocation handoff
into `Tls13Session`. Handshake and established-record buffers overlap, so they
are never used as two live engines over the same memory. Unconsumed socket input
survives the handoff and may contain the first HTTP application record.

The adapter returns positive plaintext progress, `-2` for kernel readiness,
`-3` for local runnable work, and `-1` for terminal closure/error. EAGAIN keeps
ciphertext queued; EINTR yields locally. An HTTP write is acknowledged only
after its sealed record is fully written. Both HTTP-requested shutdown and
peer-initiated close_notify flush the native response alert across partial
writes before closing the descriptor. Raw EOF is truncation, not authenticated
TLS closure. Abort and timeout release owners and descriptors once.

The shared reactor admits at most 256 connections, accepts at most 16 per
listener turn, and bounds each connection drive to 64 transitions/eight
responses. Ten seconds without HTTP plaintext progress expires an incomplete
handshake or idle/blocked connection. X25519 remains synchronous CPU work;
these bounds are not a real-time latency guarantee. Existing HTTP framing,
body/header limits and handler lifetimes are unchanged.

Each TLS owner requests 180000 + 32768 bytes, plus an 18437-byte transport input
buffer and ownership metadata. The reactor separately reserves 36 MiB for
HTTP buffers. A bounded std pool reuses small transport allocations and frees
large connection allocations on teardown; no tiny memory-footprint claim is
made.

## Checks and remaining scope

```sh
PYTHON=/path/to/python-with-cryptography \
OPENSSL=/path/to/reference/openssl sh scripts/check-native.sh
```

OpenSSL and Python cryptography are independent test peers only. Checks cover
fragmented and coalesced handshakes, handshake/application handoff, HTTP
pipelining/chunked framing, large echoes, stalled handshake and slow-reader
isolation, authentication rejection, timeout, reciprocal close_notify and
repeated cleanup. An intentionally broken local-runnable scheduler must stall
the test. Allocation/entropy failures and injected EINTR have dedicated adapter
checks; an injected errno is not an actual signal-delivery test. Separate
crypto tests check exact independent flights and reject a Finished-verification
bypass. Existing OpenSSL/plaintext/HTTP2 regression suites still apply.

Still missing: resumable native client handshakes, certificate/hostname/trust
validation, native ALPN/HTTP2 negotiation, HRR, tickets, KeyUpdate and graceful
whole-server shutdown. No security audit, portable constant-time guarantee,
compiler-resistant erasure or uWebSockets speed advantage is claimed.
