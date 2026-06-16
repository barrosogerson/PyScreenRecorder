# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running

```powershell
python screenRecorder.py
```

Stop recording by typing `q` + Enter in the terminal, pressing Ctrl+C, or by setting `DURATION` (seconds).

## Dependencies

```powershell
pip install opencv-python numpy mss
```

`tkinter` is bundled with Python on Windows. No `requirements.txt` exists yet.

## Architecture

Single-file tool (`screenRecorder.py`) with two independent display modes that can be combined:

- **Burn-in indicator** (`burn_indicator=True`): Draws a REC badge + timer directly onto each captured frame using OpenCV before writing to the video file. Implemented in `draw_recording_indicator()`.

- **On-screen overlay** (`show_on_screen=True`): Spawns a borderless tkinter window (`RecOverlay` class) that floats over the desktop during recording. It does **not** appear in the video unless the capture region includes it. Uses a chroma-key trick (`CHROMA_KEY = (1, 254, 1)`) to simulate transparent backgrounds via `wm_attributes("-transparentcolor")`.

**Recording loop** (`screen_record()`): Captures frames with `mss`, converts BGRA→BGR with OpenCV, optionally burns the indicator, writes to `.mp4` via `cv2.VideoWriter`. A daemon thread (`listen_for_quit`) watches stdin for `q`. The overlay runs in its own daemon thread and is updated each frame via `overlay.update(elapsed)`.

**Configuration**: All tunable parameters are constants at the bottom of the `__main__` block — edit them there before running.

## Key design notes

- `mss.monitors[1]` targets the primary monitor. Change the index to record a different monitor.
- Output files default to `screen_record_YYYYMMDD_HHMMSS.mp4` (excluded from git via `.gitignore`).
- The overlay's blinking dot frequency is driven by `int(time.time() * 1.65) % 2` — the `1.65` factor controls blink speed.
- `overlay_bg_color` accepts either `(R, G, B)` for opaque or `(R, G, B, A)` where `A` is `0.0`–`1.0` for semi-transparency.
