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
    subject = f"Invest AI: Executive Boardroom Briefing - {date_str}"

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
    subject = f"Invest AI: QA Audit Dashboard - {date_str}"

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

def send_error_alert(error_message: str):
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    recipient_email = os.getenv("STAN_PERSONAL_EMAIL")

    if not all([sender_email, sender_password, recipient_email]):
        logger.error("FATAL: Missing email credentials in environment variables. Cannot send error alert.")
        return False

    date_str = now_local().strftime("%B %d, %Y %H:%M:%S")
    subject = f"CRITICAL: Invest AI Boardroom Pipeline Failed - {date_str}"

    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #fef2f2; padding: 20px; color: #991b1b;">
        <h2 style="color: #dc2626;">Pipeline Execution Failed</h2>
        <p>The Invest AI Boardroom pipeline encountered a fatal error and aborted execution.</p>
        <div style="background-color: #ffffff; padding: 15px; border-left: 4px solid #dc2626; border-radius: 4px; margin-top: 20px;">
            <strong>Error Details:</strong><br><br>
            <pre style="white-space: pre-wrap;">{error_message}</pre>
        </div>
        <p style="margin-top: 20px; font-size: 0.9em; color: #6b7280;">Please check the Azure Function logs for the full stack trace.</p>
    </body>
    </html>
    """

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"Investment Boardroom System <{sender_email}>"
    msg['To'] = recipient_email

    msg.attach(MIMEText(html_content, 'html'))

    try:
        logger.info(f"Connecting to SMTP server to send error alert to {recipient_email}...")
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
        logger.info("Error alert successfully delivered.")
        return True
    except Exception as e:
        logger.error(f"Failed to send error alert: {e}")
        return False

def send_qa_digest(html_content: str):
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    recipient_email = os.getenv("STAN_PERSONAL_EMAIL")

    if not all([sender_email, sender_password, recipient_email]):
        logger.error("FATAL: Missing email credentials in environment variables. Cannot send QA Digest.")
        return False

    date_str = now_local().strftime("%B %d, %Y")
    subject = f"Invest AI: QA & Cost Review Digest - {date_str}"

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"Investment Boardroom QA Team <{sender_email}>"
    msg['To'] = recipient_email

    msg.attach(MIMEText(html_content, 'html'))

    try:
        logger.info(f"Connecting to SMTP server to send QA Digest to {recipient_email}...")
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
            
        logger.info("QA Digest successfully delivered to inbox.")
        return True
    except Exception as e:
        logger.error(f"Failed to send QA Digest: {e}")
        return False


def send_legal_counsel_report(html_content: str, *, subject: str) -> bool:
    """Dedicated Legal Counsel findings email (briefing per-run or daily code audit)."""
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    recipient_email = os.getenv("STAN_PERSONAL_EMAIL")

    if not all([sender_email, sender_password, recipient_email]):
        logger.error("FATAL: Missing email credentials — cannot send Legal Counsel report.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Invest AI: {subject}"
    msg["From"] = f"Investment Boardroom Legal Counsel <{sender_email}>"
    msg["To"] = recipient_email
    msg.attach(MIMEText(html_content, "html"))

    try:
        logger.info("Sending Legal Counsel report to %s …", recipient_email)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
        logger.info("Legal Counsel report delivered.")
        return True
    except Exception as e:
        logger.error("Failed to send Legal Counsel report: %s", e)
        return False


def send_finance_oversight(html_content: str):
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    recipient_email = os.getenv("STAN_PERSONAL_EMAIL")

    if not all([sender_email, sender_password, recipient_email]):
        logger.error("FATAL: Missing email credentials. Cannot send Finance Oversight report.")
        return False

    date_str = now_local().strftime("%B %d, %Y")
    subject = f"Invest AI: Finance & Subscription Oversight - {date_str}"

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"Investment Boardroom Finance <{sender_email}>"
    msg['To'] = recipient_email
    msg.attach(MIMEText(html_content, 'html'))

    try:
        logger.info(f"Sending Finance Oversight report to {recipient_email}...")
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
        logger.info("Finance Oversight report delivered.")
        return True
    except Exception as e:
        logger.error(f"Failed to send Finance Oversight report: {e}")
        return False