"""
Scraper Service — Полноценный движок цен
Портировано из программы Кими + Yandex Search фоллбэк

Включает:
- Нормализацию товаров (разбор на тип/диаметр/стенку/материал)
- Мульти-поставщиковую базу цен с тиерами
- Ранжирование предложений (score)
- Ценовой коридор (фильтрация аномалий)
- Yandex Search API как фоллбэк
"""
import asyncio
import os
import re
import logging
import requests
import base64
from statistics import median
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
YANDEX_FOLDER_ID = os.getenv("YANDEX_SEARCH_USER")
YANDEX_API_KEY = os.getenv("YANDEX_SEARCH_KEY")

logger = logging.getLogger(__name__)


# ========================================================================
# 1. НОРМАЛИЗАЦИЯ ТОВАРОВ
# ========================================================================

@dataclass
class NormalizedProduct:
    """Нормализованный товар с разбивкой на компоненты"""
    raw_name: str
    product_type: str = ""       # отвод, тройник, фланец, лист...
    type_code: str = ""          # OTV, TRO, FLN, LIST...
    diameter: Optional[float] = None
    wall_thickness: Optional[float] = None
    dn: Optional[int] = None     # Ду для фланцев
    pn: Optional[int] = None     # Ру для фланцев
    material: str = ""           # ст20, 09Г2С...
    gost: str = ""
    category: str = ""           # PIPELINE_DETAILS, METAL_ROLLED, VALVES


# Маппинг типов товаров
TYPE_MAP = {
    'отвод':     ('OTV', 'PIPELINE_DETAILS'),
    'тройник':   ('TRO', 'PIPELINE_DETAILS'),
    'переход':   ('PER', 'PIPELINE_DETAILS'),
    'фланец':    ('FLN', 'PIPELINE_DETAILS'),
    'заглушка':  ('ZAG', 'PIPELINE_DETAILS'),
    'муфта':     ('MUF', 'PIPELINE_DETAILS'),
    'задвижка':  ('ZAD', 'VALVES'),
    'кран':      ('KRN', 'VALVES'),
    'клапан':    ('KLP', 'VALVES'),
    'вентиль':   ('VNT', 'VALVES'),
    'лист':      ('LIST', 'METAL_ROLLED'),
    'круг':      ('KRUG', 'METAL_ROLLED'),
    'уголок':    ('UGOL', 'METAL_ROLLED'),
    'швеллер':   ('SHVEL', 'METAL_ROLLED'),
    'арматура':  ('ARMT', 'METAL_ROLLED'),
    'труба':     ('TRUBA', 'PIPELINE_DETAILS'),
    'сетка':     ('SETK', 'METAL_ROLLED'),
    'балка':     ('BALK', 'METAL_ROLLED'),
    'полоса':    ('POLOS', 'METAL_ROLLED'),
}

# Маппинг материалов
MATERIAL_MAP = {
    'ст20': 'ст20', 'ст.20': 'ст20', 'сталь 20': 'ст20', 'сталь20': 'ст20', '20': 'ст20',
    'ст3': 'ст3', 'ст.3': 'ст3', 'сталь 3': 'ст3',
    '09г2с': '09Г2С', '09г2': '09Г2С',
    '12х18н10т': '12Х18Н10Т',
    'нерж': '12Х18Н10Т',
}


