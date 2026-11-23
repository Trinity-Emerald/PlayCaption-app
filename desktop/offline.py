# SPDX-License-Identifier: AGPL-3.0-or-later
"""Local English-to-Czech translation via the Argos OPUS-MT package."""

from pathlib import Path
import sys


def offline_translator():
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "translate-en-cs"
    if not (root / "model" / "model.bin").is_file():
        raise ValueError("Chybí místní model EN → CS. Použij instalační balíček NEXCAP.")
    import ctranslate2
    from sacremoses import MosesDetokenizer, MosesPunctNormalizer, MosesTokenizer
    from subword_nmt.apply_bpe import BPE

    engine = ctranslate2.Translator(str(root / "model"), device="cpu", inter_threads=1, intra_threads=2)
    english = MosesTokenizer("en")
    normalize = MosesPunctNormalizer("en")
    czech = MosesDetokenizer("cs")
    with (root / "bpe.model").open(encoding="utf-8") as codes:
        bpe = BPE(codes)

    def translate(text):
        translated = []
        for line in text.splitlines():
            words = bpe.segment_tokens(english.tokenize(normalize.normalize(line)))
            if not words:
                continue
            tokens = engine.translate_batch([words], beam_size=4)[0].hypotheses[0]
            translated.append(czech.detokenize(" ".join(tokens).replace("@@ ", "").split()))
        return "\n".join(translated)

    return translate
