# Native TLS integration with the HTTP reactor

This is a staged migration, not an implemented server backend. Native Zen
TLS supports blocking external-PSK handshakes, including X25519 PSK-DHE
client/server roles. Established sessions now expose resumable application
record progress as well as the existing blocking driver. The HTTP reactor
still uses the zen-openssl transport. The native HTTP client adapter consumes
an already authenticated blocking session.

## Current boundary

- `src/http/transport.zen` owns nonblocking socket setup and the Zen
  listener/connection records. They still carry opaque OpenSSL session/context
  handles; `src/transport.h` no longer contains SSL layouts or includes.
- `src/http/transport.zen` maps OpenSSL progress to bytes, read/write interest,
  and closure. It also handles raw socket errno and buffered TLS input.
- `src/http/server.zen` limits each drive round to 64 transitions/eight responses
  and uses std readiness plus a local runnable queue. Connection descriptors
  are copied between slot storage and local variables.
- In zen-crypto, handshake functions still perform blocking I/O. The session
  now retains partial ciphertext input and pending output through `feed`,
  `queue_record`, `pending_output`, `acknowledge`, and `read_plaintext`. Its
  blocking driver uses that same record engine. `SocketFd` still maps syscall
  failures to socket faults; calling the blocking driver on a nonblocking
  descriptor treats EAGAIN as terminal. No reactor socket adapter exists yet.

Calling the blocking native accept/read/write APIs from this reactor would
therefore block other connections or abort on ordinary nonblocking backpressure.
Wrapping those calls in an actor does not solve the transport contract.

## Shared protocol engine

Continue extracting one resumable protocol engine in zen-crypto, then make both
blocking and reactor adapters drive it. Application records now share such an
engine; the handshake remains to be converted. Do not create an HTTP-specific copy of TLS
parsing, transcript handling, key derivation, or record protection.

The engine needs persistent handshake phase, partial header/body offsets,
handshake-message accumulation, directional sequences, authenticated plaintext
remaining to deliver, and ciphertext remaining to write. Its proposed boundary
accepts bounded ciphertext input, exposes bounded pending output, acknowledges
bytes written, and reports progress such as `NeedInput`, `NeedOutput`,
`Runnable`, `Established`, or a terminal error. These names describe a proposed
unified handshake boundary; there is no resumable handshake API yet. Buffer
ownership and view lifetimes must be explicit.

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

1. **Record progress is implemented in zen-crypto.** Established sessions
   retain partial header/body input and sealed output until acknowledged. The
   blocking session uses these same transitions. Byte-fed tests cover partial
   and zero-progress retries, independent ciphertext agreement, duplex storage,
   malformed input, closure and exactly-once cleanup. These simulate transport
   progress; they do not exercise actual OS EAGAIN/EINTR. The eventual socket
   adapter must add those tests and preserve queued ciphertext across them.
   See [the session contract](https://github.com/lantos1618/zen-crypto/blob/main/docs/TLS13.md#resumable-application-records).

2. **Make the handshake resumable.** Persist ClientHello/ServerHello, transcript,
   flight and Finished phases instead of retaining execution inside socket
   loops. Preserve binder verification and peer-Finished authentication barriers.
   Gate: existing independent peers, OpenSSL and native-to-native tests pass
   through both drivers, including fragmented handshakes and rejected clients.
   Bound admitted handshakes and scheduler work; X25519 remains CPU work even
   after socket blocking is removed.

3. **Separate transport backend selection.** Socket setup and handle allocation
   have moved to Zen, preserving nonblocking mode, close-on-exec and SIGPIPE
   protection. Select native versus OpenSSL session state explicitly rather
   than treating the current opaque handles as interchangeable.
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

## Next extraction: server handshake

The smallest server integration step is to make `tls13_psk_dhe_accept` a
blocking driver over a resumable server handshake. Reuse its existing
ClientHello parser, binder verification and key-schedule functions. Retain
phases for receiving ClientHello, preparing and sending ServerHello, sending
the encrypted flight, receiving client Finished, and establishing the session.
Partial output acknowledgements must never rebuild or reseal either flight.
Preserve the existing record-count, CCS-count and handshake-size limits.

The handshake workspace at `34000..99536` overlaps the established record
engine's input buffers. Do not call `Tls13Session.feed` during the handshake.
Keep the current handshake layout until authentication completes, retain
unconsumed input at the adapter, and stop consuming input while a flight is
pending. Transfer the allocations into the established session exactly once,
after client Finished is verified and the server flight has been acknowledged.
The resumable API must define PSK/identity lifetimes beyond a single call and
release allocations on cancellation or any terminal error.

Gate this extraction with fragmented ClientHello/Finished, bytewise record
headers, short and zero output acknowledgements, EOF at every phase, malformed
CCS, replay, and failed ownership handoff. Re-run independent Python, OpenSSL
and native-pair checks. Only subsequent real reactor tests can establish that
one stalled handshake does not block another connection; X25519 still requires
bounded admission and scheduling even after socket waits become resumable.

## Scope and remaining limits

The initial target is HTTP/1 over configured external PSKs with X25519. It does
not provide certificate chains, hostname validation, general browser HTTPS,
HRR, session tickets or KeyUpdate. Native ALPN is absent, so this migration must
not claim HTTP/2 negotiation. The existing HTTP/2 and OpenSSL paths remain
separate until their required contracts are implemented and tested.

Current TLS storage requests total 212768 bytes per active session, before HTTP
buffers and metadata: about 52 MiB for 256 sessions. The initial migration should
make allocation/admission limits explicit; shrinking handshake storage is a
separate optimization. Passing
interoperability and sanitizer tests is not a security audit, secure-erasure
proof, or evidence of beating uWebSockets. Performance comparisons follow only
after equivalent behavior and fair workloads are established.

The record-engine milestone is published in zen-crypto `81189a6`. Existing
native HTTP regressions pass through its shared blocking driver on macOS
(UBSan) and Linux (ASan and UBSan): 207 parser split cases, eight parser
rejections and eight encrypted exchange cases. The runner now treats generated
comparison-parenthesis warnings as errors. [Validation details](https://github.com/lantos1618/zen-crypto/blob/main/tests/validation/tls13-record-progress-2026-09-29.txt)
record the exact compiler, source revision and limits.
