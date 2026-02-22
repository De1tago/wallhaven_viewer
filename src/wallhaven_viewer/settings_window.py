"""
Модуль окна настроек приложения.
"""

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio
from wallhaven_viewer.config import load_settings, save_settings


class SettingsWindow(Gtk.Window):
    """
    Окно настроек приложения.

    Позволяет пользователю настроить API-ключ, путь для сохранения обоев
    и количество колонок в сетке главного окна.

    Args:
        parent (MainWindow): Ссылка на родительское окно.
    """

    def __init__(self, parent):
        super().__init__(title="Настройки")
        self.set_modal(True)
        self.set_transient_for(parent)
        self.set_default_size(400, 300)

        self.parent_window = parent
        self.current_settings = load_settings()

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        vbox.set_margin_start(20)
        vbox.set_margin_end(20)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(20)
        self.set_child(vbox)

        # API Key
        vbox.append(Gtk.Label(label="<b>API Ключ (для NSFW):</b>", use_markup=True, xalign=0))
        self.entry_api = Gtk.Entry()
        self.entry_api.set_text(self.current_settings['api_key'])
        vbox.append(self.entry_api)

        vbox.append(Gtk.Separator())

        # Путь сохранения
        vbox.append(Gtk.Label(label="<b>Папка для сохранения:</b>", use_markup=True, xalign=0))
        hbox_path = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        vbox.append(hbox_path)

        self.entry_path = Gtk.Entry()
        self.entry_path.set_placeholder_text("Не выбрана (спрашивать каждый раз)")
        self.entry_path.set_text(self.current_settings['download_path'])
        self.entry_path.set_hexpand(True)
        self.entry_path.set_can_focus(False)
        hbox_path.append(self.entry_path)

        btn_path = Gtk.Button(icon_name="folder-open-symbolic")
        btn_path.connect("clicked", self.on_select_folder)
        hbox_path.append(btn_path)

        btn_clear_path = Gtk.Button(icon_name="user-trash-symbolic")
        btn_clear_path.connect("clicked", lambda x: self.entry_path.set_text(""))
        hbox_path.append(btn_clear_path)

        vbox.append(Gtk.Separator())

        # Колонки
        hbox_cols = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        vbox.append(hbox_cols)
        hbox_cols.append(Gtk.Label(label="Колонок в сетке:", xalign=0))

        adj = Gtk.Adjustment(value=int(self.current_settings['columns']), lower=2, upper=10, step_increment=1)
        self.spin_cols = Gtk.SpinButton(adjustment=adj)
        hbox_cols.append(self.spin_cols)

        vbox.append(Gtk.Separator())

        # Копировать в меню обоев GNOME при сохранении
        hbox_gnome = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        vbox.append(hbox_gnome)
        lbl_gnome = Gtk.Label(label="Копировать в меню обоев GNOME при сохранении:", xalign=0)
        lbl_gnome.set_hexpand(True)
        lbl_gnome.set_wrap(True)
        hbox_gnome.append(lbl_gnome)
        self.switch_gnome_bg = Gtk.Switch()
        self.switch_gnome_bg.set_active(self.current_settings.get('copy_to_gnome_backgrounds', 'false') == 'true')
        self.switch_gnome_bg.set_valign(Gtk.Align.CENTER)
        hbox_gnome.append(self.switch_gnome_bg)

        vbox.append(Gtk.Separator())

        btn_save = Gtk.Button(label="Сохранить настройки")
        btn_save.add_css_class("suggested-action")
        btn_save.connect("clicked", self.on_save_clicked)
        vbox.append(btn_save)

    def on_select_folder(self, btn):
        """Открывает диалог выбора папки для сохранения."""
        dialog = Gtk.FileDialog()
        dialog.select_folder(self, None, self.on_folder_selected)

    def on_folder_selected(self, dialog, result):
        """
        Обработчик завершения выбора папки.
        Устанавливает выбранный путь в поле ввода.
        """
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                self.entry_path.set_text(folder.get_path())
        except Exception:
            pass

    def on_save_clicked(self, btn):
        """
        Сохраняет настройки в INI-файл, применяет их к главному окну и закрывает диалог.
        """
        new_app_settings = {
            'api_key': self.entry_api.get_text().strip(),
            'download_path': self.entry_path.get_text().strip(),
            'columns': str(int(self.spin_cols.get_value())),
            'copy_to_gnome_backgrounds': 'true' if self.switch_gnome_bg.get_active() else 'false',
        }

        current_search_state = self.parent_window.get_current_search_state()
        final_settings = {**self.parent_window.settings, **new_app_settings, **current_search_state}

        save_settings(final_settings)
        self.parent_window.apply_settings(final_settings)
        self.parent_window.scan_downloaded_wallpapers()
        self.close()

