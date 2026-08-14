import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.tasks import scheduler
from app.tasks.scheduler import settings


class _Response:
    status_code = 200
    elapsed = SimpleNamespace(total_seconds=lambda: 0.01)


class _Client:
    requested_urls = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, **kwargs):
        self.requested_urls.append(url)
        return _Response()


class ServiceHealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_dograh_health_uses_versioned_health_endpoint(self):
        fake_httpx = SimpleNamespace(AsyncClient=_Client)
        with patch.dict(sys.modules, {"httpx": fake_httpx}):
            health = await scheduler.check_service_health(db=None)

        self.assertEqual(health["dograh"]["status"], "healthy")
        self.assertTrue(any(url.endswith("/api/v1/health") for url in _Client.requested_urls))
        self.assertTrue(any(url.endswith("/api/v1/organizations/telephony-configs") for url in _Client.requested_urls))

    async def test_whatsapp_health_checks_the_configured_phone_number_resource(self):
        _Client.requested_urls = []
        fake_httpx = SimpleNamespace(AsyncClient=_Client)
        with patch.dict(sys.modules, {"httpx": fake_httpx}):
            health = await scheduler.check_service_health(db=None)

        self.assertEqual(health["whatsapp"]["status"], "healthy")
        expected = f"{settings.WA_API_URL}/{settings.WA_PHONE_NUMBER_ID}?fields=id"
        self.assertIn(expected, _Client.requested_urls)


if __name__ == "__main__":
    unittest.main()
