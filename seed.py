import os
import sys

# Add parent directory to path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, engine
from app.models import domain

def seed_database():
    print("Creating tables...")
    domain.Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    # Check if already seeded
    if db.query(domain.PriceCatalog).count() == 0:
        print("Seeding PriceCatalog...")
        items = [
            # Pipes and fittings
            {"name": "Отвод 57х4 ст20 ГОСТ 17375-2001", "price": 1250.00, "supplier": "Сантехкомплект", "url": "https://santechkomplekt.ru/catalog/otvod_57x4", "unit": "шт"},
            {"name": "Тройник 57х4 ст20 ГОСТ 894-80", "price": 1850.00, "supplier": "Сантехкомплект", "url": "https://santechkomplekt.ru/catalog/troinik_57x4", "unit": "шт"},
            {"name": "Тройник 57х4 равнопроходный сталь 20", "price": 1900.00, "supplier": "Металлоторг", "url": "https://metallotorg.ru/catalog/troinik_ravn_57", "unit": "шт"},
            {"name": "Фланец 1-50-16 ст20 ГОСТ 12820-80", "price": 850.00, "supplier": "БК Арматура", "url": "https://bkarmatura.ru/catalog/flanets_1_50_16", "unit": "шт"},
            {"name": "Фланец 1-50-16 сталь 20", "price": 810.0, "supplier": "Лунда", "url": "https://lunda.ru/catalog/flanets_50_16", "unit": "шт"},
            {"name": "Труба 89х3.5 ст20", "price": 1150.00, "supplier": "Лунда", "url": "https://lunda.ru/catalog/truba_89", "unit": "м"},
            
            # Metal rolled
            {"name": "Лист 10мм ст20", "price": 92000.00, "supplier": "Металлосервис", "url": "https://metalloservis.ru/list_10_st20", "unit": "т"},
            {"name": "Арматура 12мм ст3 А500С", "price": 72000.00, "supplier": "Металлоторг", "url": "https://metallotorg.ru/armatura_12", "unit": "т"},
            {"name": "Уголок 50х50х5 ст3", "price": 82000.00, "supplier": "Металлосервис", "url": "https://metalloservis.ru/ugolok_50", "unit": "т"},
        ]
        
        for item in items:
            cat_item = domain.PriceCatalog(**item)
            db.add(cat_item)
            
        db.commit()
        print(f"Added {len(items)} items to PriceCatalog.")
    else:
        print("PriceCatalog already seeded.")
        
    db.close()

if __name__ == "__main__":
    seed_database()
