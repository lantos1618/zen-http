# HTTP/2 server state foundation

`src/http/http2_server_state.zen` implements bounded stream and flow-control
bookkeeping in Zen. It has no C bindings, heap allocation, socket access or TLS
calls. It is **not a listening HTTP/2 server**, a complete frame dispatcher, or a
claim of HTTP/2 compliance. The existing HTTP/2 client is separate.

Implemented and tested:

- Up to 32 admitted client streams with increasing odd 31-bit IDs; rejected
  capacity attempts consume their ID, and released/reset slots can be reused.
- Independent local and remote end-of-stream state. Receiving DATA after remote
  end or sending DATA after local end fails. Ordinary release requires both
  directions closed; reset releases the slot immediately.
- Separate connection and stream receive windows, initialized to 65,535 bytes.
  Receiving DATA checks both before changing either. Credit is separately tracked
  for each scope; over-credit and nonpositive credit are rejected.
- Connection credit survives reset so discarded bytes can still be credited.
- Send-window reservation checks both scopes before modifying either. Stream
  windows may become negative after an initial-window setting reduction; empty
  DATA remains possible. Window updates reject zero and overflow.
- Initial-window settings update live streams transactionally: an overflow on
  any stream leaves all windows and the initial value unchanged. New streams use
  the latest accepted initial send window.
- A header-block continuation barrier that only admits CONTINUATION frames on
  the matching stream while a block is unfinished.
- Draining refuses new streams while existing ones can finish. `drain()` returns
  the highest **admitted** stream ID, a conservative GOAWAY boundary if admission
  precedes application processing. `last_stream()` instead returns the highest
  observed new ID, including streams refused by capacity or draining; do not use
  it as the last processed GOAWAY stream ID.

The relevant protocol rules are in RFC 9113
[stream states and identifiers](https://www.rfc-editor.org/rfc/rfc9113.html#section-5.1),
[flow control](https://www.rfc-editor.org/rfc/rfc9113.html#section-6.9),
[CONTINUATION](https://www.rfc-editor.org/rfc/rfc9113.html#section-6.10), and
[GOAWAY](https://www.rfc-editor.org/rfc/rfc9113.html#section-6.8).

## Integration contract and outstanding work

The caller must validate the preface, SETTINGS sequencing, frame headers and
payloads, request pseudo-headers, trailers and HPACK blocks. Admit a stream only
once the caller accepts its initial HEADERS. The continuation methods track block
exclusivity, not header semantics. The caller must apply `frame_allowed` to **all
inbound frames**, including unknown extensions; `receive_data` checks it itself.
A rejected request can still require HPACK decoding to retain compression state.

`receive_data` takes the whole flow-controlled DATA payload size, including
padding and its length byte. It does not validate frame-size limits or padding.
Credit is a bookkeeping commitment to emit WINDOW_UPDATE after application
consumption or deliberate discard; no frame is emitted here. The module cannot
verify whether the application actually consumed those bytes. `send_data`
reserves flow-control credit for a committed outgoing DATA frame; the caller
must check response header sequencing, frame size and output queue capacity
before reservation. It does not enforce outbound CONTINUATION exclusivity.

Error variants are local bookkeeping failures, not wire error codes. The future
dispatcher must map them to the correct stream or connection error, including
idle/closed-stream distinctions and the relevant late-frame exceptions. This
module does not retain an unbounded history of closed streams. No buffering of
request bodies, HPACK request decoder, response encoder, network loop, stream
scheduler, SETTINGS acknowledgements, timeout policy, server ALPN selection or
interoperability test has been implemented by this change.

The next integration milestone is a network HTTP/2 server using this state with
request-header decoding and bounded per-stream buffers. It will need independent
peer tests and malformed-frame coverage before any protocol or performance claim.

## Checks

Run `python3 scripts/check-http2-server.py`. It stages only the state module and
two test programs, compiles through Zen to C, then runs with clang's undefined
behavior sanitizer. It requires the sibling `zen-actor-runtime/zen` compiler and
standard library, but no OpenSSL or network access. The package-wide HTTP/2 check
also discovers these tests. The tests cover lifecycle and capacity boundaries,
CONTINUATION exclusivity, credit after reset, independent send limits, negative
windows, overflow rollback and empty DATA at a negative stream window.

These are deterministic state tests. They establish the exercised bookkeeping
behavior, not HTTP/2 interoperability, security, fairness or speed.


A later integration now uses this component in `http2_server.zen`. See
[the experimental network endpoint](H2_NETWORK.md) and [request decoder](H2_REQUEST.md)
for newly implemented behavior and remaining limitations. The state component
itself still performs none of those I/O operations.
