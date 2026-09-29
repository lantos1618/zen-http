#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python=${PYTHON:-python3}
sh scripts/build-native.sh
"$python" scripts/check-native-transport.py
"$python" scripts/check-native-server.py
"$python" scripts/check-native-http.py
