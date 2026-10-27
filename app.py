import os, re, shutil, subprocess, uuid, zipfile
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash, abort
from werkzeug.utils import secure_filename

BASE = Path(__file__).resolve().parent
UPLOAD_DIR = BASE / "uploads"
OUTPUT_DIR = BASE / "outputs"
for folder in (UPLOAD_DIR, OUTPUT_DIR):
    folder.mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-local-dev-key")
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024 * 1024  # 4 GB local upload limit
ALLOWED = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}

def tool_path(name):
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"{name} was not found. Install FFmpeg and add it to PATH, then restart the terminal.")
    return path

def run_cmd(args):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        detail = (p.stderr or p.stdout or "Unknown FFmpeg error")[-2500:]
        raise RuntimeError(detail)
    return p

def duration_seconds(path):
    p = run_cmd([tool_path("ffprobe"), "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    try:
        return float(p.stdout.strip())
    except ValueError:
        raise RuntimeError("Could not read the video's duration. Check that the file is a valid video.")

def stamp(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds//60:02d}:{seconds%60:02d}"

def render_clip(source, destination, start, length, vertical=False):
    args = [tool_path("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{start:.3f}", "-i", str(source), "-t", f"{length:.3f}"]
    if vertical:
        args += ["-vf", "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280"]
    args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(destination)]
    run_cmd(args)

def scene_times(source):
    # Basic scene-change analysis; this is a heuristic, not semantic AI.
    cmd = [tool_path("ffmpeg"), "-hide_banner", "-i", str(source), "-vf",
           "select='gt(scene,0.32)',showinfo", "-an", "-f", "null", "-"]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    times = []
    for match in re.finditer(r"pts_time:([0-9]+(?:\.[0-9]+)?)", p.stderr):
        try:
            times.append(float(match.group(1)))
        except ValueError:
            pass
    return sorted(set(t for t in times if t > 0))

def choose_highlight_windows(duration, scenes, clip_len):
    # Generate candidate windows around detected scene changes, then prefer windows
    # containing more scene changes. Falls back to evenly spaced windows if needed.
    if duration <= clip_len:
        return [(0.0, duration)]
    starts = {0.0, max(0.0, duration - clip_len)}
    for t in scenes:
        starts.add(max(0.0, min(duration - clip_len, t - clip_len * 0.35)))
        starts.add(max(0.0, min(duration - clip_len, t - clip_len * 0.65)))
    if len(starts) < 3:
        count = min(8, max(2, int(duration // clip_len)))
        starts.update(max(0.0, min(duration - clip_len, i * (duration - clip_len) / max(1, count - 1))) for i in range(count))
    windows = [(s, min(clip_len, duration - s)) for s in starts]
    def score(item):
        s, length = item
        count = sum(1 for t in scenes if s <= t <= s + length)
        # Slightly favor clips not taken only from the extreme beginning/end.
        edge_penalty = 0.25 if s < 1 or s + length > duration - 1 else 0
        return count - edge_penalty
    windows.sort(key=score, reverse=True)
    chosen = []
    for candidate in windows:
        s, ln = candidate
        if all(abs(s - old_s) >= clip_len * 0.65 for old_s, _ in chosen):
            chosen.append(candidate)
        if len(chosen) >= 8:
            break
    return sorted(chosen, key=lambda x: x[0])

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/process", methods=["POST"])
def process():
    file = request.files.get("video")
    mode = request.form.get("mode", "split")
    vertical = request.form.get("vertical") == "on"
    try:
        if not file or not file.filename:
            flash("Choose a video file first.", "error")
            return redirect(url_for("index"))
        original_name = secure_filename(file.filename)
        suffix = Path(original_name).suffix.lower()
        if suffix not in ALLOWED:
            flash("Supported formats: MP4, MOV, MKV, WEBM, AVI, M4V.", "error")
            return redirect(url_for("index"))
        seconds = int(request.form.get("seconds", "60"))
        seconds = max(5, min(seconds, 3600))
        job = uuid.uuid4().hex[:10]
        job_upload = UPLOAD_DIR / f"{job}{suffix}"
        job_out = OUTPUT_DIR / job
        job_out.mkdir()
        file.save(job_upload)
        duration = duration_seconds(job_upload)
        if duration <= 0:
            raise RuntimeError("The video duration is zero or unreadable.")

        if mode == "shorts":
            scenes = scene_times(job_upload)
            windows = choose_highlight_windows(duration, scenes, seconds)
            if not windows:
                windows = [(0.0, min(seconds, duration))]
            label = "AI Shorts suggestions"
        else:
            windows = [(start, min(seconds, duration - start))
                       for start in (i * seconds for i in range(int((duration + seconds - 0.001) // seconds)))]
            label = "Equal split"

        clips = []
        for i, (start, length) in enumerate(windows, 1):
            if length <= 0.2:
                continue
            filename = f"clip_{i:02d}.mp4"
            render_clip(job_upload, job_out / filename, start, length, vertical)
            clips.append({"name": filename, "start": stamp(start), "end": stamp(start + length),
                          "duration": stamp(length), "number": i})

        if not clips:
            raise RuntimeError("No clips were created.")
        zip_path = job_out / "all_clips.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for clip in clips:
                zf.write(job_out / clip["name"], arcname=clip["name"])
        # Keep the original upload on disk only while processing; clips remain in outputs.
        try:
            job_upload.unlink()
        except OSError:
            pass
        return render_template("results.html", job=job, clips=clips, label=label,
                               duration=stamp(duration), vertical=vertical, mode=mode)
    except Exception as exc:
        flash(f"Processing failed: {exc}", "error")
        return redirect(url_for("index"))

@app.route("/files/<job>/<path:filename>")
def get_file(job, filename):
    # Prevent path traversal and only serve files inside the generated job directory.
    folder = (OUTPUT_DIR / job).resolve()
    if not folder.is_relative_to(OUTPUT_DIR.resolve()):
        abort(404)
    target = (folder / filename).resolve()
    if not target.is_relative_to(folder) or not target.is_file():
        abort(404)
    return send_from_directory(folder, filename, as_attachment=True)

if __name__ == "__main__":
    print("ClipForge AI is starting at http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
