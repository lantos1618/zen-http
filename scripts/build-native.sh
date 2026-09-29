#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
root=$(pwd)
compiler=${ZEN_COMPILER:-$root/../zen-crypto-numeric/zen}
stdlib=${ZEN_STD:-$root/../zen-crypto-numeric/src}
crypto=${ZEN_CRYPTO:-$root/../zen-crypto}
stage="$root/build/native-server-source"
mkdir -p "$stage/http"
for module in native_server native_transport server_core socket_setup chunked; do
    cp "$root/src/http/$module.zen" "$stage/http/$module.zen"
done
cp "$crypto"/src/*.zen "$stage/"
cp examples/echo_native.zen "$stage/main.zen"
"$compiler" build "$stage" --std "$stdlib" --emit-c -o build/zen-native-server.c
"${CC:-clang}" -O2 -g -Werror=parentheses-equality -fsanitize="${SANITIZERS:-undefined}" -fno-sanitize-recover=all \
    -Isrc -I"$stdlib/std/net" build/zen-native-server.c -o build/zen-native-server
nm -u build/zen-native-server > build/native-server-symbols.txt
if grep -E '[[:space:]]_?(SSL_|OPENSSL_|EVP_|sodium_|crypto_|randombytes)' build/native-server-symbols.txt; then
    echo 'Native server unexpectedly references an external crypto backend' >&2
    exit 1
fi
