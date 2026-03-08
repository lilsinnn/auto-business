from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class RequestItemBase(BaseModel):
    original_name: str
    quantity: int
    unit: str

class RequestItemCreate(RequestItemBase):
    pass

class RequestItemResponse(RequestItemBase):
    id: int
    found_name: Optional[str] = None
    price: Optional[float] = None
    source_url: Optional[str] = None
    supplier_name: Optional[str] = None

    class Config:
        from_attributes = True

class EmailRequestBase(BaseModel):
    sender: str
    subject: str
    body_text: str

class EmailRequestCreate(EmailRequestBase):
    pass

class EmailRequestResponse(EmailRequestBase):
    id: int
    received_at: datetime
    status: str
    invoice_path: Optional[str] = None
    items: List[RequestItemResponse] = []

    class Config:
        from_attributes = True
