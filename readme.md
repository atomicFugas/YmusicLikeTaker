# 🎵 Yandex Music Auto Downloader & Sync

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python Version">
  <img src="https://img.shields.io/badge/Docker-Supported-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker">
  <img src="https://img.shields.io/badge/Navidrome-Compatible-00A98F?style=for-the-badge&logo=headphones&logoColor=white" alt="Navidrome">
  <img src="https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge" alt="License">
</p>

<p align="center">
  <b>Автоматический многопоточный загрузчик и синхронизатор вашей медиатеки из Яндекс Музыки.</b><br>
  Разработан специально для интеграции с <b>Navidrome</b>, <b>Jellyfin</b>, <b>Plex</b> и другими селф-хостед медиасерверами.
</p>

---

## ✨ Ключевые особенности

- ⚡ **Многопоточная загрузка (`ThreadPoolExecutor`)**: скачивает сотни и тысячи треков за считанные минуты.
- 🏷️ **Полноценные теги & Жанры**: автоматическое считывание жанров с Яндекс Музыки и вшивание обложек высокого качества (400x400) прямо в аудиофайлы.
- 🎤 **Тексты песен (Lyrics)**:
  - Автоматический поиск текста в **Яндекс Музыке** и **LRCLIB**.
  - Конвертация синхронизированных `LRC` меток в чистое отображение.
  - Совместимость с любыми плеерами (**ID3v2.3 USLT** для MP3 и **LYRICS/UNSYNCEDLYRICS** для FLAC).
- 🐳 **Готов к Docker & Cron**: режим `--sync` для автономной работы на сервере без интерактивных запросов.
- 📜 **Индексация и исключение дублей**: ведет текстовый журнал `index.txt` и скачивает только новые треки.
- 🌐 **Двуязычный интерфейс (RU / EN)**: удобное CLI-меню для настройки и первичного запуска.

---

## 🛠️ Быстрый запуск через Docker (Рекомендуется)

### 1. Подготовка папок и конфигурации

Создайте структуру каталогов и файлы настроек на вашем сервере:

```bash
mkdir -p yandex-downloader/music
cd yandex-downloader
touch docker-compose.yml config.json index.txt
```

### 2. `docker-compose.yml`

```yaml
version: '3.8'

services:
  yandex-downloader:
    build: .
    container_name: yandex_music_downloader
    restart: unless-stopped
    environment:
      - YANDEX_MUSIC_TOKEN=${YANDEX_MUSIC_TOKEN:-}
      - PYTHONUNBUFFERED=1
    volumes:
      - ./music:/app/music
      - ./config.json:/app/config.json
      - ./index.txt:/app/index.txt
    command: ["python", "app.py", "--sync"]
```

### 3. Запуск

```bash
docker-compose up -d --build
```

---

## 💻 Локальный запуск (Python)

### Требования
- Python 3.10+

### Установка

1. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/ВАШ_НИК/ИМЯ_РЕПОЗИТОРИЯ.git
   cd ИМЯ_РЕПОЗИТОРИЯ
   ```

2. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```

3. Запустите в интерактивном режиме:
   ```bash
   python app.py
   ```

4. Или запустите автосинхронизацию без меню:
   ```bash
   python app.py --sync
   ```

---

## ⚙️ Конфигурация (`config.json`)

Файл `config.json` генерируется автоматически при первом запуске:

```json
{
    "token": "ВАШ_ЯНДЕКС_ТОКЕН",
    "download_path": "music",
    "language": "ru",
    "max_workers": 5
}
```

| Параметр | Описание | По умолчанию |
| :--- | :--- | :--- |
| `token` | Токен авторизации Яндекс Музыки (можно передать через `YANDEX_MUSIC_TOKEN` в env) | `""` |
| `download_path` | Путь к папке сохранения музыки (относительный или абсолютный) | `"music"` |
| `language` | Язык CLI сообщений (`ru` / `en`) | `"ru"` |
| `max_workers` | Количество параллельных потоков скачивания | `5` |

---

## 🎧 Настройка интеграции с Navidrome

1. Смонтируйте папку `./music` в контейнер **Navidrome** в качестве музыкальной библиотеки:
   ```yaml
   volumes:
     - ./music:/music:ro
   ```
2. Для корректного отображения обновленных тегов текста песен проведите **Full Scan** (Полное сканирование) в настройках Navidrome.

---

## 📄 Лицензия

Распространяется под лицензией MIT. Подробнее см. в файле [LICENSE](LICENSE).