# Bounded chunked request decoding

The HTTP/1 server now accepts `Transfer-Encoding: chunked` requests. The decoder
is written in Zen, incrementally tracks size lines, chunk payloads, delimiters
and trailers, and decodes payload bytes in place. It retains a distinct original
wire cursor so that pipelined requests begin after the terminal trailer CRLF,
not after the shorter decoded body. Each received payload byte is copied once;
line scanning resumes at its previous position after fragmentation.

This is a deliberately restricted request-body implementation, not complete
HTTP/1 transfer-coding support and not a streaming handler API:

- The synchronous handler still receives a borrowed complete decoded body.
- Decoded body maximum: 65,536 bytes. Entire encoded request maximum: 73,728
  bytes, including request headers, chunk overhead and trailers. Many tiny
  chunks can reach the encoded limit before the decoded limit.
- Only one Transfer-Encoding field whose trimmed value is `chunked`
  (case-insensitive) is accepted. Coding lists and other codings are rejected.
- Content-Length together with Transfer-Encoding is rejected in either order,
  as are duplicate Transfer-Encoding fields.
- Chunk sizes accept hexadecimal digits, including uppercase, with at most
  16 digits. Extensions, whitespace around sizes, signs and `0x` prefixes are
  conservatively rejected. Legal chunk extensions therefore remain unsupported.
- Chunk delimiters must be CRLF. Trailer lines are at most 1,024 bytes each,
  at most 64 fields and 8,192 total bytes including the terminating CRLF.
- Only `Digest`, `Content-Digest` and `X-Checksum` trailer names are accepted.
  Values are syntax-checked but discarded, **not verified**. Other trailers,
  including framing/routing/authentication fields, are rejected. This narrow
  allowlist excludes some valid HTTP trailer use cases.
- Malformed requests close the connection; they do not receive a diagnostic
  HTTP error response. Requests that stop before completion time out under
  the existing idle timeout.
- Decoding work per drive remains bounded by the input buffer, but a large
  number of tiny chunks is not separately budgeted by the scheduler.

Validation added:

- `tests/chunked.zen` tests every split point, repeated decoder calls with no
  new bytes, one-byte-at-a-time input, final cursor position and preservation of
  a pipelined suffix. It ran successfully under UBSan.
- `tests/check.py` exercises network fragmentation at every split, mixed
  chunked/fixed-length pipelines, empty and exactly 64 KiB decoded bodies,
  5,000 tiny chunks, size overflow, encoded-size exhaustion, malformed delimiters,
  unsupported extensions/codings, ambiguous framing and invalid/excessive trailers.
- The full existing HTTP/1 suite plus new chunked tests passed over plaintext
  and TLS against the normal build and UBSan build.

These checks establish tested behavior on the current macOS host. They do not
establish comprehensive RFC compliance, Linux correctness, fuzzing coverage or
performance improvement. No updated performance result is claimed for this code.
