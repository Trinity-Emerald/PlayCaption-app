# SPDX-License-Identifier: AGPL-3.0-or-later
"""Windows DPAPI storage, scoped to the current Windows user and PS5 address."""

import ctypes as ct
from ctypes import wintypes as wt
import os
from pathlib import Path
import tempfile


class Blob(ct.Structure):
    _fields_ = [("size", wt.DWORD), ("data", ct.c_void_p)]


def protect(data: bytes, host: str, *, decrypt: bool = False) -> bytes:
    if os.name != "nt":
        raise OSError("Úložiště spárování vyžaduje Windows.")
    crypt = ct.WinDLL("crypt32", use_last_error=True)
    kernel = ct.WinDLL("kernel32")
    transform = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    transform.argtypes = [ct.POINTER(Blob), ct.c_void_p, ct.POINTER(Blob),
                          ct.c_void_p, ct.c_void_p, wt.DWORD, ct.POINTER(Blob)]
    transform.restype = wt.BOOL
    kernel.LocalFree.argtypes = [ct.c_void_p]
    kernel.LocalFree.restype = ct.c_void_p
    input_buffer = ct.create_string_buffer(data)
    entropy = ct.create_string_buffer(f"NEXCAP Remote Play v1/{host}".encode())
    source = Blob(len(data), ct.addressof(input_buffer))
    extra = Blob(len(entropy) - 1, ct.addressof(entropy))
    result = Blob()
    try:
        if not transform(ct.byref(source), None, ct.byref(extra), None, None, 1, ct.byref(result)):
            raise ct.WinError(ct.get_last_error())
        return ct.string_at(result.data, result.size)
    finally:
        ct.memset(ct.addressof(input_buffer), 0, len(input_buffer))
        if result.data:
            ct.memset(result.data, 0, result.size)
            kernel.LocalFree(result.data)


def key_path(host: str) -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "PetrDevelop" / "NEXCAP" / f"{host}.dpapi"


def save_keys(host: str, keys: bytes) -> None:
    path = key_path(host)
    path.parent.mkdir(parents=True, exist_ok=True)
    encrypted = protect(keys, host)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(encrypted)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_keys(host: str) -> bytes:
    if os.name != "nt":
        raise OSError("Úložiště spárování vyžaduje Windows.")
    try:
        encrypted = key_path(host).read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("Tuto adresu PS5 nejdřív spáruj.") from exc
    keys = protect(encrypted, host, decrypt=True)
    if len(keys) != 32:
        raise ValueError("Uložené klíče Remote Play jsou poškozené.")
    return keys
