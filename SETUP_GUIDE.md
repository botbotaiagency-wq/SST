# Step-by-step setup guide — run the STT app on your computer

This guide walks you through running the **Speech-to-Text comparison app** (Google, AWS, Azure) on your local computer. Follow the steps in order.

---

## What you’ll need before starting

- A **Windows** PC (this guide uses Windows; steps are similar on Mac/Linux).
- **Internet** (to install Python, download the project, and use the cloud STT services).
- The **STT project folder** (e.g. the `STT` folder from your colleague or from the repo).
- **Credentials** (API keys for Google, AWS, and optionally Azure) — usually in a document like *STT_Credentials_Engineering* (PDF/DOCX). Someone on your team can share this.

---

## Step 1 — Install Python

1. Go to **https://www.python.org/downloads/** and download **Python 3.10 or 3.11** for Windows.
2. Run the installer.
3. **Important:** On the first screen, check the box **“Add Python to PATH”**, then click **“Install Now”**.
4. When it finishes, close the installer.

**Check it worked:** Open **Command Prompt** or **PowerShell**, type:

```text
python --version
```

You should see something like `Python 3.10.x` or `Python 3.11.x`. If you see “not recognized”, Python is not on PATH — run the installer again and make sure “Add Python to PATH” was checked.

---

## Step 2 — Open the project folder in a terminal

1. Open **File Explorer** and go to the **STT** project folder (the one that contains `app.py`, `requirements.txt`, etc.).
2. Click the **address bar** at the top, type `cmd` or `powershell`, then press **Enter**.  
   A terminal window will open with that folder as the current directory.

**Or:** Open **PowerShell** or **Command Prompt**, then type (replace with your actual path):

```powershell
cd C:\Users\YourName\Documents\ANeura\STT
```

Use the real path to your STT folder.

---

## Step 3 — Create a virtual environment and install packages

In the same terminal, run these commands **one at a time** (press Enter after each):

```powershell
python -m venv .venv
```

Wait until it finishes (no error). Then **activate** the environment.

**If you use PowerShell** and you see an error like *“running scripts is disabled on this system”* or *“UnauthorizedAccess”* when you run the command below, use **Option A** or **Option B**:

- **Option A (easiest):** Use **Command Prompt** instead of PowerShell. Close the terminal, open **Command Prompt** (type `cmd` in the Start menu), `cd` to your STT folder, then run:
  ```bat
  .venv\Scripts\activate.bat
  ```
  You should see `(.venv)` at the start of the line. Then run `pip install -r requirements.txt`.

- **Option B:** In PowerShell, allow scripts for your user (run once). Open PowerShell and run:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```
  Type `Y` and Enter if asked. Then in your STT folder run:
  ```powershell
  .venv\Scripts\activate
  ```

**If activation works** (you see `(.venv)` at the start of the line), run:

```powershell
pip install -r requirements.txt
```

Wait until all packages finish installing. If you see “Successfully installed …”, you’re good.

---

## Step 4 — Set up credentials

The app needs API keys for Google and AWS (and optionally Azure). You’ll put them in a file called `credentials.json`.

1. In the **STT** folder, find the file **`credentials.json.example`**.
2. **Copy** it and **rename** the copy to **`credentials.json`** (remove `.example`).
3. Open **`credentials.json`** in Notepad or any text editor.
4. Fill in the values. You’ll get them from your team’s credential document (e.g. *STT_Credentials_Engineering*). The file looks like this:

```json
{
  "AWS_ACCESS_KEY_ID": "paste-your-aws-access-key-here",
  "AWS_SECRET_ACCESS_KEY": "paste-your-aws-secret-key-here",
  "AWS_DEFAULT_REGION": "ap-southeast-1",
  "AZURE_SPEECH_KEY": "paste-azure-key-if-you-have-it",
  "AZURE_SPEECH_REGION": "eastus2",
  "GOOGLE_APPLICATION_CREDENTIALS": "aiellochatbot-7e91c5fcd6ee.json",
  "GOOGLE_PROJECT_ID": "aiellochatbot",
  "GOOGLE_KEY_ID": "paste-google-key-id-if-you-have-it"
}
```

**What to paste where:**

| Key | What to put |
|-----|-------------|
| `AWS_ACCESS_KEY_ID` | From the credential doc: “Access Key ID” for AWS. |
| `AWS_SECRET_ACCESS_KEY` | From the doc: “Secret Access Key” for AWS. Copy it exactly, no spaces. |
| `AWS_DEFAULT_REGION` | Usually `ap-southeast-1` (or whatever your doc says). |
| `GOOGLE_APPLICATION_CREDENTIALS` | The **filename** of the Google JSON key file (e.g. `aiellochatbot-7e91c5fcd6ee.json`). |
| `GOOGLE_PROJECT_ID` | From the doc: Google Cloud project ID (e.g. `aiellochatbot`). |

5. **Google JSON key file:** The credential doc may refer to a “Google service account” or “credential file”. That file (e.g. `aiellochatbot-7e91c5fcd6ee.json`) must be **in the same STT folder** as `app.py`. If you received it as a download or from a colleague, copy it into the STT folder and make sure the name matches what you wrote in `GOOGLE_APPLICATION_CREDENTIALS`.
6. Save **`credentials.json`** and close the editor.

---

## Step 5 — Run the app

In the **same terminal** (with `(.venv)` still showing), run:

```powershell
python app.py
```

You should see something like:

```text
Log file: ...\logs\stt_app.log
FFmpeg not found on PATH. ...  (this is OK — mic and file upload still work)
AWS credentials loaded (Access Key ID: AKIA***)
Starting STT app on http://127.0.0.1:5000
 * Running on http://127.0.0.1:5000
