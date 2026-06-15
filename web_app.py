from __future__ import annotations

import json
import mimetypes
import os
import queue
import socket
import threading
import time
import traceback
import urllib.parse
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from yt_downloader_core import DOWNLOAD_DIR, download_media, ensure_download_dir, list_downloads


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
HOST = os.getenv("YT_DOWNLOADER_HOST", "0.0.0.0").strip() or "0.0.0.0"
PORT = int(os.getenv("YT_DOWNLOADER_PORT", "8766"))

STATE_LOCK = threading.Lock()
JOB_QUEUE: queue.Queue[str] = queue.Queue()
JOBS: dict[str, dict] = {}
QUEUED_JOB_IDS: list[str] = []
WORKER_STARTED = False
STATE = {
    "version": "queue-v1",
    "running": False,
    "status": "Bereit.",
    "job_id": "",
    "current_job": None,
    "mode": "",
    "started_at": 0.0,
    "finished_at": 0.0,
    "last_error": "",
    "files": [],
}


def _json_response(handler: SimpleHTTPRequestHandler, payload: object, status: int = 200) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _text_response(handler: SimpleHTTPRequestHandler, text: str, status: int = 200) -> None:
    data = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _state_snapshot() -> dict:
    with STATE_LOCK:
        snapshot = dict(STATE)
        snapshot["current_job"] = dict(STATE["current_job"]) if STATE.get("current_job") else None
        snapshot["queued_jobs"] = [dict(JOBS[job_id]) for job_id in QUEUED_JOB_IDS if job_id in JOBS]
        snapshot["recent_jobs"] = [
            dict(job)
            for job in sorted(JOBS.values(), key=lambda item: item.get("created_at", 0.0), reverse=True)
            if job.get("state") in {"done", "error"}
        ][:8]
        snapshot["queue_size"] = len(snapshot["queued_jobs"])
        return snapshot


def _set_state(**kwargs) -> None:
    with STATE_LOCK:
        STATE.update(kwargs)


def _set_status(message: str) -> None:
    _set_state(status=str(message))


def _job_label(url: str) -> str:
    return url if len(url) <= 90 else f"{url[:87]}..."


def _enqueue_download(url: str, mode: str) -> str:
    job_id = uuid.uuid4().hex
    now = time.time()
    job = {
        "id": job_id,
        "url": url,
        "label": _job_label(url),
        "mode": mode,
        "state": "queued",
        "status": "Wartet in der Queue.",
        "created_at": now,
        "started_at": 0.0,
        "finished_at": 0.0,
        "files": [],
        "error": "",
    }
    with STATE_LOCK:
        JOBS[job_id] = job
        QUEUED_JOB_IDS.append(job_id)
        STATE["status"] = "Job zur Queue hinzugefuegt."
    JOB_QUEUE.put(job_id)
    return job_id


def _run_download_job(job_id: str) -> None:
    with STATE_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        if job_id in QUEUED_JOB_IDS:
            QUEUED_JOB_IDS.remove(job_id)
        job["state"] = "running"
        job["status"] = "Download wird vorbereitet..."
        job["started_at"] = time.time()
        STATE.update(
            running=True,
            status=job["status"],
            job_id=job_id,
            current_job=dict(job),
            mode=job["mode"],
            started_at=job["started_at"],
            finished_at=0.0,
            last_error="",
            files=[],
        )

    def set_job_status(message: str) -> None:
        with STATE_LOCK:
            active_job = JOBS.get(job_id)
            if active_job:
                active_job["status"] = str(message)
                STATE["current_job"] = dict(active_job)
            STATE["status"] = str(message)

    try:
        with STATE_LOCK:
            job = JOBS[job_id]
            url = str(job["url"])
            mode = str(job["mode"])

        files = download_media(url, mode, on_status=set_job_status)
        finished_at = time.time()
        file_names = [path.name for path in files]
        with STATE_LOCK:
            job = JOBS[job_id]
            job.update(
                state="done",
                status="Fertig. Download abgeschlossen.",
                finished_at=finished_at,
                files=file_names,
                error="",
            )
            STATE.update(
                running=False,
                status="Fertig. Download abgeschlossen.",
                current_job=None,
                finished_at=finished_at,
                files=file_names,
                last_error="",
            )
    except Exception as exc:
        finished_at = time.time()
        with STATE_LOCK:
            job = JOBS.get(job_id)
            if job:
                job.update(
                    state="error",
                    status="Fehler beim Download.",
                    finished_at=finished_at,
                    error=str(exc),
                )
            STATE.update(
                running=False,
                status="Fehler beim Download.",
                current_job=None,
                finished_at=finished_at,
                last_error=str(exc),
            )
        traceback.print_exc()


