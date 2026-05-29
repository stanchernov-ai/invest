import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.config.settings import now_local

logger = logging.getLogger(__name__)

def send_executive_briefing(html_content: str):
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    recipient_email = os.getenv("STAN_PERSONAL_EMAIL")

    if not all([sender_email, sender_password, recipient_email]):
        logger.error("FATAL: Missing email credentials in environment variables. Cannot send briefing.")
        return False

    date_str = now_local().strftime("%B %d, %Y")
    subject = f"SC Invest: Executive Boardroom Briefing - {date_str}"

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    
    # This is the line that spoofs the display name for your inbox.
    msg['From'] = f"Investment Boardroom <{sender_email}>"
    msg['To'] = recipient_email

    msg.attach(MIMEText(html_content, 'html'))

    try:
        logger.info(f"Connecting to SMTP server to send briefing to {recipient_email}...")
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
            
        logger.info("Executive briefing successfully delivered to inbox.")
        return True
    except Exception as e:
        logger.error(f"Failed to send email briefing: {e}")
        return False

def send_qa_dashboard(html_content: str):
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    recipient_email = os.getenv("STAN_PERSONAL_EMAIL")

    if not all([sender_email, sender_password, recipient_email]):
        logger.error("FATAL: Missing email credentials in environment variables. Cannot send QA Dashboard.")
        return False

    date_str = now_local().strftime("%B %d, %Y")
    subject = f"SC Invest: QA Audit Dashboard - {date_str}"

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"Investment Boardroom QA <{sender_email}>"
    msg['To'] = recipient_email

    msg.attach(MIMEText(html_content, 'html'))

    try:
        logger.info(f"Connecting to SMTP server to send QA Dashboard to {recipient_email}...")
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
            
        logger.info("QA Dashboard successfully delivered to inbox.")
        return True
    except Exception as e:
        logger.error(f"Failed to send QA Dashboard: {e}")
        return False