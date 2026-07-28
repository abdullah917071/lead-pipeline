"""WhatsApp Service - sends messages via Meta Cloud API.

Supports:
- Template messages (pre-approved by Meta)
- Interactive messages with image header + body + buttons
- Text, image, and interactive button messages

All payment references are Razorpay QR only — no UPI/transfer options.
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
        components = []
        components.append({
            "type": "header",
            "parameters": [{"type": "image", "image": {"link": image_url}}]
        })
        if variables:
            params = [{"type": "text", "text": v} for v in variables.values()]
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

    # ─── Interactive messages ─────────────────────────────────────

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
        """Send the initial opt-in message with image + Interested button."""
        image_url = settings.WA_OPTIN_IMAGE_URL
        body_text = (
            f"Hi {name or 'there'}! Welcome to Sai Bhai Cricket ID - your trusted cricket betting "
            f"ID provider. Get instant demo IDs, 24/7 support, and the best odds in the market. "
            f"Click 'Interested' below and our team will call you shortly to get started!"
        )
        buttons = [{"type": "reply", "reply": {"id": "interested", "title": "Interested"}}]

        try:
            return await self.send_template_with_image(
                to_phone=phone,
                template_name=settings.WA_OPTIN_TEMPLATE_NAME,
                image_url=image_url,
                variables={"name": name or "there"},
            )
        except Exception as e:
            logger.warning(f"Template send failed ({e}), falling back to interactive message")
            return await self.send_interactive_with_image(phone, image_url, body_text, buttons)

    async def send_call_incoming_notice(self, phone: str, name: str = "") -> dict:
        """Tell user they'll receive a call — Hindi style."""
        text = (
            f"Shukriya {name or 'aapka'} interest ke liye! 🙏\n"
            f"Hamari team aapko kuch hi minute mein call karegi. "
            f"Phone ko paas rakhiye — aapka Sai Bhai Cricket ID bas ek call ki doori par hai!"
        )
        return await self.send_text(phone, text)

    async def send_no_reply_followup(self, phone: str, name: str) -> dict:
        return await self.send_text(phone,
            f"Hi {name}, HUM yahan hain! Kya aap call chaahte hain? Haan batao to call kar dete hain. 😊")

    async def send_qr_payment(self, phone: str, amount: float, qr_image_url: str) -> dict:
        """Send Razorpay QR code with Hindi caption — QR-only payment."""
        caption = (
            f"✅ Rs {int(amount)} ka payment QR taiyaar hai!\n\n"
            f"📱 PhonePe / GPay / Paytm kholiye\n"
            f"🔍 Scan QR kariye\n"
            f"💸 Exact Rs {int(amount)} bhejiye\n"
            f"⚡ Payment hote hi ID activate!\n\n"
            f"⚠️ Sirf QR scan karein — kisi aur UPI ID par payment na bhejein!"
        )
        return await self.send_image(phone, qr_image_url, caption)

    async def send_payment_reminder(self, phone: str, amount: float) -> dict:
        return await self.send_text(phone,
            f"Sir, Rs {int(amount)} ka payment abhi baaki hai! "
            f"QR scan karke payment complete karein — ID activate ho jayegi. ⏰")

    async def send_payment_success(self, phone: str) -> dict:
        return await self.send_text(phone,
            "🎉 Payment received! Abhi aapka demo account bana rahe hain...")

    async def send_credentials(self, phone: str, user_id: str, password: str, balance: float) -> dict:
        text = (
            f"🎉 Aapka demo account ready hai!\n\n"
            f"🔑 Login ID: {user_id}\n"
            f"🔒 Password: {password}\n"
            f"💰 Starting Balance: Rs {int(balance)}\n\n"
            f"📲 App Download: {settings.PLATFORM_APP_DOWNLOAD_URL}\n\n"
            f"Shubhkamnaye! Koi help chahiye to reply karein. - Sai Bhai Cricket ID"
        )
        return await self.send_text(phone, text)

    async def send_rejection_ack(self, phone: str) -> dict:
        return await self.send_text(phone,
            "Koi baat nahi! Kabhi bhi mann kare to bata dein, call kar denge. 👍")