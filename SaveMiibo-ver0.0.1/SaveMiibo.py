#!/usr/bin/env python3
"""SaveMiibo desktop GUI for Amiibo Bridge."""
import base64
import json
import queue
import socket
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
import secrets
import webbrowser

import qrcode
from PIL import Image, ImageTk

import amiibo_bridge as bridge

APP_NAME = "SaveMiibo"
PAIR_PORT = 8766


def lan_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 80))
        return sock.getsockname()[0]
    finally:
        sock.close()


class SaveMiiboApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SaveMiibo")
        self.root.geometry("760x590")
        self.root.minsize(680, 520)
        self.events = queue.Queue()
        self.pair_server = None
        self.pair_thread = None
        self.pair_nonce = None
        self.qr_photo = None

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        outer = ttk.Frame(root, padding=22)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x")
        ttk.Label(header, text="SaveMiibo", font=("Segoe UI", 25, "bold")).pack(anchor="w")
        ttk.Label(header, text="Your Amiibo backup & NFC companion", font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 12))

        self.status_var = tk.StringVar(value="Not paired yet — pair your Android phone to get started.")
        self.status_label = ttk.Label(outer, textvariable=self.status_var, wraplength=690)
        self.status_label.pack(fill="x", pady=(0, 14))

        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)

        actions = ttk.LabelFrame(body, text="Amiibo tools", padding=14)
        actions.pack(side="left", fill="y", padx=(0, 16))
        ttk.Button(actions, text="Pair phone (show QR)", command=self.start_pairing, width=25).pack(fill="x", pady=5)
        ttk.Button(actions, text="Check connection", command=self.check_status, width=25).pack(fill="x", pady=5)
        ttk.Separator(actions).pack(fill="x", pady=10)
        ttk.Button(actions, text="Dump Amiibo to file…", command=self.dump_amiibo, width=25).pack(fill="x", pady=5)
        ttk.Button(actions, text="Restore backup to blank tag…", command=self.restore_backup, width=25).pack(fill="x", pady=5)
        ttk.Button(actions, text="Wipe blank tag…", command=self.wipe_tag, width=25).pack(fill="x", pady=5)
        ttk.Label(actions, text="Restore and wipe are for compatible writable NTAG215 tags — not genuine Amiibo figures.", wraplength=205, foreground="#9a4b00").pack(fill="x", pady=(12, 0))

        qr_box = ttk.LabelFrame(body, text="Phone pairing QR", padding=12)
        qr_box.pack(side="left", fill="both", expand=True)
        self.qr_label = ttk.Label(qr_box, text="Click “Pair phone” to display a QR code.", anchor="center", justify="center")
        self.qr_label.pack(fill="both", expand=True)
        self.qr_hint = ttk.Label(qr_box, text="Keep SaveMiibo open while scanning.", anchor="center")
        self.qr_hint.pack(fill="x", pady=(8, 0))

        footer = ttk.Label(outer, text="SaveMiibo communicates with the Amiibo Bridge Android app over your local Wi-Fi.", foreground="#666")
        footer.pack(anchor="w", pady=(14, 0))

        self.root.after(150, self.process_events)

    def set_status(self, text):
        self.status_var.set(text)

    def get_config(self):
        try:
            return bridge.load_config()
        except SystemExit as exc:
            messagebox.showwarning(APP_NAME, str(exc))
            return None

    def run_job(self, title, fn):
        self.set_status(title + "…")
        def worker():
            try:
                result = fn()
                self.events.put(("ok", title, result))
            except Exception as exc:
                self.events.put(("error", title, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def process_events(self):
        try:
            while True:
                kind, title, result = self.events.get_nowait()
                if kind == "paired":
                    self.events_pair_done = True
                    self.set_status(f"Phone paired successfully: {result}")
                    self.qr_hint.configure(text="Paired! You can now use the Amiibo tools.")
                    messagebox.showinfo(APP_NAME, "Phone paired successfully!")
                elif kind == "ok":
                    self.set_status(f"{title}: {result}")
                    if title == "Connection check":
                        messagebox.showinfo(APP_NAME, str(result))
                    elif title.startswith("Dump"):
                        messagebox.showinfo(APP_NAME, str(result))
                    elif title.startswith("Restore") or title.startswith("Wipe"):
                        messagebox.showinfo(APP_NAME, str(result))
                else:
                    self.set_status(f"{title} failed: {result}")
                    messagebox.showerror(APP_NAME, f"{title} failed:\n\n{result}")
        except queue.Empty:
            pass
        self.root.after(150, self.process_events)

    def start_pairing(self):
        if self.pair_thread and self.pair_thread.is_alive():
            messagebox.showinfo(APP_NAME, "Pairing is already waiting for your phone.")
            return
        try:
            ip = lan_ip()
            nonce = secrets.token_urlsafe(24)
            self.pair_nonce = nonce
            qr_data = json.dumps({
                "type": "amiibobridge-pair",
                "callback": f"http://{ip}:{PAIR_PORT}/pair",
                "nonce": nonce
            })
            qr = qrcode.make(qr_data).convert("RGB")
            qr.thumbnail((360, 360), Image.Resampling.LANCZOS)
            self.qr_photo = ImageTk.PhotoImage(qr)
            self.qr_label.configure(image=self.qr_photo, text="")
            self.qr_hint.configure(text=f"Scan with Amiibo Bridge on your phone\nPC address: {ip}")
            self.set_status("Waiting for your phone to scan the QR code…")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not create pairing QR:\n{exc}")
            return

        app = self

        class PairHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path != "/pair":
                    self.send_error(404)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    body = json.loads(self.rfile.read(length))
                    if not secrets.compare_digest(body.get("nonce", ""), app.pair_nonce):
                        self.send_error(403)
                        return
                    host, token = body["phone_host"], body["token"]
                    if not host.startswith("http://") or len(token) < 24:
                        self.send_error(400)
                        return
                    bridge.CONFIG.parent.mkdir(parents=True, exist_ok=True)
                    bridge.CONFIG.write_text(json.dumps({"host": host, "token": token}, indent=2))
                    try:
                        bridge.CONFIG.chmod(0o600)
                    except OSError:
                        pass
                    data = b'{"ok":true}'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    app.events.put(("paired", "Phone pairing", host))
                except Exception as exc:
                    app.events.put(("error", "Phone pairing", str(exc)))
                    self.send_error(400)

            def log_message(self, *_):
                pass

        def serve():
            try:
                server = HTTPServer(("0.0.0.0", PAIR_PORT), PairHandler)
                server.timeout = 0.5
                app.pair_server = server
                while app.pair_nonce == nonce:
                    server.handle_request()
                    if app.events_pair_done:
                        break
                server.server_close()
            except OSError as exc:
                app.events.put(("error", "Pairing server", str(exc)))

        self.events_pair_done = False
        self.pair_thread = threading.Thread(target=serve, daemon=True)
        self.pair_thread.start()

    def check_status(self):
        cfg = self.get_config()
        if not cfg:
            return
        self.run_job("Connection check", lambda: json.dumps(bridge.request(cfg["host"], cfg["token"]), indent=2))

    def dump_amiibo(self):
        cfg = self.get_config()
        if not cfg:
            return
        path = filedialog.asksaveasfilename(
            title="Save Amiibo dump", defaultextension=".bin",
            initialfile="amiibo_dump.bin", filetypes=[("Amiibo dump", "*.bin"), ("All files", "*.*")]
        )
        if not path:
            return
        def work():
            result = bridge.request(cfg["host"], cfg["token"], {"action": "dump"})
            if not result.get("ok"):
                raise RuntimeError(result.get("error", "Phone reported an error"))
            raw = base64.b64decode(result["data"])
            if len(raw) != 540:
                raise RuntimeError(f"Unexpected dump size: {len(raw)} bytes (expected 540)")
            Path(path).write_bytes(raw)
            return f"Saved {path}\n540 bytes\nUID: {result.get('uid', 'unknown')}"
        self.run_job("Dump — tap your Amiibo/tag on the phone", work)

    def restore_backup(self):
        cfg = self.get_config()
        if not cfg:
            return
        path = filedialog.askopenfilename(title="Choose 540-byte backup", filetypes=[("Amiibo dump", "*.bin"), ("All files", "*.*")])
        if not path:
            return
        raw = Path(path).read_bytes()
        if len(raw) != 540:
            messagebox.showerror(APP_NAME, f"This file is {len(raw)} bytes. A supported NTAG215 dump must be 540 bytes.")
            return
        if not messagebox.askyesno(APP_NAME, "This writes to a compatible writable NTAG215 tag. Do NOT use this on your genuine Amiibo figure.\n\nContinue?"):
            return
        def work():
            payload = {"action": "write", "data": base64.b64encode(raw).decode("ascii")}
            result = bridge.request(cfg["host"], cfg["token"], payload)
            if not result.get("ok"):
                raise RuntimeError(result.get("error", "Phone reported an error"))
            return result.get("message", "Restore completed.") + f"\nVerified: {result.get('verified', False)}"
        self.run_job("Restore — tap a blank writable NTAG215 tag", work)

    def wipe_tag(self):
        cfg = self.get_config()
        if not cfg:
            return
        if not messagebox.askyesno(APP_NAME, "Wipe the user data area of a writable NTAG215 tag?\n\nThis is irreversible. Never use this on a genuine Amiibo figure.\n\nContinue?"):
            return
        def work():
            result = bridge.request(cfg["host"], cfg["token"], {"action": "wipe"})
            if not result.get("ok"):
                raise RuntimeError(result.get("error", "Phone reported an error"))
            return result.get("message", "Wipe completed.") + f"\nVerified: {result.get('verified', False)}"
        self.run_job("Wipe — tap a blank writable NTAG215 tag", work)


def main():
    root = tk.Tk()
    SaveMiiboApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
