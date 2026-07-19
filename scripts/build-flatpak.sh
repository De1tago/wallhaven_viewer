#!/usr/bin/env bash
set -euo pipefail

DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PROJECT_ROOT="$( realpath "$DIR/.." )"

cd "$PROJECT_ROOT"

MANIFEST="flatpak/cc.wallhaven.Viewer.yml"
BUILD_DIR="build-dir"
REPO_DIR="repo"
BUNDLE="wallhaven-viewer.flatpak"

echo "==> Сборка Flatpak..."
flatpak-builder --force-clean --user "$BUILD_DIR" "$MANIFEST"

echo "==> Создание репозитория..."
flatpak-builder --repo="$REPO_DIR" --force-clean "$BUILD_DIR" "$MANIFEST"

echo "==> Создание bundle..."
flatpak build-bundle "$REPO_DIR" "$BUNDLE" cc.wallhaven.Viewer

echo "==> Готово! Bundle: $BUNDLE"
echo "    Установка: flatpak install --user $BUNDLE"