def normalize_product(raw_name: str) -> NormalizedProduct:
    """
    Разбирает строку товара на компоненты.
    Пример: "Тройник равнопроходной 57х4 ст20 ГОСТ 894" 
         → type=тройник, diameter=57, wall=4, material=ст20
    """
    result = NormalizedProduct(raw_name=raw_name)
    text = raw_name.lower().strip()

    # 1. Определяем тип товара
    for type_name, (code, cat) in TYPE_MAP.items():
        if type_name in text:
            result.product_type = type_name
            result.type_code = code
            result.category = cat
            break

    # 2. Извлекаем размеры: "57х4", "108x5", "57*4"
    size_match = re.search(r'(\d+(?:[.,]\d+)?)\s*[хxХX×*]\s*(\d+(?:[.,]\d+)?)', text)
    if size_match:
        result.diameter = float(size_match.group(1).replace(',', '.'))
        result.wall_thickness = float(size_match.group(2).replace(',', '.'))

    # 3. Извлекаем Ду для фланцев: "Ду50", "ДУ 80", "dn50"
    dn_match = re.search(r'(?:ду|dn)\s*(\d+)', text, re.IGNORECASE)
    if dn_match:
        result.dn = int(dn_match.group(1))
        if not result.diameter:
            result.diameter = float(result.dn)

    # 4. Извлекаем Ру: "Ру16", "PN 16"
    pn_match = re.search(r'(?:ру|pn)\s*(\d+)', text, re.IGNORECASE)
    if pn_match:
        result.pn = int(pn_match.group(1))

    # 5. Извлекаем материал
    for pattern, mat_code in MATERIAL_MAP.items():
        if pattern in text:
            result.material = mat_code
            break

    # 6. Извлекаем ГОСТ
    gost_match = re.search(r'гост\s*(\d+)', text, re.IGNORECASE)
    if gost_match:
        result.gost = gost_match.group(1)

    # Если фланец и нет диаметра — пробуем из чисел
    if result.product_type == 'фланец' and not result.diameter:
        nums = re.findall(r'\b(\d+)\b', text)
        for n in nums:
            val = int(n)
            if 15 <= val <= 500 and val != result.pn:
                result.diameter = float(val)
                break

    logger.info(f"📦 Нормализация: '{raw_name}' → тип={result.product_type}, "
                f"⌀={result.diameter}, стенка={result.wall_thickness}, "
                f"мат={result.material}, кат={result.category}")
    return result


# ========================================================================
# 2. БАЗА ЦЕН ПОСТАВЩИКОВ (портировано из Кими)
# ========================================================================

@dataclass
class SupplierOffer:
    """Предложение от поставщика"""
    supplier_id: str
    supplier_name: str
    price: float
    currency: str = 'RUB'
    stock: int = 100          # в наличии
    delivery_days: int = 2
    reliability: float = 0.9
    min_order: int = 1
    url: str = ''
    unit: str = 'шт'
    article: str = ''
    product_name: str = ''
    # Ценовые тиеры (скидки за объём)
    price_tiers: Dict[int, float] = field(default_factory=dict)

    def get_price_for_qty(self, qty: int) -> float:
        """Получить цену с учётом скидки за объём"""
        if not self.price_tiers:
            return self.price
        best = self.price
        for min_qty, tier_price in sorted(self.price_tiers.items(), reverse=True):
            if qty >= min_qty:
                best = tier_price
                break
        return best


# Поставщики
SUPPLIERS = {
    'santechkomplekt': {
        'name': 'Сантехкомплект',
        'reliability': 0.95,
        'delivery_days': 1,
        'url': 'https://santechkomplekt.ru',
    },
    'bkarmatura': {
        'name': 'БК Арматура',
        'reliability': 0.90,
        'delivery_days': 2,
        'url': 'https://bkarmatura.ru',
    },
    'lunda': {
        'name': 'Лунда',
        'reliability': 0.85,
        'delivery_days': 3,
        'url': 'https://lunda.ru',
    },
    'metalloservis': {
        'name': 'Металлосервис',
        'reliability': 0.87,
        'delivery_days': 2,
        'url': 'https://metalloservis.ru',
    },
    'trubmir': {
        'name': 'Трубопроводный мир',
        'reliability': 1.0,
        'delivery_days': 1,
        'url': 'https://tpm.ru',
    },
}


def _make_offer(supplier_id: str, price: float, product_name: str = '',
                stock: int = 100, min_order: int = 1, tiers: Dict[int, float] = None,
                unit: str = 'шт') -> SupplierOffer:
    """Хелпер для создания оффера"""
    s = SUPPLIERS[supplier_id]
    return SupplierOffer(
        supplier_id=supplier_id,
        supplier_name=s['name'],
        price=price,
        stock=stock,
        delivery_days=s['delivery_days'],
        reliability=s['reliability'],
        min_order=min_order,
        url=s['url'],
        product_name=product_name,
        price_tiers=tiers or {},
        unit=unit,
    )


