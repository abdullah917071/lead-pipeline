import unittest
from unittest.mock import AsyncMock

from app.services.whatsapp_service import WhatsAppService


class QrPaymentMessageTests(unittest.IsolatedAsyncioTestCase):
    async def test_qr_message_promises_id_delivery_on_whatsapp_after_payment(self):
        service = WhatsAppService()
        service.send_image = AsyncMock(return_value={"messages": [{"id": "wamid.qr"}]})

        await service.send_qr_payment("919999999999", 1000, "https://example.test/qr.png")

        _, caption = service.send_image.await_args.args[1:]
        self.assertIn("Rs 1000", caption)
        self.assertIn("Payment hote hi aapko ID WhatsApp par receive ho jayegi", caption)


if __name__ == "__main__":
    unittest.main()
