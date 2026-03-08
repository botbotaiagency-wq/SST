# STT Comparison: Google, AWS, Azure

Test and compare **Google Cloud Speech-to-Text**, **AWS Transcribe**, and **Azure Speech** with your microphone or audio files. Includes a **web app** for real-time transcription and a **CLI** script to compare all three on the same file.

**New to the project?** → See **[SETUP_GUIDE.md](SETUP_GUIDE.md)** for a step-by-step guide to run the app on your local computer (Python install, credentials, run commands, and troubleshooting).

---

## 1. Prerequisites (any local computer)

- **Python 3.10 or 3.11** (recommended). Install from [python.org](https://www.python.org/downloads/) and ensure **“Add Python to PATH”** is checked on Windows.
- **FFmpeg** is **optional**: the web app converts mic and uploaded files (MP3/M4A/WebM) in the browser, so you can run without FFmpeg. Install FFmpeg only if you need server-side conversion (e.g. for the CLI script).
  - **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) (e.g. “Windows builds” → gyan.dev), unzip, and add the `bin` folder to your system PATH.
  - **macOS**: `brew install ffmpeg`
  - **Linux**: `sudo apt install ffmpeg` (Debian/Ubuntu) or equivalent.

---

## 2. Project setup

### 2.1 Clone or copy the project

Use the project folder as your working directory (e.g. `STT`).

### 2.2 Create a virtual environment and install packages

**Windows (PowerShell or CMD):**

```powershell
cd path\to\STT
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**macOS / Linux:**

```bash
cd path/to/STT
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2.3 Credentials (from STT_Credentials_Engineering PDF/DOCX)

Copy the secret keys and API details from **STT_Credentials_Engineering** (PDF or DOCX) into one of:

**Option A – `credentials.json` (recommended)**  
Copy `credentials.json.example` to `credentials.json` in the project root. Paste in the values from the PDF:

- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`
- `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`
- `GOOGLE_APPLICATION_CREDENTIALS` (path to the Google service account JSON file), `GOOGLE_PROJECT_ID`

You can also paste the **entire Google service account JSON** into a key named `google_service_account` in `credentials.json`; the app will use it automatically.

**Option B – `.env`**  
Create a `.env` file in the project root (see `.env.example`) and paste the same keys there.

**Google Cloud**  
Use the path to your service account JSON (e.g. `Aiello_Google (1)/Aiello Chatbot.json`) or place the file as `aiellochatbot-7e91c5fcd6ee.json` in the project root.

---

## 3. Run the web app (microphone, real-time)

From the project root with the virtual environment activated:

```powershell
python app.py
```

Then open in your browser: **http://127.0.0.1:5000**

### What you can do

- **Provider**: Choose **Google**, **AWS**, or **Azure**.
- **Language**: Select the spoken language (e.g. English (US), Chinese (Taiwan)).
- **Start recording**: Click **“Start recording”**, speak; every **2 seconds** a chunk is sent (longer chunks help accuracy) and the transcript updates. Click **“Stop & transcribe”** to stop and get the last part.
- **Compare all 3**: Click **“Record & compare all 3”** to record one clip and run it through Google, AWS, and Azure so you can compare accuracy and speed side by side.

**Note:** The first time you use the mic, the browser will ask for microphone permission. Use **Chrome** or **Edge** for best support. Recording and file upload (MP3/M4A/WebM) are converted in the browser, so no FFmpeg is required.

### Deploy on Vercel

1. Connect your GitHub repo (**botbotaiagency-wq/SST**) to [Vercel](https://vercel.com) (Import Project).
2. Set **Root Directory** to the repo root (leave blank or `.`).
3. In **Project Settings → Environment Variables**, add (for Production, Preview, Development as needed):
   - **Google:** `GOOGLE_PROJECT_ID` (e.g. `aiellochatbot`). Then add **`GOOGLE_SERVICE_ACCOUNT_JSON`** — see **How to add GOOGLE_SERVICE_ACCOUNT_JSON** below.
   - **AWS:** `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION` (e.g. `ap-southeast-1`). Paste the secret with no extra spaces or newlines. If you get 403 InvalidSignatureException, create a new access key in AWS IAM and paste the new secret.
   - **Azure:** `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` (e.g. `eastus2`) — required for the Azure provider; add these if you use Azure.
4. **Redeploy** after changing env vars (Deployments → … → Redeploy). The app will be at `https://your-project.vercel.app`.  
   **Microphone:** Browsers require HTTPS and may prompt for mic permission; allow for your Vercel URL.

#### How to add GOOGLE_SERVICE_ACCOUNT_JSON (Vercel)

**Do not deploy the credential file** (e.g. `aiellochatbot-7e91c5fcd6ee.json`) to the repo or Vercel — it contains a private key and is in `.gitignore` for security. Use the environment variable instead.

