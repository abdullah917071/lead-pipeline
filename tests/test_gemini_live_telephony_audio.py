import asyncio
import unittest

from pipecat.frames.frames import InputAudioRawFrame
from api.services.pipecat.realtime.gemini_live import DograhGeminiLiveLLMService


class _Session:
    def __init__(self):
        self.audio = None

    async def send_realtime_input(self, *, audio):
        self.audio = audio


class GeminiLiveTelephonyAudioTests(unittest.TestCase):
    def test_telnyx_8khz_audio_is_resampled_to_gemini_16khz(self):
        service = object.__new__(DograhGeminiLiveLLMService)
        service._user_is_muted = False
        service._audio_input_paused = False
        service._disconnecting = False
        service._ready_for_realtime_input = True
        service._vad_disabled = False
        service._session = _Session()

        frame = InputAudioRawFrame(audio=b"\x00\x00" * 160, sample_rate=8000, num_channels=1)
        asyncio.run(service._send_user_audio(frame))

        self.assertEqual(service._session.audio.mime_type, "audio/pcm;rate=16000")
        self.assertEqual(len(service._session.audio.data), 640)
