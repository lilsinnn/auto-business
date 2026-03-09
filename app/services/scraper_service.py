import asyncio
import os
import requests
import base64
import json
import re
import logging
from statistics import median
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
YANDEX_FOLDER_ID = os.getenv("YANDEX_SEARCH_USER")
YANDEX_API_KEY = os.getenv("YANDEX_SEARCH_KEY")

logger = logging.getLogger(__name__)

# ========================================================================
# ЛОКАЛЬНАЯ БАЗА ЦЕН ПОСТАВЩИКОВ (из программы кими)
# Ключ: нормализованные ключевые слова из названия товара
# Значение: (цена, поставщик, ссылка)
# ========================================================================
PRICE_DATABASE = {
    # === ОТВОДЫ ===
    ('отвод', '57', '4', 'ст20'):     (1250.00, 'Сантехкомплект', 'https://santechkomplekt.ru'),
    ('отвод', '57', '4', '20'):       (1250.00, 'Сантехкомплект', 'https://santechkomplekt.ru'),
    ('отвод', '57', '4'):             (1180.00, 'БК Арматура',    'https://bkarmatura.ru'),
    ('отвод', '89', '4', 'ст20'):     (1850.00, 'Сантехкомплект', 'https://santechkomplekt.ru'),
    ('отвод', '89', '4', '20'):       (1850.00, 'Сантехкомплект', 'https://santechkomplekt.ru'),
    ('отвод', '89', '4'):             (1780.00, 'Лунда',          'https://lunda.ru'),
    ('отвод', '108', '4', 'ст20'):    (2450.00, 'Сантехкомплект', 'https://santechkomplekt.ru'),
    ('отвод', '108', '4'):            (2450.00, 'Сантехкомплект', 'https://santechkomplekt.ru'),
    ('отвод', '57', '4', '09г2с'):    (1450.00, 'БК Арматура',    'https://bkarmatura.ru'),

    # === ТРОЙНИКИ ===
    ('тройник', '57', '4', 'ст20'):   (1850.00, 'Сантехкомплект', 'https://santechkomplekt.ru'),
    ('тройник', '57', '4', '20'):     (1850.00, 'Сантехкомплект', 'https://santechkomplekt.ru'),
    ('тройник', '57', '4'):           (1750.00, 'БК Арматура',    'https://bkarmatura.ru'),
    ('тройник', '108', '5', '09г2с'): (3200.00, 'Сантехкомплект', 'https://santechkomplekt.ru'),
    ('тройник', '108', '5'):          (2950.00, 'Лунда',          'https://lunda.ru'),

    # === ФЛАНЦЫ ===
    ('фланец', '50', '16'):           (850.00,  'Сантехкомплект', 'https://santechkomplekt.ru'),
    ('фланец', '50'):                 (780.00,  'Лунда',          'https://lunda.ru'),
    ('фланец', '80', '16'):           (1200.00, 'Сантехкомплект', 'https://santechkomplekt.ru'),
    ('фланец', '80'):                 (1100.00, 'Лунда',          'https://lunda.ru'),
    ('фланец', '100', '16'):          (1450.00, 'Сантехкомплект', 'https://santechkomplekt.ru'),
    ('фланец', '100'):                (1350.00, 'Лунда',          'https://lunda.ru'),

    # === ПЕРЕХОДЫ ===
    ('переход', '57', '32'):          (980.00,  'Сантехкомплект', 'https://santechkomplekt.ru'),
    ('переход', '89', '57'):          (1350.00, 'БК Арматура',    'https://bkarmatura.ru'),
    ('переход', '108', '57'):         (1800.00, 'Сантехкомплект', 'https://santechkomplekt.ru'),

    # === ЗАДВИЖКИ / КРАНЫ ===
    ('задвижка', '50'):               (4500.00, 'БК Арматура',    'https://bkarmatura.ru'),
    ('задвижка', '80'):               (7200.00, 'БК Арматура',    'https://bkarmatura.ru'),
    ('задвижка', '100'):              (9500.00, 'БК Арматура',    'https://bkarmatura.ru'),
    ('кран', 'шаровой', '50'):        (3200.00, 'Сантехкомплект', 'https://santechkomplekt.ru'),
    ('кран', 'шаровой', '80'):        (5800.00, 'Сантехкомплект', 'https://santechkomplekt.ru'),

    # === МЕТАЛЛОПРОКАТ ===
    ('лист', '10', 'ст3'):            (85.00,   'Металлосервис',  'https://metalloservis.ru'),  # за кг
    ('лист', '10', 'ст20'):           (92.00,   'Металлосервис',  'https://metalloservis.ru'),  # за кг
    ('круг', '20', 'ст3'):            (78.00,   'Металлосервис',  'https://metalloservis.ru'),  # за кг
    ('круг', '20', 'ст20'):           (85.00,   'Металлосервис',  'https://metalloservis.ru'),  # за кг
    ('уголок', '50', '5'):            (82.00,   'Металлосервис',  'https://metalloservis.ru'),  # за кг
    ('швеллер', '10'):                (88.00,   'Металлосервис',  'https://metalloservis.ru'),  # за кг
    ('арматура', '12'):               (72.00,   'Металлосервис',  'https://metalloservis.ru'),  # за кг
}


def _normalize_text(text: str) -> list[str]:
    """Разбивает название товара на нормализованные токены."""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)  # убираем пунктуацию
    text = re.sub(r'\s+', ' ', text).strip()
    return text.split()


