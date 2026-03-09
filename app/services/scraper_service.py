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

# Проверенные поставщики — ищем прямо на их сайтах
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
    """Extract ALL prices from text, return list."""
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
    """Execute one Yandex Cloud Search API v2 call, return list of (price, url, title)."""
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

        result_json = resp.json()
        raw_b64 = result_json.get("rawData")
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
            doc_title = doc.title.text if doc.title else ""
            # Извлекаем цены ТОЛЬКО из сниппетов (passages), НЕ из заголовков!
            # Заголовки содержат "от X руб" — это мин. цена по всей категории, не по товару
            doc_passages = " ".join([p.text for p in doc.find_all('passage')])

            prices = extract_prices(doc_passages)
            if prices:
                # Медиана цен в рамках одного сниппета
                best_price = sorted(prices)[len(prices) // 2]
                hits.append((best_price, doc_url))
                logger.info(f"  💰 {best_price}₽ @ {_get_domain(doc_url)}")

        return hits

    except Exception as e:
        logger.error(f"Yandex search error: {e}")
        return []


async def scrape_for_items(db, items):
    """
    Для каждого товара:
    1. Сначала ищет прямо на сайтах проверенных поставщиков (site:xxx.ru товар)
    2. Если с проверенных ничего — делает общий поиск
    3. Берёт медиану найденных цен
    """
    if not YANDEX_FOLDER_ID or not YANDEX_API_KEY:
        logger.error("Missing Yandex Cloud Search Credentials.")
        return items

    for item in items:
        product = item.original_name
        all_hits = []

        # ===== ШАГ 1: Ищем прямо на проверенных сайтах =====
        # Формируем один запрос с несколькими site: операторами
        sites_query = " | ".join(f"site:{s[0]}" for s in TRUSTED_SITES[:4])
        trusted_query = f"{product} цена ({sites_query})"
        logger.info(f"[TRUSTED] Searching: '{trusted_query}'")

        trusted_hits = _yandex_search(trusted_query)
        if trusted_hits:
            all_hits = trusted_hits
            logger.info(f"[TRUSTED] Found {len(trusted_hits)} price(s) from trusted sites for '{product}'")

        # ===== ШАГ 2: Если проверенные не дали ничего — общий поиск =====
        if not all_hits:
            general_query = f"{product} цена за штуку купить"
            logger.info(f"[GENERAL] Searching: '{general_query}'")
            all_hits = _yandex_search(general_query)
            logger.info(f"[GENERAL] Found {len(all_hits)} price(s) for '{product}'")

        # ===== ШАГ 3: Выбираем лучшую цену =====
        if all_hits:
            prices_only = [h[0] for h in all_hits]
            med_price = median(prices_only)

            # Берём вариант ближайший к медиане
            best = min(all_hits, key=lambda h: abs(h[0] - med_price))
            price, source_url = best

            # НЕ меняем found_name — оставляем исходное название товара
            item.found_name = item.original_name
            item.price = price
            item.source_url = source_url

            domain = _get_domain(source_url)
            # Ищем читаемое имя поставщика
            supplier_name = domain
            for site_domain, site_name in TRUSTED_SITES:
                if site_domain in domain:
                    supplier_name = site_name
                    break
            item.supplier_name = supplier_name

            logger.info(f"✅ {product} → {price}₽ @ {supplier_name}")
        else:
            logger.warning(f"❌ No prices found for '{product}'")

    return items
