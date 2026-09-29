# Moving HTTP callers out of std

The compiler removal is tracked in [Zen PR #12](https://github.com/lantos1618/zen/pull/12).
The removal statements below describe that revision; older compiler checkouts
still contain the std APIs.

HTTP/1 and HTTP/2 are package APIs in `zen-http`. The compiler's standard
library no longer supplies `std.net.http`, `std.net.http2` or `env.net.http()`.
This is an explicit dependency migration; there is no compatibility facade or
silent fallback inside std. OS sockets, readiness, memory and actor primitives
remain standard-library responsibilities.

## Imports and construction

Replace HTTP/1 imports and the environment accessor:

```zen
// Before
HttpClient, HttpResponse, HttpError = std.net.http
client = env.net.http();

// After
HttpClient, HttpResponse, HttpError = http.client
client = HttpClient();
```

`HttpClient.post(alloc, url, headers, body)` and `post_into(..., sink)` keep their
existing argument shapes. The normal HTTPS client still uses `zen-openssl` and
certificate verification. Native PSK TLS remains a separate experimental API.

Offline callers can avoid TLS imports by using the shared response decoder:

```zen
parse_response, parse_response_into = http.response_decode
HttpError, HttpResponse, HttpResponseMeta = http.response_types
```

For HTTP/2, replace `std.net.http2` with `http.http2`. Internal codec imports
move from paths such as `std.net.http2.http2_hpack` to `http.http2_hpack`.
`H2Client`, actor-based `post_stream`, `H2Chunk` and the response APIs are
implemented by the package. Do not replace actor delivery with a second local
protocol implementation.

Applications must declare/stage the `http` package and its `tls` dependency,
following this repository's `build.zen` and `scripts/build.sh`. Importing a
package name alone does not download or resolve its dependencies. The package
uses sibling `zen-openssl` sources and OpenSSL link settings for its ordinary
HTTP clients and servers.

## Preserved compiler corpus coverage

Seven former compiler fixtures now run against package implementations:

| Former compiler fixture | Package fixture and runner |
| --- | --- |
| `net/http_post` | `tests/client-corpus/http_post.zen`, `scripts/check-client-corpus.py` |
| `actor/http2_receiver_protocol` | `tests/client-corpus/http2_receiver_protocol.zen`, `scripts/check-client-corpus.py` |
| `net/http2_chunk` | `tests/http2/http2_chunk.zen`, `scripts/check-http2.py` |
| `net/http2_frame_fields` | `tests/http2/http2_frame_fields.zen`, `scripts/check-http2.py` |
| `net/http2_hpack` | `tests/http2/http2_hpack.zen`, `scripts/check-http2.py` |
| `net/http2_hpack_boundaries` | `tests/http2/http2_hpack_boundaries.zen`, `scripts/check-http2.py` |
| `net/http2_static_table` | `tests/http2/http2_static_table.zen`, `scripts/check-http2.py` |

All expected outputs were retained byte-for-byte. The five existing HTTP/2
copies matched the std fixtures after import-path normalization. The two new
copies change only imports: the HTTP/1 case preserves framing, header limits,
streaming Sink errors and buffered response coverage; the actor case preserves
real actor delivery, JSON decoding of an owned H2 chunk, and type-checking the
generic streaming request API. The new runner uses UBSan, and both runners are
included in `scripts/check.sh` without adding Python crypto dependencies.

Validation: the full macOS `scripts/check.sh` run passed with the rebuilt
compiler and std sources after removing std HTTP. This includes all seven
migrated corpus cases, TLS verification/ALPN checks, actor delivery, server
readiness cleanup and UBSan targets. This migration changes ownership and
imports; it makes no new performance claim.
