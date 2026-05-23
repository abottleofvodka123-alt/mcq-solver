#!/usr/bin/env python3
import os, sys, base64, threading, time
from io import BytesIO
from PIL import ImageGrab, Image
from pynput import keyboard
from groq import Groq
import tkinter as tk

API_KEY = os.environ.get("GROQ_API_KEY", "")
MODEL   = "meta-llama/llama-4-scout-17b-16e-instruct"
client  = Groq(api_key=API_KEY) if API_KEY else None

def screenshot_to_b64():
    img = ImageGrab.grab()
    img = img.resize((1280, 720), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()

def ask_groq(b64):
    if not client:
        return "NO KEY"
    r = client.chat.completions.create(
        model=MODEL,
        messages=[{"role":"user","content":[
            {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}},
            {"type":"text","text":"Find the MCQ in this screenshot. Reply ONLY with the correct option letter and text, nothing else. Example: C) Paris. If no MCQ found reply: -"}
        ]}],
        max_tokens=60,
    )
    return r.choices[0].message.content.strip()

class Overlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.0)  # start invisible
        self.root.configure(bg="#000001")
        self.root.wm_attributes("-transparentcolor", "#000001")

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"300x28+{sw-320}+{sh-60}")

        self.var = tk.StringVar(value="")
        tk.Label(
            self.root, textvariable=self.var,
            font=("Segoe UI", 13, "bold"),
            fg="#1E90FF", bg="#000001",
            padx=6, pady=2
        ).pack()
        self.root.withdraw()

    def show(self, text):
        self.var.set(text)
        self.root.attributes("-alpha", 0.92)
        self.root.deiconify()

    def hide(self):
        self.root.withdraw()

    def run(self):
        self.root.mainloop()

overlay = None

def on_capture():
    overlay.root.after(0, lambda: overlay.show("..."))
    try:
        b64 = screenshot_to_b64()
        ans = ask_groq(b64)
        overlay.root.after(0, lambda a=ans: overlay.show(a))
    except Exception as e:
        overlay.root.after(0, lambda: overlay.show("ERR"))

def on_press(key):
    try:
        if key == keyboard.Key.up:
            threading.Thread(target=on_capture, daemon=True).start()
        elif key == keyboard.Key.down:
            overlay.root.after(0, overlay.hide)
        elif key == keyboard.Key.esc:
            overlay.root.after(0, overlay.root.quit)
            return False
    except:
        pass

if __name__ == "__main__":
    if not API_KEY:
        print("[!] GROQ_API_KEY not set.")
        sys.exit(1)
    overlay = Overlay()
    l = keyboard.Listener(on_press=on_press)
    l.daemon = True
    l.start()
    overlay.run()
    l.stop()