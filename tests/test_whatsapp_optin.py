import unittest
from unittest.mock import AsyncMock, patch

from app.services.whatsapp_service import WhatsAppService, settings


class WhatsAppOptinTests(unittest.IsolatedAsyncioTestCase):
    async def test_initial_optin_uses_approved_image_header_template(self):
        service = WhatsAppService()
        service.send_template_with_image = AsyncMock(return_value={"messages": [{"id": "wamid.1"}]})
        service.send_template = AsyncMock()

        with (
            patch.object(settings, "WA_OPTIN_TEMPLATE_NAME", "approved_optin"),
            patch.object(settings, "WA_OPTIN_IMAGE_URL", "https://example.test/optin.jpg"),
        ):
            await service.send_optin_message("919999999999", "Faizan")

        service.send_template_with_image.assert_awaited_once_with(
            "919999999999",
            "approved_optin",
            "https://example.test/optin.jpg",
            {"name": "Faizan"},
        )
        service.send_template.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
