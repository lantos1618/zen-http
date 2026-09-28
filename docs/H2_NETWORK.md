# Experimental HTTP/2 network endpoint

`examples/echo_h2.zen` runs a prior-knowledge HTTP/2 plaintext server on
`127.0.0.1:18082`; `--tls` enables TLS1.3 with h2 ALPN. It is an experimental echo endpoint, not a general-purpose
HTTP/2 server API or a production-ready implementation.

The frame dispatcher, stream state, HPACK request decoding, body buffering,
flow-control accounting, and response generation are written in Zen. Socket
ownership/readiness still use the package's existing native adapters. The
response is `200` with the original body for `POST /echo`, or `404` with
`not found` for other valid ordinary requests.

The implementation accepts the client connection preface, exchanges SETTINGS,
acknowledges PING, handles HEADERS/CONTINUATION, DATA padding, stream reset,
and connection/stream WINDOW_UPDATE. Completed responses wait for both send
windows and finish with END_STREAM. Multiple streams can be open within one
connection. HPACK state persists across requests. Unsupported client PUSH_PROMISE
and malformed framing are rejected.

Limits and missing behavior:

- One active TCP connection is serviced at a time. This is not the HTTP/1
  server's multi-connection scheduler, and a slow peer prevents other connections from being serviced. Extra
  accepts are rejected while the active connection waits for I/O.
- 32 active streams, 16KiB received frames, 8KiB compressed header blocks,
  64KiB buffered request bodies, and 128 requests per connection.
- Bodies are fully buffered before response generation; there is no streaming
  application handler or configurable public server API.
- Each connection owns an arena, released on disconnect. Request decoding uses
  this arena; the request-count limit bounds retained header allocations.
- After 128 requests have completed, the server sends a successful GOAWAY and
  closes. This is a resource limit, not graceful application shutdown.
- Requests with trailers, CONNECT, HTTP/1 upgrade, and priority scheduling are
  unsupported. PRIORITY is validated but does not affect scheduling.
- Most malformed request/protocol errors currently produce a connection-level
  PROTOCOL_ERROR rather than the precise stream/connection error distinctions
  required for full conformance. Oversized frames produce FRAME_SIZE_ERROR.
- Peer GOAWAY currently closes the connection rather than draining pending
  responses. Missing SETTINGS acknowledgments do not have a dedicated timer.
- A read/write operation has a ten-second deadline. There is no request-level
  deadline for a peer that keeps sending frames.
- No HTTP/2 throughput claim follows from this implementation. Correctness
  interoperability checks cover selected behaviors, not full RFC conformance.

See `scripts/check-http2-network.py` for independently encoded test traffic and
its assertions. Test execution results should be reported separately from this
implementation description.


TLS selection logic is a Zen native callback installed through a typed ABI shim
in zen-openssl. A client offering ALPN without h2 fails the handshake. A client
omitting ALPN can complete TLS but is closed before HTTP/2 responses are sent.
The local certificate/key paths are fixed test fixtures. This is not a
configurable public TLS server API.

The independent hyper-h2 peer checks plaintext and TLS: interleaved streams,
HPACK dynamic/Huffman values, CONTINUATION fragmentation, 64KiB bodies, padding,
PING/reset, zero-window stream isolation/resumption, malformed frames/headers,
128-request GOAWAY, and ALPN/certificate rejection. Exact payloads and completed
streams are checked. No HTTP/2 benchmark or comprehensive conformance test is
claimed. Response metadata is minimal; content-length is not emitted, and HTTP
method-specific response semantics remain incomplete.
