"""
Модуль для загрузки и обработки изображений.
"""

import os
import threading
import requests
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GdkPixbuf, GLib, Gdk, Gtk
from wallhaven_viewer.utils import get_cache_path, get_cache_dir


class ImageLoader:
    """Класс для загрузки и обработки изображений."""

    @staticmethod
    def load_pixbuf_from_bytes(img_bytes):
        """
        Создает GdkPixbuf из байтов изображения.

        Использует GdkPixbuf.PixbufLoader для корректной обработки данных.

        Args:
            img_bytes (bytes): Сырые байты изображения (JPEG, PNG и т. д.).

        Returns:
            GdkPixbuf.Pixbuf or None: Созданный Pixbuf или None в случае ошибки.
        """
        try:
            loader = GdkPixbuf.PixbufLoader()
            loader.write(img_bytes)
            loader.close()
            return loader.get_pixbuf()
        except Exception:
            return None

    @staticmethod
    def download_image(url, callback, progress_callback=None, timeout=60):
        """
        Загружает изображение по URL с поддержкой прогресса.

        Args:
            url (str): URL изображения.
            callback (callable): Функция обратного вызова с аргументом (bytes или None).
            progress_callback (callable, optional): Функция для обновления прогресса (current, total).
            timeout (int): Таймаут запроса в секундах.
        """
        def worker():
            try:
                resp = requests.get(url, stream=True, timeout=timeout)
                resp.raise_for_status()

                total_bytes = int(resp.headers.get('content-length', 0))
                current_bytes = 0
                image_data = b''

                for chunk in resp.iter_content(chunk_size=8192):
                    image_data += chunk
                    current_bytes += len(chunk)
                    if progress_callback and total_bytes > 0:
                        GLib.idle_add(progress_callback, current_bytes, total_bytes)

                GLib.idle_add(callback, image_data)
            except Exception:
                GLib.idle_add(callback, None)

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def load_thumbnail(local_path=None, cache_path=None, thumb_url=None, target_size=None, callback=None):
        """
        Загружает миниатюру обоев, пробуя несколько источников.

        Порядок попыток:
        1. Локальный файл
        2. Кэш
        3. Сеть

        Args:
            local_path (str, optional): Путь к локальному файлу.
            cache_path (str, optional): Путь к файлу в кэше.
            thumb_url (str, optional): URL миниатюры.
            target_size (tuple, optional): Целевой размер (width, height).
            callback (callable, optional): Функция обратного вызова (pixbuf, wallpaper_id).

        Returns:
            None (загрузка выполняется асинхронно).
        """
        def worker():
            pixbuf = None
            target_width, target_height = target_size if target_size else (300, 200)

            # 1. ЛОКАЛЬНЫЙ ФАЙЛ
            if local_path and os.path.exists(local_path):
                try:
                    file_size = os.path.getsize(local_path)
                    if file_size < 100:
                        raise ValueError("Файл слишком мал")

                    loader = GdkPixbuf.PixbufLoader()
                    with open(local_path, "rb") as f:
                        chunk = f.read(1024)
                        while chunk:
                            loader.write(chunk)
                            chunk = f.read(1024)
                    loader.close()

                    original_pixbuf = loader.get_pixbuf()
                    if original_pixbuf:
                        width = original_pixbuf.get_width()
                        height = original_pixbuf.get_height()

                        scale_factor = min(target_width / width, target_height / height)
                        new_width = max(1, int(width * scale_factor))
                        new_height = max(1, int(height * scale_factor))

                        pixbuf = original_pixbuf.scale_simple(
                            new_width,
                            new_height,
                            GdkPixbuf.InterpType.BILINEAR
                        )
                        if pixbuf and callback:
                            GLib.idle_add(callback, pixbuf)
                            return
                except Exception:
                    pass

            # 2. КЭШ
            if pixbuf is None and cache_path and os.path.exists(cache_path):
                try:
                    img_data = open(cache_path, "rb").read()
                    if len(img_data) >= 100:
                        p = ImageLoader.load_pixbuf_from_bytes(img_data)
                        if p:
                            pixbuf = p.scale_simple(
                                target_width, target_height, GdkPixbuf.InterpType.BILINEAR
                            )
                except Exception:
                    pass

            # 3. СЕТЬ
            if pixbuf is None and thumb_url:
                try:
                    resp = requests.get(thumb_url, timeout=15)
                    resp.raise_for_status()
                    img_data = resp.content
                    if len(img_data) >= 100:
                        p = ImageLoader.load_pixbuf_from_bytes(img_data)
                        if p:
                            pixbuf = p.scale_simple(
                                target_width, target_height, GdkPixbuf.InterpType.BILINEAR
                            )

                            # Сохраняем в кэш
                            if cache_path:
                                try:
                                    with open(cache_path, "wb") as f:
                                        f.write(img_data)
                                except Exception:
                                    pass
                except Exception:
                    pass

            # Финальный вызов
            if callback:
                GLib.idle_add(callback, pixbuf if pixbuf else None)

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def get_image_format_from_bytes(img_bytes):
        """
        Определяет формат изображения по его байтам.

        Args:
            img_bytes (bytes): Байты изображения.

        Returns:
            str: Имя формата ('jpeg', 'png', и т.д.) или 'jpeg' по умолчанию.
        """
        try:
            loader = GdkPixbuf.PixbufLoader()
            loader.write(img_bytes)
            content_type = loader.get_format().get_name()
            loader.close()
            return content_type
        except Exception:
            return "jpeg"

