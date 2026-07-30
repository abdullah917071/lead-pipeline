import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.models.database import LeadStatus
from app.services.orchestrator import PipelineOrchestrator


class WhatsAppReplyStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_interested_reply_does_not_trigger_a_second_call_while_one_is_active(self):
        lead = SimpleNamespace(id="lead-1", phone="919999999999", name="", status=LeadStatus.CALL_TRIGGERED)
        orchestrator = PipelineOrchestrator(db=None)
        orchestrator.leads = SimpleNamespace(get_by_phone=AsyncMock(return_value=lead))
        orchestrator.dograh = SimpleNamespace(trigger_outbound_call=AsyncMock())
        orchestrator.wa = SimpleNamespace(send_call_incoming_notice=AsyncMock())

        result = await orchestrator.handle_wa_reply(lead.phone, "interested")

        self.assertIs(result, lead)
        orchestrator.dograh.trigger_outbound_call.assert_not_awaited()
        orchestrator.wa.send_call_incoming_notice.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
