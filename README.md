# YouTube Downloader

Lokaler YouTube Downloader mit Desktop-UI und einfacher Weboberflaeche.

## Funktionen

- Video-Downloads als MP4
- Audio-Downloads als MP3
- optionale Transkripte als TXT ueber Whisper
- Weboberflaeche mit Download-Queue
- lokale Download-Liste und Dateizugriff

## Voraussetzungen

- Python 3.13 oder kompatibel
- FFmpeg im `PATH`
- Python-Pakete aus `requirements.txt`

## Installation

```powershell
python -m pip install -r requirements.txt
```

## Web-App starten

```powershell
python web_app.py
```

Danach im Browser oeffnen:

```text
http://127.0.0.1:8766
```

Alternativ kann `start_youtube_downloader_web.bat` genutzt werden, wenn der Python-Pfad auf dem Rechner passt.

## Desktop-App starten

```powershell
python "YT Downloader.py"
```

## Hinweise

Downloads werden lokal im Ordner `downloads/` gespeichert. Dieser Ordner ist absichtlich nicht Teil des Git-Repositories.
