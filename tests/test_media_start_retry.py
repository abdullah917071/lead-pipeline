import unittest

from app.models.database import LeadStatus
from app.tasks.scheduler import is_media_start_failure, should_retry_media_start_failure


class MediaStartFailureTests(unittest.TestCase):
    def test_detects_answered_call_with_no_media_packets(self):
        logs = {
            "telephony_status_callbacks": [
                {"status": "initiated"},
                {
                    "status": "no-answer",
                    "data": {
                        "data": {
                            "payload": {
                                "hangup_cause": "timeout",
                                "call_quality_stats": {
                                    "inbound": {"packet_count": "0"},
                                    "outbound": {"packet_count": "0"},
                                },
                            }
                        }
                    },
                },
            ]
        }

        self.assertTrue(is_media_start_failure(logs))

    def test_retries_media_start_failure_even_when_lead_already_has_a_qr(self):
        logs = {
            "telephony_status_callbacks": [
                {
                    "status": "no-answer",
                    "data": {
                        "data": {
                            "payload": {
                                "call_quality_stats": {
                                    "inbound": {"packet_count": "0"},
                                    "outbound": {"packet_count": "0"},
                                }
                            }
                        }
                    },
                }
            ]
        }

        self.assertTrue(
            should_retry_media_start_failure(
                "no-answer", logs, LeadStatus.AWAITING_PAYMENT
            )
        )

    def test_does_not_retry_a_normal_no_answer_without_media_stats(self):
        logs = {
            "telephony_status_callbacks": [
                {"status": "initiated"},
                {"status": "no-answer", "data": {"data": {"payload": {}}}},
            ]
        }

        self.assertFalse(is_media_start_failure(logs))

    def test_does_not_retry_when_audio_was_exchanged(self):
        logs = {
            "telephony_status_callbacks": [
                {
                    "status": "no-answer",
                    "data": {
                        "data": {
                            "payload": {
                                "call_quality_stats": {
                                    "inbound": {"packet_count": "1"},
                                    "outbound": {"packet_count": "0"},
                                }
                            }
                        }
                    },
                }
            ]
        }

        self.assertFalse(is_media_start_failure(logs))


if __name__ == "__main__":
    unittest.main()
