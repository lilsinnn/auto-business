from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Boolean, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class EmailRequest(Base):
    __tablename__ = "email_requests"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String, unique=True, index=True, nullable=True) # To prevent duplicates
    sender = Column(String, index=True)
    subject = Column(String)
    received_at = Column(DateTime, default=datetime.utcnow)
    body_text = Column(Text)
    status = Column(String, default="new") # new, processing, ready, error
    invoice_path = Column(String, nullable=True)
    
    items = relationship("RequestItem", back_populates="request", cascade="all, delete")

class RequestItem(Base):
    __tablename__ = "request_items"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("email_requests.id"))
    original_name = Column(String)
    quantity = Column(Integer, default=1)
    unit = Column(String, default="шт")
    
    # Scraped data
    found_name = Column(String, nullable=True)
    price = Column(Float, nullable=True)
    source_url = Column(String, nullable=True)
    supplier_name = Column(String, nullable=True)

    request = relationship("EmailRequest", back_populates="items")

class PriceCatalog(Base):
    """
    Local database imitating an external supplier catalog.
    Used for answering price queries without real HTTP scraping.
    """
    __tablename__ = "price_catalog"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    price = Column(Float)
    unit = Column(String, default="шт")
    supplier = Column(String)
    url = Column(String)
