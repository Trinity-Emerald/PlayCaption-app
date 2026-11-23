# SPDX-License-Identifier: AGPL-3.0-or-later
"""NEXCAP Desktop user interface for LG transport diagnostics."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Empty, SimpleQueue
import sys
from threading import Event, Thread
import tkinter as tk
from tkinter import ttk

from capture import pair_console, stream_console, test_console
from transport import probe_receiver, send_subtitle


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NEXCAP Desktop · PetrDevelop")
        self.geometry("660x665")
        self.minsize(560, 650)
        self.configure(bg="#10141c")
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.events = SimpleQueue()
        self.stop_stream = Event()
        self.tray = None
        self.icon_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "nexcap.ico"
        if self.icon_path.is_file() and sys.platform == "win32":
            self.iconbitmap(str(self.icon_path))
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.ip = tk.StringVar()
        self.console = tk.StringVar()
        self.account = tk.StringVar()
        self.pin = tk.StringVar()
        self.endpoint = tk.StringVar(value="http://localhost:5000/translate")
        self.status = tk.StringVar(value="Zadej IP adresu z LG přijímače.")

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background="#10141c", foreground="#e8eef7",
                        font=("Segoe UI", 11))
        style.configure("TEntry", fieldbackground="#1e2938", foreground="#e8eef7",
                        insertcolor="#e8eef7", padding=8)
        style.configure("TButton", background="#243348", foreground="#e8eef7",
                        padding=9)
        style.map("TButton", background=[("active", "#314865")])
        style.configure("Accent.TButton", background="#126363")
        style.map("Accent.TButton", background=[("active", "#197c7c")])
        style.configure("Status.TLabel", foreground="#a9c5db")

        root = ttk.Frame(self, padding=28)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="NEXCAP Desktop", font=("Segoe UI", 25, "bold")).pack(anchor="w")
        ttk.Label(root, text="PetrDevelop").pack(anchor="w", pady=(0, 23))
        ttk.Label(root, text="IPv4 adresa LG televize").pack(anchor="w")
        ttk.Entry(root, textvariable=self.ip).pack(fill="x", pady=(4, 14))
        ttk.Label(root, text="Testovací titulek").pack(anchor="w")
        self.subtitle = tk.Text(root, height=3, background="#1e2938",
                                foreground="#e8eef7", insertbackground="#e8eef7",
                                font=("Segoe UI", 11), padx=8, pady=6, wrap="word")
        self.subtitle.insert("1.0", "Zkouška českých titulků\nNEXCAP Desktop")
        self.subtitle.pack(fill="x", pady=(4, 14))
        buttons = ttk.Frame(root)
        buttons.pack(fill="x")
        self.probe_button = ttk.Button(buttons, text="Ověřit přijímač", command=self.probe)
        self.probe_button.pack(side="left", padx=(0, 8))
        self.send_button = ttk.Button(buttons, text="Odeslat titulek", command=self.send,
                                      style="Accent.TButton")
        self.send_button.pack(side="left")
        settings = ttk.Frame(root)
        settings.pack(fill="x", pady=(18, 0))
        settings.columnconfigure(1, weight=1)
        for row, (label, variable, masked) in enumerate((
            ("IPv4 PS5", self.console, False),
            ("Sekundární PSN Account ID", self.account, True),
            ("Kód propojení PS5", self.pin, True),
            ("LibreTranslate URL", self.endpoint, False),
        )):
            ttk.Label(settings, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12))
            ttk.Entry(settings, textvariable=variable, show="•" if masked else "").grid(
                row=row, column=1, sticky="ew", pady=2)
        controls = ttk.Frame(root)
        controls.pack(fill="x", pady=(12, 0))
        self.pair_button = ttk.Button(controls, text="Spárovat PS5", command=self.pair)
        self.pair_button.pack(side="left", padx=(0, 8))
        self.video_button = ttk.Button(controls, text="Ověřit PS5", command=self.probe_video)
        self.video_button.pack(side="left", padx=(0, 8))
        self.start_button = ttk.Button(controls, text="Spustit překlad", command=self.start,
                                       style="Accent.TButton")
        self.start_button.pack(side="left", padx=(0, 8))
        self.stop_button = ttk.Button(controls, text="Zastavit", command=self.stop_stream.set)
        self.stop_button.state(["disabled"])
        self.stop_button.pack(side="left", padx=(0, 8))
        if sys.platform == "win32":
            ttk.Button(controls, text="Do lišty", command=self.hide_to_tray).pack(side="right")
        self.operation_buttons = (self.probe_button, self.send_button,
                                  self.pair_button, self.video_button, self.start_button)
        self.after(125, self.read_events)
        status = ttk.Label(root, textvariable=self.status, style="Status.TLabel")
        status.pack(anchor="w", fill="x", pady=(15, 0))
        status.bind("<Configure>", lambda event: status.configure(wraplength=event.width))

    def probe(self):
        def check(ip):
            name = probe_receiver(ip)
            return f"{name} odpověděl. Pro ověření zobrazení odešli titulek."
        self.run(check, self.ip.get())

    def send(self):
        def deliver(ip, subtitle):
            send_subtitle(ip, subtitle)
            return "UDP paket odeslán. Zobrazení zkontroluj na televizoru."
        self.run(deliver, self.ip.get(), self.subtitle.get("1.0", "end-1c"))

    def pair(self):
        account, pin = self.account.get(), self.pin.get()
        self.account.set("")
        self.pin.set("")
        self.run(pair_console, self.console.get(), account, pin,
                 pending="Páruji sekundární účet s PS5…")

    def probe_video(self):
        self.stop_stream.clear()
        self.stop_button.state(["!disabled"])
        self.run(test_console, self.console.get(), self.stop_stream, self.report,
                 pending="Ověřuji obraz z PS5…")

    def start(self):
        self.stop_stream.clear()
        self.stop_button.state(["!disabled"])
        self.run(stream_console, self.console.get(), self.ip.get(), self.endpoint.get(),
                 self.stop_stream, self.report, pending="Spouštím Remote Play…")

    def report(self, message):
        self.events.put((self.status.set, message))

    def read_events(self):
        try:
            while True:
                callback, *args = self.events.get_nowait()
                callback(*args)
                if callback == self.close:
                    return
        except Empty:
            self.after(125, self.read_events)

    def hide_to_tray(self):
        if self.tray is None:
            try:
                import pystray
                from PIL import Image
            except ImportError:
                self.status.set("Pro ikonu v liště jsou potřeba pystray a Pillow.")
                return

            def action(callback):
                return lambda icon, item: self.events.put((callback,))

            with Image.open(self.icon_path) as icon:
                picture = icon.copy()
            self.tray = pystray.Icon("nexcap", picture, "NEXCAP Desktop", pystray.Menu(
                pystray.MenuItem("Otevřít", action(self.restore), default=True),
                pystray.MenuItem("Zastavit překlad", action(self.stop_stream.set)),
                pystray.MenuItem("Ukončit", action(self.close)),
            ))
            Thread(target=self.tray.run, daemon=True).start()
        self.withdraw()

    def restore(self):
        self.deiconify()
        self.lift()

    def run(self, operation, *args, pending="Probíhá komunikace s LG…"):
        for button in self.operation_buttons:
            button.state(["disabled"])
        self.status.set(pending)
        future = self.executor.submit(operation, *args)
        future.add_done_callback(lambda result: self.events.put((self.completed, result)))

    def completed(self, future):
        try:
            self.status.set(future.result())
        except Exception as exc:
            self.status.set(str(exc))
        finally:
            for button in self.operation_buttons:
                button.state(["!disabled"])
            self.stop_button.state(["disabled"])

    def close(self):
        self.stop_stream.set()
        if self.tray:
            self.tray.stop()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
