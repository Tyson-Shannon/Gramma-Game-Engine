#!/usr/bin/env bash
# Build every pinned Gramma toolchain image (or one named stage).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKER=${DOCKER:-docker}

build_stage() {
    local stage="$1" tag="$2"
    "$DOCKER" build -f "$ROOT/docker/Dockerfile" --target "$stage" \
        -t "$tag" "$ROOT"
}

if [[ $# -gt 0 ]]; then
    case "$1" in
        gbdk|cc65|sms|dev) stages=("$1") ;;
        *)
            echo "usage: $0 [gbdk|cc65|sms|dev]" >&2
            exit 2
            ;;
    esac
else
    stages=(gbdk cc65 sms dev)
fi

for stage in "${stages[@]}"; do
    case "$stage" in
        gbdk) tag=gramma/gbdk:4.6.0 ;;
        cc65) tag=gramma/cc65:2.19 ;;
        sms)  tag=gramma/sms:4.5.0 ;;
        dev)  tag=gramma/dev:latest ;;
    esac
    echo "==> $stage -> $tag"
    build_stage "$stage" "$tag"
done
