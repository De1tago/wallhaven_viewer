"""
Модуль окна полноразмерного просмотра обоев.
"""
import os
import shutil
import threading
import time
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, Gio, GLib, GdkPixbuf

from wallhaven_viewer.utils import resolve_path, get_gnome_backgrounds_dir, get_sidecar_path_for_image, wallpaper_portal_available
from wallhaven_viewer.image_loader import ImageLoader
from wallhaven_viewer.api import WallhavenAPI
from gi.repository import Gtk as _Gtk

class FullImageWindow(Gtk.Window):
    """
    Окно для полноразмерного просмотра и управления обоями.

    Осуществляет загрузку полного изображения, его сохранение на диск
    и установку в качестве обоев рабочего стола.

    Args:
        parent: Ссылка на родительское окно.
        image_url (str): URL-адрес полноразмерного изображения.
        download_path (str): Путь для сохранения файлов по умолчанию.
        local_path (str, optional): Локальный путь к файлу, если он уже скачан.
    """

    def __init__(self, parent, image_url, download_path, local_path=None):
        super().__init__(transient_for=parent)
        self.parent_window = parent
        self.image_url = image_url
        self.download_path = download_path
        self.local_path = local_path
        # Если локальный путь не передан, попробуем найти файл в списке скачанных у родителя
        try:
            if not self.local_path and hasattr(self.parent_window, 'downloaded_files'):
                found = self.parent_window.downloaded_files.get(self.wallpaper_id)
                if found and os.path.exists(found):
                    self.local_path = found
        except Exception:
            pass
        self.image_data = None
        # Из url вида .../wallhaven-<id>.<ext> извлекаем чистый id (без префикса "wallhaven-")
        raw_name = image_url.split('/')[-1].split('.')[0]
        if raw_name.startswith('wallhaven-'):
            self.wallpaper_id = raw_name[len('wallhaven-'):]
        else:
            self.wallpaper_id = raw_name

        # Создаем новый экземпляр Gtk.Builder для каждого окна
        builder = Gtk.Builder.new_from_file(resolve_path("fullimage.ui"))

        # Загружаем root из нового экземпляра
        content = builder.get_object("root")
        if not content:
            raise RuntimeError("root container not found in fullimage.ui")

        xml_window = builder.get_object("full_image_window")

        w, h = xml_window.get_default_size()
        self.set_default_size(w, h)
        self.set_title(f"Wallhaven - ID: {self.wallpaper_id}")

        content = xml_window.get_child()
        if content:
            content.unparent()
            overlay = Gtk.Overlay()
            overlay.set_child(content)

            self._error_bar = Gtk.InfoBar()
            self._error_bar.set_visible(False)
            self._error_bar.add_css_class("error")
            self._error_bar.set_halign(Gtk.Align.CENTER)
            self._error_bar.set_valign(Gtk.Align.START)
            self._error_bar.set_margin_top(10)
            self._error_bar.set_margin_start(10)
            self._error_bar.set_margin_end(10)
            self._error_bar.set_show_close_button(True)
            self._error_bar.connect("response", lambda bar, resp: bar.set_visible(False))

            self._error_label = Gtk.Label()
            self._error_bar.add_child(self._error_label)

            overlay.add_overlay(self._error_bar)
            self.set_child(overlay)

        self.picture = builder.get_object("picture")
        self.spinner = builder.get_object("spinner")
        self.save_btn = builder.get_object("save_btn")
        self.progress_bar = builder.get_object("progress_bar")

        self.set_wp_btn = builder.get_object("set_wp_btn")

        self.save_btn.connect("clicked", self.on_save_clicked)
        self.set_wp_btn.connect("clicked", self.on_set_wallpaper_clicked)
        # Метаданные и теги
        self.meta_label = builder.get_object("meta_label")
        self.meta_box = builder.get_object("meta_box")
        self.tags_flowbox = builder.get_object("tags_flowbox")
        # Обертка FlowBox — прокручиваемый контейнер, управление высотой будет динамическим
        self.tags_scrolled = builder.get_object("tags_scrolled")
        # Подпишемся на изменение размера контейнера тегов, чтобы пересчитывать число столбцов
        try:
            if self.tags_scrolled:
                self.tags_scrolled.connect("size-allocate", lambda w, alloc: GLib.idle_add(self.update_tag_columns))
                GLib.idle_add(self.update_tag_columns)
        except Exception:
            pass
        try:
            if self.meta_box:
                self.meta_box.set_visible(False)
        except Exception:
            pass
        if not self.meta_label:
            print("⚠️ meta_label не найден в UI")
        if not self.tags_flowbox:
            print("⚠️ tags_flowbox не найден в UI")

        # Если локальный файл передан — сразу загружаем его и помечаем как скачанный
        if self.local_path:
            self.load_image_and_info(local_mode=True)
            try:
                self.set_wp_btn.set_sensitive(True)
            except Exception:
                pass
            try:
                self.save_btn.set_sensitive(False)
                pixbuf = None
                if getattr(self, 'image_data', None):
                    try:
                        pixbuf = ImageLoader.load_pixbuf_from_bytes(self.image_data)
                    except Exception:
                        pixbuf = None

                if pixbuf:
                    resolution = ''
                    try:
                        if isinstance(self._meta_info, dict):
                            resolution = self._meta_info.get('resolution', '')
                    except Exception:
                        resolution = ''

                    GLib.idle_add(self._apply_loaded_image, pixbuf, resolution, self._meta_info, self._pending_tags)

                self.save_btn.set_label("Скачано")
            except Exception:
                pass
        else:
            # Запускаем в потоке, так как делаем API запрос и загрузку изображения
            threading.Thread(target=self.load_image_and_info, daemon=True, args=(False,)).start()

        # Инициализируем контейнеры для отложенного показа мета/тегов
        self._pending_tags = []
        self._meta_info = None
        # Поддерживаем кликабельные ссылки в мета-лейбле (для автора)
        try:
            if self.meta_label:
                self.meta_label.set_use_markup(True)
                self.meta_label.connect('activate-link', self.on_meta_activate_link)
        except Exception:
            pass
    def show_error(self, message):
        GLib.idle_add(self._show_error_ui, message)

    def _show_error_ui(self, message):
        self._error_label.set_text(message)
        self._error_bar.set_visible(True)
        GLib.timeout_add_seconds(5, lambda: self._error_bar.set_visible(False))

    def update_progress(self, current_bytes, total_bytes):
        """
        Обновляет прогресс-бар во время загрузки полноразмерного изображения.
        Вызывается из фонового потока — выполняет обновление через GLib.idle_add.
        """
        try:
            if total_bytes and total_bytes > 0:
                fraction = float(current_bytes) / float(total_bytes)
                percent = int(fraction * 100)
                GLib.idle_add(self._set_progress_ui, fraction, percent)
        except Exception:
            pass

    def _set_progress_ui(self, fraction, percent):
        try:
            if self.progress_bar:
                self.progress_bar.set_fraction(fraction)
                self.progress_bar.set_text(f"Загрузка: {percent}%")
                self.progress_bar.set_visible(True)
            if self.spinner:
                self.spinner.set_visible(False)
        except Exception:
            pass
    def load_image_and_info(self, local_mode=False):
        """Загружает полноразмерное изображение и метаданные.

        Если передан `local_mode`, пытается загрузить из `self.local_path`.
        Иначе запрашивает метаданные у API (с ретраями) и запускает загрузку изображения по сети.
        """
        resolution = ""

        # 1) Локальная загрузка
        if local_mode and self.local_path:
            try:
                with open(self.local_path, 'rb') as f:
                    self.image_data = f.read()

                # Попробуем прочитать sidecar из директории метаданных (не рядом с файлом)
                resolution = ""
                try:
                    import json
                    sidecar = get_sidecar_path_for_image(self.local_path)
                    if sidecar and os.path.exists(sidecar):
                        #print(f"✅ sidecar found for local image: {sidecar} (instance id={id(self)})")
                        with open(sidecar, 'r', encoding='utf-8') as sf:
                            j = json.load(sf)
                            meta = j.get('meta')
                            tags = j.get('tags')
                            self._meta_info = meta
                            self._pending_tags = tags or []
                            resolution = meta.get('resolution', '') if isinstance(meta, dict) else ''
                            #print(f"🔖 sidecar loaded (instance id={id(self)}): meta={'set' if self._meta_info else 'empty'}, tags_count={len(self._pending_tags)}; meta_repr={repr(self._meta_info)}")
                    else:
                        # Если sidecar отсутствует — делаем запрос к API и записываем sidecar
                        #print(f"⚠️ sidecar not found for {self.local_path}, querying API")
                        wallpaper_info = None
                        for attempt in range(1, 4):
                            try:
                                wallpaper_info = WallhavenAPI.get_wallpaper_info(self.wallpaper_id)
                                if wallpaper_info:
                                    break
                            except Exception:
                                pass
                            if attempt < 3:
                                time.sleep(0.6)

                        resolution = wallpaper_info.get('resolution', '') if wallpaper_info else ''

                        if wallpaper_info:
                            try:
                                file_size = wallpaper_info.get('file_size') or wallpaper_info.get('size') or 0
                                try:
                                    size_mb = float(file_size) / (1024 * 1024)
                                    size_str = f"{size_mb:.2f} MB"
                                except Exception:
                                    size_str = str(file_size)

                                uploader = wallpaper_info.get('uploaded_by') or wallpaper_info.get('uploader') or wallpaper_info.get('user') or ''
                                views = wallpaper_info.get('views', '')
                                favorites = wallpaper_info.get('favorites', '') or wallpaper_info.get('favourites', '')

                                self._meta_info = {
                                    'size': size_str,
                                    'uploader': uploader,
                                    'views': views,
                                    'favorites': favorites,
                                    'resolution': resolution,
                                }
                            except Exception:
                                self._meta_info = None

                            try:
                                tags = wallpaper_info.get('tags', []) or []
                                self._pending_tags = tags
                            except Exception:
                                self._pending_tags = []

                            # Записываем sidecar рядом с файлом, чтобы в следующий раз не дергать API
                            try:
                                with open(sidecar, 'w', encoding='utf-8') as sf:
                                    json.dump({'meta': self._meta_info, 'tags': self._pending_tags}, sf, ensure_ascii=False, indent=2)
                            except Exception:
                                pass
                        else:
                            self._pending_tags = []
                except Exception:
                    pass

                GLib.idle_add(self.update_title, resolution)
                #print(f"load_image_and_info finished (instance id={id(self)}), _meta_info set={'yes' if self._meta_info else 'no'}, tags_count={len(self._pending_tags) if self._pending_tags else 0}")
            except Exception as e:
                self.show_error(f"Ошибка чтения файла: {e}")
                self.image_data = None
        else:
            # 2) Получаем метаданные от API с ретраем
            wallpaper_info = None
            for attempt in range(1, 4):
                try:
                    wallpaper_info = WallhavenAPI.get_wallpaper_info(self.wallpaper_id)
                    if wallpaper_info:
                        break
                except Exception:
                    pass
                if attempt < 3:
                    time.sleep(0.6)

            resolution = wallpaper_info.get('resolution', '') if wallpaper_info else ''

            # Собираем метаданные
            if wallpaper_info:
                try:
                    file_size = wallpaper_info.get('file_size') or wallpaper_info.get('size') or 0
                    try:
                        size_mb = float(file_size) / (1024 * 1024)
                        size_str = f"{size_mb:.2f} MB"
                    except Exception:
                        size_str = str(file_size)

                    uploader = wallpaper_info.get('uploaded_by') or wallpaper_info.get('uploader') or wallpaper_info.get('user') or ''
                    views = wallpaper_info.get('views', '')
                    favorites = wallpaper_info.get('favorites', '') or wallpaper_info.get('favourites', '')

                    self._meta_info = {
                        'size': size_str,
                        'uploader': uploader,
                        'views': views,
                        'favorites': favorites,
                    }
                except Exception:
                    self._meta_info = None

                # Теги
                try:
                    tags = wallpaper_info.get('tags', []) or []
                    self._pending_tags = tags
                except Exception:
                    self._pending_tags = []
            else:
                self._pending_tags = []

            if wallpaper_info is None:
                GLib.idle_add(self.update_title, resolution)
            else:
                GLib.idle_add(self.update_title, resolution)

            # Загрузка изображения по сети
            def on_image_loaded(img_data):
                if img_data:
                    self.image_data = img_data
                    try:
                        pixbuf = ImageLoader.load_pixbuf_from_bytes(img_data)
                        if pixbuf:
                            GLib.idle_add(self.update_image, pixbuf)
                    except Exception as e:
                        self.show_error(f"Ошибка обработки изображения: {e}")
                        GLib.idle_add(lambda: self.progress_bar.set_visible(False))
                else:
                    GLib.idle_add(lambda: self.spinner.set_visible(False))
                    GLib.idle_add(lambda: self.progress_bar.set_visible(False))

            ImageLoader.download_image(
                self.image_url,
                on_image_loaded,
                progress_callback=self.update_progress,
                timeout=60,
            )
            

        # 2. Обновление UI для локального режима
        if local_mode and self.image_data:
            try:
                pixbuf = ImageLoader.load_pixbuf_from_bytes(self.image_data)
                if pixbuf:
                    GLib.idle_add(self.update_image, pixbuf)
            except Exception:
                GLib.idle_add(lambda: self.progress_bar.set_visible(False))

    def populate_tags(self, tags):
        """
        Заполняет FlowBox с тегами.

        Args:
            tags (list): Список тегов (словари или строки).
        """
        if not self.tags_flowbox:
            print("⚠️ populate_tags: tags_flowbox is None")
            return

        try:
            # Очистка старых детей
            while True:
                child = self.tags_flowbox.get_first_child()
                if child is None:
                    break
                self.tags_flowbox.remove(child)

            # Добавляем новые теги
            for t in tags:
                try:
                    name = t.get('name') if isinstance(t, dict) else str(t)
                    btn = Gtk.Button.new_with_label(name)
                    btn.add_css_class('pill')

                    def make_on_click(tag_name):
                        def on_click(_btn):
                            try:
                                if hasattr(self.parent_window, 'search_and_present'):
                                    self.parent_window.search_and_present(tag_name)
                                else:
                                    self.parent_window.start_new_search(tag_name)
                                self.parent_window.present()
                            except Exception as e:
                                print(f"Ошибка при клике по тегу: {e}")
                        return on_click

                    btn.connect('clicked', make_on_click(name))

                    try:
                        fb_child = Gtk.FlowBoxChild()
                        fb_child.set_child(btn)
                        self.tags_flowbox.append(fb_child)
                    except Exception:
                        self.tags_flowbox.append(btn)
                except Exception as e:
                    print(f"Ошибка при добавлении тега: {e}")
                    continue
            # Адаптивная установка высоты контейнера с тегами по количеству тегов
            try:
                count = len(tags) if tags is not None else 0
                if count <= 8:
                    h = 100
                elif count <= 20:
                    h = 160
                else:
                    h = 260
                if hasattr(self, 'tags_scrolled') and self.tags_scrolled:
                    # Устанавливаем рекомендуемую высоту; Gtk примет значение при отображении
                    self.tags_scrolled.set_property('height-request', h)
            except Exception:
                pass

            # Пересчитываем число столбцов после добавления элементов
            try:
                GLib.idle_add(self.update_tag_columns)
            except Exception:
                pass
        except Exception as e:
            print(f"Ошибка в populate_tags: {e}")

    def update_title(self, resolution):
        """Обновляет заголовок окна с информацией о разрешении."""
        res_str = f" ({resolution})" if resolution else ""
        self.set_title(f"Wallhaven - ID: {self.wallpaper_id}{res_str}")

    def update_image(self, pixbuf):
        """
        Отображает загруженное изображение в Gtk.Picture.

        Args:
            pixbuf (GdkPixbuf.Pixbuf): Загруженное изображение.
        """
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)

        self.picture.set_paintable(texture)
        self.spinner.set_visible(False)
        self.progress_bar.set_visible(False)

        if not self.local_path:
            self.save_btn.set_sensitive(True)
        self.set_wp_btn.set_sensitive(True)

        # После отображения изображения показываем сохранившиеся метаданные и теги
        import threading as _th
        #print(f"🖼️ update_image: image shown, scheduling meta/tags display (instance id={id(self)}, thread={_th.current_thread().name})")
        #print(f"    current _meta_info repr: {repr(self._meta_info)}; pending_tags count: {len(self._pending_tags) if self._pending_tags else 0}")
        # Всегда показываем блок мета/тегов после отображения изображения
        GLib.idle_add(self.show_meta_and_tags)

    def _apply_loaded_image(self, pixbuf, resolution, meta, tags):
        """
        Вызывается в main thread: устанавливает мета/теги, обновляет заголовок и отображает изображение.
        Это гарантирует корректный порядок действий и отсутствие гонок между
        присвоением `_meta_info/_pending_tags` и `update_image`.
        """
        try:
            self._meta_info = meta
            self._pending_tags = tags or []
            try:
                self.update_title(resolution)
            except Exception:
                pass
            try:
                self.update_image(pixbuf)
            except Exception:
                pass
        except Exception as e:
            print(f"Ошибка в _apply_loaded_image: {e}")

    def on_save_clicked(self, btn):
        """Обработчик нажатия кнопки сохранения. Сохраняет файл либо по умолчанию, либо через диалог."""
        if not self.image_data:
            return

        # Определение формата
        content_type = ImageLoader.get_image_format_from_bytes(self.image_data)
        ext = '.jpg' if 'jpeg' in content_type else '.png'
        name = self.wallpaper_id + ext

        if self.download_path and os.path.exists(self.download_path):
            try:
                local_path = os.path.join(self.download_path, name)
                with open(local_path, "wb") as f:
                    f.write(self.image_data)

                try:
                    self._write_sidecar(local_path)
                except Exception:
                    pass

                self.local_path = local_path
                self.save_btn.set_label("Скачано")
                self.save_btn.set_sensitive(False)
                self.set_wp_btn.set_sensitive(True)
                self._copy_to_gnome_backgrounds_if_enabled(local_path)

                # Обновляем список скачанных файлов в главном окне
                self.parent_window.scan_downloaded_wallpapers()
                self.parent_window.refresh_downloaded_state_in_ui()

            except Exception:
                self.open_dialog(name)
        else:
            self.open_dialog(name)

    def open_dialog(self, name):
        """Открывает диалог сохранения файла, если путь по умолчанию недоступен."""
        d = Gtk.FileDialog()
        d.set_initial_name(name)
        d.save(self, None, self.on_save_finish)

    def on_save_finish(self, d, res):
        """Обработчик завершения диалога сохранения."""
        try:
            f = d.save_finish(res)
            if f:
                local_path = f.get_path()
                with open(local_path, "wb") as file:
                    file.write(self.image_data)

                # Сохраняем сопутствующие метаданные рядом с файлом (sidecar)
                try:
                    self._write_sidecar(local_path)
                except Exception:
                    pass

                self.local_path = local_path
                self.save_btn.set_label("Скачано")
                self.save_btn.set_sensitive(False)
                self.set_wp_btn.set_sensitive(True)
                self._copy_to_gnome_backgrounds_if_enabled(local_path)

                # Обновляем список скачанных файлов в главном окне
                self.parent_window.scan_downloaded_wallpapers()
                self.parent_window.refresh_downloaded_state_in_ui()
        except Exception as e:
            self.show_error(f"Ошибка сохранения: {e}")

    def _write_sidecar(self, image_path):
        """
        Записывает sidecar JSON-файл в отдельную директорию метаданных (не рядом с изображением),
        содержащий `_meta_info` и `_pending_tags`, чтобы при открытии локального файла
        можно было восстановить метаданные без обращения к API.
        """
        try:
            import json
            sidecar_path = get_sidecar_path_for_image(image_path)
            if not sidecar_path:
                return
            meta = {
                'meta': self._meta_info,
                'tags': self._pending_tags,
            }
            with open(sidecar_path, 'w', encoding='utf-8') as sf:
                json.dump(meta, sf, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Не удалось записать sidecar: {e}")

    def _copy_to_gnome_backgrounds_if_enabled(self, image_path):
        """Если в настройках включено — копирует файл в ~/.local/share/backgrounds."""
        if not getattr(self.parent_window, 'settings', {}).get('copy_to_gnome_backgrounds') == 'true':
            return
        bg_dir = get_gnome_backgrounds_dir()
        if not bg_dir or not image_path or not os.path.exists(image_path):
            return
        try:
            dest = os.path.join(bg_dir, os.path.basename(image_path))
            shutil.copy2(image_path, dest)
            print(f"✅ Скопировано в меню обоев GNOME: {dest}")
        except Exception as e:
            self.show_error(f"Ошибка копирования в меню обоев GNOME: {e}")

    from wallhaven_viewer.utils import wallpaper_portal_available

    def on_set_wallpaper_clicked(self, _btn):
        if not self.local_path or not os.path.exists(self.local_path):
            self.show_error("Нет локального файла — нельзя установить обои")
            return

        used_portal = False
        if wallpaper_portal_available() and os.getenv("FLATPAK_ID"):
            # пробуем портал ТОЛЬКО внутри Flatpak и если backend отвечает
            try:
                import dbus, dbus.types
                bus = dbus.SessionBus()
                iface = dbus.Interface(
                    bus.get_object("org.freedesktop.portal.Desktop",
                                "/org/freedesktop/portal/desktop"),
                    "org.freedesktop.portal.Wallpaper")
                fd = os.open(self.local_path, os.O_RDONLY)
                try:
                    iface.SetWallpaperFile(
                        "",
                        dbus.types.UnixFd(fd),
                        {'show-preview': dbus.Boolean(False, variant_level=1)}
                    )
                    print(f"✅ Обои установлены через портал: {self.local_path}")
                    used_portal = True
                finally:
                    os.close(fd)
            except Exception as e:
                print(f"⚠️  Портал недоступен ({e}); fallback на GSettings")

        if not used_portal:
            self._set_wallpaper_worker(self.local_path)

    def _set_wallpaper_worker(self, path):
        """
        Устанавливает обои через GSettings.
        Безопасно проверяет доступность ключей.
        """
        try:
            # Преобразуем путь в file:// URI (экранируем пробелы и спецсимволы)
            file_uri = Gio.File.new_for_path(os.path.abspath(path)).get_uri()

            # Создаём Settings
            settings = Gio.Settings.new('org.gnome.desktop.background')

            # Проверяем схему
            schema_source = Gio.SettingsSchemaSource.get_default()
            schema = schema_source.lookup('org.gnome.desktop.background', True)

            if not schema:
                self.show_error("Схема org.gnome.desktop.background не найдена")
                return

            # Устанавливаем обои
            if schema.has_key('picture-uri-dark'):
                settings.set_string('picture-uri', file_uri)
                settings.set_string('picture-uri-dark', file_uri)
                print(f"✅ Обои установлены (с поддержкой тёмного режима): {file_uri}")
            else:
                settings.set_string('picture-uri', file_uri)
                print(f"✅ Обои установлены: {file_uri}")

        except Exception as e:
            self.show_error(f"Ошибка установки обоев: {e}")
            import traceback
            traceback.print_exc()

    def show_meta_and_tags(self):
        """
        Показывает блок с метаданными и тегами после того, как основное изображение отображено.
        """
        try:
            import threading as _th
            #print(f"🔔 show_meta_and_tags (instance id={id(self)}, thread={_th.current_thread().name}): meta_info_repr={repr(self._meta_info)}, tags_count={len(self._pending_tags) if self._pending_tags else 0}")
            # Формируем отображение метаданных: размер, автор (кликабельно), просмотры и лайки
            if self.meta_label:
                if self._meta_info:
                    size = self._meta_info.get('size') or ''
                    uploader = self._meta_info.get('uploader') or ''
                    views = self._meta_info.get('views') or ''
                    favorites = self._meta_info.get('favorites') or ''
                    # Если uploader — словарь, попробуем извлечь имя
                    if isinstance(uploader, dict):
                        uploader = uploader.get('username') or uploader.get('name') or str(uploader)
                    # Экранируем текст для безопасной вставки в markup
                    esc = GLib.markup_escape_text
                    parts = []
                    if size:
                        parts.append(f"Размер: {esc(size)}")
                    if uploader:
                        parts.append(f"Автор: <a href='https://wallhaven.cc/user/{esc(uploader)}'>{esc(uploader)}</a>")
                    if views != '':
                        parts.append(f"Просмотры: {esc(str(views))}")
                    if favorites != '':
                        parts.append(f"Лайки: {esc(str(favorites))}")
                    markup = " | ".join(parts) if parts else "Информация недоступна"
                    try:
                        self.meta_label.set_markup(markup)
                    except Exception:
                        try:
                            self.meta_label.set_text(markup)
                        except Exception:
                            self.meta_label.set_text("Информация недоступна")
                else:
                    self.meta_label.set_text("Информация недоступна")
            # Заполняем теги; если их нет — показываем плейсхолдер
            try:
                if self._pending_tags:
                    self.populate_tags(self._pending_tags)
                else:
                    # Очищаем flowbox и добавляем метку "Теги отсутствуют"
                    try:
                        # Очистка через существующую логику
                        self.populate_tags([])
                    except Exception:
                        pass
                    placeholder = Gtk.Label(label="Теги отсутствуют")
                    placeholder.add_css_class('dim-label')
                    try:
                        fb_child = Gtk.FlowBoxChild()
                        fb_child.set_child(placeholder)
                        self.tags_flowbox.append(fb_child)
                    except Exception:
                        self.tags_flowbox.append(placeholder)
            except Exception as e:
                print(f"Ошибка при populate_tags после загрузки: {e}")
            if self.meta_box:
                self.meta_box.set_visible(True)
        except Exception as e:
            print(f"Ошибка при показе мета/тегов: {e}")

    def update_tag_columns(self):
        """
        Пересчитывает рекомендованное число столбцов (`max-children-per-line`) для
        `tags_flowbox` на основе ширины `tags_scrolled` / окна.
        """
        try:
            if not self.tags_flowbox:
                return

            # Приблизительная ширина одного «пилла» тега (можно подобрать эмпирически)
            approx_tag_w = 120

            width = 0
            try:
                if hasattr(self, 'tags_scrolled') and self.tags_scrolled:
                    width = self.tags_scrolled.get_allocated_width()
            except Exception:
                width = 0

            # fallback на ширину окна, если не удалось получить ширину скролла
            if not width or width <= 0:
                try:
                    width = self.get_allocated_width()
                except Exception:
                    width = 800

            cols = max(1, int(width // approx_tag_w))
            cols = min(cols, 8)

            # Пробуем установить через метод, если он доступен, иначе через свойство
            try:
                setter = getattr(self.tags_flowbox, 'set_max_children_per_line', None)
                if callable(setter):
                    setter(cols)
                else:
                    # Попытка через сеттер свойства (имя в форме GObject)
                    try:
                        self.tags_flowbox.set_property('max-children-per-line', cols)
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass

    def on_meta_activate_link(self, label, uri):
        # Открываем профиль автора в системном браузере (с фолбеком на xdg-open)
        try:
            Gio.AppInfo.launch_default_for_uri(uri, None)
            return True
        except Exception:
            try:
                GLib.spawn_command_line_async(f"xdg-open '{uri}'")
                return True
            except Exception as e:
                print(f"Не удалось открыть ссылку: {e}")
        return False