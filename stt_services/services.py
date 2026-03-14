"""
Unified STT service functions for Google, AWS, and Azure.
Each accepts a path to a WAV file (16 kHz mono recommended) and optional language code.
"""
import asyncio
import io
import os
import wave
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Language code mapping (BCP-47 / provider-specific). Default for EN/MY/ID testing.
DEFAULT_LANGUAGE = "en-US"


def _lang_to_iso6391(language: str) -> str:
    """Map BCP-47 (e.g. en-US, ms-MY) to ISO-639-1 (e.g. en, ms) for Speechmatics, ElevenLabs, Groq."""
    if not language:
        return "en"
    part = language.split("-")[0].lower()
    return part if len(part) == 2 else "en"


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

    key = os.environ.get("AZURE_SPEECH_KEY")
    region = os.environ.get("AZURE_SPEECH_REGION")
    if not key or not region:
        raise ValueError(
            "AZURE_SPEECH_KEY and AZURE_SPEECH_REGION must be set in environment variables "
            "(e.g. Vercel dashboard → Settings → Environment Variables, or .env locally)."
        )

    # Prefer reading WAV bytes without pydub (app usually provides 16 kHz mono already; avoids ffmpeg on Vercel)
    p = Path(audio_path)
    audio_data = None
    if p.suffix.lower() == ".wav":
        try:
            with wave.open(str(p), "rb") as wav:
                if wav.getnchannels() == 1 and wav.getframerate() == 16000:
                    # Rebuild minimal WAV bytes (header + PCM) so Azure gets valid WAV
                    buf = io.BytesIO()
                    with wave.open(buf, "wb") as out:
                        out.setnchannels(1)
                        out.setsampwidth(wav.getsampwidth())
                        out.setframerate(16000)
                        out.writeframes(wav.readframes(wav.getnframes()))
                    audio_data = buf.getvalue()
        except Exception:
            pass
    if audio_data is None:
        wav_path = _ensure_wav_16k(audio_path)
        audio_data = Path(wav_path).read_bytes()

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
                if response.status == 404:
                    raise RuntimeError(
                        "Azure Speech returned 404 (endpoint or language not available in this region). "
                        "Try another region (e.g. eastasia, southeastasia) or check language code (e.g. ms-MY for Malay)."
                    )
                raise RuntimeError(f"Azure API {response.status}: {text}")
            result = await response.json()
            if result.get("RecognitionStatus") == "Success":
                return result.get("DisplayText", "")
            return None


def transcribe_azure(audio_path: str | Path, language: str = DEFAULT_LANGUAGE) -> str:
    """Transcribe with Azure Speech REST. Returns transcript or raises."""
    out = asyncio.run(_transcribe_azure_async(audio_path, language))
    return out or ""


def transcribe_speechmatics(audio_path: str | Path, language: str = DEFAULT_LANGUAGE) -> str:
    """Transcribe with Speechmatics batch API (async job + poll + get transcript)."""
    import time
    key = os.environ.get("SPEECHMATICS_API_KEY")
    if not key:
        raise ValueError(
            "SPEECHMATICS_API_KEY must be set in environment variables "
            "(e.g. Vercel dashboard or .env locally)."
        )
    try:
        import requests
    except ImportError:
        raise ImportError("Install 'requests' for Speechmatics: pip install requests")
    import json as _json
    p = Path(audio_path)
    lang = _lang_to_iso6391(language)
    base = "https://eu1.asr.api.speechmatics.com/v2"
    headers = {"Authorization": f"Bearer {key}"}
    config = {"type": "transcription", "transcription_config": {"language": lang}}
    with open(p, "rb") as f:
        files = {"data_file": (p.name, f, "audio/wav")}
        data = {"config": _json.dumps(config)}
        r = requests.post(f"{base}/jobs", headers=headers, data=data, files=files, timeout=60)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Speechmatics create job {r.status_code}: {r.text[:500]}")
    job = r.json()
    job_id = job.get("id")
    if not job_id:
        raise RuntimeError(f"Speechmatics no job id: {job}")
    for _ in range(60):
        r = requests.get(f"{base}/jobs/{job_id}", headers=headers, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"Speechmatics job status {r.status_code}: {r.text[:300]}")
        data = r.json()
        status = data.get("job", {}).get("status") or data.get("status")
        if status == "done":
            break
        if status == "rejected":
            raise RuntimeError(f"Speechmatics job rejected: {data}")
        time.sleep(1)
    else:
        raise RuntimeError("Speechmatics job timed out")
    r = requests.get(f"{base}/jobs/{job_id}/transcript", headers=headers, params={"format": "txt"}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Speechmatics transcript {r.status_code}: {r.text[:300]}")
    return (r.text or "").strip()


def transcribe_elevenlabs(audio_path: str | Path, language: str = DEFAULT_LANGUAGE) -> str:
    """Transcribe with ElevenLabs Speech-to-Text API (sync)."""
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise ValueError(
            "ELEVENLABS_API_KEY must be set in environment variables "
            "(e.g. Vercel dashboard or .env locally)."
        )
    try:
        import requests
    except ImportError:
        raise ImportError("Install 'requests' for ElevenLabs: pip install requests")
    p = Path(audio_path)
    lang = _lang_to_iso6391(language)
    url = "https://api.elevenlabs.io/v1/speech-to-text"
    headers = {"xi-api-key": key}
    with open(p, "rb") as f:
        files = {"file": (p.name, f, "audio/wav")}
        data = {} if not lang else {"language_code": lang}
        r = requests.post(url, headers=headers, files=files, data=data, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs API {r.status_code}: {r.text[:500]}")
    out = r.json()
    if isinstance(out, dict):
        return (out.get("text") or out.get("transcript") or "").strip()
    return str(out).strip()


def transcribe_groq(audio_path: str | Path, language: str = DEFAULT_LANGUAGE) -> str:
    """Transcribe with Groq Whisper API."""
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise ValueError(
            "GROQ_API_KEY must be set in environment variables "
            "(e.g. Vercel dashboard or .env locally)."
        )
    try:
        from groq import Groq
    except ImportError:
        raise ImportError("Install 'groq' for Groq: pip install groq")
    lang = _lang_to_iso6391(language)
    client = Groq(api_key=key)
    with open(audio_path, "rb") as f:
        transcription = client.audio.transcriptions.create(
            file=f,
            model="whisper-large-v3-turbo",
            language=lang,
            response_format="text",
        )
    if hasattr(transcription, "text"):
        return (transcription.text or "").strip()
    return str(transcription).strip()

