import unittest
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock

from app.models.database import LeadStatus
from app.schemas import IncomingLead
from app.services.lead_service import LeadService


class _DuplicateResult:
    def scalar_one_or_none(self):
        raise RuntimeError("duplicate phone rows")

    def scalars(self):
        return SimpleNamespace(all=lambda: [
            SimpleNamespace(id=uuid4(), status=LeadStatus.COLD, phone="919999999999"),
            SimpleNamespace(id=uuid4(), status=LeadStatus.WA_SENT, phone="919999999999"),
        ])


class LeadDeduplicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_ingest_reuses_most_recent_duplicate_instead_of_crashing(self):
        db = SimpleNamespace(execute=AsyncMock(return_value=_DuplicateResult()))
        service = LeadService(db)

        lead = await service.ingest(IncomingLead(phone="9999999999", source="test"))

        self.assertEqual(lead.status, LeadStatus.WA_SENT)
    async def test_reply_lookup_prefers_active_duplicate_over_terminal_duplicate(self):
        db = SimpleNamespace(execute=AsyncMock(return_value=_DuplicateResult()))
        service = LeadService(db)

        lead = await service.get_by_phone("9999999999")

        self.assertEqual(lead.status, LeadStatus.WA_SENT)


if __name__ == "__main__":
    unittest.main()
