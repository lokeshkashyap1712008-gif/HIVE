"""
HIVE — Communicator Agent
Multi-channel messaging: Email (SMTP), Slack, Discord, Telegram, SMS (Twilio).
"""

import smtplib
import json
import logging
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import httpx

from hive.core.llm_router import chat, QWEN_TURBO

logger = logging.getLogger(__name__)

SENT_LOG_PATH = os.path.join(os.path.expanduser("~"), ".hive", "messages_sent.json")


def _load_config() -> dict:
    return {
        "smtp_host": os.getenv("SMTP_HOST", ""),
        "smtp_port": int(os.getenv("SMTP_PORT", "587")),
        "smtp_user": os.getenv("SMTP_USER", ""),
        "smtp_pass": os.getenv("SMTP_PASS", ""),
        "slack_webhook": os.getenv("SLACK_WEBHOOK_URL", ""),
        "discord_webhook": os.getenv("DISCORD_WEBHOOK_URL", ""),
        "telegram_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
        "twilio_sid": os.getenv("TWILIO_ACCOUNT_SID", ""),
        "twilio_token": os.getenv("TWILIO_AUTH_TOKEN", ""),
        "twilio_from": os.getenv("TWILIO_FROM_NUMBER", ""),
        "twilio_to": os.getenv("TWILIO_TO_NUMBER", ""),
    }


def _log_sent(channel: str, recipient: str, message: str, msg_id: str):
    os.makedirs(os.path.dirname(SENT_LOG_PATH), exist_ok=True)
    log = []
    if os.path.exists(SENT_LOG_PATH):
        with open(SENT_LOG_PATH, "r") as f:
            log = json.load(f)
    log.append({"channel": channel, "recipient": recipient, "message": message[:100], "msg_id": msg_id})
    with open(SENT_LOG_PATH, "w") as f:
        json.dump(log[-100:], f)


async def send_email(to: str, subject: str, body: str, config: dict) -> dict:
    if not config.get("smtp_host") or not config.get("smtp_user"):
        return {"sent": False, "channel": "email", "to": to, "error": "SMTP not configured. Set SMTP_HOST, SMTP_USER, SMTP_PASS in .env"}
    
    try:
        msg = MIMEMultipart()
        msg["From"] = config["smtp_user"]
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(config["smtp_host"], config["smtp_port"]) as server:
            server.starttls()
            server.login(config["smtp_user"], config["smtp_pass"])
            server.sendmail(config["smtp_user"], to, msg.as_string())

        _log_sent("email", to, body, "email_ok")
        return {"sent": True, "channel": "email", "to": to}
    except Exception as e:
        logger.error(f"Email failed: {e}")
        return {"sent": False, "channel": "email", "to": to, "error": str(e)}


async def send_slack(text: str, config: dict) -> dict:
    webhook = config.get("slack_webhook") or os.getenv("SLACK_WEBHOOK_URL", "")
    if not webhook:
        return {"sent": False, "channel": "slack", "error": "No Slack webhook configured"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook, json={"text": text}, timeout=10.0)
            resp.raise_for_status()
        _log_sent("slack", "webhook", text, "slack_ok")
        return {"sent": True, "channel": "slack"}
    except Exception as e:
        return {"sent": False, "channel": "slack", "error": str(e)}


async def send_discord(text: str, config: dict) -> dict:
    webhook = config.get("discord_webhook") or os.getenv("DISCORD_WEBHOOK_URL", "")
    if not webhook:
        return {"sent": False, "channel": "discord", "error": "No Discord webhook configured"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook, json={"content": text}, timeout=10.0)
            resp.raise_for_status()
        _log_sent("discord", "webhook", text, "discord_ok")
        return {"sent": True, "channel": "discord"}
    except Exception as e:
        return {"sent": False, "channel": "discord", "error": str(e)}


async def send_telegram(text: str, config: dict) -> dict:
    token = config.get("telegram_token") or os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = config.get("telegram_chat_id") or os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return {"sent": False, "channel": "telegram", "error": "No Telegram token/chat_id"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            msg_id = str(data.get("result", {}).get("message_id", ""))
        _log_sent("telegram", chat_id, text, msg_id)
        return {"sent": True, "channel": "telegram", "msg_id": msg_id}
    except Exception as e:
        return {"sent": False, "channel": "telegram", "error": str(e)}


async def send_sms(text: str, config: dict) -> dict:
    sid = config.get("twilio_sid") or os.getenv("TWILIO_ACCOUNT_SID", "")
    token = config.get("twilio_token") or os.getenv("TWILIO_AUTH_TOKEN", "")
    from_num = config.get("twilio_from") or os.getenv("TWILIO_FROM_NUMBER", "")
    to_num = config.get("twilio_to") or os.getenv("TWILIO_TO_NUMBER", "")
    if not all([sid, token, from_num, to_num]):
        return {"sent": False, "channel": "sms", "error": "Twilio credentials incomplete"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                auth=(sid, token),
                data={"From": from_num, "To": to_num, "Body": text},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
        _log_sent("sms", to_num, text, data.get("sid", ""))
        return {"sent": True, "channel": "sms", "msg_id": data.get("sid", "")}
    except Exception as e:
        return {"sent": False, "channel": "sms", "error": str(e)}


async def run(task: str) -> dict:
    config = _load_config()

    result = await chat(
        [{"role": "system", "content": "Parse this messaging task. Return JSON with: channel (email|slack|discord|telegram|sms), recipient (email/phone/empty), subject (for email), message (the content)."},
         {"role": "user", "content": task}],
        model=QWEN_TURBO,
        max_tokens=256,
    )

    content = result["content"]

    import re
    json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
    parsed = {"channel": "", "message": content}

    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
        except Exception:
            pass

    channel = parsed.get("channel", "").lower()
    message = parsed.get("message", task)
    recipient = parsed.get("recipient", "")
    subject = parsed.get("subject", "HIVE Notification")

    results = []
    if "email" in channel or "@" in message:
        r = await send_email(recipient or config["smtp_user"], subject, message, config)
        results.append(r)
    if "slack" in channel:
        results.append(await send_slack(message, config))
    if "discord" in channel:
        results.append(await send_discord(message, config))
    if "telegram" in channel:
        results.append(await send_telegram(message, config))
    if "sms" in channel or "text" in channel:
        results.append(await send_sms(message, config))

    if not results:
        results = [
            r for r in [
                await send_slack(message, config) if config.get("slack_webhook") else None,
                await send_discord(message, config) if config.get("discord_webhook") else None,
                await send_telegram(message, config) if config.get("telegram_token") else None,
            ] if r is not None
        ]

    return {
        "status": "ok",
        "channel": channel or "auto",
        "results": results,
        "all_sent": all(r.get("sent", False) for r in results),
    }
