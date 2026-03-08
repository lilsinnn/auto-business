import asyncio
import os
import requests
import base64
import json
import re
import logging
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
YANDEX_FOLDER_ID = os.getenv("YANDEX_SEARCH_USER")
YANDEX_API_KEY = os.getenv("YANDEX_SEARCH_KEY")

logger = logging.getLogger(__name__)

def extract_price(text: str) -> float:
    """Attempt to extract price from snippet or title."""
    if not text:
        return None
    matches = re.finditer(r'(\d{1,3}(?:\s\d{3})*(?:[.,]\d{1,2})?)\s*(?:руб|р\.|₽)', text, re.IGNORECASE)
    for match in matches:
        try:
            val_str = match.group(1).replace(" ", "").replace(",", ".")
            return float(val_str)
        except:
            pass
    return None

async def scrape_for_items(db, items):
    """
    Takes a list of items extracted by AI and searches them using Yandex Cloud Search API v2.
    """
    if not YANDEX_FOLDER_ID or not YANDEX_API_KEY:
        logger.error("Missing Yandex Cloud Search Credentials.")
        return items

    url = "https://searchapi.api.cloud.yandex.net/v2/web/search"
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }

    for item in items:
        query_text = f"{item.original_name} цена купить"
        logger.info(f"Starting Yandex Search API v2 for: '{query_text}'")
        data = {
            "query": {
                "search_type": "SEARCH_TYPE_RU",
                "query_text": query_text
            },
            "folderId": YANDEX_FOLDER_ID
        }
        
        try:
            resp = requests.post(url, headers=headers, json=data, timeout=10)
            logger.info(f"Yandex API Response Status: {resp.status_code}")
            
            if resp.status_code == 200:
                result_json = resp.json()
                raw_data_b64 = result_json.get("rawData")
                if raw_data_b64:
                    xml_str = base64.b64decode(raw_data_b64).decode('utf-8')
                    soup = BeautifulSoup(xml_str, 'xml')
                    
                    error_node = soup.find("error")
                    if error_node:
                        logger.error(f"Yandex XML Error: {error_node.text}")
                        continue
                        
                    docs = soup.find_all('doc')
                    logger.info(f"Found {len(docs)} documents in XML response.")
                    if len(docs) == 0:
                        logger.warning(f"RAW XML: {xml_str[:500]}")

                    price_hits = []
                    for doc in docs:
                        doc_url = doc.url.text if doc.url else ""
                        doc_title = doc.title.text if doc.title else ""
                        doc_passages = " ".join([p.text for p in doc.find_all('passage')])
                        
                        price = extract_price(doc_passages) or extract_price(doc_title)
                        if price:
                            clean_title = re.sub('<[^<]+>', '', doc_title)[:50]
                            price_hits.append((price, doc_url, clean_title))
                            
                    if price_hits:
                        logger.info(f"Found {len(price_hits)} prices for '{item.original_name}'. Calculating median...")
                        # Sort by price to get median
                        price_hits.sort(key=lambda x: x[0])
                        median_idx = len(price_hits) // 2
                        med_price, med_url, med_title = price_hits[median_idx]
                        
                        item.found_name = med_title
                        item.price = med_price
                        item.source_url = med_url
                        try:
                            domain = med_url.split('/')[2]
                            item.supplier_name = domain.replace("www.", "")
                        except:
                            item.supplier_name = "Yandex Search"
            else:
                print(f"Yandex API Error for {item.original_name}: {resp.status_code} - {resp.text[:200]}")
                
        except Exception as e:
            print(f"Error doing Yandex Search for {item.original_name}: {e}")
            
    return items
