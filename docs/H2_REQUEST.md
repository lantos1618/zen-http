# Request header decoder

`http.http2_request` implements a bounded HPACK request decoder in Zen.
`h2_request_decoder(connection_alloc)` allocates a 4096-byte table buffer;
`decoder.decode(block, request_alloc)` returns `H2RequestHead` with method,
path, scheme, authority and optional content length. The returned string views
are copied into `request_alloc`; its owner must outlive the request. Use a
request/stream arena that can be released after the response. Reusing a
connection arena for all decode calls retains those allocations until close.
The connection allocator must outlive the decoder.

The dynamic table persists across header blocks. It starts at the RFC default
4096 bytes, supports table size updates from zero through 4096 at the start of
a block, evicts oldest entries, and supports indexed fields and indexed literal
names. Raw and Huffman strings use the existing Zen HPACK helpers; the response
client's stateless decoder has not been silently replaced. The table uses fixed
storage plus 128 metadata slots, with no allocations for persistent inserts.

Limits: 8192 compressed bytes, 100 fields, and 16384 decoded bytes including
HPACK's 32-byte per-field accounting. Table updates larger than 4096, invalid
indices, arithmetic overflow, truncated literals, invalid Huffman sequences,
and updates after a field are rejected. Header syntax validation rejects
uppercase names, unknown/repeated/out-of-order pseudo-headers, forbidden
connection fields, TE values other than `trailers`, malformed/duplicate content
length, control characters (including DEL, with interior HTAB permitted), and
leading/trailing field whitespace. Commas in authority values are rejected. Requests
need method, http/https scheme, a path, and authority (or Host fallback).

This is an initial-request decoder, not full HTTP semantics. CONNECT, extended
CONNECT and trailers are unsupported. Duplicate content length is rejected
even when equal. Host and authority comparisons conservatively require the
same spelling ignoring case; no default-port/URI normalization is attempted.
Ordinary headers are validated and counted but are not exposed in the returned
head. Scheme-versus-transport checks and actual body-length checks belong to
the network dispatcher. Authority validation is a character filter, not a
complete URI/IPv6 parser.

**Every decoder error is fatal to its connection.** A rejected block can have
already changed the dynamic table; continuing after a stream-only reset would
risk compression-state divergence. This interface does not provide an API to
drain and discard a rejected block while preserving its compression state.

Validation: `python3 scripts/check-http2-request.py` compiles three test programs
with undefined-behavior sanitization and checks their exact output. Fixtures
include independent python-hpack 4.1.0 output with alternating raw/Huffman
encoding, retained dynamic entries, dynamic name references, table eviction,
shrink and growth, plus malformed syntax, integer overflow, invalid Huffman,
and size/count limits. Tests are useful evidence, not proof of conformance,
security or interoperability with every HTTP/2 implementation.

Protocol references: [HPACK RFC 7541](https://www.rfc-editor.org/rfc/rfc7541.html)
and [HTTP/2 RFC 9113](https://www.rfc-editor.org/rfc/rfc9113.html).
