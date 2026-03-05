"""
Web app for real-time microphone STT comparison: Google, AWS, Azure.
Run: python app.py  then open http://127.0.0.1:5000
Credentials: copy from STT_Credentials_Engineering (PDF/DOCX) into .env or credentials.json.
Logs: console + logs/stt_app.log (create logs/ if missing).
"""
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

# Load credentials first (.env + optional credentials.json from PDF keys)
import config
config.init_credentials()

from flask import Flask, request, jsonify, render_template

# Logging: file + console locally; on Vercel (serverless) only console (no write to disk)
LOG_DIR = Path(__file__).resolve().parent / "logs"
handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
if not os.environ.get("VERCEL"):
    try:
        LOG_DIR.mkdir(exist_ok=True)
        LOG_FILE = LOG_DIR / "stt_app.log"
        handlers.append(logging.FileHandler(LOG_FILE, encoding="utf-8"))
    except OSError:
        pass
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=handlers,
)
logger = logging.getLogger("stt_app")

from stt_services.services import (
    transcribe_google,
    transcribe_aws,
    transcribe_azure,
    DEFAULT_LANGUAGE,
)

app = Flask(__name__, template_folder="templates")
# Vercel serverless has ~4.5 MB body limit; use 4 MB when on Vercel
app.config["MAX_CONTENT_LENGTH"] = (4 if os.environ.get("VERCEL") else 10) * 1024 * 1024


@app.errorhandler(404)
@app.errorhandler(500)
def json_error(e):
    """Ensure API always gets JSON, not HTML error pages."""
    logger.warning("HTTP %s: %s", getattr(e, "code", 500), e)
    return jsonify({"ok": False, "error": str(e)}), e.code if hasattr(e, "code") else 500


@app.errorhandler(Exception)
def handle_exception(e):
    """Catch any unhandled exception and return JSON."""
    logger.exception("Unhandled exception: %s", e)
    return jsonify({"ok": False, "error": str(e)}), 500

ALLOWED_PROVIDERS = {"google", "aws", "azure"}
# Primary test languages: English, Bahasa Melayu, Bahasa Indonesia (real-time)
SUPPORTED_LANGUAGES = [
    ("en-US", "English (US)"),
    ("ms-MY", "Bahasa Melayu (Malay)"),
    ("id-ID", "Bahasa Indonesia (Indonesian)"),
    ("zh-TW", "Chinese (Taiwan)"),
    ("zh-CN", "Chinese (Simplified)"),
    ("ja-JP", "Japanese"),
    ("ko-KR", "Korean"),
    ("th-TH", "Thai"),
]


class AudioConversionError(Exception):
    """Raised when audio conversion fails with a user-facing message."""
    pass


def _wav_to_16k_mono_no_ffmpeg(in_path: str | Path) -> Path | None:
    """Convert WAV to 16kHz mono using only the wave module and numpy. No FFmpeg. Returns output path or None."""
    import wave as wave_module
    try:
        import numpy as np
    except ImportError:
        logger.debug("numpy not available for WAV resampling")
        return None
    in_path = Path(in_path)
    if not in_path.exists() or in_path.stat().st_size < 44:
        return None
    try:
        with wave_module.open(str(in_path), "rb") as wav_in:
            nch, sw, sr, nf, comptype, compname = wav_in.getparams()
            if nf == 0:
                return None
            raw = wav_in.readframes(nf)
    except Exception as e:
        logger.debug("wave open failed for %s: %s", in_path, e)
        return None
    if sw != 2:
        logger.debug("Unsupported WAV sample width %s", sw)
        return None
    samples = np.frombuffer(raw, dtype=np.int16)
    if nch == 2:
        samples = (samples[0::2].astype(np.int32) + samples[1::2]).astype(np.int16) // 2
    elif nch != 1:
        return None
    if sr != 16000:
        n = len(samples)
        out_n = int(round(n * 16000 / sr))
        indices = np.linspace(0, n - 1, out_n, dtype=np.float32)
        samples = np.interp(indices, np.arange(n, dtype=np.float32), samples.astype(np.float32)).astype(np.int16)
        sr = 16000
    out_path = in_path.parent / (in_path.stem + "_16k.wav")
    try:
        with wave_module.open(str(out_path), "wb") as wav_out:
            wav_out.setnchannels(1)
            wav_out.setsampwidth(2)
            wav_out.setframerate(16000)
            wav_out.writeframes(samples.tobytes())
        return out_path
    except Exception as e:
        logger.debug("wave write failed: %s", e)
        return None


