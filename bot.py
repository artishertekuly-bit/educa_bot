import os
import json
import sys
from datetime import datetime
import feedparser
import requests
import gspread
from google.oauth2.service_account import Credentials
from google import genai

# 1. Құпия кілттерді ортадан (Environment Variables) оқу
GEMINI_API_KEY = os.environ[GEMINI_API_KEY]
TELEGRAM_BOT_TOKEN = os.environ[TELEGRAM_BOT_TOKEN]
TELEGRAM_CHAT_ID = os.environ[TELEGRAM_CHAT_ID]
SPREADSHEET_ID = os.environ[SPREADSHEET_ID]
GOOGLE_CREDENTIALS_JSON = os.environ[GOOGLE_CREDENTIALS]

# Gemini клиентін іске қосу
client = genai.Client(api_key=GEMINI_API_KEY)

# Дереккөздер (RSS таспалар)
KZ_NEWS_FEEDS = [
    httpskaz.tengrinews.kzrss,
    httpsinformburo.kzkazrssall.xml
]

TECH_AI_FEEDS = [
    httpstechcrunch.comcategoryartificial-intelligencefeed,
    httpswww.theverge.comrssindex.xml
]


def get_google_sheet()
    Google Sheets кестесіне қосылу және бағандарды дайындау.
    creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
    scopes = [
        httpswww.googleapis.comauthspreadsheets,
        httpswww.googleapis.comauthdrive
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    sheet = gc.open_by_key(SPREADSHEET_ID).sheet1

    # Егер кесте бос болса, бірінші жолға тақырыптарды жазу
    if not sheet.row_values(1)
        sheet.append_row([Уақыты, Рубрика, Бірегей ID немесе Сілтеме, Тақырыбы])
    return sheet


def get_published_ids(sheet)
    Кестедегі 3-бағаннан бұрын жарияланған барлық сілтемелер мен тақырыптарды алу.
    return set(sheet.col_values(3))


def save_to_sheet(sheet, category, unique_id, title)
    Жаңа жарияланған постты Google Sheets-ке тіркеу.
    now = datetime.now().strftime(%Y-%m-%d %H%M%S)
    sheet.append_row([now, category, unique_id, title])


def fetch_new_rss_item(feeds, published_ids)
    RSS таспалардан Google Sheets-те жоқ ең жаңа мақаланы табу.
    for feed_url in feeds
        feed = feedparser.parse(feed_url)
        for entry in feed.entries
            link = entry.get(link, ).strip()
            if link and link not in published_ids
                summary = entry.get(summary, entry.get(description, ))
                return {
                    title entry.get(title, Тақырыпсыз),
                    summary summary,
                    link link
                }
    return None


def generate_text_with_gemini(prompt)
    Gemini API арқылы пост мәтінін генерациялау.
    response = client.models.generate_content(
        model=gemini-2.5-flash,
        contents=prompt,
    )
    return response.text.strip()


def send_to_telegram(text)
    Дайын мәтінді Telegram арнаға жіберу.
    url = fhttpsapi.telegram.orgbot{TELEGRAM_BOT_TOKEN}sendMessage
    payload = {
        chat_id TELEGRAM_CHAT_ID,
        text text,
        parse_mode HTML,
        disable_web_page_preview False
    }
    response = requests.post(url, json=payload, timeout=30)
    if not response.ok
        print(fHTML форматында қате шықты, қарапайым мәтінмен жіберілуде {response.text})
        payload.pop(parse_mode)
        r2 = requests.post(url, json=payload, timeout=30)
        r2.raise_for_status()


def run_kz_news(sheet, published_ids)
    1-рубрика Қазақстан жаңалықтары.
    item = fetch_new_rss_item(KZ_NEWS_FEEDS, published_ids)
    if not item
        print(Жаңа Қазақстан жаңалығы табылмады.)
        return

    prompt = fСен кәсіби қазақтілді Telegram-арнаның бас редакторысың.
Мына жаңалықтың негізінде қысқа, нақты әрі тартымды пост жаз
Тақырыбы {item['title']}
Мазмұны {item['summary']}

Талаптар
- Тек сауатты, табиғи қазақ тілінде жаз.
- Форматтау үшін тек Telegram HTML тегтерін (bқалыңb, iкөлбеуi) қолдан. Markdown ( немесе ##) МҮЛДЕМ қолданба!
- Басында тақырыпты эмодзимен және b...b тегімен ерекшеле.
- Негізгі ойды 2-3 қысқа абзацпен немесе буллитпен (•) жеткіз.
- Соңына a href={item['link']}Толығырақ оқуa деген сілтеме мен 2-3 хэштег қос.
- Ешқандай кіріспе сөз (Міне, дайын пост) жазба, бірден пост мәтінін бер.

    post_text = generate_text_with_gemini(prompt)
    send_to_telegram(post_text)
    save_to_sheet(sheet, kz_news, item[link], item[title])
    print(fСәтті жарияланды [KZ News] {item['title']})


def run_tech_ai(sheet, published_ids)
    2-рубрика ЖИ және Технология жаңалықтары.
    item = fetch_new_rss_item(TECH_AI_FEEDS, published_ids)
    if not item
        print(Жаңа ТехноЖИ жаңалығы табылмады.)
        return

    prompt = fСен жасанды интеллект және технология туралы жазатын қазақтілді сарапшысың.
Мына шетелдік мақаланы қазақ тіліне аударып, оқырманға қызықты пост жаса
Тақырыбы {item['title']}
Мазмұны {item['summary']}

Талаптар
- Сөзбе-сөз калька аударма жасамай, мағынасын жеңіл әрі түсінікті қазақ тілінде жеткіз.
- Форматтау үшін тек HTML тегтерін (b, i) қолдан. Markdown ( немесе ##) МҮЛДЕМ қолданба!
- Құрылымы
  1. 🤖 bТартымды тақырыпb
  2. Не болды (2-3 сөйлем)
  3. Бұл несімен маңызды (2-3 пункт • белгісімен)
  4. a href={item['link']}Дереккөзa және #ЖИ #Технология хэштегтері.
- Ешқандай кіріспе сөз қоспа.

    post_text = generate_text_with_gemini(prompt)
    send_to_telegram(post_text)
    save_to_sheet(sheet, tech_ai, item[link], item[title])
    print(fСәтті жарияланды [TechAI] {item['title']})


def run_lifehacks(sheet, published_ids)
    3-рубрика Қызықты деректер мен Лайфхактар (базадағы тақырыптарды қайталамайды).
    past_topics = [x for x in published_ids if x.startswith(TOPIC)]
    recent_topics_str = , .join(past_topics[-40]) if past_topics else Жоқ

    prompt = fСен танымдық Telegram-арнаның авторысың.
Оқырмандарға арналған 1 таңғажайып ғылымитарихи дерек ЖӘНЕ күнделікті өміргесмартфонғажұмыс өнімділігіне қатысты 1 нақты практикалық лайфхак жаз.

МАҢЫЗДЫ ЕРЕЖЕ Бұрын мына тақырыптар жарияланған, оларды МҮЛДЕМ қайталама [{recent_topics_str}]

Жауабыңды міндетті түрде екі бөліктен құра
Бірінші жолға тек қана тақырыптың қысқаша кодын жаз, мысалы
TOPIC Помодоро әдісі және ми нейрондары
Екінші жолдан бастап Telegram-ға арналған дайын постты жаз
- Форматтау үшін тек HTML (b, i) қолдан, Markdown ( немесе ##) қолданба!
- Эмодзилермен (💡, 🧠, 📌) әсемдеп, оқуға жеңіл етіп жаз.
- Соңында оқырмандарды пікір жазуға шақыратын 1 сұрақ қой және #пайдалы #лайфхак #дерек хэштегтерін қос.

    raw_output = generate_text_with_gemini(prompt)
    lines = raw_output.splitlines()

    topic_id = fTOPIC {datetime.now().strftime('%Y-%m-%d %H%M')}
    post_lines = []

    for line in lines
        if line.strip().startswith(TOPIC)
            topic_id = line.strip()
        else
            post_lines.append(line)

    post_text = n.join(post_lines).strip()
    send_to_telegram(post_text)
    save_to_sheet(sheet, lifehack_fact, topic_id, topic_id)
    print(fСәтті жарияланды [Lifehack] {topic_id})


if __name__ == __main__
    # Аргумент арқылы қай рубриканы қосу керектігін анықтау kz_news, tech_ai, lifehack
    mode = sys.argv[1] if len(sys.argv)  1 else kz_news
    sheet = get_google_sheet()
    published = get_published_ids(sheet)

    if mode == kz_news
        run_kz_news(sheet, published)
    elif mode == tech_ai
        run_tech_ai(sheet, published)
    elif mode == lifehack
        run_lifehacks(sheet, published)
    else
        print(fБелгісіз режим {mode})