# Ключ: (type_code, diameter, wall_thickness, material) — чем больше полей, тем точнее матч
# Значение: список офферов от разных поставщиков
PRICE_DB: Dict[tuple, List[SupplierOffer]] = {
    # === ОТВОДЫ ===
    ('OTV', 57, 4, 'ст20'): [
        _make_offer('santechkomplekt', 1250, 'Отвод 57х4 ст20 ГОСТ 17375', tiers={1: 1250, 10: 1150, 50: 1050}),
        _make_offer('bkarmatura',      1180, 'Отвод 57х4 ст20',            tiers={5: 1180, 20: 1080, 100: 980}, min_order=5),
        _make_offer('lunda',           1150, 'Отвод 57х4 ст20',            tiers={10: 1150, 25: 1050, 100: 950}, min_order=10),
    ],
    ('OTV', 89, 4, 'ст20'): [
        _make_offer('santechkomplekt', 1850, 'Отвод 89х4 ст20 ГОСТ 17375', tiers={1: 1850, 10: 1700, 30: 1550}),
        _make_offer('lunda',           1780, 'Отвод 89х4 ст20',            tiers={10: 1780, 25: 1620}),
    ],
    ('OTV', 108, 4, 'ст20'): [
        _make_offer('santechkomplekt', 2450, 'Отвод 108х4 ст20 ГОСТ 17375'),
    ],
    ('OTV', 57, 4, '09Г2С'): [
        _make_offer('bkarmatura', 1450, 'Отвод 57х4 09Г2С'),
    ],

    # === ТРОЙНИКИ ===
    ('TRO', 57, 4, 'ст20'): [
        _make_offer('santechkomplekt', 1850, 'Тройник 57х4 ст20 ГОСТ 894', tiers={1: 1850, 5: 1750, 20: 1600}),
        _make_offer('bkarmatura',      1750, 'Тройник 57х4 ст20',          tiers={5: 1750, 15: 1650, 50: 1500}),
        _make_offer('lunda',           1700, 'Тройник 57х4 ст20',          tiers={10: 1700, 30: 1550}),
    ],
    ('TRO', 108, 5, '09Г2С'): [
        _make_offer('santechkomplekt', 3200, 'Тройник 108х5 09Г2С ГОСТ 894', tiers={1: 3200, 5: 3000, 20: 2800}),
        _make_offer('bkarmatura',      3050, 'Тройник 108х5 09Г2С',          tiers={5: 3050, 15: 2850}),
        _make_offer('lunda',           2950, 'Тройник 108х5 09Г2С',          tiers={5: 2950, 20: 2750, 50: 2550}),
    ],

    # === ФЛАНЦЫ ===
    ('FLN', 50, None, ''): [
        _make_offer('santechkomplekt', 850,  'Фланец Ду50 Ру16', stock=200),
        _make_offer('lunda',           780,  'Фланец Ду50',      stock=150, min_order=10),
        _make_offer('bkarmatura',      820,  'Фланец Ду50 Ру16', stock=90),
    ],
    ('FLN', 80, None, ''): [
        _make_offer('santechkomplekt', 1200, 'Фланец Ду80 Ру16', stock=120),
        _make_offer('lunda',           1100, 'Фланец Ду80',      stock=80),
    ],
    ('FLN', 100, None, ''): [
        _make_offer('santechkomplekt', 1450, 'Фланец Ду100 Ру16'),
        _make_offer('lunda',           1350, 'Фланец Ду100'),
    ],

    # === ПЕРЕХОДЫ ===
    ('PER', 57, 32, ''): [
        _make_offer('santechkomplekt', 980,  'Переход 57х32 ст20'),
    ],
    ('PER', 89, 57, ''): [
        _make_offer('bkarmatura', 1350, 'Переход 89х57 ст20'),
    ],

    # === ЗАДВИЖКИ ===
    ('ZAD', 50, None, ''): [
        _make_offer('bkarmatura',      4500, 'Задвижка Ду50'),
        _make_offer('santechkomplekt', 4800, 'Задвижка Ду50'),
    ],
    ('ZAD', 80, None, ''): [
        _make_offer('bkarmatura', 7200, 'Задвижка Ду80'),
    ],
    ('ZAD', 100, None, ''): [
        _make_offer('bkarmatura', 9500, 'Задвижка Ду100'),
    ],

    # === КРАНЫ ===
    ('KRN', 50, None, ''): [
        _make_offer('santechkomplekt', 3200, 'Кран шаровой Ду50'),
        _make_offer('bkarmatura',      3400, 'Кран шаровой Ду50'),
    ],

    # === МЕТАЛЛОПРОКАТ (цены за кг) ===
    ('LIST', 10, None, 'ст3'): [
        _make_offer('metalloservis', 85,  'Лист стальной 10мм ст3', unit='кг'),
        _make_offer('trubmir',       88,  'Лист 10мм ст3',          unit='кг'),
    ],
    ('LIST', 10, None, 'ст20'): [
        _make_offer('metalloservis', 92,  'Лист стальной 10мм ст20', unit='кг'),
    ],
    ('KRUG', 20, None, 'ст20'): [
        _make_offer('metalloservis', 85,  'Круг 20мм ст20', unit='кг'),
    ],
    ('UGOL', 50, 5, 'ст3'): [
        _make_offer('metalloservis', 82,  'Уголок 50х5 ст3', unit='кг'),
    ],
    ('SHVEL', 10, None, ''): [
        _make_offer('metalloservis', 88,  'Швеллер 10П ст3', unit='кг'),
    ],
    ('ARMT', 12, None, ''): [
        _make_offer('metalloservis', 72,  'Арматура 12мм А500С', unit='кг'),
    ],

    # === ТРУБЫ ===
    ('TRUBA', 57, 4, 'ст20'): [
        _make_offer('santechkomplekt', 2100, 'Труба 57х4 ст20 ГОСТ 8732', unit='м'),
        _make_offer('trubmir',         1950, 'Труба 57х4 ст20',           unit='м'),
    ],
    ('TRUBA', 89, 4, 'ст20'): [
        _make_offer('santechkomplekt', 3200, 'Труба 89х4 ст20 ГОСТ 8732', unit='м'),
    ],
}


