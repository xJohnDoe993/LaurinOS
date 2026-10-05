#!/bin/bash
set -Eeuo pipefail
REPO_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec /usr/bin/python3 "${REPO_DIR}/tools/deploy.py" "$@"
