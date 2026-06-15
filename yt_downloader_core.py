from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Callable

import yt_dlp


WHISPER_MODEL = "base"
DOWNLOAD_DIR = Path("downloads")

StatusCallback = Callable[[str], None]


def _noop_status(_message: str) -> None:
    return None


def get_whisper():
    try:
        import whisper
    except ImportError as exc:
        raise RuntimeError(
            "Whisper ist nicht installiert. Bitte installiere es mit:\n"
            "python -m pip install -U openai-whisper"
        ) from exc

    return whisper


def ensure_download_dir() -> Path:
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    return DOWNLOAD_DIR


def transcribe_media(url: str, on_status: StatusCallback | None = None) -> list[Path]:
    set_status = on_status or _noop_status
    written_files: list[Path] = []
    ensure_download_dir()

    with tempfile.TemporaryDirectory() as temp_dir:
        set_status("Audio wird fuer Transkript geladen...")
        ydl_opts = {
            "outtmpl": os.path.join(temp_dir, "%(title)s.%(ext)s"),
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "ignoreerrors": True,
            "quiet": False,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        audio_files = [
            os.path.join(temp_dir, name)
            for name in os.listdir(temp_dir)
            if name.lower().endswith(".mp3")
        ]

        if not audio_files:
            raise RuntimeError("Es wurde keine Audiodatei zum Transkribieren gefunden.")

        set_status("Whisper-Modell wird geladen...")
        whisper = get_whisper()
        model = whisper.load_model(WHISPER_MODEL)

        for audio_file in audio_files:
            title = os.path.splitext(os.path.basename(audio_file))[0]
            transcript_path = DOWNLOAD_DIR / f"{title}.txt"
            set_status(f"Transkribiere: {title}")
            result = model.transcribe(audio_file, fp16=False)

            with transcript_path.open("w", encoding="utf-8") as transcript_file:
                transcript_file.write(result.get("text", "").strip() + "\n")
            written_files.append(transcript_path)

    return written_files


class DownloadCollector:
    def __init__(self) -> None:
        self.files: list[Path] = []

    def hook(self, data: dict) -> None:
        if data.get("status") != "finished":
            return

        filename = data.get("filename")
        if filename:
            self.files.append(Path(filename))


def download_media(url: str, mode: str, on_status: StatusCallback | None = None) -> list[Path]:
    url = str(url or "").strip()
    mode = str(mode or "").strip().lower()
    set_status = on_status or _noop_status

    if not url:
        raise ValueError("Bitte eine URL eingeben.")
    if mode not in {"video", "audio", "transcript"}:
        raise ValueError("Ungueltiges Ausgabeformat.")

    download_dir = ensure_download_dir()
    before_files = {path.resolve() for path in download_dir.iterdir() if path.is_file()}

    if mode == "transcript":
        return transcribe_media(url, on_status=set_status)

    collector = DownloadCollector()
    if mode == "video":
        set_status("Video-Download laeuft...")
        ydl_opts = {
            "outtmpl": str(DOWNLOAD_DIR / "%(title)s.%(ext)s"),
            "format": "bv*[height<=360]+ba/b[height<=360]",
            "merge_output_format": "mp4",
            "postprocessors": [{
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            }],
            "ignoreerrors": True,
            "quiet": False,
            "progress_hooks": [collector.hook],
        }
    else:
        set_status("Audio-Download laeuft...")
        ydl_opts = {
            "outtmpl": str(DOWNLOAD_DIR / "%(title)s.%(ext)s"),
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "ignoreerrors": True,
            "quiet": False,
            "progress_hooks": [collector.hook],
        }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    after_files = [path for path in download_dir.iterdir() if path.is_file()]
    new_files = [path for path in after_files if path.resolve() not in before_files]
    existing_files = [path for path in collector.files if path.exists()]
    if new_files:
        existing_files = sorted(new_files, key=lambda path: path.stat().st_mtime, reverse=True)
    elif not existing_files:
        existing_files = sorted(after_files, key=lambda path: path.stat().st_mtime, reverse=True)[:1]

    return existing_files


def list_downloads() -> list[dict[str, object]]:
    download_dir = ensure_download_dir()
    files = sorted(
        [path for path in download_dir.iterdir() if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return [
        {
            "name": path.name,
            "size": path.stat().st_size,
            "modified": path.stat().st_mtime,
        }
        for path in files
    ]
