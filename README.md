# Snorx — Focus Buddy

A focus/Pomodoro timer with a physical phone jail. A Raspberry Pi 4 watches a cardboard "den" you slide your phone into, locks it in with two servos, and uses a camera + frame-diff CV to catch you reaching for it. Earn acorns by focusing, spend them on skins.

**Live UI demo (no hardware needed):** open the deployed link → demo mode auto-enables → click "Start nap" → simulated phone-in → focus screen. Press **S** during the focus session to fake an escape attempt (Snorx scolds you).

## Tech stack

A Raspberry Pi 4 runs a Flask + OpenCV server that controls two SG90 servos and streams the camera over MJPEG, while a single vanilla-JS HTML page on the laptop talks to it over HTTP. Audio uses ElevenLabs, stats persist in `localStorage` — no build step, no database, no cloud.

## Files

- `index.html` — the entire frontend (single self-contained file: HTML + CSS + JS)
- `snorx-*.png` / `snorx-*.jpg` — pixel-art skin assets
- `snorlax-cry.mp3` — ElevenLabs-generated voice ("No, don't even think about it")

The Raspberry Pi server, calibration script, and mock server live in the hardware build folder (not deployed — judges would have nothing to plug them into).

## Try it locally

```
python3 -m http.server 8000
```

Open `http://localhost:8000/` and click the "TRY DEMO" toggle bottom-right.

## Hotkeys (in demo mode, during a focus session)

- **S** — fake an escape attempt (counter ticks, Snorx scolds you)
- **E** — alias of S (legacy)
