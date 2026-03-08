"""
Unified STT service functions for Google, AWS, and Azure.
Each accepts a path to a WAV file (16 kHz mono recommended) and optional language code.
"""
import asyncio
import io
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Language code mapping (BCP-47 / provider-specific). Default for EN/MY/ID testing.
DEFAULT_LANGUAGE = "en-US"


def _ensure_wav_16k(audio_path: str | Path) -> Path:
    """Ensure file is 16 kHz mono WAV; return path to use (maybe temp)."""
    from pydub import AudioSegment
    p = Path(audio_path)
    seg = AudioSegment.from_file(str(p))
    if seg.channels == 1 and seg.frame_rate == 16000:
        return p
    seg = seg.set_channels(1).set_frame_rate(16000)
    out = p.parent / f"_stt_{p.stem}.wav"
    seg.export(str(out), format="wav")
    return out


def _find_google_creds() -> Path | None:
    """Resolve Google service account JSON path from env or project root."""
    root = Path(__file__).resolve().parent.parent
    env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if env_path and Path(env_path).exists():
        return Path(env_path)
    if env_path and (root / env_path).exists():
        return root / env_path
    for name in ("aiellochatbot-7e91c5fcd6ee.json", "service-account.json"):
        p = root / name
        if p.exists():
            return p
    alt = root / "Aiello_Google (1)" / "Aiello Chatbot.json"
    if alt.exists():
        return alt
    return None


