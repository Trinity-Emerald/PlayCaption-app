# SPDX-License-Identifier: AGPL-3.0-or-later
"""NEXCAP Desktop user interface for LG transport diagnostics."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Empty, SimpleQueue
import socket
import sys
from threading import Event, Thread
import tkinter as tk
from tkinter import ttk

from capture import DEFAULT_REGION, OCR_REGIONS, pair_console, stream_console, test_console, tv_addresses
from transport import probe_receiver, send_subtitle
from tv_output import BrowserOutput


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NEXCAP Desktop · PetrDevelop")
        self.geometry("1040x740")
        self.minsize(870, 660)
        self.configure(bg="#0b1321")
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.events = SimpleQueue()
        self.stop_stream = Event()
        self.tray = None
        self.browser = BrowserOutput()
        self.preview = None
        assets = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        self.icon_path = assets / "nexcap.ico"
        logo = tk.PhotoImage(file=assets / "nexcap.png")
        self.iconphoto(True, logo)
        self.logo = logo.subsample(5, 5)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.ip = tk.StringVar(value="192.168.0.17")
        self.console = tk.StringVar()
        self.account = tk.StringVar()
        self.pin = tk.StringVar()
        self.endpoint = tk.StringVar()
        self.region = tk.StringVar(value=DEFAULT_REGION)
        self.font = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"
        self.caption = tk.StringVar()
        self.dashboard_caption = tk.StringVar(value="Čekám na první český titulek…")
        self.caption_timeout = None
        self.lg = tk.StringVar(value="Čeká na ověření")
        self.status = tk.StringVar(value="Připraveno")
        self.browser_url = tk.StringVar()
        self.browser_state = tk.StringVar(value="Vypnutý")
        self.build_interface()
        self.after(125, self.read_events)

    def build_interface(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background="#0b1321", foreground="#ebf4ff", font=(self.font, 11))
        style.configure("Rail.TFrame", background="#101d30")
        style.configure("Rail.TLabel", background="#101d30", foreground="#9fb8d5")
        style.configure("Brand.TLabel", background="#101d30", font=(self.font, 19, "bold"))
        style.configure("Title.TLabel", font=(self.font, 29, "bold"))
        style.configure("Muted.TLabel", foreground="#9fb8d5")
        style.configure("Card.TFrame", background="#12233a")
        style.configure("Card.TLabel", background="#12233a", foreground="#eef7ff")
        style.configure("CardTitle.TLabel", background="#12233a", foreground="#7be8ff",
                        font=(self.font, 11, "bold"))
        style.configure("TEntry", fieldbackground="#172b43", foreground="#ebf4ff",
                        insertcolor="#ebf4ff", bordercolor="#2a4561", padding=9)
        style.configure("TButton", background="#1b324c", bordercolor="#304c69",
                        foreground="#ebf4ff", padding=(13, 9), relief="flat")
        style.map("TButton", background=[("active", "#263f5b")],
                  foreground=[("disabled", "#8299b3")])
        style.configure("Accent.TButton", background="#68e6fa", bordercolor="#68e6fa",
                        foreground="#081827", font=(self.font, 11, "bold"))
        style.map("Accent.TButton", background=[("disabled", "#223b50"), ("active", "#a0f2ff")])
        style.configure("Nav.TButton", background="#101d30", bordercolor="#101d30",
                        anchor="w", padding=(15, 11))
        style.map("Nav.TButton", background=[("active", "#223d58"), ("selected", "#20405a")],
                  foreground=[("selected", "#8febff")])

        rail = ttk.Frame(self, padding=19, style="Rail.TFrame")
        rail.pack(side="left", fill="y")
        ttk.Label(rail, image=self.logo, style="Brand.TLabel").pack(anchor="w")
        ttk.Label(rail, text="NEXCAP", style="Brand.TLabel").pack(anchor="w", pady=(8, 0))
        ttk.Label(rail, text="by PetrDevelop", style="Rail.TLabel").pack(anchor="w", pady=(0, 30))
        self.content = ttk.Frame(self, padding=(29, 23))
        self.content.pack(side="left", fill="both", expand=True)
        self.pages = {}
        self.nav = {}
        for name, title, description, build in (
            ("Přehled", "Přehled", "České titulky při hraní z PS5", self.build_overview),
            ("Televize", "Výstupy pro televize", "Připoj několik televizí v domácí síti.", self.build_televisions),
            ("Nastavení", "Nastavení", "Párování PS5 a volba překladového modelu", self.build_settings),
        ):
            self.nav[name] = self.button(rail, name, lambda key=name: self.navigate(key),
                                         style="Nav.TButton")
            self.nav[name].pack(fill="x", pady=3)
            page = ttk.Frame(self.content)
            ttk.Label(page, text=title, style="Title.TLabel").pack(anchor="w")
            ttk.Label(page, text=description, style="Muted.TLabel").pack(anchor="w", pady=(3, 18))
            build(page)
            self.pages[name] = page
        if sys.platform == "win32":
            self.button(rail, "Do systémové lišty", self.hide_to_tray, style="Nav.TButton").pack(
                side="bottom", fill="x")
        self.operation_buttons = (self.probe_button, self.send_button,
                                  self.pair_button, self.video_button, self.start_button)
        self.navigate("Přehled")

    def navigate(self, name):
        for key, page in self.pages.items():
            self.nav[key].state(["selected" if key == name else "!selected"])
            if key != name:
                page.pack_forget()
        self.pages[name].pack(fill="both", expand=True)

    def button(self, parent, label, command, *, style="TButton"):
        return ttk.Button(parent, text=label, command=command, style=style)

    def card(self, parent, heading):
        card = ttk.Frame(parent, style="Card.TFrame", padding=(15, 11))
        ttk.Label(card, text=heading, style="CardTitle.TLabel").pack(anchor="w", pady=(0, 7))
        return card

    def build_overview(self, page):
        actions = ttk.Frame(page)
        actions.pack(fill="x", pady=(0, 15))
        self.start_button = self.button(actions, "Spustit překlad", self.start, style="Accent.TButton")
        self.start_button.pack(side="left", padx=(0, 8))
        self.stop_button = self.button(actions, "Zastavit", self.stop_stream.set)
        self.stop_button.state(["disabled"])
        self.stop_button.pack(side="left", padx=(0, 8))
        self.button(actions, "Samostatný náhled", self.open_preview).pack(side="left")
        region = ttk.Frame(page)
        region.pack(fill="x", pady=(0, 14))
        ttk.Label(region, text="Oblast OCR").pack(side="left", padx=(0, 9))
        ttk.Combobox(region, textvariable=self.region, state="readonly", width=28,
                     values=tuple(OCR_REGIONS)).pack(side="left")
        ttk.Label(region, text="Použije se při spuštění překladu", style="Muted.TLabel").pack(
            side="left", padx=(10, 0))
        status = self.card(page, "PS5 A PŘEKLAD")
        status.pack(fill="x", pady=(0, 9))
        ttk.Label(status, textvariable=self.status, style="Card.TLabel", wraplength=540).pack(anchor="w")
        screens = self.card(page, "TELEVIZE")
        screens.pack(fill="x", pady=(0, 13))
        ttk.Label(screens, textvariable=self.lg, style="Card.TLabel", wraplength=540).pack(anchor="w")
        ttk.Label(screens, textvariable=self.browser_state, style="Card.TLabel").pack(anchor="w", pady=(4, 0))
        caption = self.card(page, "ŽIVÝ NÁHLED  /  ČEŠTINA")
        caption.pack(fill="both", expand=True)
        self.caption_label(caption, 22, self.dashboard_caption).pack(fill="both", expand=True)

    def caption_label(self, parent, size, variable=None):
        label = tk.Label(parent, textvariable=self.caption if variable is None else variable, bg="#12233a", fg="#fff",
                         font=(self.font, size, "bold"), justify="center", padx=12, pady=16)
        label.bind("<Configure>", lambda event: label.configure(wraplength=max(100, event.width - 24)))
        return label

    def open_preview(self):
        if self.preview is None or not self.preview.winfo_exists():
            self.preview = tk.Toplevel(self)
            self.preview.title("NEXCAP · České titulky")
            self.preview.geometry("720x240")
            self.preview.minsize(360, 140)
            self.caption_label(self.preview, 24).pack(fill="both", expand=True)
            self.preview.bind("<F11>", lambda event: self.preview.attributes(
                "-fullscreen", not self.preview.attributes("-fullscreen")))
            self.preview.bind("<Escape>", lambda event: self.preview.attributes("-fullscreen", False))
        self.preview.lift()

    def build_televisions(self, page):
        web = self.card(page, "WEBOVÝ PŘIJÍMAČ")
        web.pack(fill="x", pady=(0, 12))
        ttk.Label(web, text="Stejnou adresu otevři v prohlížeči každé TV. Funguje také v OBS.",
                  style="Card.TLabel", wraplength=530).pack(anchor="w")
        line = ttk.Frame(web, style="Card.TFrame")
        line.pack(fill="x", pady=(8, 0))
        ttk.Entry(line, textvariable=self.browser_url, state="readonly").pack(side="left", fill="x", expand=True)
        self.web_button = self.button(line, "Zapnout", self.toggle_browser, style="Accent.TButton")
        self.web_button.pack(side="left", padx=(8, 0))
        self.button(line, "Kopírovat", self.copy_url).pack(side="left", padx=(8, 0))
        options = ttk.Frame(web, style="Card.TFrame")
        options.pack(fill="x", pady=(6, 0))
        ttk.Label(options, textvariable=self.browser_state, style="Card.TLabel").pack(side="left")
        self.button(options, "Kopírovat pro OBS", lambda: self.copy_url(overlay=True)).pack(side="right")
        lan = self.card(page, "PŘÍMÝ PŘÍJEM LG")
        lan.pack(fill="both", expand=True)
        ttk.Label(lan, text="IPv4 adresy odděl čárkou. Pokud používáš webový příjem, pole může zůstat prázdné.",
                  style="Card.TLabel", wraplength=530).pack(anchor="w")
        ttk.Entry(lan, textvariable=self.ip).pack(fill="x", pady=(7, 9))
        self.subtitle = tk.Text(lan, height=2, bg="#172b43", fg="#ebf4ff",
                                insertbackground="#ebf4ff", relief="flat",
                                font=(self.font, 11), padx=10, pady=6, wrap="word")
        self.subtitle.insert("1.0", "Zkouška českých titulků · NEXCAP")
        self.subtitle.pack(fill="x")
        buttons = ttk.Frame(lan, style="Card.TFrame")
        buttons.pack(fill="x", pady=(8, 0))
        self.probe_button = self.button(buttons, "Ověřit LG", self.probe)
        self.probe_button.pack(side="left", padx=(0, 8))
        self.send_button = self.button(buttons, "Odeslat zkušební titulek", self.send)
        self.send_button.pack(side="left")
        ttk.Label(lan, textvariable=self.lg, style="Card.TLabel", wraplength=530).pack(anchor="w", pady=(7, 0))

    def build_settings(self, page):
        settings = ttk.Frame(page)
        settings.pack(fill="x")
        settings.columnconfigure(1, weight=1)
        for row, (label, variable, masked) in enumerate((
            ("IPv4 konzole PS5", self.console, False),
            ("Sekundární PSN Account ID", self.account, True),
            ("Kód propojení PS5", self.pin, True),
            ("LibreTranslate URL", self.endpoint, False),
        )):
            ttk.Label(settings, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
            ttk.Entry(settings, textvariable=variable, show="•" if masked else "").grid(
                row=row, column=1, sticky="ew", pady=5)
        ttk.Label(page, text="Prázdná URL použije místní anglicko-český model.", style="Muted.TLabel").pack(
            anchor="w", pady=(6, 14))
        actions = ttk.Frame(page)
        actions.pack(fill="x")
        self.pair_button = self.button(actions, "Spárovat PS5", self.pair, style="Accent.TButton")
        self.pair_button.pack(side="left", padx=(0, 8))
        self.video_button = self.button(actions, "Ověřit obraz", self.probe_video)
        self.video_button.pack(side="left", padx=(0, 8))
        ttk.Label(page, textvariable=self.status, style="Muted.TLabel", wraplength=530).pack(anchor="w", pady=15)

    def toggle_browser(self):
        if self.browser.server:
            self.browser.stop()
            self.browser_url.set("")
            self.browser_state.set("Webový přijímač vypnutý")
            self.web_button.configure(text="Zapnout")
            return
        try:
            self.browser.start()
        except OSError as error:
            self.browser_state.set(f"Webový přijímač: {error}")
            return
        address = "127.0.0.1"
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            try:
                destinations = tv_addresses(self.ip.get())
            except ValueError:
                destinations = ()
            try:
                connection.connect((destinations[0] if destinations else "192.0.2.1", 9))
                address = connection.getsockname()[0]
            except OSError:
                pass
        self.browser_url.set(self.browser.url(address))
        self.browser_state.set("Webový přijímač běží")
        self.web_button.configure(text="Vypnout")

    def copy_url(self, *, overlay=False):
        if self.browser_url.get():
            self.clipboard_clear()
            self.clipboard_append(self.browser_url.get() + ("?overlay=1" if overlay else ""))

    def probe(self):
        def check(value):
            results = []
            for ip in tv_addresses(value):
                try:
                    probe_receiver(ip)
                    results.append(f"{ip} dostupná")
                except OSError:
                    results.append(f"{ip} bez odpovědi")
            return " · ".join(results) or "Zadej adresu LG."
        self.run(check, self.ip.get(), target=self.lg)

    def send(self):
        def deliver(value, subtitle):
            results = []
            for ip in tv_addresses(value):
                try:
                    send_subtitle(ip, subtitle)
                    results.append(f"{ip} odesláno")
                except OSError:
                    results.append(f"{ip} chyba odesílání")
            if self.browser.server:
                self.browser.publish(subtitle)
                results.append("webový přijímač")
            return " · ".join(results) or "Přidej TV nebo zapni webový přijímač."
        self.run(deliver, self.ip.get(), self.subtitle.get("1.0", "end-1c"), target=self.lg)

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
                 self.stop_stream, self.report, self.report_lg, self.report_caption, self.region.get(), pending="Spouštím Remote Play…")

    def report(self, message):
        self.events.put((self.status.set, message))

    def report_lg(self, message):
        self.events.put((self.lg.set, message))

    def report_caption(self, message):
        self.events.put((self.show_caption, message))

    def show_caption(self, message):
        if self.caption_timeout is not None:
            self.after_cancel(self.caption_timeout)
        self.caption.set(message)
        self.dashboard_caption.set(message or "Čekám na první český titulek…")
        self.browser.publish(message)
        self.caption_timeout = self.after(6000, self.clear_caption) if message else None

    def clear_caption(self):
        self.caption_timeout = None
        self.caption.set("")
        self.dashboard_caption.set("Čekám na první český titulek…")

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

    def run(self, operation, *args, pending="Probíhá komunikace s LG…", target=None):
        for button in self.operation_buttons:
            button.state(["disabled"])
        if target is None:
            target = self.status
        target.set(pending)
        future = self.executor.submit(operation, *args)
        future.add_done_callback(lambda result: self.events.put((self.completed, result, target)))

    def completed(self, future, target):
        if target is self.status:
            self.show_caption("")
        try:
            target.set(future.result())
        except Exception as exc:
            target.set(str(exc))
        finally:
            for button in self.operation_buttons:
                button.state(["!disabled"])
            self.stop_button.state(["disabled"])

    def close(self):
        self.stop_stream.set()
        self.browser.stop()
        if self.tray:
            self.tray.stop()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.destroy()


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test-translation"]:
        from offline import offline_translator
        if offline_translator()("Follow me!") not in {"Za mnou!", "Pojď za mnou!", "Následuj mě!"}:
            raise SystemExit(1)
    else:
        App().mainloop()
