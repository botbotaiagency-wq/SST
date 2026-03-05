"""
Minimal Azure Speech-to-Text verification.
Demonstrates both Streaming (SDK) and REST API transcription of a local audio file.
"""
import os
import asyncio
import aiohttp
import io
from pathlib import Path
from dotenv import load_dotenv
from pydub import AudioSegment

load_dotenv(".env")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Azure Configuration
AZURE_SPEECH_KEY = os.environ.get("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.environ.get("AZURE_SPEECH_REGION")
AUDIO_FILE = "9e702cefb81ebbfd4ed298a196dde1fd4e07630f.wav"
LANGUAGE = "zh-TW"  # BCP-47 format: en-US, zh-TW, etc.

def check_config():
    if not AZURE_SPEECH_KEY or not AZURE_SPEECH_REGION:
        print("Error: AZURE_SPEECH_KEY and AZURE_SPEECH_REGION must be set in .env or .env.operator")
        return False
    if not os.path.exists(AUDIO_FILE):
        print(f"Error: Audio file {AUDIO_FILE} not found.")
        return False
    return True

async def transcribe_rest(audio_path: str, language: str):
    """Transcribe using Azure Speech REST API (similar to AzureASRService)."""
    print(f"\n--- REST API Transcription ({language}) ---")
    
    base_url = f"https://{AZURE_SPEECH_REGION}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1"
    
    # Pre-process audio (ensure 16kHz mono WAV)
    audio_wav = AudioSegment.from_file(audio_path)
    audio_wav = audio_wav.set_channels(1).set_frame_rate(16000)
    
    audio_buffer = io.BytesIO()
    audio_wav.export(audio_buffer, format="wav")
    audio_data = audio_buffer.getvalue()

    headers = {
        "Ocp-Apim-Subscription-Key": AZURE_SPEECH_KEY,
        "Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000",
        "Accept": "application/json",
    }

    params = {
        "language": language,
        "format": "detailed"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(base_url, headers=headers, params=params, data=audio_data) as response:
            if response.status != 200:
                text = await response.text()
                print(f"REST API Error: {response.status} - {text}")
                return None
            
            result = await response.json()
            status = result.get("RecognitionStatus")
            if status == "Success":
                transcript = result.get("DisplayText")
                print(f"REST Result: {transcript}")
                return transcript
            else:
                print(f"REST Recognition Status: {status}")
                return None

async def main():
    if not check_config():
        return

    print(f"Audio File: {AUDIO_FILE}")
    print(f"Region    : {AZURE_SPEECH_REGION}")

    await transcribe_rest(AUDIO_FILE, LANGUAGE)

if __name__ == "__main__":
    asyncio.run(main())
 