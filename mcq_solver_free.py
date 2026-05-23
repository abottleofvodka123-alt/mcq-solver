#!/usr/bin/env python3
"""
MCQ Screen Solver — disguised as battery/wifi popup
----------------------------------------------------
Controls:
  ↑  Arrow Up   → Capture screen & get answer
  ↓  Arrow Down → Hide the overlay
  ESC           → Quit

Setup:
  pip install groq pynput pillow dxcam pygame win10toast
  set GROQ_API_KEY=your-key-here
  python mcq_solver_free.py
"""

import os
import sys
import base64
import threading
import ctypes
import time
from io import BytesIO
from PIL import Image
from pynput import keyboard
from groq import Groq
import tkinter as tk

# ── Config ───────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("GROQ_API_KEY", "")
MODEL   = "meta-llama/llama-4-scout-17b-16e-instruct"
# ─────────────────────────────────────────────────────────────────────────────

client = Groq(api_key=API_KEY) if API_KEY else None

# ── dxcam setup ───────────────────────────────────────────────────────────────
try:
    import dxcam
    camera = dxcam.create()
    USE_DXCAM = True
except Exception:
    from PIL import ImageGrab
    USE_DXCAM = False


# ── Screenshot ────────────────────────────────────────────────────────────────
def screenshot_to_b64():
    if USE_DXCAM:
        frame = camera.grab()
        if frame is None:
            time.sleep(0.2)
            frame = camera.grab()
        img = Image.fromarray(frame)
    else:
        img = ImageGrab.grab()
    img = img.resize((1280, 720), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


# ── Groq call ─────────────────────────────────────────────────────────────────
def ask_groq(b64_img):
    if not client:
        return "GROQ_API_KEY not set.", ""

    prompt = (
        "Look at this screenshot. Find the MCQ (multiple choice question) visible on screen.\n"
        "Reply in this EXACT format (no extra text):\n\n"
        "QUESTION: <one-line question>\n"
        "ANSWER: <correct option letter + text>\n"
        "REASON: <one short sentence why>\n\n"
        "If no MCQ is found, reply: NO_MCQ_FOUND"
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}},
                {"type": "text", "text": prompt}
            ]
        }],
        max_tokens=300,
    )

    raw = response.choices[0].message.content.strip()
    if "NO_MCQ_FOUND" in raw:
        return "No MCQ detected.", ""

    parsed = {}
    for line in raw.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            parsed[k.strip()] = v.strip()

    q      = parsed.get("QUESTION", "?")
    ans    = parsed.get("ANSWER",   "?")
    reason = parsed.get("REASON",   "")
    return f"Q: {q}\n\nANS: {ans}", reason


# ── Overlay — disguised as battery/wifi popup ─────────────────────────────────
class BatteryPopup:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)          # no title bar
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.95)
        self.root.configure(bg="#2b2b2b")

        # position bottom right like a real windows popup
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        W, H = 320, 160
        x = sw - W - 12
        y = sh - H - 48        # just above taskbar
        self.root.geometry(f"{W}x{H}+{x}+{y}")
        self.W = W
        self.H = H

        # ── header row (mimics windows popup header) ──
        header = tk.Frame(self.root, bg="#2b2b2b")
        header.pack(fill="x", padx=12, pady=(10, 4))

        # battery icon (unicode)
        tk.Label(
            header, text="🔋", font=("Segoe UI", 14),
            bg="#2b2b2b", fg="white"
        ).pack(side="left")

        tk.Label(
            header, text="Battery & Network",
            font=("Segoe UI", 11, "bold"),
            bg="#2b2b2b", fg="white"
        ).pack(side="left", padx=6)

        # wifi icon right side
        tk.Label(
            header, text="📶", font=("Segoe UI", 12),
            bg="#2b2b2b", fg="white"
        ).pack(side="right")

        # ── divider ──
        tk.Frame(self.root, bg="#444", height=1).pack(fill="x", padx=12)

        # ── answer content area ──
        self.answer_var = tk.StringVar(value="Checking network status…")
        self.answer_label = tk.Label(
            self.root,
            textvariable=self.answer_var,
            font=("Segoe UI", 10),
            bg="#2b2b2b", fg="#d4f5d4",
            wraplength=290,
            justify="left",
            anchor="nw",
            padx=12, pady=6
        )
        self.answer_label.pack(fill="both", expand=True)

        # ── footer (mimics windows popup footer) ──
        footer = tk.Frame(self.root, bg="#222")
        footer.pack(fill="x")
        self.meta_var = tk.StringVar(value="Connected · 87% · Charging")
        tk.Label(
            footer,
            textvariable=self.meta_var,
            font=("Segoe UI", 8),
            bg="#222", fg="#888",
            padx=12, pady=4
        ).pack(side="left")

        # rounded corner illusion via border
        self.root.configure(highlightbackground="#555", highlightthickness=1)

        # start hidden
        self.root.withdraw()

    def set_thinking(self):
        self.answer_var.set("Checking network status…")
        self.meta_var.set("Scanning… please wait")
        self._resize()
        self.root.deiconify()

    def set_answer(self, answer, meta=""):
        self.answer_var.set(answer)
        self.meta_var.set(meta if meta else "Connected · 87% · Charging")
        self._resize()
        self.root.deiconify()

    def set_error(self, msg):
        self.answer_var.set(f"Network error: {msg}")
        self.meta_var.set("Reconnecting…")
        self._resize()
        self.root.deiconify()

    def _resize(self):
        text  = self.answer_var.get()
        lines = text.count("\n") + 1
        H     = max(160, 100 + lines * 22)
        sw    = self.root.winfo_screenwidth()
        sh    = self.root.winfo_screenheight()
        x     = sw - self.W - 12
        y     = sh - H - 48
        self.root.geometry(f"{self.W}x{H}+{x}+{y}")

    def hide(self):
        self.root.withdraw()

    def run(self):
        self.root.mainloop()


# ── Keyboard listener ─────────────────────────────────────────────────────────
overlay = None

def on_capture():
    overlay.root.after(0, overlay.set_thinking)
    try:
        b64 = screenshot_to_b64()
        ans, meta = ask_groq(b64)
        def update(a=ans, m=meta):
            overlay.set_answer(a, m)
        overlay.root.after(0, update)
    except Exception as ex:
        err = str(ex)[:100]
        def show_err(e=err):
            overlay.set_error(e)
        overlay.root.after(0, show_err)


def on_press(key):
    try:
        if key == keyboard.Key.up:
            threading.Thread(target=on_capture, daemon=True).start()
        elif key == keyboard.Key.down:
            overlay.root.after(0, overlay.hide)
        elif key == keyboard.Key.esc:
            overlay.root.after(0, overlay.root.quit)
            return False
    except Exception:
        pass


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not API_KEY:
        print("[!] GROQ_API_KEY not set.")
        print("    Get free key at: https://console.groq.com")
        sys.exit(1)

    overlay = BatteryPopup()

    listener = keyboard.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()

    print("MCQ Solver running — disguised as battery/wifi popup")
    print("  ↑  = capture & answer")
    print("  ↓  = hide")
    print("  ESC = quit")

    overlay.run()
    listener.stop()