import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from app.services.upi_service import PaymentService


class _Result:
    def __init__(self, session):
        self.session = session

    def scalar_one_or_none(self):
        return self.session


class PaymentMatchingTests(unittest.IsolatedAsyncioTestCase):
    async def test_ref_id_payment_with_wrong_amount_is_rejected(self):
        session = SimpleNamespace(
            lead_id=uuid4(), amount_inr=500.0, status="active",
            expires_at=datetime.utcnow() + timedelta(minutes=5),
            paid_at=None, utr_number=None,
        )
        db = SimpleNamespace(execute=AsyncMock(return_value=_Result(session)), commit=AsyncMock())
        service = PaymentService(db)
        service.match_incoming_payment = AsyncMock()

        matched = await service.match_by_ref_id("known-ref", "utr-1", 100.0)

        self.assertIsNone(matched)
        self.assertEqual(session.status, "active")
        db.commit.assert_not_awaited()
        service.match_incoming_payment.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
