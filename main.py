import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Optional
import argparse
import requests
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, TALB, TCON, TPE1, TIT2, USLT, ID3, ID3NoHeaderError
from mutagen.mp3 import MP3
from tqdm import tqdm
from yandex_music import Client

# for localization to my country
MESSAGES = {
    'ru': {
        'auth_open': "Перейдите по ссылке {url} и введите код: {code}",
        'auth_success': "Успешная авторизация! Пользователь: {user}",
        'downloading': "Скачивание новых треков",
        'lang_set': "Язык установлен: {lang}",
        'token_found_env': "Найден токен из переменных окружения.",
        'err_download': "Ошибка при скачивании трека {track_id}: {error}",
        'done': "Завершено. Скачано треков: {count}"
    },
    'en': {
        'auth_open': "Open {url} and enter code: {code}",
        'auth_success': "Successfully authenticated! User: {user}",
        'downloading': "Downloading new tracks",
        'lang_set': "Language set to: {lang}",
        'token_found_env': "Token found in environment variables.",
        'err_download': "Error downloading track {track_id}: {error}",
        'done': "Done. Downloaded tracks: {count}"
    }
}


class SettingsApplier:
    """Управление конфигурацией и языковыми настройками."""
    
    DEFAULT_CONFIG = {
        "token": "",
        "download_path": "music",
        "language": "ru",
        "max_workers": 5
    }

    def __init__(self, base_dir: str = "."):
        self.base_dir = base_dir
        self.config_path = os.path.join(self.base_dir, "config.json")
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            self.save_config(self.DEFAULT_CONFIG)
            return self.DEFAULT_CONFIG.copy()
        
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                for k, v in self.DEFAULT_CONFIG.items():
                    config.setdefault(k, v)
                return config
        except Exception:
            return self.DEFAULT_CONFIG.copy()

    def save_config(self, config_data: Optional[Dict[str, Any]] = None):
        data = config_data or self.config
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        self.config[key] = value
        self.save_config()

    def tr(self, key: str, **kwargs) -> str:
        lang = self.get("language", "ru")
        msg_dict = MESSAGES.get(lang, MESSAGES['ru'])
        template = msg_dict.get(key, key)
        return template.format(**kwargs)


class OAuthHandler:
    """Authorization Yandex Music Token."""

    def __init__(self, settings: SettingsApplier):
        self.settings = settings

    def _on_code_callback(self, code):
        url = getattr(code, 'verification_url', code)
        user_code = getattr(code, 'user_code', '')
        print(self.settings.tr('auth_open', url=url, code=user_code))

    def get_token(self) -> str:
        env_token = os.environ.get("YANDEX_MUSIC_TOKEN")
        if env_token:
            print(self.settings.tr('token_found_env'))
            return env_token

        saved_token = self.settings.get("token")
        if saved_token:
            return saved_token
        
        client = Client()
        token_obj = client.device_auth(on_code=self._on_code_callback)
        access_token = token_obj.access_token

        self.settings.set("token", access_token)
        return access_token


