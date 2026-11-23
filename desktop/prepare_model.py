# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stage the pinned redistributable Argos model for the Windows installer."""

import hashlib
from pathlib import Path
import shutil
import sys
from zipfile import ZipFile

URL = "https://argos-net.com/v1/translate-en_cs-1_9_6.argosmodel"
DIGEST = "f2f5b93fc5a5aa3aa6bece99e0fa9f80487bb9a2ea4e0c3def58d6a4af37c81f"
ROOT = "translate-en_cs-1_9_6/"
FILES = ("bpe.model", "metadata.json", "README.md", "model/config.json",
         "model/shared_vocabulary.json", "model/model.bin")


def stage(archive, target):
    with archive.open("rb") as data:
        if hashlib.file_digest(data, "sha256").hexdigest() != DIGEST:
            raise ValueError("Kontrolní součet modelu EN → CS nesouhlasí.")
    with ZipFile(archive) as source:
        for filename in FILES:
            path = target / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            with source.open(ROOT + filename) as input_file, path.open("wb") as output:
                shutil.copyfileobj(input_file, output)
    (target / "SOURCE.txt").write_text(
        f"Argos Translate EN-CS 1.9.6, derived from OPUS-MT.\n"
        f"Source: {URL}\nSHA256: {DIGEST}\n"
        "Original model license: https://creativecommons.org/licenses/by/4.0/\n"
        "The model weights are unchanged. The optional Stanza tokenizer is omitted.\n", encoding="utf-8")


if __name__ == "__main__":
    desktop = Path(__file__).resolve().parent
    archive = Path(sys.argv[1]) if len(sys.argv) == 2 else desktop / "models" / "translate-en_cs-1_9_6.argosmodel"
    stage(archive, desktop / "translate-en-cs")
