import os
import json
import sys
from datetime import datetime
import feedparser
import requests
import gspread
from google.oauth2.service_account import Credentials
from google import genai

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_CREDENTIALS_JSON = os.environ["GOOGLE_CREDENTIALS"]

client = genai.Client(api_key=GEMINI_API_KEY)

# Бұғатталмайтын Google News KZ және қазақстандық RSS-тер
KZ_NEWS_FEEDS = [
    "https://news.google.com/rss/search?q=Қазақстан&hl=kk&gl=KZ&ceid=KZ:kk",
    "https://kaz.tengrinews.kz/rss/",
    "https://informburo.kz/kaz/rss/all.xml",
    "https://www.zakon.kz/rss/kaz_all.xml"
]

TECH_AI_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/rss/index.xml"
]


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
            print(f"Тексерілді: {feed_url} -> {len(feed.entries)} мақала")
            for entry in feed.entries:
                link = entry.get("link", "").strip()
                if link and link not in published_ids:
                    summary = entry.get(
                        "summary", entry.get("description", "")
                    )
                    return {
                        "title": entry.get("title", "Тақырыпсыз"),
                        "summary": summary,
                        "link": link
                    }
        except Exception as e:
            print(f"Қате ({feed_url}): {e}")
    return None


def generate_text_with_gemini(prompt):
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
    )
    return response.text.strip()


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
    r = requests.post(url, json=payload, timeout=30)
    if not r.ok:
        print(f"HTML қатесі, қарапайым мәтінмен жіберілуде: {r.text}")
        payload.pop("parse_mode")
        r2 = requests.post(url, json=payload, timeout=30)
        if not r2.ok:
            print(f"Telegram қатесі: {r2.text}")
        r2.raise_for_status()
    print("Telegram-ға сәтті жіберілді!")


def run_kz_news(sheet, published_ids):
    item = fetch_new_rss_item(KZ_NEWS_FEEDS, published_ids)
    if not item:
        print("Жаңа жаңалық табылмады.")
        return

    lines = [
        "Сен қазақтілді Telegram-арна редакторысың.",
        "Мына жаңалықтан қысқа әрі тартымды пост жаз:",
        f"Тақырыбы: {item['title']}",
        f"Мазмұны: {item['summary']}",
        "Талаптар:",
        "- Тек сауатты қазақ тілінде жаз.",
        "- Тек HTML тегтерін (<b>, <i>) қолдан.",
        "- Markdown жұлдызшаларын мүлдем қолданба!",
        "- Негізгі ойды 2-3 қысқа абзацпен жеткіз.",
        f"- Соңына <a href='{item['link']}'>Толығырақ</a>",
        "  сілтемесін және 2-3 хэштег қос.",
        "- Кіріспе сөз жазба, бірден пост мәтінін бер."
    ]
    prompt = "\n".join(lines)

    post_text = generate_text_with_gemini(prompt)
    send_to_telegram(post_text)
    save_to_sheet(sheet, "kz_news", item["link"], item["title"])
    print("Сәтті жарияланды [KZ News]")


def run_tech_ai(sheet, published_ids):
    item = fetch_new_rss_item(TECH_AI_FEEDS, published_ids)
    if not item:
        print("Жаңа Техно жаңалық табылмады.")
        return

    lines = [
        "Сен ЖИ және технология туралы жазатын сарапшысың.",
        "Мына мақаланы қазақ тіліне аударып, пост жаса:",
        f"Тақырыбы: {item['title']}",
        f"Мазмұны: {item['summary']}",
        "Талаптар:",
        "- Жеңіл әрі түсінікті қазақ тілінде жаз.",
        "- Тек HTML тегтерін (<b>, <i>) қолдан.",
        "- Markdown мүлдем қолданба!",
        "- Құрылымы: Тақырып, Не болды, Маңызы (2-3 пункт).",
        f"- Соңына <a href='{item['link']}'>Дереккөз</a>",
        "  сілтемесін және #ЖИ #Технология хэштегін қос.",
        "- Ешқандай кіріспе сөз қоспа."
    ]
    prompt = "\n".join(lines)

    post_text = generate_text_with_gemini(prompt)
    send_to_telegram(post_text)
    save_to_sheet(sheet, "tech_ai", item["link"], item["title"])
    print("Сәтті жарияланды [Tech/AI]")


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
        "- Тек HTML тегтерін (<b>, <i>) қолдан.",
        "- Markdown мүлдем қолданба!",
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

    post_text = "\n".join(post_lines).strip()
    send_to_telegram(post_text)
    save_to_sheet(sheet, "lifehack", topic_id, topic_id)
    print("Сәтті жарияланды [Lifehack]")


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