def _save_upload_as_wav() -> tuple[Path, Path] | None:
    """Save uploaded file to a temp WAV (16kHz mono). Returns (wav_path, temp_path_to_cleanup) or None.
    For .wav uploads (e.g. from browser recording) uses wave+numpy only (no FFmpeg). For WebM/MP3 uses pydub."""
    if "audio" not in request.files:
        return None
    f = request.files["audio"]
    if not f:
        return None
    ext = (Path(f.filename or "audio.webm").suffix or ".webm").lower()
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        f.save(tmp.name)
        in_path = tmp.name
    if ext == ".wav":
        with open(in_path, "rb") as fp:
            magic = fp.read(4)
        if magic == b"RIFF":
            out_path = _wav_to_16k_mono_no_ffmpeg(in_path)
            if out_path is not None:
                logger.debug("Processed WAV without FFmpeg: %s -> %s", in_path, out_path)
                return (out_path, Path(in_path))
    try:
        from pydub import AudioSegment
    except ImportError:
        logger.error("pydub not installed")
        _try_unlink_temp(in_path)
        raise AudioConversionError("Server error: pydub not installed.")
    try:
        seg = AudioSegment.from_file(in_path)
        seg = seg.set_channels(1).set_frame_rate(16000)
        out_path = in_path + ".wav"
        seg.export(out_path, format="wav")
        return (Path(out_path), Path(in_path))
    except FileNotFoundError as e:
        logger.warning("FFmpeg not found (required for WebM/MP3): %s", e)
        _try_unlink_temp(in_path)
        raise AudioConversionError(
            "FFmpeg is required for MP3/WebM. Upload a WAV file to transcribe without FFmpeg, or install FFmpeg and add it to PATH (see README)."
        )
    except OSError as e:
        if getattr(e, "errno", None) == 2:
            logger.warning("FFmpeg not on PATH: %s", e)
            _try_unlink_temp(in_path)
            raise AudioConversionError(
                "FFmpeg is required for MP3/WebM. Upload a WAV file to transcribe without FFmpeg, or install FFmpeg and add it to PATH (see README)."
            )
        logger.exception("Audio conversion failed: %s", e)
        _try_unlink_temp(in_path)
        raise AudioConversionError(f"Audio conversion failed: {e}")
    except Exception as e:
        logger.exception("Audio conversion failed: %s", e)
        _try_unlink_temp(in_path)
        raise AudioConversionError(f"Audio conversion failed: {e}")


def _is_garbage_transcript(text: str) -> bool:
    """Return True if transcript looks like hallucinated garbage (e.g. random numbers from Google on silence)."""
    if not text or not text.strip():
        return False
    t = text.strip()
    alnum = [c for c in t if c.isalnum()]
    if len(alnum) < 5:
        return False
    digits = sum(1 for c in alnum if c.isdigit())
    if digits / len(alnum) >= 0.5:
        return True
    return False


def _is_silence(wav_path: str | Path, threshold_rms: float = 150.0) -> bool:
    """Return True if the WAV is effectively silence (no speech). Avoids sending silence to STT and getting phantom text."""
    try:
        import wave as wave_module
        import numpy as np
    except ImportError:
        return False
    wav_path = Path(wav_path)
    if not wav_path.exists() or wav_path.stat().st_size <= 44:
        return True
    try:
        with wave_module.open(str(wav_path), "rb") as w:
            n = w.getnframes()
            if n == 0:
                return True
            raw = w.readframes(n)
    except Exception as e:
        logger.debug("Silence check read failed for %s: %s", wav_path, e)
        return False
    try:
        samples = np.frombuffer(raw, dtype=np.int16)
        rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
        return rms < threshold_rms
    except Exception as e:
        logger.debug("Silence check RMS failed: %s", e)
        return False


