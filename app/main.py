from fastapi import FastAPI, Depends, BackgroundTasks, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log", mode='a', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

from app.database import engine, Base, get_db
from app.models import domain, schemas
from app.services import email_service, ai_service, scraper_service, invoice_service

# Create DB tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Light Invoice App")

# Allow CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi import Request

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Incoming request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response

# Route for frontend
import os
os.makedirs("app/static", exist_ok=True)
import app.services.invoice_service as inv_service
os.makedirs("storage/invoices", exist_ok=True)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/invoices", StaticFiles(directory="storage/invoices"), name="invoices")

@app.get("/api/requests", response_model=List[schemas.EmailRequestResponse])
def get_requests(db: Session = Depends(get_db)):
    """Get all requests from the DB"""
    requests = db.query(domain.EmailRequest).order_by(domain.EmailRequest.received_at.desc()).all()
    return requests

async def process_email_background(db: Session, request_id: int):
    """
    Background worker to process the email.
    1. Extract items using YandexGPT
    2. Scrape suppliers
    3. Generate PDF
    4. Mark ready
    """
    logger.info(f"Starting background processing for request {request_id}")
    db_request = db.query(domain.EmailRequest).filter(domain.EmailRequest.id == request_id).first()
    if not db_request:
        return
        
    db_request.status = "processing"
    db.commit()
    
    try:
        # 1. AI Extraction & Classification
        ai_response = ai_service.extract_items_from_text(db_request.body_text)
        
        is_order_raw = ai_response.get("is_order", False)
        is_order = str(is_order_raw).lower() == "true" if isinstance(is_order_raw, str) else bool(is_order_raw)
        raw_items = ai_response.get("items", [])
        
        # Check if AI considers it an order
        if not is_order:
            db_request.status = "ignored"
            db.commit()
            return
            
        # Check if list is completely empty / failed
        if not raw_items:
            db_request.status = "error"
            db.commit()
            return

        items_to_scrape = []
        for ri in raw_items:
            item = domain.RequestItem(
                request_id=db_request.id,
                original_name=ri.get("original_name", "Unknown item"),
                quantity=ri.get("quantity", 1),
                unit=ri.get("unit", "шт")
            )
            items_to_scrape.append(item)
            db.add(item)
        
        db.commit()
        
        # 2. Scrape prices 
        scraped_items = await scraper_service.scrape_for_items(db, items_to_scrape)
        
        for item in scraped_items:
            db.add(item)
        db.commit()
        
        # 3. Generate Invoice
        invoice_path = invoice_service.generate_invoice(db_request.id, scraped_items, db_request.sender)
        db_request.invoice_path = invoice_path
        
        # 4. Finish
        db_request.status = "ready"
        db.commit()
        
    except Exception as e:
        print(f"Error processing request {request_id}: {e}")
        db_request.status = "error"
        db.commit()


@app.post("/api/fetch_emails")
async def trigger_email_fetch(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Manual trigger to fetch emails from IMAP"""
    emails = await email_service.get_unread_emails()
    added_count = 0
    
    if not emails:
        return {"status": "success", "fetched": 0}
    
    for email_data in emails:
        message_id = email_data.get("message_id")
        
        # Check for duplicates using message_id
        if message_id:
            existing = db.query(domain.EmailRequest).filter(domain.EmailRequest.message_id == message_id).first()
            if existing:
                logger.info(f"Skipping duplicate email with Message-ID: {message_id}")
                continue # Skip already processed email
            else:
                logger.info(f"Adding new email with Message-ID: {message_id}")
        else:
            logger.warning("Email has no Message-ID, adding anyway.")

        # Create request
        db_req = domain.EmailRequest(
            message_id=message_id,
            sender=email_data["sender"],
            subject=email_data["subject"],
            body_text=email_data["body"]
        )
        db.add(db_req)
        db.commit()
        db.refresh(db_req)
        
        added_count += 1
        
        # Queue processing
        background_tasks.add_task(process_email_background, db, db_req.id)
        
    return {"status": "success", "fetched": added_count}

@app.post("/api/reset")
async def reset_database(db: Session = Depends(get_db)):
    """Deletes all emails and items from the database."""
    try:
        db.query(domain.RequestItem).delete()
        db.query(domain.EmailRequest).delete()
        db.commit()
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error resetting database: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs")
async def download_logs():
    """Downloads the app.log file safely by reading it into memory."""
    logger.info("Downloading logs requested.")
    log_path = "app.log"
    if not os.path.exists(log_path):
        logger.warning("Log file not found.")
        raise HTTPException(status_code=404, detail="Log file not found.")
        
    with open(log_path, "rb") as f:
        content = f.read()
        
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=light_invoice_app.log"}
    )

class ConfigData(schemas.BaseModel):
    imap_server: str
    imap_port: str
    imap_user: str
    imap_pass: str
    yandex_search_user: str
    yandex_search_key: str

@app.get("/api/config")
async def get_config():
    """Returns safe masked configuration for the settings UI."""
    return {
        "imap_server": os.getenv("IMAP_SERVER", ""),
        "imap_port": os.getenv("IMAP_PORT", "993"),
        "imap_user": os.getenv("IMAP_USER", ""),
        "imap_pass": os.getenv("IMAP_PASS", ""),
        "yandex_search_user": os.getenv("YANDEX_SEARCH_USER", ""),
        "yandex_search_key": os.getenv("YANDEX_SEARCH_KEY", "")
    }

@app.post("/api/config")
async def update_config(data: ConfigData):
    """Updates the .env file with new credentials."""
    logger.info("Updating .env configuration.")
    try:
        env_dict = {
            "IMAP_SERVER": data.imap_server,
            "IMAP_PORT": data.imap_port,
            "IMAP_USER": data.imap_user,
            "IMAP_PASS": data.imap_pass,
            "YANDEX_SEARCH_USER": data.yandex_search_user,
            "YANDEX_SEARCH_KEY": data.yandex_search_key
        }
        
        env_content = ""
        if os.path.exists(".env"):
            with open(".env", "r", encoding="utf-8") as f:
                env_content = f.read()
                
        # Helper to replace or append
        import re
        for key, value in env_dict.items():
            if value: # dont write empty values
                pattern = f"^{key}=.*$"
                if re.search(pattern, env_content, flags=re.MULTILINE):
                    env_content = re.sub(pattern, f"{key}={value}", env_content, flags=re.MULTILINE)
                else:
                    env_content += f"\n{key}={value}"
                    
        with open(".env", "w", encoding="utf-8") as f:
            f.write(env_content.strip() + "\n")
            
        return {"status": "ok", "message": "Настройки сохранены. Требуется перезагрузка сервера."}
    except Exception as e:
        logger.error(f"Failed to update config: {e}")
        raise HTTPException(status_code=500, detail="Failed to write configuration.")

class FeedbackData(schemas.BaseModel):
    message: str

@app.post("/api/feedback")
async def submit_feedback(data: FeedbackData):
    """Saves user feedback to a text file."""
    logger.info("Feedback submitted.")
    try:
        with open("feedback.txt", "a", encoding="utf-8") as f:
            f.write(f"- {data.message}\n")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Failed to save feedback: {e}")
        raise HTTPException(status_code=500, detail="Failed to save feedback.")

@app.get("/")
def read_root():
    logger.info("Serving index.html")
    import os
    if os.path.exists("app/static/index.html"):
        with open("app/static/index.html", "r", encoding="utf-8") as f:
            from fastapi.responses import HTMLResponse
            return HTMLResponse(content=f.read(), status_code=200)
