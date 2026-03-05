"""
Minimal AWS Transcribe Streaming verification.
Demonstrates transcription of a local audio file via the streaming API.
"""
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent
from amazon_transcribe.utils import apply_realtime_delay

# AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and optionally AWS_DEFAULT_REGION should be set in .env
load_dotenv(".env")

AUDIO_FILE   = "9e702cefb81ebbfd4ed298a196dde1fd4e07630f.wav"
LANGUAGE     = "zh-TW"   # e.g. en-US, zh-TW, ja-JP, ko-KR, th-TH, ms-MY
REGION       = os.environ.get("AWS_DEFAULT_REGION", "ap-southeast-1")


class _Handler(TranscriptResultStreamHandler):
    def __init__(self, output_stream):
        super().__init__(output_stream)
        self.parts: list[str] = []

    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        for result in transcript_event.transcript.results:
            if not result.is_partial:
                for alt in result.alternatives:
                    self.parts.append(alt.transcript)


async def transcribe(audio_path: Path, language: str | None) -> str:
    client = TranscribeStreamingClient(region=REGION)

    stream_kwargs = {
        "media_sample_rate_hz": 16000,
        "media_encoding": "pcm",
    }
    if language:
        stream_kwargs["language_code"] = language
    else:
        stream_kwargs["identify_language"] = True

    stream = await client.start_stream_transcription(**stream_kwargs)

    async def write_chunks():
        async def pcm_reader():
            chunk_size = 8 * 1024
            with open(audio_path, "rb") as f:
                f.read(44)  # skip WAV header, send raw PCM
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk

        await apply_realtime_delay(
            stream, pcm_reader(), bytes_per_sample=2, sample_rate=16000, channel_nums=1
        )
        await stream.input_stream.end_stream()

    handler = _Handler(stream.output_stream)
    await asyncio.gather(write_chunks(), handler.handle_events())
    return " ".join(handler.parts).strip()


if __name__ == "__main__":
    print(f"Audio : {AUDIO_FILE}")
    print(f"Lang  : {LANGUAGE or 'auto-detect'}")
    print(f"Region: {REGION}")
    print()

    transcript = asyncio.run(transcribe(AUDIO_FILE, LANGUAGE))
    print(f"Transcript: {transcript}")
 