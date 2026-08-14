import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from api.services.pipecat.realtime.gemini_live import DograhGeminiLiveLLMService
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService


class GeminiLiveInitialTransitionGuardTests(unittest.TestCase):
    def test_blocks_node_transition_before_caller_has_spoken(self):
        service = object.__new__(DograhGeminiLiveLLMService)
        service._caller_has_spoken = False

        self.assertFalse(service._may_execute_node_transition())

    def test_allows_node_transition_after_caller_has_spoken(self):
        service = object.__new__(DograhGeminiLiveLLMService)
        service._caller_has_spoken = True

        self.assertTrue(service._may_execute_node_transition())

    def test_input_transcription_unlocks_node_transitions(self):
        service = object.__new__(DograhGeminiLiveLLMService)
        service._caller_has_spoken = False
        message = SimpleNamespace(
            server_content=SimpleNamespace(
                input_transcription=SimpleNamespace(text="haan, main khelta hoon")
            )
        )

        with patch.object(
            GeminiLiveLLMService,
            "_handle_msg_input_transcription",
            new=AsyncMock(),
        ) as parent_handler:
            asyncio.run(service._handle_msg_input_transcription(message))

        self.assertTrue(service._caller_has_spoken)
        parent_handler.assert_awaited_once_with(message)


if __name__ == "__main__":
    unittest.main()
