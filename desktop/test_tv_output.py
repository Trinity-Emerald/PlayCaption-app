# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import urlopen
import unittest

from capture import tv_addresses
from tv_output import BrowserOutput


class TelevisionOutputTest(unittest.TestCase):
    def test_two_viewers_receive_the_same_caption_and_expiry(self):
        output = BrowserOutput()
        output.start("127.0.0.1")
        self.addCleanup(output.stop)
        url = output.url("127.0.0.1")
        self.assertIn(b"textContent", urlopen(url + "?overlay=1", timeout=2).read())

        text = "Český titulek\n<b>zůstane text</b>"
        output.publish(text)
        with ThreadPoolExecutor(max_workers=2) as pool:
            def read(_):
                with urlopen(url + "/caption", timeout=2) as response:
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    return json.load(response)["text"]

            self.assertEqual(list(pool.map(read, range(2))), [text, text])
            output.publish(text, duration=0)
            self.assertEqual(read(0), "")

        with self.assertRaises(HTTPError) as missing:
            urlopen(url.rsplit("/", 1)[0] + "/caption", timeout=2)
        self.assertEqual(missing.exception.code, 404)

    def test_multiple_direct_tv_addresses_and_browser_only(self):
        self.assertEqual(tv_addresses("192.168.0.17, 192.168.0.19, 192.168.0.17"),
                         ("192.168.0.17", "192.168.0.19"))
        self.assertEqual(tv_addresses("  "), ())
        with self.assertRaises(ValueError):
            tv_addresses("192.168.0.17, chybna")


if __name__ == "__main__":
    unittest.main()
