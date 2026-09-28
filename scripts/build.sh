#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
root=$(pwd)
compiler=${ZEN_COMPILER:-$root/../zen-actor-runtime/zen}
stdlib=${ZEN_STD:-$root/../zen-actor-runtime/src}
test -f "$stdlib/std/net/zen_readiness.h" || {
    echo 'This revision requires std.net.readiness; set ZEN_STD to its compiler checkout (docs/STD_READINESS.md).' >&2
    exit 1
}
openssl="$root/build/openssl"
mkdir -p build
test -f "$openssl/lib/libssl.a" || { echo 'Build dependencies first; see README.md' >&2; exit 1; }
mkdir -p build/source
ln -sfn "$root/src/http" build/source/http
ln -sfn "$root/../zen-openssl/src/tls.zen" build/source/tls.zen
ln -sfn "$root/examples/echo.zen" build/source/main.zen
ZEN_STD="$stdlib" "$compiler" build "$root/build/source" --emit-c -o build/zen.c
clang -O3 -flto -DNDEBUG -I"$stdlib/std/net" -Isrc -I../zen-openssl/src -I"$openssl/include" -include src/reactor.h build/zen.c \
    "$openssl/lib/libssl.a" "$openssl/lib/libcrypto.a" -o build/zen-server > build/zen-build.log 2>&1
ln -sfn "$root/tests/client.zen" build/source/client_test.zen
ZEN_STD="$stdlib" "$compiler" build "$root/build/source" --entry client_test.zen --emit-c -o build/client.c
clang -O3 -flto -DNDEBUG -I../zen-openssl/src -I"$openssl/include" build/client.c "$openssl/lib/libssl.a" "$openssl/lib/libcrypto.a" \
    -o build/client-test > build/client-build.log 2>&1
ln -sfn "$root/examples/echo_h2.zen" build/source/h2_main.zen
ZEN_STD="$stdlib" "$compiler" build "$root/build/source" --entry h2_main.zen --emit-c -o build/h2-server.c
clang -O3 -flto -DNDEBUG -I"$stdlib/std/net" -Isrc -I../zen-openssl/src -I"$openssl/include" build/h2-server.c \
    "$openssl/lib/libssl.a" "$openssl/lib/libcrypto.a" -o build/zen-h2-server > build/h2-build.log 2>&1
make -B -C build/uWebSockets/uSockets CC=clang CXX=clang++ WITH_OPENSSL=1 \
    CFLAGS="-I$openssl/include" CXXFLAGS="-I$openssl/include" > build/usockets-build.log 2>&1
clang++ -std=c++20 -O3 -flto -DNDEBUG -DUWS_HTTPRESPONSE_NO_WRITEMARK \
    -Ibuild/uWebSockets/src -Ibuild/uWebSockets/uSockets/src -I"$openssl/include" \
    bench/uws.cpp build/uWebSockets/uSockets/uSockets.a "$openssl/lib/libssl.a" "$openssl/lib/libcrypto.a" \
    -lz -o build/uws-server > build/uws-build.log 2>&1
go_bin=${GO_BIN:-}
if [ -z "$go_bin" ]; then
    if [ -x ../zen-bench/build/toolchains/go/bin/go ]; then go_bin=../zen-bench/build/toolchains/go/bin/go
    else go_bin=$(command -v go); fi
fi
GOCACHE="$root/build/go-cache" GOTOOLCHAIN=local "$go_bin" build -o build/load bench/load.go
if [ ! -f build/cert.pem ]; then
    OPENSSL_CONF="$root/build/openssl-src/apps/openssl.cnf" "$openssl/bin/openssl" req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
        -keyout build/key.pem -out build/cert.pem -days 30 -subj /CN=localhost \
        -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1' > build/cert.log 2>&1
fi
{
    uname -a
    clang --version
    "$go_bin" version
    "$openssl/bin/openssl" version
    git -C build/uWebSockets rev-parse HEAD
    git -C build/uWebSockets/uSockets rev-parse HEAD
    shasum -a 256 "$compiler" src/http/*.zen src/transport.h src/reactor.h "$stdlib/std/net/readiness.zen" "$stdlib/std/net/zen_readiness.h" ../zen-openssl/src/tls.zen ../zen-openssl/src/zen_tls.h bench/uws.cpp bench/load.go build/zen.c build/client.c build/h2-server.c build/zen-h2-server build/zen-server build/uws-server build/load "$openssl/lib/libssl.a" "$openssl/lib/libcrypto.a" build/cert.pem
} > build/environment.txt
