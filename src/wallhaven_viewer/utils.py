"""
Утилиты для работы с путями, кэшем и файловой системой.
"""

import hashlib
import os
import sys
from gi.repository import GLib


def resolve_path(filename: str) -> str:
    """
    Ищет ресурс по следующим местам (в указанном порядке):

    1. dev-режим: ../data/(css|ui)/<file> или ../data/<file>
    2. установленный Flatpak: /app/share/wallhaven_viewer/(css|ui)/<file>
    3. рядом с текущим модулем (старое расположение)
    """
    import pathlib

    here = pathlib.Path(__file__).parent
    project_root = (here / ".." / "..").resolve()
    dev_data = project_root / "data"

    # 1. поиск в каталоге data/
    candidates = [
        dev_data / filename,                   # data/<file>
        dev_data / "css" / filename,           # data/css/<file>
        dev_data / "ui" / filename,            # data/ui/<file>
    ]

    # 2. путь внутри Flatpak
    flatpak_base = pathlib.Path("/app/share/wallhaven_viewer")
    candidates += [
        flatpak_base / filename,
        flatpak_base / "css" / filename,
        flatpak_base / "ui" / filename,
    ]

    # 3. исторический — рядом с .py
    candidates.append(here / filename)

    for path in candidates:
        if path.exists():
            return str(path)

    # fallback — вернём абсолютный путь для отладки
    return str((here / filename).resolve())

def get_cache_dir():
    """
    Возвращает путь к папке кэша Wallhaven Viewer.

    Returns:
        str or None: Абсолютный путь к папке кэша или None в случае ошибки.
    """
    cache_dir = os.path.join(GLib.get_user_cache_dir(), "wallhaven_viewer_cache")
    if not os.path.exists(cache_dir):
        try:
            os.makedirs(cache_dir)
        except OSError as e:
            print(f"Ошибка создания папки кэша: {e}")
            return None
    return cache_dir


def get_meta_dir():
    """
    Возвращает директорию для хранения sidecar-метаданных (JSON) к скачанным обоям.
    Файлы метаданных хранятся здесь, а не рядом с изображениями.

    Returns:
        str or None: Абсолютный путь к папке meta или None в случае ошибки.
    """
    base = get_cache_dir()
    if not base:
        return None
    meta_dir = os.path.join(base, "meta")
    if not os.path.exists(meta_dir):
        try:
            os.makedirs(meta_dir, exist_ok=True)
        except OSError as e:
            print(f"Ошибка создания папки метаданных: {e}")
            return None
    return meta_dir


def get_sidecar_path_for_image(image_path):
    """
    Возвращает путь к JSON-файлу метаданных для данного изображения.
    Файл хранится в отдельной директории (кэш), а не рядом с изображением.

    Args:
        image_path (str): Путь к файлу изображения.

    Returns:
        str or None: Абсолютный путь к .json файлу или None если директория метаданных недоступна.
    """
    meta_dir = get_meta_dir()
    if not meta_dir:
        return None
    abs_path = os.path.abspath(image_path)
    key = hashlib.sha256(abs_path.encode("utf-8")).hexdigest()
    return os.path.join(meta_dir, key + ".json")


def get_gnome_backgrounds_dir():
    """
    Возвращает директорию обоев GNOME (~/.local/share/backgrounds).
    Обои, скопированные сюда, отображаются в меню «Параметры → Внешний вид → Обои».

    В Flatpak GLib.get_user_data_dir() указывает на песочницу приложения,
    а не на реальный ~/.local/share, поэтому для Flatpak используем явный путь.
    """
    if os.environ.get("FLATPAK_ID"):
        # В Flatpak пишем в реальный каталог пользователя (доступ есть при --filesystem=home)
        base = os.path.join(os.path.expanduser("~"), ".local", "share")
    else:
        base = GLib.get_user_data_dir()
    if not base:
        return None
    bg_dir = os.path.join(base, "backgrounds")
    if not os.path.exists(bg_dir):
        try:
            os.makedirs(bg_dir, exist_ok=True)
        except OSError as e:
            print(f"Ошибка создания папки обоев GNOME: {e}")
            return None
    return bg_dir


