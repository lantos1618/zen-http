#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python=${PYTHON:-python3}
"$python" -m pip install --disable-pip-version-check --no-cache-dir --target build/python-deps -r tests/http2-requirements.txt