def _try_unlink_temp(path: str | Path) -> None:
    """Try to unlink a temp file; ignore WinError 32 (file in use)."""
    if not path or not os.path.exists(path):
        return
    try:
        os.unlink(path)
        logger.debug("Removed temp: %s", path)
    except OSError as e:
        logger.debug("Could not unlink temp %s (ignored): %s", path, e)


@app.before_request
def log_request():
    if request.path.startswith("/api/"):
        logger.debug("Request %s %s", request.method, request.path)


@app.route("/")
def index():
    return render_template("index.html", languages=SUPPORTED_LANGUAGES)


def _safe_unlink(path: Path, label: str = "file") -> None:
    """Unlink path; on Windows retry once after a short delay to avoid WinError 32."""
    if not path or not path.exists():
        return
    try:
        os.unlink(path)
        logger.debug("Removed %s: %s", label, path)
    except OSError as e:
        logger.warning("First unlink failed for %s %s: %s", label, path, e)
        if sys.platform == "win32":
            time.sleep(0.2)
            try:
                os.unlink(path)
                logger.debug("Removed %s on retry: %s", label, path)
            except OSError as e2:
                logger.error("Could not remove %s %s: %s", label, path, e2)


@app.route("/api/transcribe", methods=["POST"])
def api_transcribe():
    try:
        result = _save_upload_as_wav()
    except AudioConversionError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    wav_path = result[0] if result else None
    temp_path = result[1] if result else None
    try:
        provider = (request.form.get("provider") or "").strip().lower()
        language = (request.form.get("language") or DEFAULT_LANGUAGE).strip()
        logger.info("POST /api/transcribe provider=%s language=%s", provider, language)
        if provider not in ALLOWED_PROVIDERS:
            return jsonify({"ok": False, "error": "Invalid provider"}), 400

        if not result:
            logger.warning("No audio file or invalid format")
            return jsonify({
                "ok": False,
                "error": "No audio file received. Choose a WAV, MP3, or WebM file and try again."
            }), 400

        # Skip STT for silence to avoid phantom transcriptions (e.g. "i'm sorry" from Google on silence)
        if _is_silence(wav_path):
            logger.debug("Audio chunk is silence; skipping STT call")
            return jsonify({"ok": True, "text": ""})

        try:
            if provider == "google":
                text = transcribe_google(wav_path, language=language)
            elif provider == "aws":
                text = transcribe_aws(wav_path, language=language)
            else:
                text = transcribe_azure(wav_path, language=language)
            if text and _is_garbage_transcript(text):
                logger.debug("Filtered garbage transcript (e.g. number hallucination): %s", text[:80])
                text = ""
            logger.info("Transcribed provider=%s len=%d", provider, len(text or ""))
            return jsonify({"ok": True, "text": text or ""})
        finally:
            _safe_unlink(wav_path, "wav")
            time.sleep(0.1)
            _safe_unlink(temp_path, "temp")
    except Exception as e:
        logger.exception("api_transcribe failed: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


def _check_ffmpeg() -> bool:
    """Return True if FFmpeg appears to be on PATH (needed for WebM/MP3 conversion)."""
    import shutil
    return bool(shutil.which("ffmpeg") or shutil.which("avconv"))


if __name__ == "__main__":
    logger.info("Log file: %s", LOG_FILE)
    if not _check_ffmpeg():
        logger.warning("FFmpeg not found on PATH. Microphone (WebM) and MP3 uploads will fail until FFmpeg is installed.")
    else:
        logger.info("FFmpeg found on PATH.")
    # Log which AWS key is loaded (for debugging 403 / InvalidSignatureException)
    aws_key = os.environ.get("AWS_ACCESS_KEY_ID", "").strip()
    if aws_key:
        logger.info("AWS credentials loaded (Access Key ID: %s***)", (aws_key[:4] if len(aws_key) >= 4 else "****"))
    else:
        logger.warning("AWS_ACCESS_KEY_ID not set; AWS Transcribe will not work.")
    logger.info("Starting STT app on http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)
