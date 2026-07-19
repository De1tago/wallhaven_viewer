#!/usr/bin/env bash
set -euo pipefail

DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PROJECT_ROOT="$( realpath "$DIR/.." )"

cd "$PROJECT_ROOT"

echo "==> Активация виртуального окружения..."
if [ -d venv ]; then
    source venv/bin/activate
fi

echo "==> Установка зависимостей для сборки..."
pip install -q pyinstaller packaging setuptools

echo "==> Сборка бинарника через PyInstaller..."
pyinstaller --clean wallhaven-viewer.spec

echo "==> Готово! Бинарник в dist/wallhaven-viewer/"
echo "    Запуск: ./dist/wallhaven-viewer/wallhaven-viewer"
