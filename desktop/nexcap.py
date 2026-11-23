# SPDX-License-Identifier: AGPL-3.0-or-later
"""NEXCAP Desktop: Windows-to-LG subtitle transport test (no PS5 capture yet)."""
import ipaddress
import socket
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

PORT = 41989

def make_packet(text: str, duration_ms: int = 6000) -> bytes:
    clean = text.replace("\\", "\\\\").replace("\t", " ").replace("\r", " ").replace("\n", "\\n")
    if not clean.strip():
        raise ValueError("Zadej text titulku.")
    if len(clean.encode("utf-8")) > 4096:
        raise ValueError("Titulek je příliš dlouhý.")
    packet = f"PCT1\t{int(time.time() * 1000)}\t{duration_ms}\t{clean}\t"
    return packet.encode("utf-8")

def send_subtitle(ip: str, text: str) -> None:
    address = ipaddress.ip_address(ip.strip())
    if address.version != 4 or not address.is_private:
        raise ValueError("Použij soukromou IPv4 adresu LG televize v domácí síti.")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(make_packet(text), (str(address), PORT))

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NEXCAP Desktop · PetrDevelop")
        self.geometry("570x330")
        self.minsize(520, 300)
        self.configure(bg="#101018")
        self.ip = tk.StringVar(value="192.168.0.17")
        self.subtitle = tk.StringVar(value="Test NEXCAP Desktop – české titulky fungují!")
        self.status = tk.StringVar(value="Připraveno k testu LG přijímače.")
        root = ttk.Frame(self, padding=24)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="NEXCAP Desktop", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(root, text="by PetrDevelop  •  test přenosu titulků na LG webOS").pack(anchor="w", pady=(0, 18))
        ttk.Label(root, text="IP adresa LG televize").pack(anchor="w")
        ttk.Entry(root, textvariable=self.ip).pack(fill="x", pady=(3, 12))
        ttk.Label(root, text="Testovací český titulek").pack(anchor="w")
        ttk.Entry(root, textvariable=self.subtitle).pack(fill="x", pady=(3, 14))
        ttk.Button(root, text="Odeslat testovací titulek na LG", command=self.send).pack(fill="x")
        ttk.Label(root, textvariable=self.status, wraplength=490).pack(anchor="w", pady=(14, 0))
        ttk.Label(root, text="PS5 Remote Play, OCR a překlad: zatím nejsou ve Windows verzi implementované.", wraplength=490).pack(anchor="w", pady=(12, 0))
    def send(self):
        ip, subtitle = self.ip.get(), self.subtitle.get()
        def worker():
            try:
                send_subtitle(ip, subtitle)
                self.after(0, lambda: self.status.set("UDP titulek odeslán. Zobrazení ověř na LG (přijímač musí běžet)."))
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("NEXCAP Desktop", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

if __name__ == "__main__":
    App().mainloop()
