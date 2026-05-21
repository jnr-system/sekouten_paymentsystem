from dotenv import load_dotenv
load_dotenv()

import os
import smtplib
import logging
from io import BytesIO

import requests

logger = logging.getLogger(__name__)

_SMTP_CONFIGURED = bool(os.environ.get("SMTP_USER") and os.environ.get("SMTP_USER") != "送信元メールアドレス")
_LINE_CONFIGURED = bool(os.environ.get("LINE_CHANNEL_ACCESS_TOKEN") and os.environ.get("LINE_CHANNEL_ACCESS_TOKEN") != "LINEのチャネルアクセストークン")


def send_notice(contractor: dict, pdf: BytesIO, month: str) -> bool:
    method = contractor.get("send_method", "manual")
    if method == "email":
        if not _SMTP_CONFIGURED:
            logger.info("【ダミー】メール送信スキップ: contractor_id=%s", contractor.get("contractor_id"))
            return True
        return _send_email(contractor, pdf, month)
    elif method == "line":
        if not _LINE_CONFIGURED:
            logger.info("【ダミー】LINE送信スキップ: contractor_id=%s", contractor.get("contractor_id"))
            return True
        return _send_line(contractor, month)
    elif method == "fax":
        logger.warning("FAX送付は手動対応が必要: contractor_id=%s", contractor.get("contractor_id"))
        return True
    else:  # manual
        logger.info("手動送付: contractor_id=%s", contractor.get("contractor_id"))
        return True


def _send_email(contractor: dict, pdf: BytesIO, month: str) -> bool:
    from email.message import EmailMessage
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ["SMTP_USER"]
    smtp_password = os.environ["SMTP_PASSWORD"]
    mail_from = os.environ.get("MAIL_FROM", smtp_user)

    msg = EmailMessage()
    msg["Subject"] = f"支払通知書（{month}月分）"
    msg["From"] = mail_from
    msg["To"] = contractor["email"]
    msg.set_content(f"{contractor['name']} 様\n\n{month}分の支払通知書をお送りします。\n添付PDFをご確認ください。")

    pdf.seek(0)
    filename = f"{contractor.get('contractor_id', 'notice')}_{month}.pdf"
    msg.add_attachment(pdf.read(), maintype="application", subtype="pdf", filename=filename)

    with smtplib.SMTP(smtp_host, smtp_port) as s:
        s.starttls()
        s.login(smtp_user, smtp_password)
        s.send_message(msg)

    logger.info("メール送信完了: contractor_id=%s", contractor.get("contractor_id"))
    return True


def _send_line(contractor: dict, month: str) -> bool:
    token = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
    user_id = contractor["line_user_id"]
    message_text = f"{contractor['name']} 様\n{month}分の支払通知書が発行されました。"

    resp = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"to": user_id, "messages": [{"type": "text", "text": message_text}]},
        timeout=10,
    )
    resp.raise_for_status()
    logger.info("LINE送信完了: contractor_id=%s", contractor.get("contractor_id"))
    return True
