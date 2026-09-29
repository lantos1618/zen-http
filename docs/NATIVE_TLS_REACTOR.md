# Native TLS integration with the HTTP reactor

This is a proposed migration, not an implemented server backend. Native Zen
TLS currently supports blocking external-PSK connections, including X25519
PSK-DHE client/server roles and reusable record sessions. The HTTP reactor
still uses the zen-openssl transport. The native HTTP client adapter consumes
an already authenticated blocking session.

## Current boundary

- `src/transport.h` accepts nonblocking sockets, but its listener/connection
  layouts contain `SSL_CTX*`/`SSL*` and unconditionally include `zen_tls.h`.
- `src/http/transport.zen` maps OpenSSL progress to bytes, read/write interest,
  and closure. It also handles raw socket errno and buffered TLS input.
- `src/http/server.zen` limits each drive round to 64 transitions/eight responses
  and uses std readiness plus a local runnable queue. Connection descriptors
  are copied between slot storage and local variables.
- In zen-crypto, `src/tls13_server.zen` and `src/tls13_session.zen` perform
  read-exact/write-all loops. `SocketFd` maps syscall failures to socket faults;
  it does not expose recoverable EAGAIN to these callers. The current native
  session treats an I/O error as terminal and releases its storage.

Calling the blocking native accept/read/write APIs from this reactor would
therefore block other connections or abort on ordinary nonblocking backpressure.
Wrapping those calls in an actor does not solve the transport contract.

## Shared protocol engine

Refactor zen-crypto into one resumable protocol engine, then make both blocking
and reactor adapters drive it. Do not create an HTTP-specific copy of TLS
parsing, transcript handling, key derivation, or record protection.

The engine needs persistent handshake phase, partial header/body offsets,
handshake-message accumulation, directional sequences, authenticated plaintext
remaining to deliver, and ciphertext remaining to write. Its proposed boundary
accepts bounded ciphertext input, exposes bounded pending output, acknowledges
bytes written, and reports progress such as `NeedInput`, `NeedOutput`,
`Runnable`, `Established`, or a terminal error. These names are illustrative;
there is no such API today. Buffer ownership and view lifetimes must be explicit.

A record is sealed once and retained across partial writes. Retries must never
re-encrypt plaintext or consume another sequence number. Authentication and
inner-record validation precede plaintext release. EOF before close_notify
remains truncation; authenticated shutdown and all fatal cleanup remain shared
protocol behavior. Existing blocking APIs become compatibility drivers for this
engine and retain their observable contracts.

Each progress call must bound protocol work. Local buffered work must report a
runnable yield, rather than pretending it needs another socket event. The current
HTTP `-2` wait result alone cannot express this distinction. Existing handshake,
message-size, empty-record and parser limits must survive the refactor.

## Migration and verification gates

1. **Extract record progress in zen-crypto.** Add retained read/write offsets and
   output queuing. Drive the existing blocking session through the same engine.
   Gate: all current vectors, tampering, replay, truncation, partial-read,
   shutdown, alignment and exactly-once cleanup tests still pass. Scripted I/O
   must force short reads/writes, EAGAIN and EINTR at record boundaries and
   within headers, ciphertext and tags; verify no duplicate output or nonce use.

2. **Make the handshake resumable.** Persist ClientHello/ServerHello, transcript,
   flight and Finished phases instead of retaining execution inside socket
   loops. Preserve binder verification and peer-Finished authentication barriers.
   Gate: existing independent peers, OpenSSL and native-to-native tests pass
   through both drivers, including fragmented handshakes and rejected clients.
   Bound admitted handshakes and scheduler work; X25519 remains CPU work even
   after socket blocking is removed.

3. **Separate socket setup from the OpenSSL adapter.** Keep platform socket ABI
   glue small and preserve nonblocking mode, close-on-exec and SIGPIPE protection.
   Remove SSL types/includes from the generic listener/connection boundary.
   Store each owning TLS engine at a stable location; HTTP slot copies should
   carry borrowed handles, not duplicate a Drop-owning session. Gate: allocation
   failure, connection timeout, abort and repeated cleanup release resources
   once, without closing unrelated descriptors.

4. **Wire an explicit native PSK HTTP/1 target.** Let the HTTP adapter translate
   raw nonblocking I/O and engine progress into readiness/runnable decisions.
   Reuse the HTTP parser, handlers, fairness budgets and std readiness. Keep PSK
   configuration distinct from certificate/private-key options. Gate: real
   listener tests show one stalled handshake or blocked writer cannot stop
   other connections; buffered progress cannot stall awaiting a nonexistent
   kernel event. Run HTTP framing, pipelining and shutdown regressions on macOS
   and Linux, plus sanitizer checks and a deliberate stalled-progress control.
   Inspect the final executable/link inputs for absence of OpenSSL and libsodium.

## Scope and remaining limits

The initial target is HTTP/1 over configured external PSKs with X25519. It does
not provide certificate chains, hostname validation, general browser HTTPS,
HRR, session tickets or KeyUpdate. Native ALPN is absent, so this migration must
not claim HTTP/2 negotiation. The existing HTTP/2 and OpenSSL paths remain
separate until their required contracts are implemented and tested.

Current TLS storage requests total 212768 bytes per active session, before HTTP
buffers and metadata: about 52 MiB for 256 sessions. The initial migration should
make allocation/admission limits explicit; shrinking handshake storage is a
subsequent optimization, not a prerequisite for copying protocol code. Passing
interoperability and sanitizer tests is not a security audit, secure-erasure
proof, or evidence of beating uWebSockets. Performance comparisons follow only
after equivalent behavior and fair workloads are established.
