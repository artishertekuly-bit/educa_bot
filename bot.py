import os
import re
import json
import sys
import time
from datetime import datetime
import feedparser
import requests
import gspread
from google.oauth2.service_account import Credentials
from google import genai
from google.genai import types

def log(msg):
    print(msg, flush=True)

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_CREDENTIALS_JSON = os.environ["GOOGLE_CREDENTIALS"]

# Тайм-аутты 120 секундқа (120000 мс) дейін ұзартамыз
client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options=types.HttpOptions(timeout=120000)
)

# Қазақстан жаңалықтары (тікелей әрі жылдам RSS көздері бірінші тұрады)
KZ_NEWS_FEEDS = [
    "https://kaz.tengrinews.kz/rss/",
    "https://informburo.kz/kaz/rss/all.xml",
    "https://www.zakon.kz/rss/kaz_all.xml",
    "https://news.google.com/rss/search?q=Қазақстан&hl=kk&gl=KZ&ceid=KZ:kk"
]

TECH_AI_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/rss/index.xml"
]

SUBSCRIBE_FOOTER = (
    "\n\n🔔 <b>Осындай маңызды жаңалықтар мен пайдалы "
    "ақпараттарды күн сайын оқығыңыз келсе, "
    "арнамызға тіркеліп қойыңыз!</b>"
)


def clean_telegram_html(text):
    """Telegram қолдамайтын HTML тегтері мен Markdown белгілерін тазалау."""
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text.strip())
    text = re.sub(r"\n?```$", "", text.strip())

    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def get_google_sheet():
    creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(
        creds_dict, scopes=scopes
    )
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SPREADSHEET_ID).sheet1

    if not sheet.row_values(1):
        sheet.append_row(["Уақыты", "Рубрика", "ID", "Тақырыбы"])
    return sheet


def get_published_ids(sheet):
    return set(sheet.col_values(3))


def save_to_sheet(sheet, category, unique_id, title):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row([now, category, unique_id, title])


def fetch_new_rss_item(feeds, published_ids):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    }
    for feed_url in feeds:
        try:
            resp = requests.get(feed_url, headers=headers, timeout=15)
            feed = feedparser.parse(resp.content)
            for entry in feed.entries:
                link = entry.get("link", "").strip()
                if link and link not in published_ids:
                    raw_summary = entry.get(
                        "summary", entry.get("description", "")
                    )
                    # RSS ішіндегі қоқыс HTML тегтерін тазалау (Gemini жылдам оқуы үшін)
                    clean_summary = re.sub(r"<[^>]+>", " ", raw_summary)
                    clean_summary = re.sub(r"\s+", " ", clean_summary).strip()
                    return {
                        "title": entry.get("title", "Тақырыпсыз"),
                        "summary": clean_summary[:1000],
                        "link": link
                    }
        except Exception as e:
            log(f"RSS қатесі ({feed_url}): {e}")
    return None