class Downloader:
    """Download, fetch lyrics, convert/embed tags and maintain index."""

    def __init__(self, client: Client, base_dir: str, settings: SettingsApplier):
        self.client = client
        self.settings = settings
        self.base_dir = base_dir
        
        self.index_file = os.path.join(self.base_dir, "index.txt")
        
        download_subfolder = self.settings.get("download_path", "music")
        if os.path.isabs(download_subfolder):
            self.download_path = download_subfolder
        else:
            self.download_path = os.path.join(self.base_dir, download_subfolder)
            
        os.makedirs(self.download_path, exist_ok=True)
        self.genres_map = self._load_genres_map()

    def _load_genres_map(self) -> Dict[str, str]:
        """Taking dictionary of genres through Yandex Music API."""
        genres_dict = {}
        try:
            genres_list = self.client.genres()
            for genre in genres_list:
                genres_dict[genre.id] = genre.titles.get('ru', {}).get('title', genre.id)
        except Exception:
            pass
        return genres_dict

    def _clean_lrc_timestamps(self, lyrics: str) -> str:
        """Cleans song text from LRC timestamps [00:12.34], transforming it into simple text."""
        if not lyrics:
            return ""
        cleaned = re.sub(r'\[\d+:\d+\.\d+\]', '', lyrics)
        cleaned = re.sub(r'\[\d+:\d+\]', '', cleaned)
        return "\n".join([line.strip() for line in cleaned.splitlines() if line.strip()])

    def fetch_lyrics_lrclib(self, artist: str, title: str, album: str) -> Optional[str]:
        try:
            url = "https://lrclib.net/api/get"
            params = {'artist_name': artist, 'track_name': title, 'album_name': album}
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                raw_lyrics = data.get('plainLyrics') or data.get('syncedLyrics')
                if raw_lyrics:
                    return self._clean_lrc_timestamps(raw_lyrics)
        except Exception:
            pass
        return None

    def get_track_metadata(self, track_id: str) -> Dict[str, Any]:
        track = self.client.tracks([track_id])[0]
        artist = track.artists[0].name if track.artists else "Unknown Artist"
        title = track.title or "Unknown Title"
        album = track.albums[0].title if track.albums else "Single"
        
        genre_id = "Pop"
        if track.albums and len(track.albums) > 0:
            if hasattr(track.albums[0], 'genre') and track.albums[0].genre:
                genre_id = track.albums[0].genre
        genre = self.genres_map.get(genre_id, genre_id.capitalize())

        download_info = track.get_download_info()
        best_audio = max(download_info, key=lambda x: x.bitrate_in_kbps)
        codec = best_audio.codec

        safe_filename = f"{artist} - {title}.{codec}".translate(str.maketrans("", "", '<>:"/\\|?*'))

        return {
            'track_id': track_id,
            'artist': artist,
            'title': title,
            'album': album,
            'genre': genre,
            'best_audio': best_audio,
            'codec': codec,
            'file_name': safe_filename,
            'cover_uri': track.cover_uri
        }

    def _tag_mp3(self, file_path: str, meta: Dict[str, Any], cover_data: Optional[bytes], lyrics: Optional[str]):
        try:
            audio = MP3(file_path, ID3=ID3)
            audio.add_tags()
        except ID3NoHeaderError:
            audio.add_tags()

        audio.tags.add(TIT2(encoding=3, text=meta['title']))
        audio.tags.add(TPE1(encoding=3, text=meta['artist']))
        audio.tags.add(TALB(encoding=3, text=meta['album']))
        audio.tags.add(TCON(encoding=3, text=meta['genre']))

        if lyrics:
            lang_code = 'rus' if any('\u0400' <= char <= '\u04FF' for char in lyrics) else 'eng'
            # Пустой desc="" обеспечивает универсальное чтение всеми плеерами
            audio.tags.add(USLT(encoding=3, lang=lang_code, desc="", text=lyrics))

        if cover_data:
            audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=cover_data))

        audio.save()

    def _tag_flac(self, file_path: str, meta: Dict[str, Any], cover_data: Optional[bytes], lyrics: Optional[str]):
        audio = FLAC(file_path)
        audio['title'] = meta['title']
        audio['artist'] = meta['artist']
        audio['album'] = meta['album']
        audio['genre'] = meta['genre']

        if lyrics:
            audio['lyrics'] = lyrics
            audio['unsyncedlyrics'] = lyrics

        if cover_data:
            pic = Picture()
            pic.data = cover_data
            pic.type = 3
            pic.mime = 'image/jpeg'
            audio.add_picture(pic)

        audio.save()

    def download_and_enrich_track(self, track_id: str) -> Dict[str, Any]:
        meta = self.get_track_metadata(track_id)
        file_path = os.path.join(self.download_path, meta['file_name'])

        meta['best_audio'].download(file_path)

        cover_data = None
        if meta['cover_uri']:
            cover_url = f"https://{meta['cover_uri'].replace('%%', '400x400')}"
            try:
                cover_data = requests.get(cover_url, timeout=10).content
            except Exception:
                pass

        lyrics = self.fetch_lyrics_lrclib(meta['artist'], meta['title'], meta['album'])

        if meta['codec'] == 'mp3':
            self._tag_mp3(file_path, meta, cover_data, lyrics)
        else:
            self._tag_flac(file_path, meta, cover_data, lyrics)

        meta['has_lyrics'] = 'Yes' if lyrics else 'No'
        meta['file_path'] = file_path
        return meta

    def get_downloaded_uids(self) -> set:
        downloaded = set()
        if os.path.exists(self.index_file):
            with open(self.index_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if 'uid:' in line:
                        parts = line.split(' | ')
                        uid = parts[0].split('uid: ')[1].strip()
                        downloaded.add(uid)
        return downloaded

    def append_to_index(self, meta: Dict[str, Any]):
        """Saving data about the track in index.txt."""
        with open(self.index_file, 'a', encoding='utf-8') as f:
            f.write(
                f"uid: {meta['track_id']} | Title: {meta['title']} | "
                f"Artist: {meta['artist']} | Format: {meta['codec']} | "
                f"Lyrics: {meta['has_lyrics']} | Path: {meta['file_path']}\n"
            )

    def sync_liked_tracks(self):
        downloaded = self.get_downloaded_uids()
        liked_tracks = self.client.users_likes_tracks()
        to_download = [str(item['id']) for item in liked_tracks if str(item['id']) not in downloaded]

        downloaded_count = 0
        max_workers = self.settings.get("max_workers", 5)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_track = {
                executor.submit(self.download_and_enrich_track, track_id): track_id 
                for track_id in to_download
            }

            with tqdm(total=len(to_download), desc=self.settings.tr('downloading'), unit="track") as pbar:
                for future in as_completed(future_to_track):
                    track_id = future_to_track[future]
                    try:
                        meta = future.result()
                        self.append_to_index(meta)
                        downloaded_count += 1
                    except Exception as e:
                        pbar.write(self.settings.tr('err_download', track_id=track_id, error=e))
                    finally:
                        pbar.update(1)

        print(self.settings.tr('done', count=downloaded_count))


class MainApp:
    """enter point in app"""

    def __init__(self, base_dir: str = "."):
        self.base_dir = base_dir
        self.settings = SettingsApplier(base_dir=self.base_dir)

    def select_language_interactively(self):
        print("\nSelect language / Выберите язык:")
        print("1. Русский (ru)")
        print("2. English (en)")
        
        choice = input("Enter option (1/2) [default: 1]: ").strip()
        lang = "en" if choice == "2" else "ru"

        self.settings.set("language", lang)
        print(self.settings.tr('lang_set', lang=lang))

    def run(self, auto_sync: bool = False):
        if auto_sync:
            if "language" not in self.settings.config:
                self.settings.set("language", "ru")
            self._start_sync()
            return

        if "language" not in self.settings.config:
            self.select_language_interactively()

        while True:
            current_lang = self.settings.get("language", "ru")
            print("\n==============================")
            if current_lang == "ru":
                print("1. Запустить синхронизацию треков")
                print("2. Изменить язык (Change language)")
                print("3. Выход")
            else:
                print("1. Start track synchronization")
                print("2. Change language")
                print("3. Exit")
            print("==============================")

            choice = input("> ").strip()

            if choice == "1":
                self._start_sync()
                break
            elif choice == "2":
                self.select_language_interactively()
            elif choice == "3":
                sys.exit(0)
            else:
                print("Invalid input / Неверный ввод")

    def _start_sync(self):
        self.oauth = OAuthHandler(self.settings)
        token = self.oauth.get_token()
        client = Client(token).init()

        user_name = client.me.account.login
        print(self.settings.tr('auth_success', user=user_name))

        downloader = Downloader(client, self.base_dir, self.settings)
        downloader.sync_liked_tracks()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Yandex Music Downloader CLI")
    parser.add_argument(
        "--sync", "--auto",
        action="store_true",
        help="Запустить синхронизацию сразу без показа меню (для Docker/Cron)"
    )
    args = parser.parse_args()

    app = MainApp()
    app.run(auto_sync=args.sync)