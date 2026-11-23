# SPDX-License-Identifier: AGPL-3.0-or-later
"""Opt-in subtitle display for multiple browsers on the local network."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import threading
import time

PAGE = rb"""<!doctype html><html lang="cs"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NEXCAP | Titulky</title>
<style>
html,body{height:100%;margin:0;background:#0a1120;color:#fff;font-family:Segoe UI,Arial,sans-serif}
main{position:absolute;left:6%;right:6%;bottom:12%;text-align:center}
#caption{display:inline-block;white-space:pre-wrap;overflow-wrap:break-word;padding:.45em .8em;
border-radius:.28em;background:#101927;font-size:5vw;max-width:90%}
#caption:empty{display:none}
#status{position:absolute;top:7%;left:7%;font-size:2.5vw;color:#91a5bd}
.overlay{background:transparent}.overlay #status{display:none}
</style>
<div id="status">NEXCAP &middot; p&#345;ipojuji se</div>
<main><span id="caption"></span></main>
<script>
(function(){
 var caption=document.getElementById('caption'), status=document.getElementById('status');
 if(location.search==='?overlay=1'){
   document.documentElement.className='overlay';document.body.className='overlay';
 }
 function poll(){
  var request=new XMLHttpRequest();
  request.open('GET', location.pathname+'/caption', true);
  request.timeout=2500;
  request.onloadend=function(){
   try{
    if(request.status!==200)throw Error();
    var text=JSON.parse(request.responseText).text;
    if(caption.textContent!==text)caption.textContent=text;
    status.textContent=text?'':'NEXCAP | \u010cek\u00e1m na titulky';
   }catch(error){caption.textContent='';status.textContent='NEXCAP | obnovuji spojen\u00ed';}
   setTimeout(poll,350);
  };
  request.send();
 }
 poll();
})();
</script></html>"""


class BrowserOutput:
    def __init__(self):
        self.server = None
        self.token = ""
        self.text = ""
        self.expires = 0.0
        self.lock = threading.Lock()

    def publish(self, text, duration=6):
        with self.lock:
            self.text = text
            self.expires = time.monotonic() + duration

    def current(self):
        with self.lock:
            return self.text if time.monotonic() < self.expires else ""

    def start(self, host="0.0.0.0", port=0):
        if self.server:
            return
        self.token = secrets.token_urlsafe(18)
        route = "/" + self.token
        output = self

        class Handler(BaseHTTPRequestHandler):
            timeout = 3

            def log_message(self, *args):
                pass

            def do_GET(self):
                path = self.path.partition("?")[0]
                if path == route:
                    content, kind = PAGE, "text/html; charset=utf-8"
                elif path == route + "/caption":
                    content = json.dumps({"text": output.current()}).encode("utf-8")
                    kind = "application/json"
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

        self.server = ThreadingHTTPServer((host, port), Handler)
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .1}, daemon=True).start()

    def url(self, address):
        return f"http://{address}:{self.server.server_port}/{self.token}"

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        self.publish("")
