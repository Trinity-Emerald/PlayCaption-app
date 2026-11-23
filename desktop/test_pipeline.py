# SPDX-License-Identifier: AGPL-3.0-or-later
"""Integration test requiring FFmpeg, Tesseract eng and Pillow."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
from threading import Event, Thread

from PIL import Image, ImageDraw, ImageFont

from capture import child, decoder_command, process_frames, translate
from transport import PORT


class TranslationFixture(BaseHTTPRequestHandler):
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if request != {"q": "Follow me!", "source": "en", "target": "cs", "format": "text"}:
            self.send_error(400)
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"translatedText": "Pojď za mnou!"}).encode())

    def log_message(self, *args):
        pass


def main():
    ffmpeg = shutil.which("ffmpeg")
    tesseract = shutil.which("tesseract")
    assert ffmpeg and tesseract
    frame = Image.new("RGB", (1280, 720), "black")
    ImageDraw.Draw(frame).text((465, 586), "Follow me!", fill="white",
                              font=ImageFont.load_default(size=52))
    with tempfile.TemporaryDirectory() as folder:
        image = Path(folder) / "frame.png"
        video = Path(folder) / "sample.h264"
        frame.save(image)
        subprocess.run([ffmpeg, "-v", "error", "-loop", "1", "-i", str(image), "-t", "3",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-f", "h264", str(video)],
                       check=True, timeout=15)
        with (HTTPServer(("127.0.0.1", 0), TranslationFixture) as translator,
              socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as tv,
              video.open("rb") as source,
              child(decoder_command(ffmpeg), stdin=source, stdout=subprocess.PIPE) as decoder):
            tv.bind(("127.0.0.1", PORT))
            tv.settimeout(12)
            worker = Thread(target=translator.serve_forever, daemon=True)
            worker.start()
            endpoint = f"http://127.0.0.1:{translator.server_port}/translate"
            stop = Event()
            pipeline = Thread(target=process_frames, args=(
                decoder, stop, tesseract, lambda text: translate(endpoint, text), "127.0.0.1", print))
            pipeline.start()
            try:
                data, _ = tv.recvfrom(8192)
                assert data.decode().split("\t")[2:] == ["6000", "Pojď za mnou!", ""]
            finally:
                stop.set()
                pipeline.join()
                translator.shutdown()
                worker.join()


if __name__ == "__main__":
    main()
