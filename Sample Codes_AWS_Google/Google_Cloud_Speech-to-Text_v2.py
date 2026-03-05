"""
Minimal Google Cloud Speech-to-Text v2 verification.
Demonstrates both chirp_2 and chirp_3 models are available.
"""
import os
import sys

from google.api_core.client_options import ClientOptions
from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech
from google.oauth2 import service_account

SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "aiellochatbot-7e91c5fcd6ee.json")
AUDIO_FILE           = os.environ.get("GOOGLE_AUDIO_FILE", "9e702cefb81ebbfd4ed298a196dde1fd4e07630f.mp3")
PROJECT_ID           = os.environ.get("GOOGLE_PROJECT_ID", "aiellochatbot")
LANGUAGE_CODE        = os.environ.get("GOOGLE_LANGUAGE", "cmn-Hant-TW")

MODELS = {
    "chirp_2": "us-central1",
    "chirp_3": "us",
}

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=["https://www.googleapis.com/auth/cloud-platform"],
)

with open(AUDIO_FILE, "rb") as f:
    content = f.read()

for model, location in MODELS.items():
    print(f"=== {model} (location: {location}) ===")

    client = SpeechClient(
        credentials=credentials,
        client_options=ClientOptions(api_endpoint=f"{location}-speech.googleapis.com"),
    )

    request = cloud_speech.RecognizeRequest(
        recognizer=f"projects/{PROJECT_ID}/locations/{location}/recognizers/_",
        config=cloud_speech.RecognitionConfig(
            auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
            language_codes=[LANGUAGE_CODE],
            model=model,
        ),
        content=content,
    )

    response = client.recognize(request=request)

    if not response.results:
        print("  No results returned.", file=sys.stderr)
        continue

    for result in response.results:
        print(f"  {result.alternatives[0].transcript}")
 