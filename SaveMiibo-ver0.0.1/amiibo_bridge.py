#!/usr/bin/env python3
"""PC companion for Amiibo Bridge. Pair once by scanning a PC-displayed QR code."""
import argparse, base64, json, secrets, socket, webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import urllib.request
CONFIG = Path.home() / ".config" / "amiibo-bridge" / "config.json"
def load_config():
    if not CONFIG.exists(): raise SystemExit("Not paired yet. Run: python3 pc/amiibo_bridge.py pair")
    return json.loads(CONFIG.read_text())
def request(host, token, payload=None):
    url = host.rstrip('/') + ('/status' if payload is None else '/job')
    data = None if payload is None else json.dumps(payload).encode()
    headers = {} if payload is None else {'Content-Type':'application/json','X-Bridge-Token':token}
    req=urllib.request.Request(url,data=data,headers=headers)
    with urllib.request.urlopen(req,timeout=75) as response: return json.loads(response.read())
def get_lan_ip():
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try: sock.connect(('192.0.2.1',80)); return sock.getsockname()[0]
    finally: sock.close()
def pair(args):
    try: import qrcode
    except ImportError: raise SystemExit("Install QR support: python3 -m pip install --user 'qrcode[pil]'")
    nonce=secrets.token_urlsafe(24); ip=args.pc_ip or get_lan_ip(); state={'paired':None}
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path!='/pair': self.send_error(404); return
            try:
                body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
                if not secrets.compare_digest(body.get('nonce',''),nonce): self.send_error(403); return
                host,token=body['phone_host'],body['token']
                if not host.startswith('http://') or len(token)<24: self.send_error(400); return
                state['paired']={'host':host,'token':token}; out=b'{"ok":true}'
                self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(out))); self.end_headers(); self.wfile.write(out)
            except Exception: self.send_error(400)
        def log_message(self,*_): pass
    server=HTTPServer(('0.0.0.0',args.port),Handler); server.timeout=1
    qrdata=json.dumps({'type':'amiibobridge-pair','callback':f'http://{ip}:{args.port}/pair','nonce':nonce})
    out=Path.home()/'amiibobridge-pair.png'; qrcode.make(qrdata).save(out)
    print(f'Pairing QR saved to {out}; opening it now.')
    webbrowser.open(out.resolve().as_uri())
    print("On your phone, tap 'Scan PC pairing QR'. Waiting (Ctrl+C to cancel)...")
    try:
        while state['paired'] is None: server.handle_request()
    except KeyboardInterrupt: print('Pairing cancelled.'); return
    finally: server.server_close()
    CONFIG.parent.mkdir(parents=True,exist_ok=True); CONFIG.write_text(json.dumps(state['paired'],indent=2)); CONFIG.chmod(0o600)
    print(f'Paired! Saved credentials securely in {CONFIG}')
    print('Next time: python3 pc/amiibo_bridge.py dump test.bin')
def main():
    p=argparse.ArgumentParser(description='Control Amiibo Bridge using your phone NFC reader')
    p.add_argument('--host'); p.add_argument('--token'); p.add_argument('--pc-ip'); p.add_argument('--port',type=int,default=8766)
    sub=p.add_subparsers(dest='cmd',required=True); sub.add_parser('pair'); sub.add_parser('status')
    d=sub.add_parser('dump'); d.add_argument('output',nargs='?',default='amiibo_dump.bin')
    w=sub.add_parser('write'); w.add_argument('file'); sub.add_parser('wipe')
    a=p.parse_args()
    if a.cmd=='pair': pair(a); return
    cfg=load_config() if not (a.host and a.token) else {'host':a.host,'token':a.token}; host,token=cfg['host'],cfg['token']
    if a.cmd=='status': print(json.dumps(request(host,token),indent=2)); return
    payload={'action':a.cmd}
    if a.cmd=='write':
        b=Path(a.file).read_bytes()
        if len(b)!=540: p.error(f'{a.file} must be exactly 540 bytes, got {len(b)}')
        payload['data']=base64.b64encode(b).decode('ascii')
    print('Send the job, then tap the NTAG215 tag on the phone...'); result=request(host,token,payload)
    if not result.get('ok'): raise SystemExit('Phone error: '+result.get('error','unknown error'))
    if a.cmd=='dump':
        raw=base64.b64decode(result['data']); Path(a.output).write_bytes(raw); print(f"Saved {a.output} ({len(raw)} bytes), UID {result.get('uid')}")
    else: print(result.get('message','Operation complete.'),'Verified:',result.get('verified',False))
if __name__=='__main__': main()