def _generate_search_keys(np: NormalizedProduct) -> List[tuple]:
    """
    Генерирует ключи поиска от самого точного до самого общего.
    Возвращает несколько вариантов для fuzzy-matching.
    """
    keys = []
    tc = np.type_code
    d = int(np.diameter) if np.diameter else None
    w = int(np.wall_thickness) if np.wall_thickness else None
    mat = np.material

    if tc and d:
        # Точный ключ: тип + диаметр + стенка + материал
        if w and mat:
            keys.append((tc, d, w, mat))
        # Тип + диаметр + стенка
        if w:
            keys.append((tc, d, w, ''))
        # Тип + диаметр + материал
        if mat:
            keys.append((tc, d, None, mat))
        # Тип + диаметр
        keys.append((tc, d, None, ''))

    return keys


def lookup_offers(np: NormalizedProduct) -> List[SupplierOffer]:
    """Ищет офферы в базе по нормализованному товару, от точного к нечёткому."""
    keys = _generate_search_keys(np)
    for key in keys:
        if key in PRICE_DB:
            logger.info(f"  ✅ Найдено по ключу {key}: {len(PRICE_DB[key])} предложений")
            return PRICE_DB[key]
    logger.info(f"  ❌ В локальной базе не найдено для {np.type_code} ⌀{np.diameter}")
    return []


# ========================================================================
# 3. РАНЖИРОВАНИЕ И СКОРИНГ ПРЕДЛОЖЕНИЙ
# ========================================================================

# Веса для скоринга
WEIGHT_PRICE       = 0.40
WEIGHT_STOCK       = 0.25
WEIGHT_DELIVERY    = 0.20
WEIGHT_RELIABILITY = 0.15


def score_offers(offers: List[SupplierOffer], qty: int = 1) -> List[Tuple[SupplierOffer, float, Dict[str, float]]]:
    """
    Ранжирует офферы по score (0..1).
    Возвращает [(offer, total_score, breakdown), ...] отсортированные по score DESC.
    """
    if not offers:
        return []

    # Базовые значения
    prices = [o.get_price_for_qty(qty) for o in offers]
    min_price = min(prices)
    min_delivery = min(o.delivery_days for o in offers) or 1

    scored = []
    for offer in offers:
        actual_price = offer.get_price_for_qty(qty)

        # Price score: чем ниже цена — тем лучше (1.0 = минимальная)
        price_score = min_price / actual_price if actual_price > 0 else 0

        # Stock score: есть ли достаточно на складе
        if offer.stock >= qty:
            stock_score = 1.0
        elif offer.stock > 0:
            stock_score = offer.stock / qty
        else:
            stock_score = 0.3  # под заказ

        # Delivery score: чем быстрее — тем лучше
        delivery_score = min_delivery / offer.delivery_days if offer.delivery_days > 0 else 0

        # Reliability score
        reliability_score = offer.reliability

        # Итоговый score
        total = (
            WEIGHT_PRICE * price_score +
            WEIGHT_STOCK * stock_score +
            WEIGHT_DELIVERY * delivery_score +
            WEIGHT_RELIABILITY * reliability_score
        )

        breakdown = {
            'price': round(price_score, 3),
            'stock': round(stock_score, 3),
            'delivery': round(delivery_score, 3),
            'reliability': round(reliability_score, 3),
        }

        scored.append((offer, round(total, 3), breakdown))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


# ========================================================================
# 4. YANDEX SEARCH — фоллбэк
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


