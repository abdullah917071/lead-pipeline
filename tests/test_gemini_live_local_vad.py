import unittest

from api.services.pipecat.realtime.gemini_live import DograhGeminiLiveLLMService


class GeminiLiveLocalVADTests(unittest.TestCase):
    def test_telnyx_realtime_defaults_to_local_turn_completion(self):
        service = DograhGeminiLiveLLMService(
            api_key="test-key",
            settings=DograhGeminiLiveLLMService.Settings(
                model="google/gemini-live-2.5-flash-native-audio",
                voice="Charon",
                language="hi",
            ),
        )

        self.assertIsNotNone(service._settings.vad)
        self.assertTrue(service._settings.vad.disabled)


if __name__ == "__main__":
    unittest.main()
