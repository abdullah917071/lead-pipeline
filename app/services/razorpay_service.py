"""Razorpay Service - dynamic QR code generation and payment verification.

Uses Razorpay's QR Code API to create dynamic UPI QR codes linked to a payment.
On payment capture, Razorpay fires a webhook to /api/webhooks/payment/razorpay.

API docs: https://razorpay.com/docs/api/payments/qr-codes/dynamic/
"""

import logging
import base64
import hmac
import hashlib
import json
import httpx
from typing import Optional, Dict
from datetime import datetime

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class RazorpayService:
    def __init__(self):
        self.api_url = settings.RAZORPAY_API_URL
        self.key_id = settings.RAZORPAY_KEY_ID
        self.key_secret = settings.RAZORPAY_KEY_SECRET
        self.auth = (self.key_id, self.key_secret)

    def _auth_header(self) -> str:
        """Basic auth header for Razorpay API."""
        creds = f"{self.key_id}:{self.key_secret}"
        encoded = base64.b64encode(creds.encode()).decode()
        return f"Basic {encoded}"

    def _headers(self) -> dict:
        return {
            "Authorization": self._auth_header(),
            "Content-Type": "application/json",
        }

    async def create_dynamic_qr(self, amount_inr: float, ref_id: str,
                                 notes: Optional[Dict] = None) -> dict:
        """Create a dynamic QR code via Razorpay.

        Returns dict with:
          - qr_id: Razorpay QR code ID
          - qr_image_url: URL to the QR image (PNG)
          - qr_image_base64: base64-encoded PNG image
          - payment_id: (empty, filled on payment)
          - razorpay_order_id: linked order ID
        """
        # Razorpay expects amount in paise
        amount_paise = int(amount_inr * 100)

        # close_by must be at least 2 minutes in the future (Unix timestamp)
        import time
        close_by_ts = int(time.time()) + (settings.PAYMENT_SESSION_EXPIRY_MINUTES * 60)

        payload = {
            "type": "upi_qr",
            "name": settings.UPI_MERCHANT_NAME,
            "usage": "single_use",  # single-use QR for one payment
            "fixed_amount": True,
            "payment_amount": amount_paise,
            "description": f"Deposit-{ref_id[:8]}",
            "notes": notes or {"ref_id": ref_id},
            "close_by": close_by_ts,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.api_url}/payments/qr_codes",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()

        qr_id = data.get("id", "")
        qr_image_url = data.get("image_url", "")
        # Razorpay also returns the image as raw SVG/PNG in `image`
        # We'll use the image_url if available, otherwise download the image field
        if not qr_image_url and "image" in data:
            # Razorpay returns raw SVG data in 'image' field
            svg_data = data["image"]
            qr_image_base64 = base64.b64encode(svg_data.encode()).decode()
            qr_image_url = f"data:image/svg+xml;base64,{qr_image_base64}"

        logger.info(f"Razorpay dynamic QR created: qr_id={qr_id}, amount=Rs{amount_inr}, ref={ref_id}")

        return {
            "qr_id": qr_id,
            "qr_image_url": qr_image_url,
            "qr_image_base64": qr_image_base64 if not qr_image_url else "",
            "amount_paise": amount_paise,
            "currency": data.get("currency", "INR"),
            "status": data.get("status", "active"),
            "raw": data,
        }

    async def fetch_qr(self, qr_id: str) -> dict:
        """Fetch details of a QR code by ID."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.api_url}/payments/qr_codes/{qr_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def fetch_qr_payments(self, qr_id: str) -> list:
        """Fetch payments made against a QR code."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.api_url}/payments/qr_codes/{qr_id}/payments",
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("items", []) if data.get("items") else [data]

    async def close_qr(self, qr_id: str) -> dict:
        """Close a QR code (mark it as used/expired)."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.api_url}/payments/qr_codes/{qr_id}/close",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    def verify_webhook_signature(self, payload_body: bytes, signature: str) -> bool:
        """Verify Razorpay webhook signature using HMAC SHA256.

        Args:
            payload_body: Raw request body bytes
            signature: X-Razorpay-Signature header value
        """
        if not settings.RAZORPAY_WEBHOOK_SECRET:
            logger.warning("RAZORPAY_WEBHOOK_SECRET not set — skipping signature verification")
            return True

        expected = hmac.new(
            settings.RAZORPAY_WEBHOOK_SECRET.encode(),
            payload_body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    async def create_order(self, amount_inr: float, ref_id: str,
                           notes: Optional[Dict] = None) -> dict:
        """Create a Razorpay order (optional — for order-based payment flow)."""
        amount_paise = int(amount_inr * 100)
        payload = {
            "amount": amount_paise,
            "currency": "INR",
            "notes": notes or {"ref_id": ref_id},
            "partial_payment": False,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.api_url}/orders",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()