1. **Get the value (one line):** On your computer, in the project folder, run one of these in a terminal (use the path to your actual JSON file):
   ```powershell
   python -c "import json; print(json.dumps(json.load(open('aiellochatbot-7e91c5fcd6ee.json'))))"
   ```
   Or, if the file is in a subfolder:
   ```powershell
   python -c "import json; print(json.dumps(json.load(open(r'Aiello_Google (1)/Aiello Chatbot.json'))))"
   ```
   The command prints the JSON as a single line. Copy the **entire output** (from `{` to `}`).

2. **Add it in Vercel:** Project → **Settings** → **Environment Variables** → **Add New** → Name: `GOOGLE_SERVICE_ACCOUNT_JSON`, Value: paste the copied line → Save. Apply to Production (and Preview/Development if you want).

3. **Redeploy** so the new variable is used.

---

## 4. Run the CLI comparison (file-based)

To compare all three providers on the **same audio file** (no mic):

1. Put a WAV file in the project root named  
   `9e702cefb81ebbfd4ed298a196dde1fd4e07630f.wav`  
   (or set `AUDIO_WAV` / `AUDIO_MP3` in `.env`; see below).
2. With the same venv and `.env` as above, run:

```powershell
python run_stt_comparison.py
```

The script prints each provider’s transcript and timing so you can compare performance.

Optional env vars for the CLI script:

- `AUDIO_WAV` – WAV filename (default: `9e702cefb81ebbfd4ed298a196dde1fd4e07630f.wav`)
- `AUDIO_MP3` – MP3 filename for Google (default: same base name as `AUDIO_WAV` with `.mp3`)

---

## 5. Transcription quality

Quality depends on both the **model** and **how audio is sent**:

- **Chunk length**: The app sends **2-second** chunks during live recording so the model has more context and tends to transcribe more fully. You can change this in the frontend (`chunkSeconds` in `templates/index.html`) if you want faster updates (e.g. 1 s) or higher accuracy (e.g. 3 s).
- **Google (chirp_2)**: Automatic punctuation is enabled. For best results use a clear mic and 16 kHz mono (the app does this for you).
- **AWS**: Partial-results stabilization is set to **high** so streaming results are more stable and complete.
- **Silence**: Very quiet or silent chunks are not sent to the API (avoids phantom text). If the start/end of your speech is cut off, try speaking a bit louder or moving closer to the mic.

For domain-specific terms (e.g. product names), consider provider-specific options: **Google** phrase hints / adaptation, **AWS** custom vocabulary.

---

## 6. Packages included

| Package              | Purpose                          |
|----------------------|----------------------------------|
| `Flask`              | Web app server                   |
| `python-dotenv`      | Load `.env` credentials          |
| `pydub`              | Audio conversion (WAV, etc.)      |
| `google-cloud-speech`| Google Speech-to-Text v2         |
| `google-auth`        | Google service account auth      |
| `amazon-transcribe`  | AWS Transcribe streaming         |
| `aiohttp`            | Azure Speech REST API calls      |

FFmpeg is **not** installed via pip; install it on your system as in section 1.

---

## 7. Logs

When the app runs, it writes logs to:

- **Console** – every log line is printed to the terminal.
- **File** – `logs/stt_app.log` in the project root (created automatically).

Use this file to trace errors (e.g. WinError 32, API failures, missing credentials). The log includes timestamps, level (DEBUG/INFO/WARNING/ERROR), and full exception tracebacks.

---

## 8. Troubleshooting

- **“No audio file or invalid format”** / **“FFmpeg not found”** (or `FileNotFoundError: [WinError 2]` in logs)  
  Choose a supported file (WAV, MP3, M4A, WebM); the browser converts non-WAV uploads without FFmpeg. If you see this for the CLI or another workflow, install FFmpeg and add its `bin` folder to PATH (see Prerequisites).

- **Google: “GOOGLE_APPLICATION_CREDENTIALS must point to a service account JSON”**  
  Set `GOOGLE_APPLICATION_CREDENTIALS` in `.env` to the full path of your JSON key file, or place the key file in the project root as `aiellochatbot-7e91c5fcd6ee.json`.

- **AWS: “InvalidSignatureException” / “request signature we calculated does not match”**  
  The app loads AWS keys from **credentials.json** (which overrides **.env**). **Restart the app** after changing either file. The Secret Access Key must contain only letters, digits, and `/+=` (no spaces or newlines). In AWS Console → IAM → Users → your user → Security credentials → **Create access key**, then copy the **Secret access key** and paste it as `AWS_SECRET_ACCESS_KEY` in **credentials.json** with no spaces before/after. If you copied the key from a PDF/Word doc, create a **new** access key in IAM and use that secret. On startup the app logs “AWS credentials loaded (Access Key ID: AKIA***)” so you can confirm the right key is used.

- **AWS / Azure errors**  
  Check that the corresponding variables in `.env` or `credentials.json` are set and that the keys are valid and have Speech/Transcribe permissions.

- **“Requested device not found” / “No microphone found”**  
  Use a built-in or USB microphone and allow access when the browser asks. You can still test without a mic: use **Upload audio** in the app (choose a WAV/MP3 file and click “Transcribe file”).

- **Microphone not working**  
  Use HTTPS or `http://127.0.0.1` (localhost); allow microphone access when the browser prompts.
