import threading
import tkinter as tk
from tkinter import ttk, messagebox

from yt_downloader_core import download_media as run_download_media


def download_media():
    url = url_entry.get().strip()
    mode = format_var.get()

    if not url:
        messagebox.showwarning("Fehler", "Bitte eine URL eingeben.")
        return

    status_label.config(text="Download laeuft...")
    download_button.config(state="disabled")

    def run_download():
        try:
            def set_status(text):
                root.after(0, lambda: status_label.config(text=text))

            run_download_media(url, mode, on_status=set_status)

            root.after(0, lambda: status_label.config(text="Fertig! Download abgeschlossen."))
            root.after(0, lambda: messagebox.showinfo("Erfolg", "Download abgeschlossen."))

        except Exception as e:
            root.after(0, lambda: status_label.config(text="Fehler beim Download."))
            root.after(0, lambda: messagebox.showerror("Fehler", str(e)))

        finally:
            root.after(0, lambda: download_button.config(state="normal"))

    threading.Thread(target=run_download, daemon=True).start()


# Hauptfenster
root = tk.Tk()
root.title("YouTube Downloader")
root.geometry("500x240")
root.resizable(False, False)

# URL
url_label = ttk.Label(root, text="YouTube-URL:")
url_label.pack(pady=(15, 5))

url_entry = ttk.Entry(root, width=60)
url_entry.pack(pady=5)

# Formatwahl
format_var = tk.StringVar(value="video")

format_label = ttk.Label(root, text="Ausgabeformat:")
format_label.pack(pady=(15, 5))

radio_frame = ttk.Frame(root)
radio_frame.pack()

video_radio = ttk.Radiobutton(radio_frame, text="Video (MP4)", variable=format_var, value="video")
video_radio.grid(row=0, column=0, padx=10)

audio_radio = ttk.Radiobutton(radio_frame, text="Audio (MP3)", variable=format_var, value="audio")
audio_radio.grid(row=0, column=1, padx=10)

transcript_radio = ttk.Radiobutton(radio_frame, text="Transkript (TXT)", variable=format_var, value="transcript")
transcript_radio.grid(row=0, column=2, padx=10)

# Download-Button
download_button = ttk.Button(root, text="Download starten", command=download_media)
download_button.pack(pady=20)

# Status
status_label = ttk.Label(root, text="Bereit")
status_label.pack()

root.mainloop()