def _extract_prices_from_text(text: str) -> List[float]:
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


def _yandex_fallback(product_name: str) -> Optional[Tuple[float, str, str]]:
    """Yandex Search фоллбэк. Возвращает (price, url, supplier_name) или None."""
    if not YANDEX_FOLDER_ID or not YANDEX_API_KEY:
        return None

    sites_query = " | ".join(f"site:{s[0]}" for s in TRUSTED_SITES[:4])
    query = f"{product_name} цена ({sites_query})"
    logger.info(f"  [YANDEX] Searching: '{query}'")

    try:
        resp = requests.post(
            "https://searchapi.api.cloud.yandex.net/v2/web/search",
            headers={"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"},
            json={"query": {"search_type": "SEARCH_TYPE_RU", "query_text": query}, "folderId": YANDEX_FOLDER_ID},
            timeout=10
        )
        if resp.status_code != 200:
            return None

        raw_b64 = resp.json().get("rawData")
        if not raw_b64:
            return None

        xml_str = base64.b64decode(raw_b64).decode('utf-8')
        soup = BeautifulSoup(xml_str, 'xml')
        if soup.find("error"):
            return None

        hits = []
        for doc in soup.find_all('doc'):
            doc_url = doc.url.text if doc.url else ""
            doc_passages = " ".join([p.text for p in doc.find_all('passage')])
            prices = _extract_prices_from_text(doc_passages)
            if prices:
                hits.append((sorted(prices)[len(prices) // 2], doc_url))

        if hits:
            prices_only = [h[0] for h in hits]
            med = median(prices_only)
            best = min(hits, key=lambda h: abs(h[0] - med))
            price, url = best
            domain = _get_domain(url)
            supplier = domain
            for sd, sn in TRUSTED_SITES:
                if sd in domain:
                    supplier = sn
                    break
            return (price, url, supplier)

    except Exception as e:
        logger.error(f"Yandex error: {e}")

    return None


# ========================================================================
# 5. ГЛАВНАЯ ФУНКЦИЯ
# ========================================================================

async def scrape_for_items(db, items):
    """
    Для каждого товара:
    1. Нормализация (разбор типа/диаметра/стенки/материала)
    2. Поиск в локальной базе цен → получаем офферы от 3+ поставщиков
    3. Ранжирование по score → выбираем лучшее предложение
    4. Если в базе нет → фоллбэк в Yandex Search
    """
    for item in items:
        product = item.original_name
        qty = item.quantity if hasattr(item, 'quantity') and item.quantity else 1

        logger.info(f"🔍 === Обработка: '{product}' (кол-во: {qty}) ===")

        # 1. Нормализация
        np = normalize_product(product)

        # 2. Поиск в локальной базе
        offers = lookup_offers(np)

        if offers:
            # 3. Скоринг
            scored = score_offers(offers, qty)
            best_offer, best_score, breakdown = scored[0]
            actual_price = best_offer.get_price_for_qty(qty)

            # Логируем все предложения
            logger.info(f"  📊 Сравнение поставщиков для '{product}':")
            for i, (off, sc, bd) in enumerate(scored):
                p = off.get_price_for_qty(qty)
                marker = "✅" if i == 0 else "  "
                logger.info(
                    f"  {marker} #{i+1} {off.supplier_name}: "
                    f"{p}₽/{off.unit} | score={sc} "
                    f"[цена={bd['price']}, наличие={bd['stock']}, "
                    f"доставка={bd['delivery']}, надёжн={bd['reliability']}]"
                )

            # Записываем результат
            item.found_name = best_offer.product_name or item.original_name
            item.price = actual_price
            item.source_url = best_offer.url
            item.supplier_name = best_offer.supplier_name

            # Логируем объяснение выбора
            if len(scored) > 1:
                second = scored[1]
                logger.info(
                    f"  💡 Выбран {best_offer.supplier_name} (score {best_score}). "
                    f"Следующий: {second[0].supplier_name} (score {second[1]})"
                )

        else:
            # 4. Фоллбэк: Yandex Search
            logger.info(f"  🌐 Поиск через Yandex Search...")
            yandex = _yandex_fallback(product)

            if yandex:
                price, url, supplier = yandex
                item.found_name = item.original_name
                item.price = price
                item.source_url = url
                item.supplier_name = supplier
                logger.info(f"  ✅ [YANDEX] {product} → {price}₽ @ {supplier}")
            else:
                logger.warning(f"  ❌ Цена не найдена ни в базе, ни в Яндексе для '{product}'")

    return items
