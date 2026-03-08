import os
from datetime import datetime
from typing import Dict, Any, List, Optional

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import black, white, HexColor

class InvoiceTemplate:
    """
    Фирменный шаблон счёта "Трубопроводный мир"
    """
    
    PAGE_WIDTH, PAGE_HEIGHT = A4
    
    COMPANY = {
        'name': 'ТРУБОПРОВОДНЫЙ МИР',
        'legal_name': 'ООО "ТМ"',
        'inn': '773347239',
        'kpp': '773301001',
        'ogrn': '1047796688557',
        'bank_name': 'АО "АЛЬФА-БАНК" Г. МОСКВА',
        'bank_bik': '044525593',
        'bank_account': '4070281000000000593',
        'bank_corr': '30101810200000000593',
        'address': 'Москва г, Свободы ул, дом № 35, строение 42, эт. 1, пом. II, комн. 46',
        'phone1': '+7 (925) 506-98-93',
        'phone2': '+7 (977) 699-00-32',
        'phone3': '+7 (495) 143-00-93',
        'email': 'sales@magsklad.ru',
        'website': 'http://трубопроводный-мир.рф/',
        'director': 'Ильина М.М.',
        'accountant': 'Туранская Н.В.',
    }
    
    def __init__(self):
        font_path = os.path.join(os.path.dirname(__file__), "..", "static", "fonts", "Roboto.ttf")
        if os.path.exists(font_path):
            pdfmetrics.registerFont(TTFont('Roboto', font_path))
            self.font = 'Roboto'
            self.font_bold = 'Roboto' # Roboto.ttf might not have bold, but we use it as fallback
        else:
            self.font = 'Helvetica'
            self.font_bold = 'Helvetica-Bold'
            
        # Try finding a bold font if possible to improve looks, but fallback to regular if not
        # To avoid reinventing, we'll just use the regular font for bold if bold is missing.
    
    def generate_pdf(
        self,
        invoice_data: Dict[str, Any],
        client_data: Optional[Dict[str, Any]] = None,
        output_path: str = "invoice.pdf",
        logo_path: Optional[str] = None,
        stamp_path: Optional[str] = None
    ) -> str:
        c = canvas.Canvas(output_path, pagesize=A4)
        
        self._draw_header(c, logo_path)
        self._draw_bank_details(c)
        self._draw_invoice_title(c, invoice_data)
        self._draw_supplier_block(c)
        self._draw_client_block(c, client_data)
        self._draw_items_table(c, invoice_data)
        self._draw_totals(c, invoice_data)
        self._draw_signatures(c, stamp_path)
        self._draw_footer(c)
        
        c.save()
        return output_path
    
    def _draw_header(self, c: canvas.Canvas, logo_path: Optional[str] = None):
        y = self.PAGE_HEIGHT - 15*mm
        
        if logo_path and os.path.exists(logo_path):
            try:
                c.drawImage(logo_path, 15*mm, y - 15*mm, width=20*mm, height=20*mm, preserveAspectRatio=True)
            except:
                pass
        else:
            c.setFillColor(HexColor('#1E5AA8'))
            c.circle(25*mm, y - 10*mm, 10*mm, fill=1, stroke=0)
            c.setFillColor(black)
        
        c.setFont(self.font_bold, 14)
        c.drawString(40*mm, y - 5*mm, self.COMPANY['name'])
        c.setFont(self.font, 10)
        c.drawString(40*mm, y - 10*mm, self.COMPANY['legal_name'])
        
        x_right = 120*mm
        c.setFont(self.font, 8)
        c.drawString(x_right, y - 3*mm, self.COMPANY['website'])
        c.drawString(x_right, y - 7*mm, self.COMPANY['phone1'])
        c.drawString(x_right, y - 11*mm, self.COMPANY['phone2'])
        c.drawString(x_right, y - 15*mm, self.COMPANY['phone3'])
        
        c.drawString(x_right + 45*mm, y - 3*mm, self.COMPANY['email'])
        
        c.setFont(self.font, 7)
        c.drawString(15*mm, y - 25*mm, 'Собственное производство деталей трубопроводов.')
        c.drawString(15*mm, y - 29*mm, 'Качество, проверенное давлением.')
    
    def _draw_bank_details(self, c: canvas.Canvas):
        y = self.PAGE_HEIGHT - 55*mm
        c.rect(15*mm, y - 25*mm, 85*mm, 25*mm, stroke=1, fill=0)
        
        c.setFont(self.font, 8)
        c.drawString(17*mm, y - 5*mm, 'БИК')
        c.drawString(40*mm, y - 5*mm, self.COMPANY['bank_bik'])
        
        c.drawString(17*mm, y - 12*mm, 'Сч. №')
        c.drawString(40*mm, y - 12*mm, self.COMPANY['bank_corr'])
        
        c.drawString(17*mm, y - 19*mm, 'Сч. №')
        c.drawString(40*mm, y - 19*mm, self.COMPANY['bank_account'])
        
        c.setFont(self.font_bold, 9)
        c.drawString(105*mm, y - 5*mm, self.COMPANY['bank_name'])
    
    def _draw_invoice_title(self, c: canvas.Canvas, invoice_data: Dict[str, Any]):
        y = self.PAGE_HEIGHT - 90*mm
        
        invoice_number = invoice_data.get('invoice_number', 'Б/Н')
        invoice_date = invoice_data.get('date', datetime.now().strftime('%d.%m.%Y'))
        
        c.setFont(self.font_bold, 14)
        c.drawString(15*mm, y, f'Счет на оплату № {invoice_number} от {invoice_date}')
    
    def _draw_supplier_block(self, c: canvas.Canvas):
        y = self.PAGE_HEIGHT - 100*mm
        
        c.setFont(self.font_bold, 9)
        c.drawString(15*mm, y, 'Поставщик:')
        
        c.setFont(self.font, 8)
        supplier_text = f"Общество с ограниченной ответственностью \"ТРУБОПРОВОДНЫЙ МИР\", ИНН {self.COMPANY['inn']}, КПП {self.COMPANY['kpp']}, {self.COMPANY['address']}, e-mail: {self.COMPANY['email']}"
        
        words = supplier_text.split()
        lines = []
        current_line = ''
        for word in words:
            if len(current_line + ' ' + word) < 100:
                current_line += ' ' + word if current_line else word
            else:
                lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        
        for i, line in enumerate(lines[:3]):
            c.drawString(15*mm, y - 5*mm - i*4*mm, line)
        
        y -= 20*mm
        c.setFont(self.font_bold, 9)
        c.drawString(15*mm, y, 'Грузоотправитель:')
        c.setFont(self.font, 8)
        c.drawString(15*mm, y - 5*mm, supplier_text[:100])
    
    def _draw_client_block(self, c: canvas.Canvas, client_data: Optional[Dict[str, Any]] = None):
        y = self.PAGE_HEIGHT - 145*mm
        
        c.setFont(self.font_bold, 9)
        c.drawString(15*mm, y, 'Покупатель:')
        
        c.setFont(self.font, 8)
        if client_data:
            name = client_data.get('name', '_______________________________________________')
            inn = client_data.get('inn', '_______________')
            kpp = client_data.get('kpp', '_______________')
            address = client_data.get('address', '_______________________________________________')
            client_text = f"{name}, ИНН {inn}, КПП {kpp}, {address}"
        else:
            client_text = '________________________________________________________________________________'
        
        c.drawString(15*mm, y - 5*mm, client_text[:110])
        
        y -= 15*mm
        c.setFont(self.font_bold, 9)
        c.drawString(15*mm, y, 'Грузополучатель:')
        c.setFont(self.font, 8)
        if client_data:
            c.drawString(15*mm, y - 5*mm, client_text[:110])
        else:
            c.drawString(15*mm, y - 5*mm, '________________________________________________________________________________')
    
    def _draw_items_table(self, c: canvas.Canvas, invoice_data: Dict[str, Any]):
        y = self.PAGE_HEIGHT - 175*mm
        
        positions = invoice_data.get('positions', [])
        
        c.setFont(self.font_bold, 8)
        c.rect(15*mm, y - 8*mm, 180*mm, 8*mm, stroke=1, fill=0)
        
        headers = ['№', 'Товары (работы, услуги)', 'Кол-во', 'Ед.', 'Цена', 'Сумма']
        col_widths = [10*mm, 85*mm, 20*mm, 15*mm, 25*mm, 25*mm]
        col_x = [15*mm, 25*mm, 110*mm, 130*mm, 145*mm, 170*mm]
        
        for i, header in enumerate(headers):
            c.drawString(col_x[i] + 2*mm, y - 6*mm, header)
        
        y -= 8*mm
        c.setFont(self.font, 8)
        
        for i, pos in enumerate(positions, 1):
            name = pos.get('name', '')[:50]
            qty = str(pos.get('quantity', 0))
            unit = pos.get('unit', 'шт')
            price = f"{pos.get('client_price', 0):,.2f}".replace(',', ' ')
            total = f"{pos.get('line_total', 0):,.2f}".replace(',', ' ')
            
            c.rect(15*mm, y - 6*mm, 180*mm, 6*mm, stroke=1, fill=0)
            
            c.drawRightString(col_x[0] + 8*mm, y - 4.5*mm, str(i))
            c.drawString(col_x[1] + 2*mm, y - 4.5*mm, name)
            c.drawRightString(col_x[2] + 18*mm, y - 4.5*mm, qty)
            c.drawString(col_x[3] + 2*mm, y - 4.5*mm, unit)
            c.drawRightString(col_x[4] + 23*mm, y - 4.5*mm, price)
            c.drawRightString(col_x[5] + 23*mm, y - 4.5*mm, total)
            
            y -= 6*mm
            
            if y < 50*mm and i < len(positions):
                c.showPage()
                y = self.PAGE_HEIGHT - 30*mm
                c.setFont(self.font_bold, 8)
                c.rect(15*mm, y - 8*mm, 180*mm, 8*mm, stroke=1, fill=0)
                for j, header in enumerate(headers):
                    c.drawString(col_x[j] + 2*mm, y - 6*mm, header)
                y -= 8*mm
                c.setFont(self.font, 8)
    
    def _draw_totals(self, c: canvas.Canvas, invoice_data: Dict[str, Any]):
        totals = invoice_data.get('totals', {})
        
        subtotal = totals.get('total_amount', 0)
        vat_amount = totals.get('vat_amount', 0)
        total = totals.get('total_with_vat', 0)
        vat_rate = totals.get('vat_rate', 20)
        
        positions = invoice_data.get('positions', [])
        y = self.PAGE_HEIGHT - 175*mm - 8*mm - len(positions) * 6*mm - 10*mm
        
        if y < 50*mm:
            c.showPage()
            y = self.PAGE_HEIGHT - 30*mm
        
        c.setFont(self.font_bold, 9)
        c.drawString(130*mm, y, 'Итого:')
        c.drawRightString(195*mm, y, f"{total:,.2f}".replace(',', ' ')) # We don't have separate subtotal on simplified items here right now
        
        y -= 6*mm
        c.drawString(130*mm, y, f'Без НДС')
        
        y -= 6*mm
        c.drawString(130*mm, y, 'Всего к оплате:')
        c.drawRightString(195*mm, y, f"{total:,.2f}".replace(',', ' '))
        
        y -= 10*mm
        c.setFont(self.font, 8)
        total_words = self._number_to_words(int(total))
        c.drawString(15*mm, y, f'Всего наименований {len(positions)}, на сумму {total:,.2f} руб.'.replace(',', ' '))
        y -= 5*mm
        c.drawString(15*mm, y, total_words)
    
    def _draw_signatures(self, c: canvas.Canvas, stamp_path: Optional[str] = None):
        y = 60*mm
        
        c.setStrokeColor(black)
        
        c.line(100*mm, y, 160*mm, y)
        c.setFont(self.font, 8)
        c.drawString(100*mm, y + 2*mm, 'Руководитель')
        c.drawString(100*mm, y - 4*mm, 'должность')
        c.drawString(165*mm, y - 4*mm, self.COMPANY['director'])
        
        y -= 15*mm
        c.line(100*mm, y, 160*mm, y)
        c.drawString(100*mm, y + 2*mm, 'Главный (старший) бухгалтер')
        c.drawString(165*mm, y - 4*mm, self.COMPANY['accountant'])
        
        y -= 15*mm
        c.line(100*mm, y, 160*mm, y)
        c.drawString(100*mm, y + 2*mm, 'Ответственный')
        c.drawString(100*mm, y - 4*mm, 'должность')
        
        if stamp_path and os.path.exists(stamp_path):
            try:
                c.drawImage(stamp_path, 20*mm, 30*mm, width=50*mm, height=50*mm, preserveAspectRatio=True)
            except:
                pass
        else:
            c.setStrokeColor(HexColor('#1E5AA8'))
            c.setLineWidth(2)
            c.circle(45*mm, 55*mm, 20*mm, fill=0, stroke=1)
            c.setFont(self.font, 8)
            c.setFillColor(HexColor('#1E5AA8'))
            c.drawCentredString(45*mm, 55*mm, 'М.П.')
            c.setFillColor(black)
            
    def _draw_footer(self, c: canvas.Canvas):
        y = 25*mm
        
        c.setFont(self.font, 7)
        note = ('Внимание! При оплате нельзя самостоятельно изменять счет или оплачивать выборочно позиции. Указанная цена '
                'действует только при оплате всего счета. В случае частичной оплаты счета цена может быть скорректирована.')
        
        words = note.split()
        lines = []
        current_line = ''
        for word in words:
            if len(current_line + ' ' + word) < 130:
                current_line += ' ' + word if current_line else word
            else:
                lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        
        for i, line in enumerate(lines):
            c.drawString(15*mm, y - i*3.5*mm, line)
            
    def _number_to_words(self, number: int) -> str:
        units = ['', 'один', 'два', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять']
        teens = ['десять', 'одиннадцать', 'двенадцать', 'тринадцать', 'четырнадцать',
                'пятнадцать', 'шестнадцать', 'семнадцать', 'восемнадцать', 'девятнадцать']
        tens = ['', '', 'двадцать', 'тридцать', 'сорок', 'пятьдесят',
               'шестьдесят', 'семьдесят', 'восемьдесят', 'девяносто']
        hundreds = ['', 'сто', 'двести', 'триста', 'четыреста', 'пятьсот',
                   'шестьсот', 'семьсот', 'восемьсот', 'девятьсот']
        
        if number == 0:
            return 'ноль рублей 00 копеек'
        
        result = []
        
        thousands = number // 1000
        if thousands > 0:
            if thousands == 1:
                result.append('одна тысяча')
            elif thousands == 2:
                result.append('две тысячи')
            elif thousands < 10:
                result.append(units[thousands] + ' тысяч')
            else:
                result.append(str(thousands) + ' тысяч')
        
        remainder = number % 1000
        h = remainder // 100
        if h > 0:
            result.append(hundreds[h])
        
        remainder = remainder % 100
        if 10 <= remainder < 20:
            result.append(teens[remainder - 10])
        else:
            t = remainder // 10
            if t > 0:
                result.append(tens[t])
            u = remainder % 10
            if u > 0:
                result.append(units[u])
        
        return ' '.join(result) + ' рублей 00 копеек'
