#!/usr/bin/env python3
"""
MCQ Screen Solver — FREE version (Groq + dxcam)
------------------------------------------------
Controls:
  ↑  Arrow Up   → Capture screen & get answer
  ↓  Arrow Down → Hide the overlay window
  ESC           → Quit

Setup:
  pip install groq pynput pillow dxcam
  set GROQ_API_KEY=your-key-here
  python mcq_solver_free.py
"""

import os
import sys
import base64
import threading
import tkinter as tk
from io import BytesIO
from PIL import Image
from pynput import keyboard

# ── Config ───────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("GROQ_API_KEY", "")
MODEL   = "meta-llama/llama-4-scout-17b-16e-instruct"
# ─────────────────────────────────────────────────────────────────────────────

from groq import Groq
client = Groq(api_key=API_KEY) if API_KEY else None

# ── dxcam setup ───────────────────────────────────────────────────────────────
try:
    import dxcam
    camera = dxcam.create()
    USE_DXCAM = True
    print("[+] dxcam loaded — using DirectX capture")
except Exception as e:
    from PIL import ImageGrab
    USE_DXCAM = False
    print(f"[!] dxcam not available ({e}), falling back to ImageGrab")


# ── Overlay window ────────────────────────────────────────────────────────────
class OverlayWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("MCQ Solver")
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.93)
        self.root.geometry("420x160+40+40")
        self.root.configure(bg="#0d0d0d")
        self.root.resizable(True, True)

        header = tk.Frame(self.root, bg="#0d0d0d")
        header.pack(fill="x", padx=10, pady=(8, 0))

        tk.Label(
            header, text="⬆ capture  ⬇ hide  ESC quit",
            font=("Courier New", 8), fg="#444", bg="#0d0d0d"
        ).pack(side="left")

        self.status_dot = tk.Label(
            header, text="●", font=("Courier New", 10),
            fg="#2ecc71", bg="#0d0d0d"
        )
        self.status_dot.pack(side="right")

        self.answer_var = tk.StringVar(value="Press ↑ to scan screen")
        self.answer_label = tk.Label(
            self.root,
            textvariable=self.answer_var,
            font=("Courier New", 12, "bold"),
            fg="#00ff88", bg="#0d0d0d",
            wraplength=390,
            justify="left",
            anchor="nw",
            padx=10, pady=4
        )
        self.answer_label.pack(fill="both", expand=True)

        self.meta_var = tk.StringVar(value="")
        tk.Label(
            self.root, textvariable=self.meta_var,
            font=("Courier New", 8), fg="#555", bg="#0d0d0d",
            anchor="w", padx=10
        ).pack(fill="x", pady=(0, 6))

    def set_thinking(self):
        self.status_dot.config(fg="#f39c12")
        self.answer_var.set("Analysing…")
        self.meta_var.set("")
        self.root.deiconify()

    def set_answer(self, answer, meta=""):
        self.status_dot.config(fg="#2ecc71")
        self.answer_var.set(answer)
        self.meta_var.set(meta)
        lines = answer.count("\n") + 1
        h = max(140, 80 + lines * 22)
        w = self.root.winfo_width()
        x = self.root.winfo_x()
        y = self.root.winfo_y()
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.deiconify()

    def set_error(self, msg):
        self.status_dot.config(fg="#e74c3c")
        self.answer_var.set(f"Error: {msg}")
        self.meta_var.set("")
        self.root.deiconify()

    def hide(self):
        self.root.withdraw()

    def run(self):
        self.root.mainloop()


# ── Screenshot ────────────────────────────────────────────────────────────────
def screenshot_to_b64():
    if USE_DXCAM:
        frame = camera.grab()
        if frame is None:
            # retry once
            import time
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
        return "GROQ_API_KEY not set.", "get free key at console.groq.com"

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
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ],
        max_tokens=300,
    )

    raw = response.choices[0].message.content.strip()

    if "NO_MCQ_FOUND" in raw:
        return "No MCQ detected on screen.", ""

    parsed = {}
    for line in raw.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            parsed[k.strip()] = v.strip()

    q      = parsed.get("QUESTION", "?")
    ans    = parsed.get("ANSWER",   "?")
    reason = parsed.get("REASON",   "")

    display = f"Q: {q}\n\nANS: {ans}"
    return display, reason


# ── Keyboard listener ─────────────────────────────────────────────────────────
overlay = None

def on_capture():
    overlay.set_thinking()
    try:
        b64 = screenshot_to_b64()
        answer, meta = ask_groq(b64)
        def update(a=answer, m=meta):
            overlay.set_answer(a, m)
        overlay.root.after(0, update)
    except Exception as ex:
        err = str(ex)[:120]
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
        print("[!] GROQ_API_KEY is not set.")
        print("    Get a free key at: https://console.groq.com")
        print("    Then run: set GROQ_API_KEY=your-key   (Windows)")
        sys.exit(1)

    overlay = OverlayWindow()

    listener = keyboard.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()

    capture_method = "dxcam (DirectX)" if USE_DXCAM else "ImageGrab (fallback)"
    print(f"MCQ Solver running — capture: {capture_method}")
    print("  ↑  = capture screen & answer")
    print("  ↓  = hide window")
    print("  ESC = quit")

    overlay.run()
    listener.stop()