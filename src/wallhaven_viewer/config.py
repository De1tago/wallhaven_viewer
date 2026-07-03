"""
Модуль констант и настроек приложения Wallhaven Viewer.
"""

import os
import configparser
from gi.repository import GLib

# API константы
API_URL = "https://wallhaven.cc/api/v1/search"
WALLPAPER_API_URL = "https://wallhaven.cc/api/v1/w"

# Опции разрешений
RESOLUTION_OPTIONS = [
    ("Любое", ""),
    ("1024x768 (XGA)", "1024x768"),
    ("1280x720 (HD)", "1280x720"),
    ("1920x1080 (FHD)", "1920x1080"),  # Wallhaven использует "at least" для 1920x1080
    ("2560x1440 (QHD)", "2560x1440"),
    ("3840x2160 (4K)", "3840x2160"),
    ("5120x2880 (5K)", "5120x2880"),
    ("7680x4320 (8K)", "7680x4320"),
]

# Опции соотношения сторон
RATIO_OPTIONS = [
    ("Любое", ""),
    ("16:9", "16x9"),
    ("16:10", "16x10"),
    ("4:3", "4x3"),
    ("5:4", "5x4"),
    ("21:9", "21x9"),
    ("32:9", "32x9"),
]

# Опции сортировки
SORT_OPTIONS = ["Relevance", "Random", "Date Added", "Views", "Favorites", "Toplist", "Hot"]

# Настройки по умолчанию
DEFAULT_SETTINGS = {
    'api_key': '',
    'download_path': '',
    'columns': '4',
    'last_query': '',
    'cat_general': 'true',
    'cat_anime': 'true',
    'cat_people': 'true',
    'purity_sfw': 'true',
    'purity_sketchy': 'false',
    'purity_nsfw': 'false',
    'sort_index': '5',
    'resolution_index': '0',
    'ratio_index': '0',
    'copy_to_gnome_backgrounds': 'false',
}


def get_config_path():
    """Возвращает путь к config.ini в папке ~/.config пользователя."""
    config_dir = os.path.join(GLib.get_user_config_dir(), "wallhaven-viewer")
    if not os.path.exists(config_dir):
        os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, "config.ini")


def load_settings():
    """
    Загружает настройки из INI-файла.

    Если файл не найден, возвращает словарь с настройками по умолчанию.

    Returns:
        dict: Словарь текущих или дефолтных настроек приложения.
    """
    config = configparser.ConfigParser()
    config_path = get_config_path()
    config.read(config_path)
    settings = DEFAULT_SETTINGS.copy()
    if 'Settings' in config:
        for key in settings:
            if key in config['Settings']:
                settings[key] = config['Settings'][key]
    return settings


def save_settings(settings_dict):
    """
    Сохраняет переданный словарь настроек в INI-файл.

    Args:
        settings_dict (dict): Словарь настроек, которые необходимо сохранить.
    """
    config = configparser.ConfigParser()
    config['Settings'] = {k: v for k, v in settings_dict.items() if k in DEFAULT_SETTINGS}
    config_path = get_config_path()
    with open(config_path, 'w') as configfile:
        config.write(configfile)

