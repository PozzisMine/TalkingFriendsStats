import os
import json
import csv
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

CHANNELS_FILE = "channels.json"
STATE_FILE = "bot_state.json"
LOG_FILE = "stats_log.csv"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = str(os.getenv("TELEGRAM_CHAT_ID"))
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")


def now_msk():
    return datetime.now(ZoneInfo("Europe/Moscow")).strftime("%Y-%m-%d %H:%M:%S")


def load_json(filename, default):
    if not os.path.exists(filename):
        return default

    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_channels():
    return load_json(CHANNELS_FILE, [])


def save_channels(channels):
    save_json(CHANNELS_FILE, channels)


def load_state():
    return load_json(STATE_FILE, {"last_update_id": 0})


def save_state(state):
    save_json(STATE_FILE, state)


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


def handle_commands(channels):
    state = load_state()
    offset = state.get("last_update_id", 0) + 1

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    data = requests.get(url, params={"offset": offset}).json()

    if not data.get("ok"):
        return channels

    for update in data.get("result", []):
        state["last_update_id"] = update["update_id"]

        message = update.get("message", {})
        chat = message.get("chat", {})
        text = message.get("text", "")

        if str(chat.get("id")) != TELEGRAM_CHAT_ID:
            continue

        if text.startswith("/start"):
            send_telegram(
                "✅ Бот работает.\n\n"
                "Команды:\n"
                "/addchannel UCxxxx Название\n"
                "/channels\n"
                "/removechannel UCxxxx"
            )

        elif text.startswith("/addchannel"):
            parts = text.split(" ", 2)

            if len(parts) < 3:
                send_telegram("❌ Используй так:\n/addchannel UCxxxx Название канала")
                continue

            youtube_id = parts[1].strip()
            name = parts[2].strip()

            found = False

            for ch in channels:
                if ch["id"] == youtube_id:
                    ch["name"] = name
                    ch["deleted"] = False
                    found = True
                    send_telegram(f"♻️ Канал обновлён: <b>{name}</b>")
                    break

            if not found:
                channels.append({
                    "id": youtube_id,
                    "name": name,
                    "deleted": False,
                    "last_subs": None,
                    "last_views": None,
                    "last_videos": None
                })

                send_telegram(f"✅ Канал добавлен: <b>{name}</b>")

        elif text.startswith("/channels"):
            if not channels:
                send_telegram("📺 Список каналов пуст.")
                continue

            msg = "📺 <b>Список каналов:</b>\n\n"

            for i, ch in enumerate(channels, start=1):
                status = "❌ удалён/недоступен" if ch.get("deleted") else "✅ активен"
                msg += f"{i}. <b>{ch['name']}</b>\n{ch['id']}\n{status}\n\n"

            send_telegram(msg)

        elif text.startswith("/removechannel"):
            parts = text.split(" ", 1)

            if len(parts) < 2:
                send_telegram("❌ Используй так:\n/removechannel UCxxxx")
                continue

            youtube_id = parts[1].strip()
            removed = False

            for ch in channels:
                if ch["id"] == youtube_id:
                    ch["deleted"] = True
                    removed = True
                    send_telegram(f"🗑 Канал помечен как удалённый: <b>{ch['name']}</b>")
                    break

            if not removed:
                send_telegram("❌ Канал не найден.")

    save_state(state)
    return channels


def check_youtube_stats(channels):
    for ch in channels:
        if ch.get("deleted"):
            continue

        data = get_stats(ch["id"])

        if data is None:
            ch["deleted"] = True
            send_telegram(f"❌ Канал стал недоступен: <b>{ch['name']}</b>")
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

    return channels


def main():
    channels = load_channels()

    channels = handle_commands(channels)
    channels = check_youtube_stats(channels)

    save_channels(channels)


if __name__ == "__main__":
    main()
