import cv2          # OpenCV — image/video processing and drawing primitives
import numpy as np   # NumPy — used to convert raw screen-grab bytes into an array OpenCV can work with
import mss           # Multi-Screen Shot — fast cross-platform screen capture library
import time          # Standard library — used for sleep, elapsed-time math, and the blink-rate calculation
import threading     # Standard library — runs the quit-listener and overlay window on separate threads
import tkinter as tk # Standard GUI toolkit bundled with Python — used for the on-screen floating overlay
from datetime import datetime  # Used to build the default filename timestamp and format overlay date/time labels

# Global flag that signals the recording loop to stop.
# Set to True by the quit-listener thread when the user types 'q'.
stop_recording = False


def listen_for_quit():
    """
    Runs on a background daemon thread and blocks on stdin.
    When the user types 'q' + Enter the flag is flipped and the thread exits,
    which causes the main recording loop to break on its next iteration.
    """
    global stop_recording
    while True:
        user_input = input()           # Blocks until the user presses Enter
        if user_input.strip().lower() == 'q':
            stop_recording = True
            break                      # Exit the thread — the main loop will notice the flag


def draw_recording_indicator(frame, elapsed_seconds):
    """
    Burns a 'REC ● MM:SS' badge directly onto a video frame (in-place mutation).

    The badge is drawn with OpenCV primitives (rectangle + circles for rounded
    corners, text, a blinking dot, and a thin divider line) so it becomes a
    permanent part of the saved video.

    Args:
        frame:           NumPy array (H x W x 3, BGR) — the captured screen frame.
        elapsed_seconds: Seconds since recording started — used to render the timer.

    Returns:
        The same frame array with the badge drawn on it.
    """
    # ── Timer text ──────────────────────────────────────────────────────────────
    minutes = int(elapsed_seconds // 60)   # Floor-divide to get whole minutes
    seconds = int(elapsed_seconds % 60)    # Remainder seconds
    timer_text = f"{minutes:02d}:{seconds:02d}"  # Zero-padded "MM:SS" string

    # ── Style constants ─────────────────────────────────────────────────────────
    padding    = 12                        # Inner whitespace (px) around badge contents
    dot_radius = 10                        # Radius (px) of the blinking REC dot
    font       = cv2.FONT_HERSHEY_DUPLEX  # Slightly nicer than the default SIMPLEX font
    font_scale = 0.75                      # Multiplier on the base font size
    font_thick = 2                         # Stroke width in pixels
    red        = (0, 0, 220)              # OpenCV uses BGR order, so this is red
    white      = (255, 255, 255)           # BGR white for the timer digits
    dark_bg    = (30, 30, 30)             # Near-black background for the badge

    # ── Measure text extents so the badge auto-sizes to its content ─────────────
    # getTextSize returns ((width, height), baseline) for a given string + font config
    (rec_w, rec_h), _ = cv2.getTextSize("REC",      font, font_scale, font_thick)
    (tim_w, tim_h), _ = cv2.getTextSize(timer_text, font, font_scale, font_thick)

    # Total pixel width of all elements packed inside the badge (no outer padding yet)
    inner_w = dot_radius * 2 + 8 + rec_w + 16 + tim_w
    # Badge height is the tallest of the three elements
    inner_h = max(rec_h, tim_h, dot_radius * 2)
    badge_w  = inner_w + padding * 2      # Add left + right padding
    badge_h  = inner_h + padding * 2      # Add top + bottom padding

    # ── Badge position — top-right corner with an 18 px margin ─────────────────
    h, w = frame.shape[:2]               # frame.shape is (height, width, channels)
    x1 = w - badge_w - 18               # Left edge of badge
    y1 = 18                              # Top edge of badge
    x2 = x1 + badge_w                   # Right edge
    y2 = y1 + badge_h                   # Bottom edge

    # ── Draw rounded-rectangle background ───────────────────────────────────────
    # OpenCV has no native rounded-rect, so we composite three shapes:
    #   1. A horizontal rectangle (full width, minus the corner radius r on each side)
    #   2. A vertical rectangle (full height, minus r top and bottom)
    #   3. Four filled circles at each corner to round them off
    r = 10  # Corner radius in pixels
    cv2.rectangle(frame, (x1 + r, y1), (x2 - r, y2), dark_bg, -1)   # Horizontal bar
    cv2.rectangle(frame, (x1, y1 + r), (x2, y2 - r), dark_bg, -1)   # Vertical bar
    # -1 thickness means "filled" in OpenCV
    for cx, cy_c in [(x1+r, y1+r), (x2-r, y1+r), (x1+r, y2-r), (x2-r, y2-r)]:
        cv2.circle(frame, (cx, cy_c), r, dark_bg, -1)                # Corner circles

    # ── Vertical centre of the badge — used to align all elements ───────────────
    cy    = y1 + badge_h // 2
    dot_x = x1 + padding + dot_radius    # Horizontal centre of the blinking dot

    # ── Blinking REC dot ────────────────────────────────────────────────────────
    # Multiplying time.time() by 1.65 gives ~1.65 blinks per second.
    # int(...) % 2 alternates between 0 and 1 to toggle the colour each ~0.6 s.
    if int(time.time() * 1.65) % 2 == 0:
        cv2.circle(frame, (dot_x, cy), dot_radius, red, -1)           # Bright red dot
        cv2.circle(frame, (dot_x, cy), dot_radius + 2, (0, 0, 160), 1)  # Dark-red ring
    else:
        cv2.circle(frame, (dot_x, cy), dot_radius, (60, 60, 60), -1)  # Dim grey (dot "off")

    # ── "REC" label ─────────────────────────────────────────────────────────────
    rec_x = dot_x + dot_radius + 8       # Place text just right of the dot
    # putText baseline is the bottom of the text; shift up by half the height to centre
    cv2.putText(frame, "REC", (rec_x, cy + rec_h // 2),
                font, font_scale, red, font_thick, cv2.LINE_AA)
    # cv2.LINE_AA = anti-aliased rendering for smoother edges

    # ── Thin vertical divider between "REC" and the timer ───────────────────────
    div_x = rec_x + rec_w + 8
    cv2.line(frame, (div_x, y1 + 8), (div_x, y2 - 8), (80, 80, 80), 1)

    # ── Timer digits ────────────────────────────────────────────────────────────
    tim_x = div_x + 8
    cv2.putText(frame, timer_text, (tim_x, cy + tim_h // 2),
                font, font_scale, white, font_thick, cv2.LINE_AA)

    return frame


def rgb_to_hex(rgb):
    """Convert an (R, G, B) tuple to a '#rrggbb' hex string for tkinter colour arguments."""
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def blend_color(fg, alpha, chroma_key):
    """
    Linearly interpolate between fg and chroma_key based on alpha.

    This simulates a semi-transparent background:  instead of true window
    transparency (which is limited on Windows), we pre-blend the desired
    background colour toward the chroma-key colour and then tell tkinter to
    make the chroma-key colour fully transparent via wm_attributes.

    Args:
        fg:         (R, G, B) — the "real" background colour the user wants.
        alpha:      float 0.0–1.0 — desired opacity (0 = invisible, 1 = fully opaque).
        chroma_key: (R, G, B) — the special colour that will be made transparent.

    Returns:
        (R, G, B) tuple — the blended colour to use as the actual widget background.
    """
    r = int(fg[0] * alpha + chroma_key[0] * (1 - alpha))
    g = int(fg[1] * alpha + chroma_key[1] * (1 - alpha))
    b = int(fg[2] * alpha + chroma_key[2] * (1 - alpha))
    return (r, g, b)


class RecOverlay:
    """
    A floating, always-on-top tkinter window that shows the REC indicator
    on the desktop during recording.

    The window is NOT captured in the video (unless the user positions it
    inside the recorded region).  It runs on its own daemon thread so it
    doesn't block the recording loop.

    Transparency is achieved via a chroma-key trick:
      1. The background is filled with a colour very close to CHROMA_KEY.
      2. wm_attributes("-transparentcolor") makes that exact colour transparent.
      3. blend_color() pre-blends the user's bg colour toward CHROMA_KEY so
         that partial alpha values produce a visually accurate result.
    """

    # A unique, unlikely-to-appear-naturally colour used as the transparency mask.
    # (1, 254, 1) — nearly pure green but not #00ff00, reducing false-positive matches.
    CHROMA_KEY = (1, 254, 1)

    def __init__(
        self,
        label_text,    # String shown next to the dot — supports {date} and {time} placeholders
        font_size,     # Point size for both the label and timer
        font_family,   # e.g. "Segoe UI" — any font installed on the system
        text_color,    # (R, G, B) for the label and timer text
        bg_color,      # (R, G, B) opaque  OR  (R, G, B, A) with A as float 0.0–1.0
        borderless,    # True = no title bar / window chrome (overrideredirect)
        corner,        # "top-left" | "top-right" | "bottom-left" | "bottom-right"
        screen_w,      # Full screen width (px) — used to compute corner positions
        screen_h,      # Full screen height (px)
        margin_h,      # Horizontal distance (px) from the chosen screen edge
        margin_v,      # Vertical distance (px) from the chosen screen edge
    ):
        self.label_text  = label_text
        self.font_size   = font_size
        self.font_family = font_family
        self.borderless  = borderless
        self.corner      = corner
        self.screen_w    = screen_w
        self.screen_h    = screen_h
        self.margin_h    = margin_h
        self.margin_v    = margin_v

        # ── Parse bg_color — support both (R,G,B) and (R,G,B,A) ────────────────
        if len(bg_color) == 4:
            self.bg_rgb   = bg_color[:3]           # Separate the colour from the alpha
            self.bg_alpha = float(bg_color[3])     # Normalise to float just in case an int was passed
        else:
            self.bg_rgb   = bg_color
            self.bg_alpha = 1.0                    # No alpha supplied → fully opaque

        # ── Resolve the effective background colour for the tkinter widgets ──────
        if self.bg_alpha < 1.0:
            # Pre-blend toward chroma key so that wm_attributes transparency looks correct
            blended_bg      = blend_color(self.bg_rgb, self.bg_alpha, self.CHROMA_KEY)
            self.bg_hex     = rgb_to_hex(blended_bg)
            self.use_chroma = True   # Flag: apply "-transparentcolor" to the window
        else:
            self.bg_hex     = rgb_to_hex(self.bg_rgb)
            self.use_chroma = False  # Fully opaque — no chroma trick needed

        self.text_color = rgb_to_hex(text_color)   # Convert once; reused in multiple widgets

        # ── Internal state ───────────────────────────────────────────────────────
        self.elapsed  = 0.0    # Seconds since recording started — updated by the main loop
        self.running  = False  # Guards the tkinter refresh loop; set False to trigger shutdown
        self._root    = None   # The tk.Tk() root window — created inside the thread
        self._thread  = None   # Reference to the daemon thread running the tkinter event loop

    def start(self):
        """Spawn the daemon thread that owns and drives the tkinter window."""
        self.running = True
        # daemon=True means the thread is killed automatically when the main program exits,
        # so we don't need explicit join() calls.
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def update(self, elapsed):
        """
        Called from the recording loop each frame to push the current elapsed time
        to the overlay.  Thread-safe because only a float is written.
        """
        self.elapsed = elapsed

    def stop(self):
        """
        Signal the overlay to shut down.
        root.after(0, ...) schedules destroy() on the tkinter event loop's own thread,
        which is the only safe way to call tkinter methods from outside that thread.
        """
        self.running = False
        if self._root:
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass  # Window may already be gone; ignore

    def _get_position(self, win_w, win_h):
        """
        Return the (x, y) screen coordinates for the window's top-left corner
        based on the chosen corner name and margin settings.
        """
        corners = {
            "top-left":     (self.margin_h,
                             self.margin_v),
            "top-right":    (self.screen_w - win_w - self.margin_h,
                             self.margin_v),
            "bottom-left":  (self.margin_h,
                             self.screen_h - win_h - self.margin_v),
            "bottom-right": (self.screen_w - win_w - self.margin_h,
                             self.screen_h - win_h - self.margin_v),
        }
        # Fall back to top-right if an unrecognised corner name is given
        return corners.get(self.corner, corners["top-right"])

    def _run(self):
        """
        Creates and runs the tkinter window.  Must execute entirely on this thread —
        tkinter is not thread-safe and its event loop (mainloop) blocks until the
        window is destroyed.
        """
        self._root = tk.Tk()
        root = self._root

        root.title("REC Indicator")
        root.configure(bg=self.bg_hex)
        root.attributes("-topmost", True)    # Always render above other windows
        root.resizable(False, False)         # Prevent manual resizing
        root.attributes("-alpha", "0.5")     # Overall window opacity (0.0–1.0)

        if self.borderless:
            # overrideredirect(True) removes the OS title bar and window border,
            # making the widget look like a pure overlay rather than a normal window.
            root.overrideredirect(True)

        # Apply chroma-key: the OS will composite this colour as fully transparent,
        # revealing whatever is behind the window at those pixels.
        if self.use_chroma:
            root.wm_attributes("-transparentcolor", rgb_to_hex(self.CHROMA_KEY))

        # ── Layout padding scales with font size ─────────────────────────────────
        pad_x = max(10, self.font_size // 2)
        pad_y = max(6,  self.font_size // 4)

        # Outer frame acts as a padding container; its bg must match the window bg
        frame = tk.Frame(root, bg=self.bg_hex)
        frame.pack(padx=pad_x, pady=pad_y)

        # ── Blinking dot — drawn on a tiny Canvas so we can change its fill colour ──
        dot_size = max(10, self.font_size - 4)  # dot px = font size minus a small offset

        self._dot_canvas = tk.Canvas(
            frame,
            width=dot_size, height=dot_size,
            bg=self.bg_hex, highlightthickness=0,  # Remove the default 1px border
        )
        self._dot_canvas.pack(side=tk.LEFT, padx=(0, 6))
        # create_oval draws an ellipse inscribed in the bounding box (x0,y0,x1,y1)
        self._dot_oval = self._dot_canvas.create_oval(
            1, 1, dot_size - 1, dot_size - 1, fill="#dc0000", outline=""
        )

        # ── Label (e.g. "REC" or a date string) ────────────────────────────────
        # StringVar lets us update the widget text without recreating it
        self._label_var = tk.StringVar()
        tk.Label(
            frame,
            textvariable=self._label_var,
            font=(self.font_family, self.font_size, "bold"),
            fg=self.text_color,
            bg=self.bg_hex,
        ).pack(side=tk.LEFT, padx=(0, 8))

        # ── Thin vertical separator between label and timer ─────────────────────
        tk.Frame(frame, width=1, bg="#555555").pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))

        # ── Timer display ───────────────────────────────────────────────────────
        self._timer_var = tk.StringVar(value="00:00")
        tk.Label(
            frame,
            textvariable=self._timer_var,
            font=(self.font_family, self.font_size, "bold"),
            fg=self.text_color,
            bg=self.bg_hex,
        ).pack(side=tk.LEFT)

        # ── Position the window after widgets are laid out ──────────────────────
        # update_idletasks() forces tkinter to compute actual widget sizes
        # before we read winfo_reqwidth/Height, which would otherwise return 1.
        root.update_idletasks()
        win_w = root.winfo_reqwidth()
        win_h = root.winfo_reqheight()
        x, y  = self._get_position(win_w, win_h)
        root.geometry(f"+{x}+{y}")   # "+x+y" syntax sets position without changing size

        self._refresh()    # Start the periodic refresh loop before handing off to mainloop
        root.mainloop()    # Blocks until the window is destroyed

    def _refresh(self):
        """
        Periodic callback (every 30 ms) that updates all dynamic widget content:
        the timer text, the label (with date/time interpolation), and the blinking dot.

        Scheduled with root.after() instead of a sleep loop so it runs on the
        tkinter event thread and is therefore safe to call widget methods.
        """
        if not self.running:
            return  # Don't reschedule once stop() has been called

        # ── Update timer ────────────────────────────────────────────────────────
        minutes = int(self.elapsed // 60)
        seconds = int(self.elapsed % 60)
        self._timer_var.set(f"{minutes:02d}:{seconds:02d}")

        # ── Update label — supports {date} and {time} format placeholders ───────
        now   = datetime.now()
        label = self.label_text.format(
            date=now.strftime("%Y-%m-%d"),
            time=now.strftime("%H:%M:%S"),
        )
        self._label_var.set(label)

        # ── Blink the dot at ~1.65 Hz (same formula as the burn-in indicator) ───
        dot_color = "#dc0000" if int(time.time() * 1.65) % 2 == 0 else "#3c3c3c"
        self._dot_canvas.itemconfig(self._dot_oval, fill=dot_color)

        # Schedule the next refresh in 30 ms (~33 fps refresh rate for the overlay)
        self._root.after(30, self._refresh)


def screen_record(
    output_filename      = None,    # Path/name for the .mp4 file; auto-generated if None
    fps                  = 10,      # Frames per second written to the video file
    duration             = None,    # Auto-stop after this many seconds; None = manual stop
    burn_indicator       = True,    # Bake the REC badge into each video frame
    show_on_screen       = False,   # Show a floating tkinter overlay on the desktop
    overlay_label        = "REC",   # Text in the overlay; supports {date} / {time}
    overlay_font_size    = 18,      # Overlay font point size
    overlay_font_family  = "Segoe UI",  # Any system-installed font name
    overlay_text_color   = (255, 255, 255),  # (R, G, B) — white by default
    overlay_bg_color     = (30, 30, 30),     # (R,G,B) or (R,G,B,A) where A is 0.0–1.0
    overlay_borderless   = False,   # Remove OS window chrome from the overlay
    overlay_corner       = "top-right",   # Which screen corner to place the overlay
    overlay_margin_h     = 18,      # Horizontal margin (px) from the screen edge
    overlay_margin_v     = 18,      # Vertical margin (px) from the screen edge
):
    """
    Capture the primary monitor and write it to an .mp4 file.

    Supports two optional visual indicators (independently toggleable):
      - burn_indicator:  embeds a REC badge permanently into the video frames.
      - show_on_screen:  displays a floating window on the desktop while recording.

    Recording stops when:
      - The user types 'q' + Enter in the terminal.
      - Ctrl+C is pressed (KeyboardInterrupt).
      - 'duration' seconds have elapsed (if set).
    """
    global stop_recording
    stop_recording = False   # Reset in case screen_record() is called more than once

    # ── Screen capture setup ─────────────────────────────────────────────────────
    _sct          = mss.mss()            # Create an mss context (manages OS screen APIs)
    _monitor      = _sct.monitors[1]    # monitors[0] = virtual bounding box of all screens;
                                         # monitors[1] = primary monitor
    screen_width  = _monitor["width"]
    screen_height = _monitor["height"]

    # ── Output file ──────────────────────────────────────────────────────────────
    if output_filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"screen_record_{timestamp}.mp4"

    # mp4v = MPEG-4 Visual codec; widely compatible and doesn't need external codecs
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    # VideoWriter(path, codec, fps, (width, height)) — creates/overwrites the file
    out    = cv2.VideoWriter(output_filename, fourcc, fps, (screen_width, screen_height))

    # ── Console summary ──────────────────────────────────────────────────────────
    # Summarise bg color for the log
    if len(overlay_bg_color) == 4:
        bg_desc = f"RGB{overlay_bg_color[:3]}  alpha={overlay_bg_color[3]}"
    else:
        bg_desc = f"RGB{overlay_bg_color}  alpha=1.0 (opaque)"

    print(f"🎥 Recording started! Output: {output_filename}")
    print(f"   Burn indicator in video : {'Yes' if burn_indicator else 'No'}")
    print(f"   Show overlay on screen  : {'Yes' if show_on_screen else 'No'}")
    if show_on_screen:
        print(f"   Label        : {overlay_label}")
        print(f"   Font         : {overlay_font_family} {overlay_font_size}pt")
        print(f"   Background   : {bg_desc}")
        print(f"   Corner       : {overlay_corner}")
        print(f"   Margin H/V   : {overlay_margin_h}px / {overlay_margin_v}px")
        print(f"   Borderless   : {overlay_borderless}")
    if duration:
        print(f"   Recording for {duration} seconds...")
    else:
        print("   Type 'q' and press Enter to stop recording...")

    # ── Start optional on-screen overlay ────────────────────────────────────────
    overlay = None
    if show_on_screen:
        overlay = RecOverlay(
            label_text  = overlay_label,
            font_size   = overlay_font_size,
            font_family = overlay_font_family,
            text_color  = overlay_text_color,
            bg_color    = overlay_bg_color,
            borderless  = overlay_borderless,
            corner      = overlay_corner,
            screen_w    = screen_width,
            screen_h    = screen_height,
            margin_h    = overlay_margin_h,
            margin_v    = overlay_margin_v,
        )
        overlay.start()   # Spawns the overlay's daemon thread

    # ── Quit-listener thread ─────────────────────────────────────────────────────
    # daemon=True so it's killed automatically if the main thread exits first
    listener_thread = threading.Thread(target=listen_for_quit, daemon=True)
    listener_thread.start()

    # ── Recording state ──────────────────────────────────────────────────────────
    start_time     = time.time()
    frame_count    = 0
    frame_interval = 1.0 / fps   # Target seconds per frame (e.g. 0.1 s at 10 fps)

    try:
        while not stop_recording:
            frame_start = time.time()          # Timestamp at the beginning of this frame
            elapsed     = frame_start - start_time

            # ── Capture screen ───────────────────────────────────────────────────
            # mss.grab() returns a ScreenShot object; np.array() converts it to (H,W,4) BGRA
            frame = np.array(_sct.grab(_monitor))
            # Drop the alpha channel — VideoWriter expects 3-channel BGR
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

            # ── Optionally burn REC badge into the frame ─────────────────────────
            if burn_indicator:
                frame = draw_recording_indicator(frame, elapsed)

            out.write(frame)   # Append the frame to the video file
            frame_count += 1

            # ── Push elapsed time to the overlay widget ──────────────────────────
            if overlay:
                overlay.update(elapsed)

            # ── Check duration limit ─────────────────────────────────────────────
            if duration and elapsed >= duration:
                print(f"\n⏱️  Reached {duration}s duration. Stopping...")
                break

            # ── Progress indicator (overwrites the same terminal line each frame) ─
            # \r returns the cursor to the start of the line; end="" suppresses newline
            print(f"\r   Frames: {frame_count} | Time: {elapsed:.1f}s", end="", flush=True)

            # ── Frame-rate pacing ────────────────────────────────────────────────
            # Sleep only for the remaining time in this frame's budget so that
            # capture + processing overhead doesn't push us below the target fps.
            sleep_time = frame_interval - (time.time() - frame_start)
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n⚠️  Stopped by Ctrl+C.")

    finally:
        # ── Cleanup — always runs even if an exception occurred ──────────────────
        out.release()      # Flush and close the video file
        _sct.close()       # Release OS screen-capture resources
        if overlay:
            overlay.stop()
        total_time = time.time() - start_time
        print(f"\n✅ Saved: '{output_filename}'")
        print(f"   Duration: {total_time:.1f}s | Frames: {frame_count} | Avg FPS: {frame_count/total_time:.1f}")


# ── Entry point — edit the constants below to configure a recording session ──────
if __name__ == "__main__":
    OUTPUT_FILE  = None    # None = auto-generate filename from current timestamp
    FPS          = 10      # Capture rate; 10 fps is a good balance of file size vs. smoothness
    DURATION     = None    # None = record until 'q' is typed; set e.g. 30 to stop after 30 s

    # ── Video burn-in ──────────────────────────────────────────────────────────
    # When True, the REC badge is drawn into every frame of the saved .mp4 file.
    BURN_INDICATOR       = False

    # ── On-screen floating overlay ─────────────────────────────────────────────
    # When True, a tkinter window is shown on the desktop during recording.
    # It is NOT part of the video unless the capture area includes it.
    SHOW_ON_SCREEN       = True
    OVERLAY_LABEL        = "{date}"          # Supports {date} and {time} placeholders
    OVERLAY_FONT_SIZE    = 10
    OVERLAY_FONT_FAMILY  = "Segoe UI"
    OVERLAY_TEXT_COLOR   = (255, 255, 255)   # (R, G, B) — white

    # Background color — choose one style:
    #   Fully opaque  : (30, 30, 30)
    #   Semi-transparent: (30, 30, 30, 0.55)   ← alpha 0.0=invisible  1.0=opaque
    #   Fully transparent background: (30, 30, 30, 0.0)
    OVERLAY_BG_COLOR     = (0, 0, 0)

    OVERLAY_BORDERLESS   = True              # No title bar
    OVERLAY_CORNER       = "bottom-right"    # Which corner of the screen to use
    OVERLAY_MARGIN_H     = 100               # Pixels from the left/right screen edge
    OVERLAY_MARGIN_V     = 60               # Pixels from the top/bottom screen edge

    screen_record(
        output_filename     = OUTPUT_FILE,
        fps                 = FPS,
        duration            = DURATION,
        burn_indicator      = BURN_INDICATOR,
        show_on_screen      = SHOW_ON_SCREEN,
        overlay_label       = OVERLAY_LABEL,
        overlay_font_size   = OVERLAY_FONT_SIZE,
        overlay_font_family = OVERLAY_FONT_FAMILY,
        overlay_text_color  = OVERLAY_TEXT_COLOR,
        overlay_bg_color    = OVERLAY_BG_COLOR,
        overlay_borderless  = OVERLAY_BORDERLESS,
        overlay_corner      = OVERLAY_CORNER,
        overlay_margin_h    = OVERLAY_MARGIN_H,
        overlay_margin_v    = OVERLAY_MARGIN_V,
    )
