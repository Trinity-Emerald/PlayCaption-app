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
main{position:absolute;left:8%;right:8%;bottom:6%;text-align:center}
.panel{display:inline-block;white-space:pre-wrap;overflow-wrap:break-word;padding:.42em .7em;
border-radius:.26em;background:rgba(10,17,32,.88);max-width:100%;max-height:30vh;overflow:hidden}
.panel:empty{display:none}
#caption{font-size:4vw}
#phone,#mission{position:absolute;font-size:2.35vw;max-width:35%}
#phone{left:4%;top:38%;border-left:.2em solid #68e6fa}
#mission{right:4%;top:5%;border-left:.2em solid #ffcc70}
#status{position:absolute;top:7%;left:7%;font-size:2.5vw;color:#91a5bd}
.overlay{background:transparent}.overlay #status{display:none}
</style>
<div id="status">NEXCAP &middot; p&#345;ipojuji se</div>
<main><span class="panel" id="caption"></span></main>
<aside class="panel" id="phone"></aside><aside class="panel" id="mission"></aside>
<script>
(function(){
 var status=document.getElementById('status');
 var panels={dialog:document.getElementById('caption'),phone:document.getElementById('phone'),
             mission:document.getElementById('mission')};
 function render(values){
   Object.keys(panels).forEach(function(key){
     var text=values[key]||'';
     if(panels[key].textContent!==text)panels[key].textContent=text;
   });
 }
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
    var data=JSON.parse(request.responseText), values=data.panels||{dialog:data.text};
    render(values);
    status.textContent=(values.dialog||values.phone||values.mission)?'':'NEXCAP | \u010cek\u00e1m na titulky';
   }catch(error){render({});status.textContent='NEXCAP | obnovuji spojen\u00ed';}
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
        self.panels = {}
        self.lock = threading.Lock()
        self.last_viewer = 0.0

    def publish(self, text, duration=6):
        with self.lock:
            self.panels = {"dialog": (text, time.monotonic() + duration)} if text else {}

    def publish_panels(self, updates, duration=6):
        with self.lock:
            expires = time.monotonic() + duration
            for key, text in updates.items():
                if key in ("dialog", "phone", "mission"):
                    self.panels[key] = (text, expires)

    def current_panels(self):
        with self.lock:
            now = time.monotonic()
            return {key: text for key, (text, expires) in self.panels.items()
                    if text and now < expires}

    def current(self):
        return self.current_panels().get("dialog", "")

    def viewer_connected(self):
        with self.lock:
            return self.last_viewer > 0 and time.monotonic() - self.last_viewer < 5

    def start(self, host="0.0.0.0", port=0):
        if self.server:
            return
        self.token = secrets.token_hex(8)
        self.last_viewer = 0.0
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
                    with output.lock:
                        if output.token == route[1:]:
                            output.last_viewer = time.monotonic()
                    panels = output.current_panels()
                    content = json.dumps({"text": panels.get("dialog", ""), "panels": panels}).encode("utf-8")
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
        with self.lock:
            self.token = ""
            self.last_viewer = 0.0
        self.publish("")
