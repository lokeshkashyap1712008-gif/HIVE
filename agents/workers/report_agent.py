"""
HIVE — Report Agent Worker
Generates PDF reports, sends emails, Slack/Discord webhooks, Slack notifications
"""

import logging
import json
import re

logger = logging.getLogger(__name__)


class ReportAgent:
    """Generates reports, sends notifications, formats output."""

    async def run(description: str, context: dict = None) -> dict:
        description = description.lower()
        context = context or {}

        try:
            if any(word in description for word in ["email", "mail", "smtp", "send to"]):
                return await _send_email(description, context)
            elif any(word in description for word in ["slack", "discord", "webhook"]):
                return await _send_webhook(description, context)
            elif any(word in description for word in ["pdf", "report", "generate", "document"]):
                return await _generate_report(description, context)
            elif any(word in description for word in ["summarize", "summary", "overview"]):
                return await _summarize(description, context)
            else:
                return await _format_output(description, context)

        except Exception as e:
            logger.error(f"[ReportAgent] Error: {e}")
            return {"status": "error", "error": str(e)}


async def _send_email(description: str, context: dict) -> dict:
    """Send an email notification."""
    # Extract email address
    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", description)
    if not email_match:
        return {"status": "skipped", "reason": "No email address found in task description"}

    to_email = email_match.group(0)

    # Extract subject
    subject_match = re.search(r'subject[:\s]+["\'"]?([^\n"\']+)["\'"]?', description, re.IGNORECASE)
    subject = subject_match.group(1).strip() if subject_match else "HIVE Report"

    # Extract body
    body_match = re.search(r'body[:\s]+["\'"]?([^\n"\']+)["\'"]?', description, re.IGNORECASE)
    body = body_match.group(1).strip() if body_match else description[:200]

    # Check for attachment
    attachment_match = re.search(r"attach[:\s]+([^\n]+)", description, re.IGNORECASE)
    attachment = attachment_match.group(1).strip() if attachment_match else None

    try:
        from core.config import settings
        if settings.DASHSCOPE_API_KEY:
            # Use DashScope email or SMTP
            pass
        # Fallback: just return what would be sent
        return {
            "status": "would_send",
            "to": to_email,
            "subject": subject,
            "body_preview": body[:100],
            "attachment": attachment,
            "tip": "Configure SMTP server in settings for actual sending",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _send_webhook(description: str, context: dict) -> dict:
    """Send a Slack or Discord webhook notification."""
    webhook_match = re.search(r"https?://hooks\.(slack|discord)\.com/[^\s]+", description)
    if not webhook_match:
        # Try to find any URL
        webhook_match = re.search(r"https?://[^\s]+\.glitch\.me/[^\s]+|https?://[^\s]+webhook[^\s]+", description, re.IGNORECASE)

    if not webhook_match:
        return {
            "status": "would_send",
            "webhook_url": "not_detected",
            "message": _extract_message(description),
            "tip": "Provide a Slack/Discord webhook URL in the task description",
        }

    webhook_url = webhook_match.group(0)
    message = _extract_message(description)

    # Detect platform
    platform = "slack" if "slack" in webhook_url.lower() or "hooks.slack.com" in webhook_url.lower() else "discord"

    return {
        "status": "would_send",
        "platform": platform,
        "webhook_url": webhook_url[:50] + "...",
        "message": message[:200],
        "tip": "Configure webhook in settings for actual delivery",
    }


async def _generate_report(description: str, context: dict) -> dict:
    """Generate a PDF report."""
    # Extract title
    title_match = re.search(r'title[:\s]+["\'"]?([^\n"\']+)["\'"]?', description, re.IGNORECASE)
    title = title_match.group(1).strip() if title_match else "HIVE Report"

    # Check for data source
    data_match = re.search(r"data[:\s]+([^\n]{50,})", description, re.IGNORECASE)
    data_summary = data_match.group(1).strip()[:300] if data_match else "No structured data provided"

    return {
        "status": "ready_to_generate",
        "title": title,
        "data_summary": data_summary,
        "format": "pdf",
        "sections": ["Summary", "Findings", "Recommendations", "Appendix"],
        "tip": "PDF generation requires reportlab/weasyprint to be installed",
    }


async def _summarize(description: str, context: dict) -> dict:
    """Summarize content."""
    from core.llm_router import chat

    messages = [
        {"role": "system", "content": "Summarize the following content in 3-5 bullet points."},
        {"role": "user", "content": description},
    ]
    result = await chat(messages, quality_mode=False)
    return {
        "status": "success",
        "summary": result["content"],
        "source_length": len(description),
    }


async def _format_output(description: str, context: dict) -> dict:
    """Format output as structured data."""
    # Extract any structured information
    data = {"raw_input_length": len(description), "input_preview": description[:200]}
    return {"status": "success", "formatted": data}


def _extract_message(description: str) -> str:
    """Extract the message content from description."""
    # Remove common prefixes
    cleaned = re.sub(r"^(?:send|post|notify|message)[:\s]+", "", description, flags=re.IGNORECASE)
    return cleaned[:500]


async def run(description: str, context: dict = None) -> dict:
    return await ReportAgent.run(description, context)