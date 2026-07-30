import unittest
from unittest.mock import patch

from app.main import is_configured_whatsapp_phone_number, settings


class WhatsAppWebhookPhoneNumberTests(unittest.TestCase):
    def test_accepts_the_configured_phone_number_id(self):
        with patch.object(settings, "WA_PHONE_NUMBER_ID", "configured-phone-id"):
            self.assertTrue(is_configured_whatsapp_phone_number({
                "metadata": {"phone_number_id": "configured-phone-id"}
            }))

    def test_rejects_a_different_phone_number_id(self):
        with patch.object(settings, "WA_PHONE_NUMBER_ID", "configured-phone-id"):
            self.assertFalse(is_configured_whatsapp_phone_number({
                "metadata": {"phone_number_id": "unconfigured-phone-id"}
            }))

    def test_rejects_a_message_with_no_phone_number_id(self):
        with patch.object(settings, "WA_PHONE_NUMBER_ID", "configured-phone-id"):
            self.assertFalse(is_configured_whatsapp_phone_number({"metadata": {}}))


if __name__ == "__main__":
    unittest.main()
