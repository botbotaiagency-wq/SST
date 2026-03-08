"""
Load credentials from .env and optionally from credentials.json.
Copy keys from STT_Credentials_Engineering (PDF/DOCX) into .env or credentials.json.
"""
import json
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent


def _load_credentials_json() -> None:
    """If credentials.json exists, load into os.environ (without overwriting existing)."""
    path = PROJECT_ROOT / "credentials.json"
    if not path.exists():
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(data, dict):
        return
    # Google: support embedded service account JSON
    google_embed = data.pop("google_service_account", None)
    if isinstance(google_embed, dict):
        try:
            fd, tmp = tempfile.mkstemp(suffix=".json", prefix="google_creds_")
            os.close(fd)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(google_embed, f, indent=2)
            os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", tmp)
        except (OSError, TypeError):
            pass
    for key, value in data.items():
        if key.startswith("_") or not isinstance(value, str):
            continue
        value = value.strip()
        # AWS secret: keep only printable ASCII to avoid copy-paste/signing issues (key is base64-like: A-Za-z0-9/+=)
        if key == "AWS_SECRET_ACCESS_KEY":
            value = "".join(c for c in value if ord(c) < 128 and (c.isalnum() or c in "/+="))
            value = value.strip()
        # Resolve Google credentials path relative to project root if needed
        if key == "GOOGLE_APPLICATION_CREDENTIALS":
            p = Path(value)
            if not p.is_absolute() and (PROJECT_ROOT / value).exists():
                value = str((PROJECT_ROOT / value).resolve())
        # Let credentials.json override .env so updating the file and restarting uses the new values
        os.environ[key] = value


def _apply_google_service_account_json() -> None:
    """If GOOGLE_SERVICE_ACCOUNT_JSON is set and the credential file path is missing, use it (after credentials.json load)."""
    google_json = (os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or "").strip()
    if google_json.upper().startswith("GOOGLE_SERVICE_ACCOUNT_JSON="):
        google_json = google_json.split("=", 1)[1].strip()
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    path_exists = creds_path and (Path(creds_path).exists() or (PROJECT_ROOT / creds_path).exists())
    path_missing = creds_path and not path_exists
    if not google_json or (creds_path and path_exists):
        return
    if creds_path and not path_missing:
        return
    try:
        data = json.loads(google_json)
        if not isinstance(data, dict):
            raise ValueError("not a dict")
        fd, tmp = tempfile.mkstemp(suffix=".json", prefix="google_creds_")
        os.close(fd)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp
    except (json.JSONDecodeError, OSError, ValueError):
        try:
            unescaped = google_json.replace("\\n", "\n")
            data = json.loads(unescaped)
            if isinstance(data, dict):
                fd, tmp = tempfile.mkstemp(suffix=".json", prefix="google_creds_")
                os.close(fd)
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp
        except (json.JSONDecodeError, OSError):
            pass


def init_credentials() -> None:
    """Load .env first, then overlay credentials.json. Call once at app startup."""
    load_dotenv(PROJECT_ROOT / ".env")
    _load_credentials_json()
    # After credentials.json: if GOOGLE_APPLICATION_CREDENTIALS points to a missing file, use GOOGLE_SERVICE_ACCOUNT_JSON
    # so that .env or Vercel env can supply the JSON and we don't get overwritten by credentials.json.
    _apply_google_service_account_json()
