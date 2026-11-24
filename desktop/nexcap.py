# SPDX-License-Identifier: AGPL-3.0-or-later
"""NEXCAP Desktop user interface for LG transport diagnostics."""

from concurrent.futures import ThreadPoolExecutor
import ipaddress
import json
import os
from pathlib import Path
from queue import Empty, SimpleQueue
import socket
import shutil
import sys
from threading import Event, Thread
from tempfile import NamedTemporaryFile
import tkinter as tk
from tkinter import ttk

from capture import DEFAULT_REGION, OCR_REGIONS, pair_console, stream_console, test_console, tv_addresses
from transport import discover_lg, probe_receiver, send_subtitle
from tv_output import BrowserOutput


TV_PROFILES = {
    "LG · webOS": "Na TV otevři Webový prohlížeč. Pokud už máš doplněk PlayCaption, můžeš použít přímý příjem LG.",
    "Samsung · Tizen": "Na TV otevři aplikaci Internet a zadej zobrazenou adresu včetně http://.",
    "Sony / Google TV / Android TV": "Otevři nainstalovaný prohlížeč TV. Pokud chybí, použij telefon, tablet nebo zařízení s prohlížečem připojené přes HDMI.",
    "Jiná TV / telefon / tablet": "Otevři adresu v prohlížeči zařízení ve stejné síti jako PC.",
}


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
        self.ip = tk.StringVar()
        self.tv_profile = tk.StringVar(value="Jiná TV / telefon / tablet")
        self.tv_mode = tk.StringVar(value="web")
        self.tv_help = tk.StringVar()
        self.pc_address = tk.StringVar()
        self.configured = False
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
        self.load_preferences()
        self.build_interface()
        self.after(125, self.read_events)
        self.after(500, self.refresh_browser_state)

    def preferences_path(self):
        if sys.platform == "win32" and "LOCALAPPDATA" in os.environ:
            return Path(os.environ["LOCALAPPDATA"]) / "PetrDevelop" / "NEXCAP" / "display-settings.json"
        return None

    def load_preferences(self):
        path = self.preferences_path()
        if path is None:
            return
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(settings, dict):
            return
        self.configured = bool(settings.get("tv_profile"))
        for name, field in (("console", self.console), ("televisions", self.ip)):
            value = settings.get(name)
            if isinstance(value, str):
                field.set(value)
        if isinstance(settings.get("ocr_region"), str) and settings["ocr_region"] in OCR_REGIONS:
            self.region.set(settings["ocr_region"])

        profile = settings.get("tv_profile")
        if isinstance(profile, str) and profile in TV_PROFILES:
            self.tv_profile.set(profile)
        # Preserve the direct target for existing installations created by 0.3.
        if self.ip.get() and settings.get("tv_mode", "lg") == "lg":
            self.tv_mode.set("lg")

    def save_preferences(self):
        path = self.preferences_path()
        if path is None:
            return
        temporary = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(mode="w", dir=path.parent, delete=False, encoding="utf-8") as file:
                temporary = Path(file.name)
                json.dump({"console": self.console.get(), "televisions": self.ip.get(),
                           "ocr_region": self.region.get(), "tv_profile": self.tv_profile.get(),
                           "tv_mode": self.tv_mode.get()}, file, ensure_ascii=False)
            temporary.replace(path)
        except OSError:
            pass
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

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
        style.map("TEntry", fieldbackground=[("readonly", "#172b43")])
        style.configure("TCombobox", fieldbackground="#172b43", background="#1b324c",
                        foreground="#ebf4ff", arrowcolor="#7be8ff", bordercolor="#2a4561",
                        padding=6)
        style.map("TCombobox", fieldbackground=[("readonly", "#172b43")],
                  foreground=[("readonly", "#ebf4ff")])
        self.option_add("*TCombobox*Listbox.background", "#172b43")
        self.option_add("*TCombobox*Listbox.foreground", "#ebf4ff")
        self.option_add("*TCombobox*Listbox.selectBackground", "#26516a")
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
            ("Televize", "Připojení televize", "Vyber značku a vyzkoušej připojení.", self.build_televisions),
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
        self.operation_buttons = (self.probe_button, self.find_button, self.send_button,
                                  self.pair_button, self.video_button, self.start_button)
        self.navigate("Přehled" if self.configured else "Televize")

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
        device = self.card(page, "ZNAČKA NEBO SYSTÉM TV")
        device.pack(fill="x", pady=(0, 12))
        selector = ttk.Combobox(device, textvariable=self.tv_profile, state="readonly",
                                values=tuple(TV_PROFILES))
        selector.pack(fill="x")
        selector.bind("<<ComboboxSelected>>", self.select_profile)
        ttk.Label(device, textvariable=self.tv_help, style="Card.TLabel", wraplength=550).pack(
            anchor="w", pady=(7, 0))
        modes = ttk.Frame(page)
        modes.pack(fill="x", pady=(0, 10))
        ttk.Radiobutton(modes, text="Prohlížeč TV (doporučeno)", variable=self.tv_mode, value="web",
                        command=self.show_tv_mode).pack(side="left")
        self.direct_radio = ttk.Radiobutton(modes, text="Přímý příjem LG", variable=self.tv_mode,
                                           value="lg", command=self.show_tv_mode)
        self.direct_radio.pack(side="left", padx=12)

        self.web_card = web = self.card(page, "WEBOVÝ PŘIJÍMAČ")
        self.lg_card = lan = self.card(page, "PŘÍMÝ PŘÍJEM LG")
        line = ttk.Frame(web, style="Card.TFrame")
        line.pack(fill="x")
        ttk.Entry(line, textvariable=self.browser_url, state="readonly").pack(side="left", fill="x", expand=True)
        self.web_button = self.button(line, "Připravit adresu", self.toggle_browser, style="Accent.TButton")
        self.web_button.pack(side="left", padx=(8, 0))
        self.button(line, "Kopírovat", self.copy_url).pack(side="left", padx=(8, 0))
        ttk.Label(web, textvariable=self.browser_state, style="Card.TLabel", wraplength=530).pack(
            anchor="w", pady=(9, 8))
        options = ttk.Frame(web, style="Card.TFrame")
        options.pack(fill="x")
        self.button(options, "Zobrazit zkušební titulek", self.test_web).pack(side="left")
        self.button(options, "Kopírovat pro OBS", lambda: self.copy_url(overlay=True)).pack(side="right")
        manual = ttk.Frame(web, style="Card.TFrame")
        manual.pack(fill="x", pady=(11, 3))
        ttk.Label(manual, text="Náhradní IPv4 počítače", style="Card.TLabel").pack(side="left", padx=(0, 8))
        ttk.Entry(manual, textvariable=self.pc_address, width=17).pack(side="left", padx=(0, 8))
        self.button(manual, "Použít adresu", self.apply_pc_address).pack(side="left")
        ttk.Label(web, text="Pokud se stránka neotevře, ověř stejnou Wi-Fi a povol NEXCAP v bráně Windows pro soukromou síť.",
                  style="Card.TLabel", wraplength=530).pack(anchor="w", pady=(5, 0))

        ttk.Label(lan, text="Na televizoru spusť doplněk PlayCaption LG, potom vyhledej přijímač nebo zadej jeho IPv4.",
                  style="Card.TLabel", wraplength=530).pack(anchor="w")
        entry = ttk.Frame(lan, style="Card.TFrame")
        entry.pack(fill="x", pady=(8, 9))
        ttk.Entry(entry, textvariable=self.ip).pack(side="left", fill="x", expand=True)
        self.find_button = self.button(entry, "Vyhledat LG", self.find_lg, style="Accent.TButton")
        self.find_button.pack(side="left", padx=(8, 0))
        self.subtitle = tk.Text(lan, height=2, bg="#172b43", fg="#ebf4ff",
                                insertbackground="#ebf4ff", relief="flat",
                                font=(self.font, 11), padx=10, pady=6, wrap="word")
        self.subtitle.insert("1.0", "Zkouška českých titulků · NEXCAP")
        self.subtitle.pack(fill="x")
        buttons = ttk.Frame(lan, style="Card.TFrame")
        buttons.pack(fill="x", pady=(8, 0))
        self.probe_button = self.button(buttons, "Ověřit IP", self.probe)
        self.probe_button.pack(side="left", padx=(0, 8))
        self.send_button = self.button(buttons, "Odeslat zkušební titulek", self.send)
        self.send_button.pack(side="left")
        ttk.Label(lan, textvariable=self.lg, style="Card.TLabel", wraplength=530).pack(anchor="w", pady=(7, 0))
        self.show_tv_mode()

    def select_profile(self, _event=None):
        self.tv_mode.set("web")
        self.show_tv_mode()

    def show_tv_mode(self):
        self.tv_help.set(TV_PROFILES[self.tv_profile.get()])
        direct_available = self.tv_profile.get() == "LG · webOS" or self.tv_mode.get() == "lg"
        self.direct_radio.state(["!disabled" if direct_available else "disabled"])
        self.web_card.pack_forget()
        self.lg_card.pack_forget()
        card = self.lg_card if self.tv_mode.get() == "lg" else self.web_card
        card.pack(fill="x")

    def refresh_browser_state(self):
        if self.browser.server:
            if self.browser.viewer_connected():
                self.browser_state.set("Prohlížeč je připojený.")
            elif not self.browser_url.get():
                self.browser_state.set("Zadej IPv4 počítače ručně.")
            else:
                self.browser_state.set("Čekám, až otevřeš adresu v prohlížeči TV.")
        self.after(500, self.refresh_browser_state)

    def apply_pc_address(self):
        try:
            address = ipaddress.IPv4Address(self.pc_address.get().strip())
            if address.is_unspecified or address.is_multicast or address.is_reserved:
                raise ValueError()
        except ValueError:
            self.browser_state.set("Zadej platnou IPv4 adresu tohoto počítače.")
            return
        if not self.browser.server:
            self.start_browser(str(address))
        else:
            self.browser_url.set(self.browser.url(str(address)))

    def test_web(self):
        if not self.browser.server:
            self.start_browser()
        if self.browser.server:
            self.browser.publish("Vidíš tento titulek? NEXCAP je připojený.", duration=10)

    def find_lg(self):
        def scan():
            answers = discover_lg()
            if len(answers) == 1:
                address, name = next(iter(answers.items()))
                self.events.put((self.ip.set, address))
                return f"{name} nalezen na {address}. Můžeš odeslat test."
            if answers:
                return "Nalezené adresy: " + ", ".join(sorted(answers)) + ". Zadej adresu své TV."
            return "Přijímač se neozval. Zadej IPv4 ručně nebo použij prohlížeč TV."
        self.run(scan, target=self.lg, pending="Hledám přijímač LG v domácí síti…")

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
        tools = self.card(page, "PŘÍPRAVA WINDOWS")
        tools.pack(fill="x")
        self.tools_state = tk.StringVar()
        ttk.Label(tools, textvariable=self.tools_state, style="Card.TLabel", wraplength=530).pack(anchor="w")
        row = ttk.Frame(tools, style="Card.TFrame")
        row.pack(fill="x", pady=(8, 0))
        self.button(row, "Zkontrolovat nástroje", self.check_tools).pack(side="left", padx=(0, 8))
        self.button(row, "Kopírovat instalační příkazy", self.copy_install_commands).pack(side="left")
        self.check_tools()

    def check_tools(self):
        missing = [name for name in ("ffmpeg", "tesseract") if shutil.which(name) is None]
        if missing:
            self.tools_state.set("Ve Windows PATH chybí: " + ", ".join(missing) +
                                 ". Zkopíruj příkazy do PowerShellu a po instalaci znovu otevři NEXCAP.")
        else:
            self.tools_state.set("FFmpeg a Tesseract jsou v PATH. Pro OCR potřebuje Tesseract jazyk eng.")

    def copy_install_commands(self):
        self.clipboard_clear()
        self.clipboard_append("winget install --id Gyan.FFmpeg -e\n"
                              "winget install --id UB-Mannheim.TesseractOCR -e")
        self.tools_state.set("Příkazy zkopírovány. Spusť je v PowerShellu a znovu otevři NEXCAP.")

    def toggle_browser(self):
        if self.browser.server:
            self.browser.stop()
            self.browser_url.set("")
            self.browser_state.set("Webový přijímač vypnutý")
            self.web_button.configure(text="Připravit adresu")
            return
        self.start_browser()

    def start_browser(self, address=None):
        try:
            self.browser.start()
        except OSError as error:
            self.browser_state.set(f"Webový přijímač: {error}")
            return
        if address is None:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
                try:
                    connection.connect(("192.0.2.1", 9))
                    address = connection.getsockname()[0]
                except OSError:
                    pass
        if address:
            self.pc_address.set(address)
            self.browser_url.set(self.browser.url(address))
        self.web_button.configure(text="Vypnout")
        self.browser_state.set("Čekám na připojení prohlížeče TV.")

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
        if not self.console.get().strip():
            self.status.set("Vyplň adresu PS5 a ověř párování.")
            self.navigate("Nastavení")
            return
        if self.tv_mode.get() == "lg" and not self.ip.get().strip():
            self.lg.set("Vyhledej LG nebo zadej její IPv4 adresu.")
            self.navigate("Televize")
            return
        self.stop_stream.clear()
        self.stop_button.state(["!disabled"])
        self.run(stream_console, self.console.get(), self.ip.get() if self.tv_mode.get() == "lg" else "", self.endpoint.get(),
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
        self.save_preferences()
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
