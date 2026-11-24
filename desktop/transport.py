# SPDX-License-Identifier: AGPL-3.0-or-later
"""UDP subtitle and receiver discovery protocol shared with LG webOS."""

import ipaddress
import re
import secrets
import socket
import time
from threading import Lock

PORT = 41989

_id_lock = Lock()
_last_id = 0


def make_packet(text: str, duration_ms: int = 6000) -> bytes:
    global _last_id
    clean = (text.replace("\\", "\\\\").replace("\t", " ")
             .replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n"))
    if not clean.strip() or not text.strip():
        raise ValueError("Zadej text titulku.")
    if len(clean.encode("utf-16-le")) // 2 > 4096:
        raise ValueError("Titulek je příliš dlouhý.")
    if type(duration_ms) is not int or not 1 <= duration_ms <= 60000:
        raise ValueError("Délka titulku musí být 1 až 60 000 ms.")
    with _id_lock:
        _last_id = max(_last_id + 1, time.time_ns() // 1_000_000)
        packet_id = _last_id
    packet = f"PCT1\t{packet_id}\t{duration_ms}\t{clean}\t".encode("utf-8")
    if len(packet) > 8192:
        raise ValueError("Titulek překračuje velikost UDP paketu přijímače.")
    return packet


def _endpoint(ip: str) -> tuple[str, int]:
    try:
        address = ipaddress.IPv4Address(ip.strip())
    except ipaddress.AddressValueError as exc:
        raise ValueError("Zadej platnou IPv4 adresu LG televize.") from exc
    if address.is_unspecified or address.is_multicast or address.is_reserved:
        raise ValueError("Zadej individuální IPv4 adresu LG televize.")
    return str(address), PORT


def send_subtitle(ip: str, text: str, duration_ms: int = 6000) -> None:
    endpoint = _endpoint(ip)
    packet = make_packet(text, duration_ms)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(packet, endpoint)


def _receiver_name(packet, nonce):
    fields = packet.decode("utf-8", errors="replace").split("\t")
    if (len(fields) == 5 and fields[0] == "PLAYCAPTION_TV"
            and re.fullmatch(r"lg-[0-9a-f]{12}", fields[1])
            and fields[2] and fields[4] == nonce):
        return fields[2]
    return None


def discover_lg(timeout=1.4):
    nonce = secrets.token_hex(16)
    query = f"PLAYCAPTION_FIND\t{nonce}".encode("ascii")
    results = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(query, ("255.255.255.255", PORT))
        deadline = time.monotonic() + timeout
        while (remaining := deadline - time.monotonic()) > 0:
            sock.settimeout(remaining)
            try:
                packet, (address, port) = sock.recvfrom(8192)
            except TimeoutError:
                break
            name = _receiver_name(packet, nonce)
            if port == PORT and name:
                results[address] = name
    return results


def probe_receiver(ip: str, timeout: float = 1.0, attempts: int = 3) -> str:
    endpoint = _endpoint(ip)
    nonce = secrets.token_hex(16)
    query = f"PLAYCAPTION_FIND\t{nonce}".encode("ascii")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect(endpoint)
        for _ in range(attempts):
            deadline = time.monotonic() + timeout
            sock.send(query)
            while (remaining := deadline - time.monotonic()) > 0:
                sock.settimeout(remaining)
                try:
                    packet = sock.recv(8192)
                except (TimeoutError, ConnectionResetError, ConnectionRefusedError):
                    break
                name = _receiver_name(packet, nonce)
                if name:
                    return name
    raise TimeoutError("LG přijímač neodpověděl na UDP portu 41989.")
