import os
import json
import sys
from datetime import datetime
import feedparser
import requests
import gspread
from google.oauth2.service_account import Credentials
from google import genai

# 1. Получение секретных ключей из GitHub Secrets
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_CREDENTIALS_JSON = os.environ["GOOGLE_CREDENTIALS"]

# Инициализация клиента Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

# RSS-источники
KZ_NEWS_FEEDS = [
    "https://kaz.tengrinews.kz/rss/",
    "https://informburo.kz/kaz/rss/all.xml"
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
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SPREADSHEET_ID).sheet1

    if not sheet.row_values(1):
        sheet.append_row(["Уақыты", "Рубрика", "Бірегей ID немесе Сілтеме", "Тақырыбы"])
    return sheet


def get_published_ids(sheet):
    return set(sheet.col_values(3))


def save_to_sheet(sheet, category, unique_id, title):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row([now, category, unique_id, title])


def fetch_new_rss_item(feeds, published_ids):
    for feed_url in feeds:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            link = entry.get("link", "").strip()
            if link and link not in published_ids:
                summary = entry.get("summary", entry.get("description", ""))
                return {
                    "title": entry.get("title", "Тақырыпсыз"),
                    "summary": summary,
                    "link": link
                }
    return None


def generate_text_with_gemini(prompt):
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    return response.text.strip()


def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    response = requests.post(url, json=payload, timeout=30)
    if not response.ok:
        print(f"HTML қатесі, қарапайым мәтінмен жіберілуде: {response.text}")
        payload.pop("parse_mode")
        r2 = requests.post(url, json=payload, timeout=30)
        r2.raise_for_status()


def run_kz_news(sheet, published_ids):
    item = fetch_new_rss_item(KZ_NEWS_FEEDS, published_ids)
    if not item:
        print("Жаңа Қазақстан жаңалығы табылмады.")
        return

    prompt = (
        "Сен кәсіби қазақтілді Telegram-арнаның бас редакторысың.\n"
        "Мына жаңалықтың негізінде қысқа, нақты әрі тартымды пост жаз:\n"
        f"Тақырыбы: {item['title']}\n"
        f"Мазмұны: {item['summary']}\n\n"
        "Талаптар:\n"
        "- Тек сауатты, табиғи қазақ тілінде жаз.\n"
        "- Форматтау үшін тек Telegram HTML тегтерін (<b>қалың</b>, <i>көлбеу</i>
