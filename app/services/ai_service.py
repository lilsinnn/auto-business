import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("YANDEX_SA_API_KEY")
ENDPOINT = os.getenv("YANDEX_GPT_API_ENDPOINT", "https://llm.api.cloud.yandex.net/foundationModels/v1/completion")
MODEL_URI = os.getenv("YANDEX_GPT_MODEL_URI_PATTERN", "gpt://b1gqrc1lk6bt1a3l2k5o/yandexgpt-lite/latest")

def extract_items_from_text(text: str):
    """
    Sends the email text to YandexGPT to extract a list of requested items.
    """
    if not API_KEY:
        print("Warning: Missing Yandex API Keyword.")
        return []

    prompt = f"""
    Тебе дается текст письма от клиента или системное уведомление.
    Твоя задача:
    1. Определить, является ли это письмо реальным запросом/заявкой от клиента на покупку или расчет стоимости товаров (арматура, трубы, детали, отводы, фланцы и т.п.). 
       ВНИМАНИЕ: Если текст написан живым языком (например, "здравствуйте, есть ли возможность исполнить заказ", "прошу выставить счет", "нужно купить"), то это ТОЧНО заявка! Установи "is_order": true.
       Если это автоматическое системное письмо (например, "кассовый чек ОФД", спам рассылка или реклама), то это НЕ заявка.
    2. Если это заявка, извлечь список товаров.
    
    Отвечай строго в формате JSON:
    {{
        "is_order": true или false,
        "items": [
            {{
                "original_name": "название товара как в тексте",
                "quantity": числовое_количество (ставь 1 если не указано),
                "unit": "шт, м, кг, т или другое (если нет, ставь 'шт')"
            }}
        ]
    }}
    
    Не пиши ничего кроме валидного JSON (никаких комментариев, markdown-блоков, приветствий).
    
    Текст письма:
    {text}
    """

    data = {
        "modelUri": MODEL_URI,
        "completionOptions": {
            "stream": False,
            "temperature": 0.1,
            "maxTokens": "1000"
        },
        "messages": [
            {
                "role": "system",
                "text": "Ты - строгий и точный парсер информации. Ты отвечаешь только чистым, валидным JSON без обертки Markdown."
            },
            {
                "role": "user",
                "text": prompt
            }
        ]
    }

    headers = {
        "Authorization": f"Api-Key {API_KEY}",
        "x-folder-id": MODEL_URI.split("/")[2], # Extract folder ID from custom URI if possible, or fallback
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(ENDPOINT, headers=headers, json=data)
        response.raise_for_status()
        
        result = response.json()
        ai_text = result.get("result", {}).get("alternatives", [{}])[0].get("message", {}).get("text", "")
        
        # Clean up possible markdown or bad formatting
        ai_text = ai_text.strip()
        
        # Strip exact markdown block starting with ```json or just ```
        if ai_text.startswith("```json"):
            ai_text = ai_text[7:]
        elif ai_text.startswith("```"):
            ai_text = ai_text[3:]
            
        if ai_text.endswith("```"):
            ai_text = ai_text[:-3]
            
        ai_text = ai_text.strip()
        items = json.loads(ai_text)
        return items

    except Exception as e:
        print(f"Error calling YandexGPT: {e}")
        return {"is_order": False, "items": []}
