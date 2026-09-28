#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
root=$(pwd)
mkdir -p build
# uSockets only: do not recursively fetch unused BoringSSL, QUIC or fuzzers.
commit=4e7578d175fcb6d2f5b3ae7ad7b13ce14f4309d8
if [ ! -d build/uWebSockets/.git ]; then
    git init build/uWebSockets
    git -C build/uWebSockets remote add origin https://github.com/uNetworking/uWebSockets.git
    git -C build/uWebSockets fetch --depth 1 origin "$commit"
    git -C build/uWebSockets checkout --detach FETCH_HEAD
fi
test "$(git -C build/uWebSockets rev-parse HEAD)" = "$commit"
git -C build/uWebSockets submodule update --init --depth 1 uSockets
sh ../zen-openssl/scripts/build-openssl.sh "$root/build"