def transcribe_google(audio_path: str | Path, language: str = DEFAULT_LANGUAGE) -> str:
    """Transcribe with Google Cloud Speech-to-Text v2 (chirp_2). Uses credential file and Key ID from config."""
    from google.api_core.client_options import ClientOptions
    from google.cloud.speech_v2 import SpeechClient
    from google.cloud.speech_v2.types import cloud_speech
    from google.oauth2 import service_account

    creds_file = _find_google_creds()
    if not creds_file:
        raise FileNotFoundError(
            "Google credentials not found. Set GOOGLE_APPLICATION_CREDENTIALS to the credential file "
            "(e.g. aiellochatbot-7e91c5fcd6ee.json) and optionally GOOGLE_KEY_ID in credentials.json or .env."
        )
    creds_file = str(creds_file)
    project_id = os.environ.get("GOOGLE_PROJECT_ID", "aiellochatbot")
    expected_key_id = os.environ.get("GOOGLE_KEY_ID")
    # Google Speech-to-Text v2: BCP-47 for most; zh-TW uses cmn-Hant-TW
    lang = "cmn-Hant-TW" if language == "zh-TW" else language  # en-US, ms-MY, id-ID used as-is

    wav_path = _ensure_wav_16k(audio_path)
    with open(wav_path, "rb") as f:
        content = f.read()

    credentials = service_account.Credentials.from_service_account_file(
        creds_file,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    if expected_key_id:
        with open(creds_file, "r", encoding="utf-8") as f:
            import json as _json
            data = _json.load(f)
        if data.get("private_key_id") != expected_key_id:
            raise ValueError(
                f"Credential file key ID ({data.get('private_key_id')}) does not match GOOGLE_KEY_ID ({expected_key_id})."
            )
    client = SpeechClient(
        credentials=credentials,
        client_options=ClientOptions(api_endpoint="us-central1-speech.googleapis.com"),
    )
    request = cloud_speech.RecognizeRequest(
        recognizer=f"projects/{project_id}/locations/us-central1/recognizers/_",
        config=cloud_speech.RecognitionConfig(
            auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
            language_codes=[lang],
            model="chirp_2",
            features=cloud_speech.RecognitionFeatures(
                enable_automatic_punctuation=True,
            ),
        ),
        content=content,
    )
    response = client.recognize(request=request)
    if not response.results:
        return ""
    return " ".join(r.alternatives[0].transcript for r in response.results).strip()


def _get_aws_credential_resolver():
    """Build credential resolver from env so the exact secret is used (avoids signature mismatch)."""
    from amazon_transcribe.auth import StaticCredentialResolver

    access_key = (os.environ.get("AWS_ACCESS_KEY_ID") or "").strip()
    secret_key = (os.environ.get("AWS_SECRET_ACCESS_KEY") or "").strip()
    # Remove newlines/spaces (Vercel or copy-paste can add them); then keep only base64-like chars
    secret_key = "".join(secret_key.split()).replace("\\n", "").replace("\\r", "")
    secret_key = "".join(c for c in secret_key if ord(c) < 128 and (c.isalnum() or c in "/+=")).strip()
    if not access_key or not secret_key:
        return None
    return StaticCredentialResolver(
        access_key_id=access_key,
        secret_access_key=secret_key,
        session_token=None,
    )


async def _transcribe_aws_async(audio_path: str | Path, language: str = DEFAULT_LANGUAGE) -> str:
    from amazon_transcribe.client import TranscribeStreamingClient
    from amazon_transcribe.handlers import TranscriptResultStreamHandler
    from amazon_transcribe.model import TranscriptEvent
    from amazon_transcribe.utils import apply_realtime_delay

    region = (os.environ.get("AWS_DEFAULT_REGION") or "ap-southeast-1").strip()
    wav_path = _ensure_wav_16k(audio_path)
    cred_resolver = _get_aws_credential_resolver()
    client = TranscribeStreamingClient(
        region=region,
        credential_resolver=cred_resolver if cred_resolver else None,
    )
    stream_kwargs = {
        "media_sample_rate_hz": 16000,
        "media_encoding": "pcm",
        "language_code": language or "zh-TW",
        "enable_partial_results_stabilization": True,
        "partial_results_stability": "high",
    }
    stream = await client.start_stream_transcription(**stream_kwargs)

    class Handler(TranscriptResultStreamHandler):
        def __init__(self, output_stream):
            super().__init__(output_stream)
            self.parts: list[str] = []

        async def handle_transcript_event(self, transcript_event: TranscriptEvent):
            for result in transcript_event.transcript.results:
                if not result.is_partial:
                    for alt in result.alternatives:
                        self.parts.append(alt.transcript)

    async def pcm_reader():
        chunk_size = 8 * 1024
        with open(wav_path, "rb") as f:
            f.read(44)
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk  # async generator

    async def pump():
        await apply_realtime_delay(
            stream, pcm_reader(), bytes_per_sample=2, sample_rate=16000, channel_nums=1
        )
        await stream.input_stream.end_stream()

    handler = Handler(stream.output_stream)
    await asyncio.gather(pump(), handler.handle_events())
    return " ".join(handler.parts).strip()


def transcribe_aws(audio_path: str | Path, language: str = DEFAULT_LANGUAGE) -> str:
    """Transcribe with AWS Transcribe Streaming. Returns transcript or raises."""
    return asyncio.run(_transcribe_aws_async(audio_path, language))


async def _transcribe_azure_async(audio_path: str | Path, language: str = DEFAULT_LANGUAGE) -> str | None:
    import aiohttp
    from pydub import AudioSegment

    key = os.environ.get("AZURE_SPEECH_KEY")
    region = os.environ.get("AZURE_SPEECH_REGION")
    if not key or not region:
        raise ValueError(
            "AZURE_SPEECH_KEY and AZURE_SPEECH_REGION must be set in environment variables "
            "(e.g. Vercel dashboard → Settings → Environment Variables, or .env locally)."
        )

    wav_path = _ensure_wav_16k(audio_path)
    audio_wav = AudioSegment.from_file(str(wav_path))
    audio_wav = audio_wav.set_channels(1).set_frame_rate(16000)
    buf = io.BytesIO()
    audio_wav.export(buf, format="wav")
    audio_data = buf.getvalue()

    base_url = f"https://{region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1"
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000",
        "Accept": "application/json",
    }
    params = {"language": language, "format": "detailed"}

    async with aiohttp.ClientSession() as session:
        async with session.post(base_url, headers=headers, params=params, data=audio_data) as response:
            if response.status != 200:
                text = await response.text()
                raise RuntimeError(f"Azure API {response.status}: {text}")
            result = await response.json()
            if result.get("RecognitionStatus") == "Success":
                return result.get("DisplayText", "")
            return None


def transcribe_azure(audio_path: str | Path, language: str = DEFAULT_LANGUAGE) -> str:
    """Transcribe with Azure Speech REST. Returns transcript or raises."""
    out = asyncio.run(_transcribe_azure_async(audio_path, language))
    return out or ""

