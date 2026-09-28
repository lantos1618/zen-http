#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python=${PYTHON:-python3}
"$python" -c 'import ssl; assert ssl.HAS_TLSv1_3, "Use a Python runtime with TLS 1.3 support"'
"$python" -B -m unittest discover -s bench -p test_benchmark.py
go_bin=${GO_BIN:-}
if [ -z "$go_bin" ]; then
    if [ -x ../zen-bench/build/toolchains/go/bin/go ]; then go_bin=../zen-bench/build/toolchains/go/bin/go
    else go_bin=$(command -v go); fi
fi
GOCACHE="$PWD/build/go-test-cache" GOTOOLCHAIN=local "$go_bin" test bench/load.go bench/load_test.go
sh scripts/build.sh
compiler=${ZEN_COMPILER:-../zen-actor-runtime/zen}
stdlib=${ZEN_STD:-../zen-actor-runtime/src}
ln -sfn "$PWD/tests/transport.zen" build/source/transport_test.zen
ZEN_STD="$stdlib" "$compiler" build build/source --entry transport_test.zen --emit-c -o build/transport-test.c
clang -O2 -g -fsanitize=undefined -fno-sanitize-recover=all -Isrc -I../zen-crypto/src -Ibuild/openssl/include \
    build/transport-test.c build/openssl/lib/libssl.a build/openssl/lib/libcrypto.a -o build/transport-test
./build/transport-test
ln -sfn "$PWD/tests/chunked.zen" build/source/chunked_test.zen
ZEN_STD="$stdlib" "$compiler" build build/source --entry chunked_test.zen --emit-c -o build/chunked-test.c
clang -O2 -g -fsanitize=undefined -fno-sanitize-recover=all build/chunked-test.c -o build/chunked-test
./build/chunked-test
"$python" tests/check.py
"$python" tests/disconnect.py
"$python" scripts/check-http2.py
"$python" scripts/check-http2-server.py
"$python" scripts/check-http2-request.py
"$python" scripts/check-http2-network.py
clang -O2 -g -fsanitize=undefined -fno-sanitize-recover=all \
    -I"$stdlib/std/net" -Isrc -I../zen-crypto/src -Ibuild/openssl/include build/h2-server.c \
    build/openssl/lib/libssl.a build/openssl/lib/libcrypto.a -o build/zen-h2-sanitized-server
"$python" scripts/check-http2-network.py --binary build/zen-h2-sanitized-server
clang -O2 -g -fsanitize=undefined -fno-sanitize-recover=all \
    -I"$stdlib/std/net" -Isrc -I../zen-crypto/src -Ibuild/openssl/include -include src/reactor.h \
    build/zen.c build/openssl/lib/libssl.a build/openssl/lib/libcrypto.a \
    -o build/zen-sanitized-server
"$python" tests/check.py --server zen-sanitized
"$python" tests/disconnect.py --server zen-sanitized