def generate_text_with_gemini(prompt):
    """Gemini сервері бос болмаса (504/503), бірнеше рет қайталап көру."""
    models = ["gemini-3.8-flash", "gemini-3-flash-preview"]
    for attempt in range(1, 4):
        for model_name in models:
            try:
                log(f"Gemini сұранысы (Талпыныс {attempt}, модель: {model_name})...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                if response and response.text:
                    return clean_telegram_html(response.text)
            except Exception as e:
                log(f"Ескерту ({model_name}): {e}")
                time.sleep(5)
    raise RuntimeError("Gemini сервері уақытша жауап бермеді. Сәлден соң қайта қосыңыз.")


def send_to_telegram(text):
    url = (
        "https://api.telegram.org/bot"
        f"{TELEGRAM_BOT_TOKEN}/sendMessage"
    )
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    r = requests.post(url, json=payload, timeout=20)
    if not r.ok:
        log(f"HTML қатесі, тегтерді өшіріп жіберуде: {r.text}")
        clean_plain = re.sub(r"<[^>]+>", "", text)
        payload["text"] = clean_plain
        payload.pop("parse_mode")
        r2 = requests.post(url, json=payload, timeout=20)
        r2.raise_for_status()
    log("Telegram-ға сәтті жарияланды!")


def run_kz_news(sheet, published_ids):
    item = fetch_new_rss_item(KZ_NEWS_FEEDS, published_ids)
    if not item:
        log("Жаңа жаңалық табылмады.")
        return

    lines = [
        "Сен қазақтілді Telegram-арна редакторысың.",
        "Мына жаңалықтан қысқа әрі тартымды пост жаз:",
        f"Тақырыбы: {item['title']}",
        f"Мазмұны: {item['summary']}",
        "Талаптар:",
        "- Тек сауатты қазақ тілінде жаз.",
        "- Пост ішінде мағынасына сай эмодзилерді (🇰🇿, ⚡, 📌, 💬) орынды қолдан.",
        "- Форматтау үшін ТЕК <b>және</b>, <i>және</i> тегтерін қолдан.",
        "- <br>, <p> тегтерін және Markdown (**) МҮЛДЕМ қолданба!",
        "- Абзацтарды тек кәдімгі жаңа жолмен (Enter) бөл.",
        "- Негізгі ойды 2-3 қысқа абзацпен жеткіз.",
        f"- Соңына 🔗 <a href=\"{item['link']}\">Толығырақ оқу</a>",
        "  сілтемесін және 2-3 хэштег қос.",
        "- Кіріспе сөз жазба, бірден пост мәтінін бер."
    ]
    prompt = "\n".join(lines)

    post_text = generate_text_with_gemini(prompt) + SUBSCRIBE_FOOTER
    send_to_telegram(post_text)
    save_to_sheet(sheet, "kz_news", item["link"], item["title"])
    log("Сәтті жарияланды [KZ News]")


def run_tech_ai(sheet, published_ids):
    item = fetch_new_rss_item(TECH_AI_FEEDS, published_ids)
    if not item:
        log("Жаңа Техно жаңалық табылмады.")
        return

    lines = [
        "Сен ЖИ және технология туралы жазатын сарапшысың.",
        "Мына мақаланы қазақ тіліне аударып, пост жаса:",
        f"Тақырыбы: {item['title']}",
        f"Мазмұны: {item['summary']}",
        "Талаптар:",
        "- Жеңіл әрі түсінікті қазақ тілінде жаз.",
        "- Әр бөлімнің алдына тақырыпқа сай эмодзилер (🤖, 🚀, 💡, 🔹) қой.",
        "- Форматтау үшін ТЕК <b>және</b>, <i>және</i> тегтерін қолдан.",
        "- <br>, <p> тегтерін және Markdown (**) МҮЛДЕМ қолданба!",
        "- Абзацтарды тек кәдімгі жаңа жолмен (Enter) бөл.",
        "- Құрылымы: Тақырып, Не болды, Маңызы (2-3 пункт).",
        f"- Соңына 🔗 <a href=\"{item['link']}\">Дереккөз</a>",
        "  сілтемесін және #ЖИ #Технология хэштегін қос.",
        "- Ешқандай кіріспе сөз қоспа."
    ]
    prompt = "\n".join(lines)

    post_text = generate_text_with_gemini(prompt) + SUBSCRIBE_FOOTER
    send_to_telegram(post_text)
    save_to_sheet(sheet, "tech_ai", item["link"], item["title"])
    log("Сәтті жарияланды [Tech/AI]")


def run_lifehacks(sheet, published_ids):
    past = [x for x in published_ids if x.startswith("TOPIC:")]
    recent_str = ", ".join(past[-30:]) if past else "Жоқ"

    lines = [
        "Сен танымдық Telegram-арнаның авторысың.",
        "1 ғылыми/тарихи дерек ЖӘНЕ 1 пайдалы лайфхак жаз.",
        f"Мына тақырыптарды қайталама: [{recent_str}]",
        "Бірінші жолға тек тақырып кодын жаз, мысалы:",
        "TOPIC: Помодоро әдісі және ми",
        "Екінші жолдан бастап дайын постты жаз:",
        "- Мәтін ішінде әдемі эмодзилерді (🧠, 💡, ✨, 👇) қолдан.",
        "- ТЕК <b>және</b>, <i>және</i> тегтерін қолдан.",
        "- <br>, <p> тегтерін және Markdown (**) МҮЛДЕМ қолданба!",
        "- Абзацтарды тек кәдімгі жаңа жолмен (Enter) бөл.",
        "- Соңында оқырманға 1 сұрақ қой және",
        "  #пайдалы #лайфхак #дерек хэштегтерін қос."
    ]
    prompt = "\n".join(lines)

    raw_output = generate_text_with_gemini(prompt)
    out_lines = raw_output.splitlines()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    topic_id = f"TOPIC: {now_str}"
    post_lines = []

    for line in out_lines:
        if line.strip().startswith("TOPIC:"):
            topic_id = line.strip()
        else:
            post_lines.append(line)

    post_text = "\n".join(post_lines).strip() + SUBSCRIBE_FOOTER
    send_to_telegram(post_text)
    save_to_sheet(sheet, "lifehack", topic_id, topic_id)
    log("Сәтті жарияланды [Lifehack]")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "kz_news"
    sheet = get_google_sheet()
    published = get_published_ids(sheet)

    if mode == "kz_news":
        run_kz_news(sheet, published)
    elif mode == "tech_ai":
        run_tech_ai(sheet, published)
    elif mode == "lifehack":
        run_lifehacks(sheet, published)
