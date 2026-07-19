"""
Модуль для работы с Wallhaven API.
"""

import requests
from wallhaven_viewer.config import API_URL, WALLPAPER_API_URL, RESOLUTION_OPTIONS, RATIO_OPTIONS, SORT_OPTIONS


class WallhavenAPI:
    """Класс для работы с API Wallhaven."""

    @staticmethod
    def build_search_params(settings, query, page):
        """
        Формирует словарь параметров для запроса к Wallhaven API на основе текущих фильтров.

        Args:
            settings (dict): Словарь настроек приложения.
            query (str): Поисковый запрос.
            page (int): Номер страницы.

        Returns:
            dict: Параметры запроса.
        """
        c_gen = "1" if settings.get('cat_general', 'true').lower() == 'true' else "0"
        c_ani = "1" if settings.get('cat_anime', 'true').lower() == 'true' else "0"
        c_peo = "1" if settings.get('cat_people', 'true').lower() == 'true' else "0"
        p_sfw = "1" if settings.get('purity_sfw', 'true').lower() == 'true' else "0"
        api_key = settings.get('api_key', '')

        # Обработка Purity в зависимости от наличия API-ключа
        if api_key:
            p_sky = "1" if settings.get('purity_sketchy', 'false').lower() == 'true' else "0"
            p_nsf = "1" if settings.get('purity_nsfw', 'false').lower() == 'true' else "0"
        else:
            p_sky = "0"
            p_nsf = "0"

        sort_idx = int(settings.get('sort_index', '5'))
        sort_modes = ["relevance", "random", "date_added", "views", "favorites", "toplist", "hot"]
        sorting = sort_modes[sort_idx] if sort_idx < len(sort_modes) else "views"

        res_idx = int(settings.get('resolution_index', '0'))
        ratio_idx = int(settings.get('ratio_index', '0'))
        selected_res = RESOLUTION_OPTIONS[res_idx][1] if res_idx < len(RESOLUTION_OPTIONS) else ""
        selected_ratio = RATIO_OPTIONS[ratio_idx][1] if ratio_idx < len(RATIO_OPTIONS) else ""

        params = {
            "q": query,
            "categories": f"{c_gen}{c_ani}{c_peo}",
            "purity": f"{p_sfw}{p_sky}{p_nsf}",
            "sorting": sorting,
            "page": page
        }

        if selected_res:
            params["resolutions"] = selected_res
        if selected_ratio:
            params["ratios"] = selected_ratio
        if api_key:
            params["apikey"] = api_key

        return params

    @staticmethod
    def search_wallpapers(query, page, settings, timeout=10):
        """
        Выполняет поиск обоев через API Wallhaven.

        Args:
            query (str): Поисковый запрос.
            page (int): Номер страницы.
            settings (dict): Словарь настроек приложения.
            timeout (int): Таймаут запроса в секундах.

        Returns:
            tuple: (data, meta) - список обоев и метаданные, или (None, None) в случае ошибки.
        """
        try:
            params = WallhavenAPI.build_search_params(settings, query, page)
            resp = requests.get(API_URL, params=params, timeout=timeout)
            resp.raise_for_status()
            json_data = resp.json()
            return json_data.get("data", []), json_data.get("meta", {})
        except Exception:
            return None, None

    @staticmethod
    def get_wallpaper_info(wallpaper_id, timeout=5):
        """
        Получает информацию об обоях по ID.

        Args:
            wallpaper_id (str): ID обоев.
            timeout (int): Таймаут запроса в секундах.

        Returns:
            dict or None: Информация об обоях или None в случае ошибки.
        """
        try:
            info_url = f"{WALLPAPER_API_URL}/{wallpaper_id}"
            resp = requests.get(info_url, timeout=timeout)
            try:
                resp.raise_for_status()
            except Exception:
                return None
            # Parse json
            j = resp.json()
            data = j.get("data") if isinstance(j, dict) else None
            if not data:
                return None
            return data
        except Exception:
            return None

    @staticmethod
    def build_wallpaper_url(wallpaper_id, extension="jpg"):
        """
        Строит URL для полноразмерного изображения обоев.

        Args:
            wallpaper_id (str): ID обоев.
            extension (str): Расширение файла (jpg, png).

        Returns:
            str: URL изображения.
        """
        return f"https://w.wallhaven.cc/full/{wallpaper_id[0:2]}/wallhaven-{wallpaper_id}.{extension}"