def _lookup_local_price(product_name: str):
    """
    Ищет цену в локальной базе по максимальному совпадению ключевых слов.
    Возвращает (price, supplier, url) или None.
    """
    tokens = _normalize_text(product_name)

    best_match = None
    best_match_len = 0

    for key_tuple, value in PRICE_DATABASE.items():
        # Все ключи из кортежа должны присутствовать в токенах
        if all(k in tokens for k in key_tuple):
            # Чем длиннее совпадение (больше специфичность) — тем лучше
            if len(key_tuple) > best_match_len:
                best_match = value
                best_match_len = len(key_tuple)

    return best_match


# ========================================================================
# Yandex Search — фоллбэк для товаров, которых нет в локальной базе
# ========================================================================

TRUSTED_SITES = [
    ('santechkomplekt.ru', 'Сантехкомплект'),
    ('bkarmatura.ru', 'БК Арматура'),
    ('lunda.ru', 'Лунда'),
    ('metalloservis.ru', 'Металлосервис'),
    ('tpm.ru', 'Трубопроводный Мир'),
    ('pulscen.ru', 'Пульс Цен'),
]


def _get_domain(url: str) -> str:
    try:
        return url.split('/')[2].replace('www.', '')
    except:
        return ''


def extract_prices(text: str) -> list[float]:
    if not text:
        return []
    prices = []
    for m in re.finditer(r'(\d{1,3}(?:\s\d{3})*(?:[.,]\d{1,2})?)\s*(?:руб|р\b|₽)', text, re.IGNORECASE):
        try:
            val = float(m.group(1).replace(" ", "").replace(",", "."))
            if 10 <= val <= 50000:
                prices.append(val)
        except:
            pass
    return prices


def _yandex_search(query_text: str) -> list:
    """Yandex Cloud Search API v2, возвращает [(price, url)]."""
    url = "https://searchapi.api.cloud.yandex.net/v2/web/search"
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "query": {
            "search_type": "SEARCH_TYPE_RU",
            "query_text": query_text
        },
        "folderId": YANDEX_FOLDER_ID
    }

    try:
        resp = requests.post(url, headers=headers, json=data, timeout=10)
        if resp.status_code != 200:
            logger.error(f"Yandex API {resp.status_code}: {resp.text[:200]}")
            return []

        raw_b64 = resp.json().get("rawData")
        if not raw_b64:
            return []

        xml_str = base64.b64decode(raw_b64).decode('utf-8')
        soup = BeautifulSoup(xml_str, 'xml')

        if soup.find("error"):
            logger.error(f"Yandex XML Error: {soup.find('error').text}")
            return []

        hits = []
        for doc in soup.find_all('doc'):
            doc_url = doc.url.text if doc.url else ""
            doc_passages = " ".join([p.text for p in doc.find_all('passage')])
            prices = extract_prices(doc_passages)
            if prices:
                best_price = sorted(prices)[len(prices) // 2]
                hits.append((best_price, doc_url))
                logger.info(f"  💰 {best_price}₽ @ {_get_domain(doc_url)}")

        return hits

    except Exception as e:
        logger.error(f"Yandex search error: {e}")
        return []


# ========================================================================
# Главная функция — вызывается из main.py
# ========================================================================

async def scrape_for_items(db, items):
    """
    Для каждого товара:
    1. Сначала ищет в ЛОКАЛЬНОЙ БАЗЕ ЦЕН (мгновенно, точно)
    2. Если не нашёл — фоллбэк в Yandex Search API
    """
    for item in items:
        product = item.original_name
        logger.info(f"🔍 Ищем цену для: '{product}'")

        # ===== ШАГ 1: Локальная база цен =====
        local = _lookup_local_price(product)
        if local:
            price, supplier, url = local
            item.found_name = item.original_name
            item.price = price
            item.source_url = url
            item.supplier_name = supplier
            logger.info(f"✅ [ЛОКАЛЬНО] {product} → {price}₽ @ {supplier}")
            continue

        # ===== ШАГ 2: Yandex Search (фоллбэк) =====
        if not YANDEX_FOLDER_ID or not YANDEX_API_KEY:
            logger.warning(f"❌ Нет API ключей и нет локальной цены для '{product}'")
            continue

        # Ищем на проверенных сайтах
        sites_query = " | ".join(f"site:{s[0]}" for s in TRUSTED_SITES[:4])
        trusted_query = f"{product} цена ({sites_query})"
        logger.info(f"[YANDEX] Searching: '{trusted_query}'")

        all_hits = _yandex_search(trusted_query)

        # Если ничего с проверенных — общий поиск
        if not all_hits:
            general_query = f"{product} цена за штуку купить"
            logger.info(f"[YANDEX GENERAL] Searching: '{general_query}'")
            all_hits = _yandex_search(general_query)

        if all_hits:
            prices_only = [h[0] for h in all_hits]
            med_price = median(prices_only)
            best = min(all_hits, key=lambda h: abs(h[0] - med_price))
            price, source_url = best

            item.found_name = item.original_name
            item.price = price
            item.source_url = source_url

            domain = _get_domain(source_url)
            supplier_name = domain
            for site_domain, site_name in TRUSTED_SITES:
                if site_domain in domain:
                    supplier_name = site_name
                    break
            item.supplier_name = supplier_name
            logger.info(f"✅ [YANDEX] {product} → {price}₽ @ {supplier_name}")
        else:
            logger.warning(f"❌ Цена не найдена для '{product}'")

    return items
