# ClipForge AI — Local Video Splitter & Shorts Maker

A local Windows-friendly Flask app that uses FFmpeg to split video files into clips, export clips individually, and package all clips in a ZIP. The "AI Shorts" starter mode uses FFmpeg scene-change detection to suggest up to eight candidate windows. It is a heuristic, not a trained semantic AI model.

## Requirements
- Windows 10/11
- Python 3.10 or newer
- FFmpeg and FFprobe installed and added to PATH
- VS Code (recommended)

## 1. Install Python
Install Python from https://www.python.org/downloads/ . During setup, tick **Add python.exe to PATH**.

## 2. Install FFmpeg
Install FFmpeg from https://ffmpeg.org/download.html or a trusted Windows build. Extract it and add the folder containing `ffmpeg.exe` and `ffprobe.exe` to your Windows PATH. Open a new PowerShell window and check:

```powershell
python --version
ffmpeg -version
ffprobe -version
```

Each command should print version information.

## 3. Open this folder in VS Code
Extract the ZIP. In VS Code choose **File → Open Folder** and select `clipforge_ai`.

## 4. Create a virtual environment and install dependencies
Open Terminal → New Terminal in VS Code, then run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks activation, use Command Prompt in VS Code and run `.venv\Scripts\activate.bat`, then install requirements.

## 5. Start the website

```powershell
python app.py
```

Open http://127.0.0.1:5000 in your browser. Keep the terminal running while using the site. Stop the server with Ctrl+C.

## How to use
1. Select a video from your laptop.
2. Choose **Equal Split** or **AI Shorts**.
3. Pick the clip length.
4. Optional: select vertical 9:16 export (this crops the center of the frame).
5. Click **Process video**.
6. Download each MP4 or the all-clips ZIP.

## Notes
- Large videos take time because clips are re-encoded for broad compatibility.
- This starter processes one job at a time and keeps output clips in `outputs/<job-id>/`. Delete old output folders manually when you no longer need them.
- Maximum upload size is configured as 4 GB. Increase or reduce `MAX_CONTENT_LENGTH` in `app.py` if needed.
- AI Shorts mode detects visual scene changes and chooses candidate windows around them. It does not transcribe speech, understand plot context, identify copyrighted content, or guarantee viral highlights.
- Vertical mode center-crops to 720×1280. A future version could add subject tracking and subtitle generation.
- Use only videos you own or have permission to edit. Do not use this app to bypass DRM or download protected streaming content.
- The Flask development server is intended for local use, not public internet deployment.