def extract_wallpaper_id(filename):
    """
    Извлекает ID обоев из имени файла.

    Поддерживает различные форматы:
    - yqqxq7.jpg → yqqxq7
    - wallhaven-yqqxq7.jpg → yqqxq7
    - full-yqqxq7.png → yqqxq7

    Args:
        filename (str): Имя файла.

    Returns:
        str: ID обоев или пустая строка, если не удалось извлечь.
    """
    name = filename.split('.')[0]
    # Удаляем возможные префиксы
    for prefix in ['wallhaven-', 'full-', 'w-', 'wh-']:
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name


def get_cache_path(thumb_url, cache_dir=None):
    """
    Возвращает путь к файлу в кэше для заданного URL миниатюры.

    Args:
        thumb_url (str): URL миниатюры.
        cache_dir (str, optional): Путь к папке кэша. Если None, будет получен автоматически.

    Returns:
        str or None: Путь к файлу в кэше или None, если cache_dir недоступен.
    """
    if not thumb_url:
        return None

    if cache_dir is None:
        cache_dir = get_cache_dir()

    if not cache_dir:
        return None

    filename = thumb_url.split('/')[-1]
    return os.path.join(cache_dir, filename)


def clean_cache(max_age_days=7, max_total_mb=300):
    """
    Очищает кэш:
      1) удаляет файлы старше `max_age_days`,
      2) если суммарный размер кэша превышает `max_total_mb`, удаляет старые файлы до укладки под лимит.

    Args:
        max_age_days (int): время жизни файлов в днях.
        max_total_mb (int|None): лимит кэша в мегабайтах; None — не применять ограничение.
    """
    try:
        cache_dir = get_cache_dir()
        if not cache_dir:
            return

        import time
        now = time.time()
        max_age = max_age_days * 24 * 60 * 60
        max_total_bytes = (max_total_mb * 1024 * 1024) if max_total_mb else None

        files = []
        for name in os.listdir(cache_dir):
            path = os.path.join(cache_dir, name)
            try:
                if not os.path.isfile(path):
                    continue
                st = os.stat(path)
                files.append({
                    'path': path,
                    'mtime': st.st_mtime,
                    'size': st.st_size,
                    'removed': False
                })
            except Exception:
                continue

        # 1) удалить по возрасту
        for f in files:
            try:
                if now - f['mtime'] > max_age:
                    os.remove(f['path'])
                    f['removed'] = True
            except Exception:
                continue

        # 2) проверить суммарный размер и удалить старые файлы, если нужно
        remaining = [f for f in files if not f['removed']]
        total = sum(f['size'] for f in remaining)

        if max_total_bytes and total > max_total_bytes:
            # сортируем по времени изменения — старые первыми
            remaining.sort(key=lambda x: x['mtime'])
            for f in remaining:
                try:
                    os.remove(f['path'])
                    total -= f['size']
                    if total <= max_total_bytes:
                        break
                except Exception:
                    continue
    except Exception:
        return

import os, subprocess

def wallpaper_portal_available() -> bool:
    """True, если org.freedesktop.portal.Wallpaper реагирует."""
    try:
        # qdbus/dbus-send отсутствуют в некоторых системах; ловим любые ошибки
        out = subprocess.check_output(
            ["gdbus", "call", "--session",
             "--dest", "org.freedesktop.portal.Desktop",
             "--object-path", "/org/freedesktop/portal/desktop",
             "--method", "org.freedesktop.DBus.Properties.Get",
             "org.freedesktop.portal.Wallpaper", "version"],
            stderr=subprocess.DEVNULL,
            timeout=2
        )
        return b"(" in out  # ответ пришёл
    except Exception:
        return False