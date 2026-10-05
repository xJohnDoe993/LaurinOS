#!/bin/bash
# Shared installer helpers. No shell module is executed as a separate process.
install_repo_file() {
    local relative="$1" target="$2"
    install -D -m 0644 "${REPO_DIR}/${relative}" "$target"
}
# render receives repository-relative source paths
render_repo_file() {
    local relative="$1" target="$2"
    /usr/bin/python3 "${REPO_DIR}/tools/render-config.py" "${REPO_DIR}/${relative}" "$target" \
        "APP_ENTRIES=${APP_ENTRIES:-}" "WEBAPP_ENTRIES=${WEBAPP_ENTRIES:-}"
}
install_runtime() {
    /usr/bin/python3 "${REPO_DIR}/tools/deploy.py" --initial
}
