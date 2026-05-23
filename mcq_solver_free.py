#!/usr/bin/env python3
"""
MCQ Screen Solver — DirectX overlay version (pygame)
-----------------------------------------------------
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
    print("[+] dxcam loaded")
except Exception as e:
    from PIL import ImageGrab
    USE_DXCAM = False
    print(f"[!] dxcam fallback: {e}")

# ── toast setup ───────────────────────────────────────────────────────────────
try:
    from win10toast import ToastNotifier
    toaster = ToastNotifier()
    USE_TOAST = True
    print("[+] win10toast loaded")
except Exception:
    USE_TOAST = False

# ── pygame overlay ────────────────────────────────────────────────────────────
import pygame
import pygame.locals as pl

# Windows API for layered/transparent window
GWL_EXSTYLE    = -20
WS_EX_LAYERED  = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST  = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
LWA_COLORKEY   = 0x00000001
LWA_ALPHA      = 0x00000002
HWND_TOPMOST   = -1
SWP_NOMOVE     = 0x0002
SWP_NOSIZE     = 0x0001

user32 = ctypes.windll.user32
TRANSPARENT_COLOR = (1, 1, 1)   # key color we make transparent

# ── Shared state ──────────────────────────────────────────────────────────────
state = {
    "visible": False,
    "answer": "Press ↑ to scan",
    "meta": "",
    "thinking": False,
    "dirty": True,
}
state_lock = threading.Lock()


def set_state(**kwargs):
    with state_lock:
        state.update(kwargs)
        state["dirty"] = True


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


# ── Capture thread ────────────────────────────────────────────────────────────
def on_capture():
    set_state(visible=True, thinking=True, answer="Analysing…", meta="")
    try:
        b64     = screenshot_to_b64()
        ans, meta = ask_groq(b64)
        set_state(thinking=False, answer=ans, meta=meta, visible=True)
        if USE_TOAST:
            threading.Thread(
                target=lambda: toaster.show_toast("MCQ", ans, duration=10, threaded=True),
                daemon=True
            ).start()
    except Exception as ex:
        set_state(thinking=False, answer=f"Error: {str(ex)[:100]}", visible=True)


# ── Keyboard ──────────────────────────────────────────────────────────────────
def on_press(key):
    try:
        if key == keyboard.Key.up:
            threading.Thread(target=on_capture, daemon=True).start()
        elif key == keyboard.Key.down:
            set_state(visible=False)
        elif key == keyboard.Key.esc:
            pygame.event.post(pygame.event.Event(pygame.QUIT))
            return False
    except Exception:
        pass


# ── Pygame overlay loop ───────────────────────────────────────────────────────
def wrap_text(font, text, max_width):
    lines = []
    for paragraph in text.split("\n"):
        words = paragraph.split(" ")
        current = ""
        for word in words:
            test = (current + " " + word).strip()
            if font.size(test)[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        lines.append("")   # blank line between paragraphs
    return lines[:-1]      # remove trailing blank


def run_overlay():
    os.environ["SDL_VIDEO_WINDOW_POS"] = "30,30"

    pygame.init()
    W, H = 440, 180
    flags = pygame.NOFRAME | pygame.SRCALPHA
    screen = pygame.display.set_mode((W, H), flags)
    pygame.display.set_caption("MCQ")

    # Make window transparent + always on top via Win32
    hwnd = pygame.display.get_wm_info()["window"]
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
        style | WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW)
    user32.SetLayeredWindowAttributes(hwnd, 0, 0, LWA_COLORKEY)
    # colorkey: render TRANSPARENT_COLOR as see-through
    user32.SetLayeredWindowAttributes(
        hwnd,
        (TRANSPARENT_COLOR[0] | TRANSPARENT_COLOR[1] << 8 | TRANSPARENT_COLOR[2] << 16),
        220,
        LWA_COLORKEY | LWA_ALPHA
    )
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 30, 30, W, H, SWP_NOMOVE | SWP_NOSIZE)

    font_ans  = pygame.font.SysFont("Consolas", 14, bold=True)
    font_meta = pygame.font.SysFont("Consolas", 11)
    font_hint = pygame.font.SysFont("Consolas", 10)

    BG       = (13, 13, 13)
    GREEN    = (0, 255, 136)
    GREY     = (80, 80, 80)
    ORANGE   = (243, 156, 18)
    RED      = (231, 76, 60)
    TRANSP   = TRANSPARENT_COLOR

    clock = pygame.time.Clock()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return

        with state_lock:
            visible  = state["visible"]
            answer   = state["answer"]
            meta     = state["meta"]
            thinking = state["thinking"]

        if not visible:
            screen.fill(TRANSP)
            pygame.display.flip()
            clock.tick(10)
            continue

        screen.fill(BG)

        # dot indicator
        dot_color = ORANGE if thinking else GREEN
        pygame.draw.circle(screen, dot_color, (W - 16, 14), 5)

        # hint
        hint = font_hint.render("↑ capture  ↓ hide  ESC quit", True, GREY)
        screen.blit(hint, (10, 8))

        # answer text
        lines = wrap_text(font_ans, answer, W - 20)
        y = 28
        for line in lines:
            surf = font_ans.render(line, True, GREEN)
            screen.blit(surf, (10, y))
            y += 18
            if y > H - 30:
                break

        # meta
        if meta:
            m = font_meta.render(meta[:60], True, GREY)
            screen.blit(m, (10, H - 18))

        # border
        pygame.draw.rect(screen, (30, 30, 30), (0, 0, W, H), 1)

        pygame.display.flip()
        clock.tick(30)


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not API_KEY:
        print("[!] GROQ_API_KEY not set. Get free key at console.groq.com")
        sys.exit(1)

    listener = keyboard.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()

    print("MCQ Solver (pygame DirectX overlay) running")
    print("  ↑  = capture & answer")
    print("  ↓  = hide")
    print("  ESC = quit")

    run_overlay()
    listener.stop()