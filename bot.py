import os
import json
import csv
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

CHANNELS_FILE = "channels.json"
LOG_FILE = "stats_log.csv"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")


def now_msk():
    return datetime.now(ZoneInfo("Europe/Moscow")).strftime("%Y-%m-%d %H:%M:%S")


def load_channels():
    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_channels(channels):
    with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    })


def get_stats(channel_id):
    url = (
        "https://www.googleapis.com/youtube/v3/channels"
        f"?part=statistics&id={channel_id}&key={YOUTUBE_API_KEY}"
    )

    data = requests.get(url).json()

    if "items" not in data or len(data["items"]) == 0:
        return None

    stats = data["items"][0]["statistics"]

    return {
        "subs": int(stats.get("subscriberCount", 0)),
        "views": int(stats.get("viewCount", 0)),
        "videos": int(stats.get("videoCount", 0))
    }


def format_change(value):
    if value > 0:
        return f"+{value:,}"
    return f"{value:,}"


def write_log(name, channel_id, subs, views, videos, change_subs, change_views, change_videos):
    file_exists = os.path.exists(LOG_FILE)

    with open(LOG_FILE, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow([
                "time_msk",
                "name",
                "channel_id",
                "subs",
                "views",
                "videos",
                "change_subs",
                "change_views",
                "change_videos"
            ])

        writer.writerow([
            now_msk(),
            name,
            channel_id,
            subs,
            views,
            videos,
            change_subs,
            change_views,
            change_videos
        ])


def main():
    send_telegram("✅ Бот работает! Тест")
    
    channels = load_channels()

    for ch in channels:
        if ch.get("deleted"):
            continue

        data = get_stats(ch["id"])

        if data is None:
            ch["deleted"] = True
            send_telegram(f"❌ Канал стал недоступен: {ch['name']}")
            continue

        subs = data["subs"]
        views = data["views"]
        videos = data["videos"]

        if ch.get("last_subs") is None:
            ch["last_subs"] = subs
            ch["last_views"] = views
            ch["last_videos"] = videos
            continue

        change_subs = subs - ch["last_subs"]
        change_views = views - ch["last_views"]
        change_videos = videos - ch["last_videos"]

        if change_subs == 0 and change_views == 0 and change_videos == 0:
            continue

        write_log(
            ch["name"],
            ch["id"],
            subs,
            views,
            videos,
            change_subs,
            change_views,
            change_videos
        )

        text = (
            f"📊 <b>Изменение статистики</b>\n\n"
            f"📺 Канал: <b>{ch['name']}</b>\n"
            f"👥 Подписчики: {subs:,} ({format_change(change_subs)})\n"
            f"👀 Просмотры: {views:,} ({format_change(change_views)})\n"
            f"🎬 Видео: {videos:,} ({format_change(change_videos)})\n\n"
            f"⏱ Обновлено: {now_msk()} МСК"
        )

        send_telegram(text)

        ch["last_subs"] = subs
        ch["last_views"] = views
        ch["last_videos"] = videos

    save_channels(channels)


if __name__ == "__main__":
    main()
