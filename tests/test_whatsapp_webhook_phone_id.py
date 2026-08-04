import unittest
from unittest.mock import patch

from app.main import (
    extract_whatsapp_statuses,
    is_configured_whatsapp_phone_number,
    settings,
)


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
    def test_extracts_delivery_status_with_message_and_recipient_ids(self):
        statuses = extract_whatsapp_statuses({
            "statuses": [{
                "id": "wamid.123",
                "status": "failed",
                "recipient_id": "919999999999",
                "errors": [{"code": 131049, "title": "Marketing limit"}],
            }]
        })

        self.assertEqual(statuses, [{
            "message_id": "wamid.123",
            "status": "failed",
            "recipient_id": "919999999999",
            "error_codes": [131049],
        }])


if __name__ == "__main__":
    unittest.main()
