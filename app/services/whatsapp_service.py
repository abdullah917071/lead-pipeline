"""WhatsApp Service - sends messages via Meta Cloud API.

Supports:
- Template messages (pre-approved by Meta)
- Interactive messages with image header + body + buttons
- Text, image, and interactive button messages
"""

import logging
import httpx
from typing import Optional, List, Dict

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class WhatsAppService:
    def __init__(self):
        self.base_url = f"{settings.WA_API_URL}/{settings.WA_PHONE_NUMBER_ID}/messages"
        self.headers = {
            "Authorization": f"Bearer {settings.WA_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }

    # ─── Template messages ────────────────────────────────────────

    async def send_template(self, to_phone: str, template_name: str,
                            variables: Optional[Dict] = None, language: str = "en") -> dict:
        components = []
        if variables:
            params = [{"type": "text", "text": v} for v in variables.values()]
            components.append({"type": "body", "parameters": params})
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "template",
            "template": {"name": template_name, "language": {"code": language}},
        }
        if components:
            payload["template"]["components"] = components
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self.base_url, json=payload, headers=self.headers)
            resp.raise_for_status()
            return resp.json()

    async def send_template_with_image(self, to_phone: str, template_name: str,
                                        image_url: str, variables: Optional[Dict] = None,
                                        language: str = "en") -> dict:
        """Send a template that has an image header and body variables."""
        components = []
        # Image header component
        components.append({
            "type": "header",
            "parameters": [{"type": "image", "image": {"link": image_url}}]
        })
        if variables:
            params = [{"type": "text", "value": v} for v in variables.values()]
            components.append({"type": "body", "parameters": params})
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": components,
            },
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self.base_url, json=payload, headers=self.headers)
            resp.raise_for_status()
            return resp.json()

    # ─── Interactive messages (within 24h window) ─────────────────

    async def send_text(self, to_phone: str, text: str) -> dict:
        payload = {"messaging_product": "whatsapp", "to": to_phone, "type": "text", "text": {"body": text}}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self.base_url, json=payload, headers=self.headers)
            resp.raise_for_status()
            return resp.json()

    async def send_image(self, to_phone: str, image_url: str, caption: str = "") -> dict:
        payload = {"messaging_product": "whatsapp", "to": to_phone, "type": "image",
                   "image": {"link": image_url, "caption": caption}}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self.base_url, json=payload, headers=self.headers)
            resp.raise_for_status()
            return resp.json()

    async def send_interactive(self, to_phone: str, header: str, body: str,
                               buttons: List[Dict]) -> dict:
        payload = {"messaging_product": "whatsapp", "to": to_phone, "type": "interactive",
                   "interactive": {"type": "button", "header": {"type": "text", "text": header},
                                   "body": {"text": body}, "action": {"buttons": buttons}}}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self.base_url, json=payload, headers=self.headers)
            resp.raise_for_status()
            return resp.json()

    async def send_interactive_with_image(self, to_phone: str, image_url: str,
                                           body: str, buttons: List[Dict]) -> dict:
        """Send interactive message with image header + body text + buttons."""
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "header": {"type": "image", "image": {"link": image_url}},
                "body": {"text": body},
                "action": {"buttons": buttons},
            },
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self.base_url, json=payload, headers=self.headers)
            resp.raise_for_status()
            return resp.json()

    # ─── Pipeline-specific messages ──────────────────────────────

    async def send_optin_message(self, phone: str, name: str) -> dict:
        """Send the initial opt-in message with image, text, and 'Interested' button.

        Tries Meta template first (production-safe), falls back to interactive message.
        """
        image_url = settings.WA_OPTIN_IMAGE_URL
        body_text = (
            f"Hi {name or 'there'}! Welcome to Sai Bhai Cricket ID - your trusted cricket betting ID provider. "
            f"Get instant demo IDs, 24/7 support, and the best odds in the market. "
            f"Click 'Interested' below and our team will call you shortly to get started!"
        )
        buttons = [{"type": "reply", "reply": {"id": "interested", "title": "Interested"}}]

        # Try the approved template first (production-safe, works outside 24h window).
        # saibhaiimg already has the image baked into its HEADER, so we only pass the
        # BODY variable {{1}} (name). Do NOT send an image header component here or the
        # API rejects it ("header handle not needed").
        try:
            return await self.send_template(
                to_phone=phone,
                template_name=settings.WA_OPTIN_TEMPLATE_NAME,
                variables={"name": name or "there"},
            )
        except Exception as e:
            logger.warning(f"Template send failed ({e}), falling back to interactive message")
            # Fallback: interactive message with image header (works within 24h window)
            return await self.send_interactive_with_image(phone, image_url, body_text, buttons)

    async def send_call_incoming_notice(self, phone: str, name: str = "") -> dict:
        """Tell the user they will receive a call shortly."""
        text = (
            f"Great, {name or 'there'}! Thanks for your interest. "
            f"Our team will call you in just a few minutes to help you get started. "
            f"Please keep your phone ready. Your Sai Bhai Cricket ID account is just a call away!"
        )
        return await self.send_text(phone, text)

    async def send_no_reply_followup(self, phone: str, name: str) -> dict:
        return await self.send_text(phone, f"Hi {name}, just checking in! Reply YES to get a call from our team.")

    async def send_qr_payment(self, phone: str, amount: float, qr_image_url: str) -> dict:
        caption = (
            f"Awesome! Deposit locked at Rs {int(amount)}.\n"
            f"Scan this QR with PhonePe/GPay/Paytm.\n"
            f"Pay exactly Rs {int(amount)}. Do not include text in UPI note.\n"
            f"Your Sai Bhai Cricket ID demo account will be sent instantly after payment!"
        )
        return await self.send_image(phone, qr_image_url, caption)

    async def send_payment_reminder(self, phone: str, amount: float) -> dict:
        return await self.send_text(phone, f"Still waiting for Rs {int(amount)}! Complete within 5 minutes to get your demo ID instantly.")

    async def send_payment_success(self, phone: str) -> dict:
        return await self.send_text(phone, "Payment received! Creating your demo account now...")

    async def send_credentials(self, phone: str, user_id: str, password: str, balance: float) -> dict:
        text = (
            f"Your demo account is ready!\n"
            f"Login ID: {user_id}\n"
            f"Password: {password}\n"
            f"Starting Balance: Rs {int(balance)}\n\n"
            f"Download: {settings.PLATFORM_APP_DOWNLOAD_URL}\n"
            f"Happy betting! For support, reply to this chat anytime. - Sai Bhai Cricket ID"
        )
        return await self.send_text(phone, text)

    async def send_rejection_ack(self, phone: str) -> dict:
        return await self.send_text(phone, "No problem! Reply YES anytime if you change your mind.")
