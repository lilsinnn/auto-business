import os
from datetime import datetime
from app.services.invoice_template import InvoiceTemplate

OUTPUT_DIR = "storage/invoices"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def generate_invoice(request_id: int, items: list, client_name: str = "Клиент"):
    """
    Generates a professional PDF invoice using the Kimi InvoiceTemplate for the given items.
    """
    filename = f"Invoice_{request_id}_{datetime.now().strftime('%Y%m%d%H%M')}.pdf"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    positions = []
    total_sum = 0
    
    for i, item in enumerate(items, 1):
        name = item.found_name or item.original_name
        qty = item.quantity or 1
        price = item.price or 0.0
        line_total = float(qty) * float(price)
        total_sum += line_total
        
        positions.append({
            'name': name,
            'quantity': qty,
            'unit': item.unit or 'шт',
            'client_price': price,
            'line_total': line_total
        })
        
    invoice_data = {
        'invoice_number': str(request_id),
        'date': datetime.now().strftime('%d.%m.%Y'),
        'positions': positions,
        'totals': {
            'total_amount': total_sum,
            'vat_rate': 0, # Since we simplified
            'vat_amount': 0,
            'total_with_vat': total_sum
        }
    }
    
    client_data = {
        'name': client_name,
        'inn': '',
        'kpp': '',
        'address': ''
    }
    
    template = InvoiceTemplate()
    template.generate_pdf(invoice_data, client_data, filepath)
    
    return filepath
