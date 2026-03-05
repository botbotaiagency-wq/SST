"""
Run Google, AWS, and Azure STT on the same audio and compare performance.
Usage: from project root (STT):  python run_stt_comparison.py
Credentials: copy from STT_Credentials_Engineering (PDF/DOCX) into .env or credentials.json.
"""
import config
config.init_credentials()

import os
import re
import subprocess
import sys
import time
from pathlib import Path

# Project root = directory containing this script
PROJECT_ROOT = Path(__file__).resolve().parent
AUDIO_WAV = os.environ.get("AUDIO_WAV", "9e702cefb81ebbfd4ed298a196dde1fd4e07630f.wav")
AUDIO_MP3 = os.environ.get("AUDIO_MP3", "9e702cefb81ebbfd4ed298a196dde1fd4e07630f.mp3")


def run_cmd(cmd: list[str], cwd: Path, env: dict | None = None, timeout: int = 120) -> tuple[str, str, float]:
    """Run command; return (stdout, stderr, elapsed_seconds)."""
    full_env = {**os.environ, **(env or {})}
    t0 = time.perf_counter()
    try:
        r = subprocess.run(
            cmd,
            cwd=cwd,
            env=full_env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.perf_counter() - t0
        return (r.stdout or "", r.stderr or "", elapsed)
    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - t0
        return ("", "Timeout", elapsed)
    except FileNotFoundError:
        return ("", f"Command not found: {cmd[0]}", 0.0)
    except Exception as e:
        return ("", str(e), 0.0)


def parse_google_stdout(stdout: str) -> str:
    """Extract first transcript from Google script output (chirp_2 block)."""
    # Lines like "  transcript text" under "=== chirp_2 ... ==="
    in_chirp2 = False
    parts = []
    for line in stdout.splitlines():
        if "=== chirp_2 " in line:
            in_chirp2 = True
            continue
        if in_chirp2 and line.strip().startswith("==="):
            break
        if in_chirp2 and line.strip() and line.startswith("  "):
            parts.append(line.strip())
    return " ".join(parts).strip() if parts else stdout.strip()


def parse_aws_stdout(stdout: str) -> str:
    """Extract transcript from AWS script output."""
    m = re.search(r"Transcript:\s*(.+)", stdout, re.DOTALL)
    return m.group(1).strip() if m else stdout.strip()


def parse_azure_stdout(stdout: str) -> str:
    """Extract transcript from Azure script output."""
    m = re.search(r"REST Result:\s*(.+)", stdout, re.DOTALL)
    return m.group(1).strip() if m else stdout.strip()


def ensure_mp3_for_google() -> str | None:
    """If MP3 missing but WAV exists, create MP3 from WAV; return path to use for Google or None."""
    wav = PROJECT_ROOT / AUDIO_WAV
    mp3 = PROJECT_ROOT / AUDIO_MP3
    if mp3.exists():
        return str(mp3)
    if not wav.exists():
        return None
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_file(str(wav))
        seg.export(str(mp3), format="mp3")
        return str(mp3)
    except Exception:
        return None


def check_setup() -> list[str]:
    """Return list of missing setup items."""
    missing = []
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        missing.append(".env (for AWS and Azure)")
    google_json = PROJECT_ROOT / "aiellochatbot-7e91c5fcd6ee.json"
    alt_json = PROJECT_ROOT / "Aiello_Google (1)" / "Aiello Chatbot.json"
    if not google_json.exists() and not alt_json.exists():
        missing.append("Google service account JSON (aiellochatbot-7e91c5fcd6ee.json or Aiello Chatbot.json)")
    wav = PROJECT_ROOT / AUDIO_WAV
    if not wav.exists():
        missing.append(f"Audio WAV: {AUDIO_WAV}")
    mp3 = PROJECT_ROOT / AUDIO_MP3
    if not mp3.exists() and not wav.exists():
        missing.append(f"Audio: {AUDIO_WAV} or {AUDIO_MP3}")
    elif not mp3.exists():
        try:
            __import__("pydub")
        except ImportError:
            missing.append("Audio MP3 for Google (or install pydub to convert WAV→MP3)")
    return missing


def main():
    os.chdir(PROJECT_ROOT)
    missing = check_setup()
    if missing:
        print("Missing setup:", ", ".join(missing))
        print("Create .env with AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AZURE_SPEECH_KEY, AZURE_SPEECH_REGION.")
        print("Place audio as", AUDIO_WAV, "(and optionally", AUDIO_MP3, ") in project root.")
        sys.exit(1)

    py = sys.executable
    results = []

    # Google: ensure MP3 path and credential path
    google_mp3 = ensure_mp3_for_google() or str(PROJECT_ROOT / AUDIO_MP3)
    google_json = PROJECT_ROOT / "aiellochatbot-7e91c5fcd6ee.json"
    if not google_json.exists():
        google_json = PROJECT_ROOT / "Aiello_Google (1)" / "Aiello Chatbot.json"
    google_env = {**os.environ, "GOOGLE_AUDIO_FILE": str(Path(google_mp3).resolve())}
    if google_json.exists():
        google_env["GOOGLE_APPLICATION_CREDENTIALS"] = str(google_json)

    # ----- Google -----
    google_script = PROJECT_ROOT / "Sample Codes_AWS_Google" / "Google_Cloud_Speech-to-Text_v2.py"
    if not google_script.exists():
        results.append(("Google", "", 0.0, "Script not found", False))
    else:
        # Run from PROJECT_ROOT so relative GOOGLE_AUDIO_FILE resolves if script uses cwd
        run_cwd = PROJECT_ROOT
        stdout, stderr, elapsed = run_cmd([py, str(google_script)], run_cwd, env=google_env)
        transcript = parse_google_stdout(stdout) if stdout else ""
        err = stderr.strip() or ""
        ok = bool(transcript) and "Error" not in stderr
        results.append(("Google (chirp_2)", transcript or "(no transcript)", elapsed, err, ok))

    # ----- AWS -----
    aws_script = PROJECT_ROOT / "Sample Codes_AWS_Google" / "AWS_Transcribe_streaming_API.py"
    if not aws_script.exists():
        results.append(("AWS Transcribe", "", 0.0, "Script not found", False))
    else:
        stdout, stderr, elapsed = run_cmd([py, str(aws_script)], PROJECT_ROOT)
        transcript = parse_aws_stdout(stdout) if stdout else ""
        err = stderr.strip() or ""
        ok = bool(transcript) and "Error" not in stderr
        results.append(("AWS Transcribe", transcript or "(no transcript)", elapsed, err, ok))

    # ----- Azure -----
    azure_script = PROJECT_ROOT / "SampleCode_Azure.py" / "SampleCode_Azure.py"
    if not azure_script.exists():
        results.append(("Azure Speech", "", 0.0, "Script not found", False))
    else:
        stdout, stderr, elapsed = run_cmd([py, str(azure_script)], PROJECT_ROOT)
        transcript = parse_azure_stdout(stdout) if stdout else ""
        err = stderr.strip() or ""
        ok = bool(transcript) and "Error" not in stderr
        results.append(("Azure Speech", transcript or "(no transcript)", elapsed, err, ok))

    # ----- Report -----
    print("\n" + "=" * 60)
    print("STT COMPARISON (same audio)")
    print("=" * 60)
    for name, transcript, elapsed, err, ok in results:
        status = "OK" if ok else "FAIL"
        print(f"\n--- {name} [{status}] ---")
        print(f"  Time: {elapsed:.2f}s")
        print(f"  Transcript: {transcript[:200]}{'...' if len(transcript) > 200 else ''}")
        if err:
            print(f"  Stderr: {err[:300]}")
    print("\n" + "=" * 60)
    print("Summary (time in seconds)")
    print("-" * 60)
    for name, _, elapsed, _, ok in results:
        print(f"  {name}: {elapsed:.2f}s  {'✓' if ok else '✗'}")
    print()


if __name__ == "__main__":
    main()
