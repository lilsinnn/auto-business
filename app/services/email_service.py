import os
import aioimaplib
import email
from email.header import decode_header
from sqlalchemy.orm import Session
from app.models import domain
import logging

logger = logging.getLogger(__name__)

from dotenv import load_dotenv

def get_imap_creds():
    load_dotenv()
    server = os.getenv("IMAP_SERVER")
    port = os.getenv("IMAP_PORT", 993)
    user = os.getenv("IMAP_USER")
    password = os.getenv("IMAP_PASS")
    return server, port, user, password

def decode_mime_words(s):
    if not s:
        return ""
    return u''.join(
        word.decode(encoding or 'utf8') if isinstance(word, bytes) else word
        for word, encoding in decode_header(s)
    )

def extract_body(msg):
    # Simplified extraction, focusing on text/plain
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdispo = str(part.get('Content-Disposition'))
            
            if ctype == 'text/plain' and 'attachment' not in cdispo:
                try:
                    return part.get_payload(decode=True).decode()
                except:
                    pass
    else:
        try:
            return msg.get_payload(decode=True).decode()
        except:
            pass
    return ""

async def get_unread_emails():
    """Connects to IMAP, fetches latest unread emails and returns a list of dictionaries."""
    server, port, user, password = get_imap_creds()
    
    if not all([server, user, password]):
        logger.warning(f"IMAP credentials missing. server={server}, user={user}")
        return []
        
    logger.info(f"Connecting to IMAP {server} as {user}...")
    try:
        imap_client = aioimaplib.IMAP4_SSL(host=server, port=int(port))
        await imap_client.wait_hello_from_server()
        await imap_client.login(user, password)
        await imap_client.select('INBOX')
        
        status, response = await imap_client.search('ALL')
        if status != 'OK' or not response[0]:
            logger.info("No emails found.")
            await imap_client.logout()
            return []
            
        msg_nums = response[0].split()
        parsed_emails = []
        
        # Take the last 5 emails
        limit = 5
        logger.info(f"Processable emails found: {len(msg_nums)}")
        for raw_num in msg_nums[-limit:]:
            num = raw_num.decode() if isinstance(raw_num, bytes) else raw_num
            try:
                s, res = await imap_client.fetch(num, '(RFC822)')
                if s == 'OK':
                    raw_email = res[1]
                    logger.info(f"Fetched raw email: type={type(raw_email)}, snippet={str(raw_email)[:50]}")
                    msg = email.message_from_bytes(raw_email)
                    
                    subject = decode_mime_words(msg["Subject"])
                    sender = decode_mime_words(msg["From"])
                    msg_id = msg.get("Message-ID", "")
                    body_text = extract_body(msg)
                    
                    logger.info(f"Parsed: subject='{subject}', sender='{sender}', msg_id='{msg_id}'")
                    
                    parsed_emails.append({
                        "message_id": msg_id,
                        "subject": subject,
                        "sender": sender,
                        "body": body_text
                    })
            except Exception as inner_e:
                logger.error(f"Failed to parse email {num}: {inner_e}")
                
        await imap_client.logout()
        logger.info(f"Returning {len(parsed_emails)} parsed emails")
        return parsed_emails
        
    except Exception as e:
        logger.error(f"Error fetching emails globally: {e}")
        return []
