# SPDX-License-Identifier: AGPL-3.0-or-later
"""Silent video capture, English OCR, and EN→CS translation."""

import base64
import binascii
from contextlib import contextmanager
from difflib import SequenceMatcher
import ipaddress
import json
import os
from pathlib import Path
from queue import Empty, Full, Queue
import re
import shutil
import subprocess as sp
import sys
from threading import Event, Thread
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from credentials import load_keys, save_keys
from offline import offline_translator
from transport import probe_receiver, send_subtitle

WINDOW = getattr(sp, "CREATE_NO_WINDOW", 0)
APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
WIDTH, HEIGHT = 1280, 256
SIZE = WIDTH * HEIGHT
PGM_HEADER = f"P5\n{WIDTH} {HEIGHT}\n255\n".encode("ascii")


def console_address(value):
    try:
        host = ipaddress.IPv4Address(value.strip())
    except ipaddress.AddressValueError as exc:
        raise ValueError("Zadej platnou IPv4 adresu PS5.") from exc
    if host.is_unspecified or host.is_multicast or host.is_reserved:
        raise ValueError("Zadej individuální IPv4 adresu PS5.")
    return str(host)


def helper_path():
    name = "nexcap-remote.exe" if os.name == "nt" else "nexcap-remote"
    path = APP_DIR / "native" / name
    if not path.is_file():
        raise ValueError(f"Chybí nativní součást {name}.")
    return str(path)