def _download_worker() -> None:
    while True:
        job_id = JOB_QUEUE.get()
        try:
            _run_download_job(job_id)
        finally:
            JOB_QUEUE.task_done()
            with STATE_LOCK:
                if not STATE["running"] and QUEUED_JOB_IDS:
                    STATE["status"] = f"{len(QUEUED_JOB_IDS)} Job(s) warten."


def _start_worker_once() -> None:
    global WORKER_STARTED
    if WORKER_STARTED:
        return
    worker = threading.Thread(target=_download_worker, name="download-worker", daemon=True)
    worker.start()
    WORKER_STARTED = True


class AppHandler(SimpleHTTPRequestHandler):
    server_version = "YTDownloaderWeb/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._serve_static_file(STATIC_DIR / "index.html")
            return
        if path == "/app.js":
            self._serve_static_file(STATIC_DIR / "app.js")
            return
        if path == "/api/status":
            _json_response(self, _state_snapshot())
            return
        if path == "/api/downloads":
            _json_response(self, {"items": list_downloads()})
            return
        if path.startswith("/downloads/"):
            self._serve_download(path.removeprefix("/downloads/"))
            return

        _text_response(self, "Nicht gefunden.", 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/download":
            _text_response(self, "Nicht gefunden.", 404)
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError:
            _json_response(self, {"error": "Ungueltiges JSON."}, 400)
            return

        url = str(payload.get("url", "")).strip()
        mode = str(payload.get("mode", "video")).strip().lower()
        if not url:
            _json_response(self, {"error": "Bitte eine URL eingeben."}, 400)
            return
        if mode not in {"video", "audio", "transcript"}:
            _json_response(self, {"error": "Ungueltiges Ausgabeformat."}, 400)
            return

        job_id = _enqueue_download(url, mode)
        _json_response(self, {"ok": True, "job_id": job_id, "queued": True})

    def _serve_static_file(self, file_path: Path) -> None:
        if not file_path.exists() or not file_path.is_file():
            _text_response(self, "Nicht gefunden.", 404)
            return

        data = file_path.read_bytes()
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        if file_path.suffix.lower() in {".html", ".js", ".css"}:
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_download(self, raw_name: str) -> None:
        ensure_download_dir()
        name = urllib.parse.unquote(raw_name)
        file_path = (DOWNLOAD_DIR / name).resolve()
        download_root = DOWNLOAD_DIR.resolve()

        if download_root not in [file_path, *file_path.parents] or not file_path.is_file():
            _text_response(self, "Nicht gefunden.", 404)
            return

        data = file_path.read_bytes()
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{urllib.parse.quote(file_path.name)}")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:
        return


def _find_free_port(host: str, preferred_port: int) -> int:
    for port in range(preferred_port, preferred_port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex((host, port)) != 0:
                return port
    raise RuntimeError("Kein freier Port gefunden.")


def main() -> None:
    ensure_download_dir()
    _start_worker_once()
    port = _find_free_port(HOST, PORT)
    httpd = ThreadingHTTPServer((HOST, port), AppHandler)
    print(f"YouTube Downloader Web laeuft lokal auf http://127.0.0.1:{port}")
    print(f"Im LAN erreichbar unter http://<deine-lokale-ip>:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
