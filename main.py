from fastapi import FastAPI, Query, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import os, uuid, yt_dlp, traceback

app = FastAPI()

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Optional: only mount /static if it exists (avoids Render errors)
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Progress tracking store
download_progress = {}

@app.get("/", response_class=HTMLResponse)
def home():
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/info")
async def get_video_info(url: str):
    try:
        ydl_opts = {
            "cookiefile": "cookies.txt",
            "quiet": True,
            "user_agent": "Mozilla/5.0"
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "title": info.get("title"),
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration")
            }
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.get("/progress")
def get_progress(id: str):
    return {"progress": download_progress.get(id, 0)}


@app.get("/convert")
async def convert_youtube(
    background_tasks: BackgroundTasks,
    url: str = Query(...),
    format: str = Query("mp4"),
    resolution: str = Query("best"),
    id: str = Query(...)
):
    try:
        download_progress[id] = 0

        # Extract filename/title
        info_opts = {
            "cookiefile": "cookies.txt",
            "quiet": True,
            "user_agent": "Mozilla/5.0"
        }
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get("title").replace(" ", "_").replace("/", "_")
        filename = f"{title}_{uuid.uuid4().hex[:6]}"
        output_template = os.path.join(DOWNLOAD_DIR, f"{filename}.%(ext)s")

        # Progress hook
        def progress_hook(d):
            if d['status'] == 'downloading':
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
                downloaded = d.get("downloaded_bytes", 0)
                download_progress[id] = int(downloaded / total * 100)
            elif d['status'] == 'finished':
                download_progress[id] = 100

        # Final download options
        common_opts = {
            "cookiefile": "cookies.txt",
            "outtmpl": output_template,
            "user_agent": "Mozilla/5.0",
            "progress_hooks": [progress_hook],
            "quiet": True,
        }

        if format == "mp4":
            ydl_opts = {
                **common_opts,
                'format': f'bestvideo[height={resolution}]+bestaudio/best[height={resolution}]/best',
                'merge_output_format': 'mp4'
            }
        else:  # mp3
            ydl_opts = {
                **common_opts,
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=True)
            base = ydl.prepare_filename(result).rsplit(".", 1)[0]
            final_file = base + (".mp3" if format == "mp3" else ".mp4")
            media_type = "audio/mpeg" if format == "mp3" else "video/mp4"

            # Schedule cleanup
            background_tasks.add_task(os.remove, final_file)
            return FileResponse(path=final_file, filename=os.path.basename(final_file), media_type=media_type)

    except Exception as e:
        return JSONResponse(status_code=400, content={
            "error": str(e),
            "traceback": traceback.format_exc()
        })