```

**Leave this window open** — the app is running. If you close it, the app stops.

---

## Step 6 — Open the app in your browser

1. Open **Chrome** or **Edge**.
2. In the address bar, type exactly: **http://127.0.0.1:5000** and press **Enter**.
3. You should see the **Speech-to-Text comparison** page.

---

## Step 7 — Use the app

### Allow the microphone (for live recording)

- The first time you use the mic, the browser will ask: **“Allow microphone?”** → click **Allow**.
- If it doesn’t ask: go to **chrome://settings/content/microphone**, under “Allow” add **http://127.0.0.1:5000**, then reload the page.

### Transcribe with your voice (real time)

1. Choose **Provider** (e.g. Google or AWS) and **Language** (e.g. English (US)).
2. Click **“Start recording”**, then speak. The transcript appears as you talk (updates every 2 seconds).
3. Click **“Stop & transcribe”** when done.

### Transcribe an audio file (no mic needed)

1. Click **“Choose File”** and select an audio file (WAV, MP3, M4A, or WebM).
2. Click **“Transcribe file”**. The file is converted in the browser and sent to the server — no FFmpeg needed.
3. The transcript appears in the **Live transcript** box.

### Compare all three providers (Google, AWS, Azure)

- **With mic:** Click **“Record & compare all 3”**, speak for a few seconds, then wait. You’ll see results for Google, AWS, and Azure side by side.
- **With a file:** Choose a file with **“Choose File”** in the compare section, then click **“Compare with this file”**.

---

## If something goes wrong

| Problem | What to do |
|--------|------------|
| **“running scripts is disabled” / “UnauthorizedAccess”** when running `.venv\Scripts\activate` | Windows PowerShell is blocking the script. Use **Command Prompt** (cmd) and run **`.venv\Scripts\activate.bat`** instead, or run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` in PowerShell once, then try again. See Step 3 for details. |
| **“python” not recognized** | Install Python again and tick **“Add Python to PATH”**. Restart the terminal. |
| **“No module named …”** | Make sure you ran `pip install -r requirements.txt` **after** activating the venv (you should see `(.venv)`). |
| **“Credentials not found” / Google error** | Check that `credentials.json` exists in the STT folder and the Google JSON key file (e.g. `aiellochatbot-7e91c5fcd6ee.json`) is in the same folder. Restart the app after changing `credentials.json`. |
| **AWS “InvalidSignatureException”** | The AWS Secret Key in `credentials.json` must be copied exactly (no spaces or newlines). Create a **new** access key in AWS IAM and paste the new secret. Restart the app. |
| **“No microphone found”** | Allow the mic for `http://127.0.0.1:5000` in Chrome (see Step 7). Or use **“Upload audio”** to test with a file instead. |
| **Page doesn’t load** | Make sure you ran `python app.py` and left the terminal open. Use **http://127.0.0.1:5000** (not https). |

For more detail (and for Mac/Linux), see the main **README.md** in the same folder.

---

## Quick reference — run the app next time

1. Open a terminal in the **STT** folder (Command Prompt or PowerShell).
2. Activate the environment: **`.venv\Scripts\activate`** (PowerShell) or **`.venv\Scripts\activate.bat`** (Command Prompt). You should see `(.venv)`.
3. Run: **`python app.py`**.
4. In the browser open: **http://127.0.0.1:5000**.

That’s it. Enjoy comparing the STT engines.