def pair_console(address, account, pin):
    host = console_address(address)
    try:
        account_id = base64.b64decode(account.strip(), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("PSN Account ID musí být platné Base64.") from exc
    if len(account_id) != 8 or not re.fullmatch(r"[0-9]{8}", pin):
        raise ValueError("Použij osmibajtové PSN Account ID v Base64 a osmimístný kód PS5.")
    result = sp.run([helper_path(), "pair", host], input=account_id + pin.encode("ascii"),
                    capture_output=True, timeout=30, creationflags=WINDOW, check=False)
    if result.returncode or len(result.stdout) != 32:
        raise ValueError("Párování PS5 selhalo. Ověř IP, sekundární účet a nový kód Remote Play.")
    save_keys(host, result.stdout)
    return "PS5 spárována. Klíče jsou uložené pro tento účet Windows."


def translation_url(value):
    value = value.strip()
    parsed = urlsplit(value)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if not parsed.hostname or parsed.username or parsed.password or parsed.fragment or (
            parsed.scheme != "https" and not (local and parsed.scheme == "http")):
        raise ValueError("Zadej HTTPS adresu LibreTranslate /translate nebo lokální HTTP adresu.")
    return value


def translate(url, text):
    data = json.dumps({"q": text, "source": "en", "target": "cs", "format": "text"}).encode()
    request = Request(url, data=data, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        result = json.loads(response.read(65536))
    translated = result.get("translatedText") if isinstance(result, dict) else None
    if not isinstance(translated, str) or not translated.strip():
        raise ValueError("LibreTranslate vrátil prázdný překlad.")
    return translated.strip()


def decoder_command(ffmpeg):
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-threads", "1",
            "-probesize", "32768", "-analyzeduration", "100000", "-f", "h264", "-i", "pipe:0",
            "-an", "-vf", f"fps=4,scale={WIDTH}:720,crop={WIDTH}:{HEIGHT}:0:440,format=gray",
            "-threads", "1", "-pix_fmt", "gray", "-f", "rawvideo", "pipe:1"]


def recognize(tesseract, frame):
    result = sp.run([tesseract, "stdin", "stdout", "-l", "eng", "--psm", "6", "tsv"],
                    input=PGM_HEADER + frame, capture_output=True, timeout=4,
                    creationflags=WINDOW, check=False)
    if result.returncode:
        raise ValueError("Tesseract OCR selhal. Zkontroluj dostupnost modelu eng.")
    lines = {}
    for row in result.stdout.decode("utf-8", errors="replace").splitlines()[1:]:
        columns = row.split("\t", 11)
        if len(columns) == 12 and columns[0] == "5" and columns[11].strip():
            if float(columns[10]) >= 55:
                lines.setdefault(tuple(columns[1:5]), []).append(columns[11].strip())
    return "\n".join(" ".join(words) for words in lines.values())[:500]


@contextmanager
def child(command, **kwargs):
    process = sp.Popen(command, creationflags=WINDOW, **kwargs)
    try:
        yield process
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except sp.TimeoutExpired:
                process.kill()
                process.wait()
        for pipe in (process.stdin, process.stdout, process.stderr):
            if pipe is not None:
                pipe.close()


def read_frames(pipe, frames):
    while len(frame := pipe.read(SIZE)) == SIZE:
        try:
            frames.put_nowait(frame)
        except Full:
            try:
                frames.get_nowait()
            except Empty:
                pass
            frames.put_nowait(frame)


def process_frames(decoder, stop, tesseract, translate_text, tv, status, *, first_only=False, failed=None, local_caption=None):
    frames = Queue(maxsize=1)
    reader = Thread(target=read_frames, args=(decoder.stdout, frames), daemon=True)
    reader.start()
    last_frame = time.monotonic()
    last_text = ""
    czech = ""
    last_sent = 0.0
    previous = ""
    first_frame = True
    while not stop.is_set() and not (failed and failed.is_set()):
        try:
            frame = frames.get(timeout=0.25)
        except Empty:
            if not reader.is_alive() or time.monotonic() - last_frame > 15:
                return
            continue
        if first_only:
            return True
        if first_frame:
            first_frame = False
            status("Přijímám obraz PS5. Hledám anglický titulek…")
        last_frame = time.monotonic()
        text = recognize(tesseract, frame)
        if len(text) < 4 or SequenceMatcher(None, text, previous).ratio() < 0.85:
            previous = text
            continue
        same = SequenceMatcher(None, last_text, text).ratio() >= 0.9
        if same and last_frame - last_sent < 3.5:
            continue
        if stop.is_set():
            return
        if not same:
            try:
                czech = translate_text(text)
            except (OSError, ValueError, RuntimeError) as exc:
                status(f"Překlad se nepodařil ({type(exc).__name__}). Zkouším znovu…")
                if stop.wait(3):
                    return
                continue
            last_text = text
        if stop.is_set():
            return
        if not czech:
            continue
        if local_caption is not None:
            local_caption(czech)
        try:
            send_subtitle(tv, czech)
        except OSError as exc:
            status(f"Překlad hotov, odeslání na LG selhalo ({exc}).")
            last_sent = time.monotonic() - 1.5
            continue
        last_sent = time.monotonic()
        status("Český titulek odeslán přes UDP.")


def test_console(address, stop, status):
    return stream_console(address, None, None, stop, status)


def stream_console(address, tv, endpoint, stop, status, lg_status=None, local_caption=None):
    host = console_address(address)
    test_only = endpoint is None
    translate_text = None
    if not test_only:
        tv = console_address(tv)
        if endpoint.strip():
            url = translation_url(endpoint)
            translate_text = lambda text: translate(url, text)
    keys = load_keys(host)
    helper = helper_path()
    ffmpeg = shutil.which("ffmpeg")
    tesseract = shutil.which("tesseract")
    if not ffmpeg:
        raise ValueError("Přidej FFmpeg do Windows PATH.")
    if not test_only and not tesseract:
        raise ValueError("Přidej Tesseract OCR s modelem eng do Windows PATH.")
    if not test_only and translate_text is None:
        status("Načítám místní překlad EN → CS…")
        translate_text = offline_translator()
    if lg_status is None:
        return run_sessions(host, tv, keys, helper, ffmpeg, tesseract, translate_text, stop, status, test_only, local_caption)
    finished = Event()

    def monitor_lg():
        while not finished.is_set():
            try:
                name = probe_receiver(tv, timeout=0.7, attempts=1)
                lg_status(f"{name} odpovídá na UDP.")
            except OSError:
                lg_status("LG neodpovídá. Opakuji kontrolu UDP.")
            finished.wait(3)

    monitor = Thread(target=monitor_lg, daemon=True)
    monitor.start()
    try:
        return run_sessions(host, tv, keys, helper, ffmpeg, tesseract, translate_text, stop, status, test_only, local_caption)
    finally:
        finished.set()
        monitor.join()
        lg_status("Kontrola LG zastavena.")


def run_sessions(host, tv, keys, helper, ffmpeg, tesseract, translate_text, stop, status, test_only, local_caption):
    delay = 2
    while not stop.is_set():
        status(f"Připojuji se k PS5 na {host}…")
        detail = []
        pin_required = Event()
        opened = time.monotonic()
        with child([helper, "stream", host], stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.PIPE) as remote:
            def diagnostics(pipe):
                for line in pipe:
                    message = line.decode(errors="replace").strip()
                    detail[:] = [message]
                    if message == "console-login-pin-required":
                        pin_required.set()
                    if message == "connected":
                        status("PS5 připojena. Čekám na video…")

            logger = Thread(target=diagnostics, args=(remote.stderr,), daemon=True)
            logger.start()
            try:
                remote.stdin.write(keys)
                remote.stdin.close()
                with child(decoder_command(ffmpeg), stdin=remote.stdout, stdout=sp.PIPE,
                           stderr=sp.DEVNULL) as decoder:
                    remote.stdout.close()
                    if process_frames(decoder, stop, tesseract, translate_text, tv, status,
                                      first_only=test_only, failed=pin_required, local_caption=local_caption):
                        return "Test PS5 prošel. NEXCAP přijal a dekódoval snímek videa."
            except BrokenPipeError:
                pass
            finally:
                if remote.poll() is None:
                    remote.terminate()
                logger.join(timeout=2)
        if stop.is_set():
            break
        if pin_required.is_set():
            raise ValueError("PS5 vyžaduje přihlašovací PIN uživatele.")
        if time.monotonic() - opened >= 60:
            delay = 2
        reason = detail[-1] if detail else "video nedorazilo"
        if test_only:
            raise ValueError(f"Test videa PS5 selhal ({reason}).")
        status(f"Remote Play se přerušilo ({reason}). Další pokus za {delay} s.")
        stop.wait(delay)
        delay = min(30, delay * 2)
    return "Remote Play zastaveno."
