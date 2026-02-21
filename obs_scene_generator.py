"""
OBS Scene Collection Generator — KH Video Switcher
Generates an OBS scene collection JSON file configured for PTZ camera control.

Scenes:
  - "Media" scene (optional) with a Display Capture source for presentations/laptops
  - N camera preset scenes, each with:
      • PTZ Camera video capture source (visible, top layer) — shared across all scenes
      • Browser source (hidden, bottom layer) that fires the PTZ preset URL on scene activation
  - "Black" scene (optional) — empty scene for clean fade-to-black transitions

Transitions:
  - Supports Stinger, Fade, and Cut as the default transition
  - Stinger is pre-configured at 800ms transition point and the stinger file is
    automatically downloaded to C:\\Program Files (x86)\\KH Switcher\\Stingers

PTZ Control:
  - Camera presets are triggered via HTTP: http://[IP]/cgi-bin/ptzctrl.cgi?ptzcmd&poscall&[pos]
  - Each scene fires its preset URL when the scene becomes active in OBS
"""

import json
import uuid
import os
import sys
import threading
import urllib.request
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from copy import deepcopy

# ── Windows admin elevation ─────────────────────────────────────────────────
# If not running as admin on Windows, relaunch the process with elevation.
# This is required to write to C:\Program Files (x86)\KH Switcher\Stingers.
def _require_admin():
    if sys.platform != "win32":
        return  # Only relevant on Windows
    try:
        import ctypes
        if ctypes.windll.shell32.IsUserAnAdmin():
            return  # Already admin, nothing to do
        # Relaunch with admin rights via ShellExecute runas verb
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(f'"{a}"' for a in sys.argv), None, 1
        )
        sys.exit(0)  # Exit the non-elevated instance
    except Exception:
        pass  # If elevation fails, continue anyway and let the download error handle it

_require_admin()

# ── Shared canvas UUID used by OBS for default canvas ──────────────────────
DEFAULT_CANVAS_UUID = "6c69626f-6273-4c00-9d88-c5136d61696e"


# ═══════════════════════════════════════════════════════════════════════════
#  JSON BUILDER
# ═══════════════════════════════════════════════════════════════════════════

def make_uuid():
    return str(uuid.uuid4())


def make_source_base(name, src_id, versioned_id, settings, extra=None):
    """Return a minimal OBS source dict."""
    src = {
        "prev_ver": 536870916,
        "name": name,
        "uuid": make_uuid(),
        "id": src_id,
        "versioned_id": versioned_id,
        "settings": settings,
        "mixers": 255,
        "sync": 0,
        "flags": 0,
        "volume": 1.0,
        "balance": 0.5,
        "enabled": True,
        "muted": False,
        "push-to-mute": False,
        "push-to-mute-delay": 0,
        "push-to-talk": False,
        "push-to-talk-delay": 0,
        "hotkeys": {},
        "deinterlace_mode": 0,
        "deinterlace_field_order": 0,
        "monitoring_type": 0,
        "private_settings": {}
    }
    if extra:
        src.update(extra)
    return src


def make_scene_item(name, source_uuid, item_id, visible=True):
    return {
        "name": name,
        "source_uuid": source_uuid,
        "visible": visible,
        "locked": False,
        "rot": 0.0,
        "align": 5,
        "bounds_type": 0,
        "bounds_align": 0,
        "bounds_crop": False,
        "crop_left": 0,
        "crop_top": 0,
        "crop_right": 0,
        "crop_bottom": 0,
        "id": item_id,
        "group_item_backup": False,
        "pos": {"x": 0.0, "y": 0.0},
        "scale": {"x": 1.0, "y": 1.0},
        "bounds": {"x": 0.0, "y": 0.0},
        "scale_filter": "disable",
        "blend_method": "default",
        "blend_type": "normal",
        "show_transition": {"duration": 0},
        "hide_transition": {"duration": 0},
        "private_settings": {}
    }


def make_scene_source(scene_name, items, id_counter):
    """Return the source dict for an OBS scene."""
    src = make_source_base(
        name=scene_name,
        src_id="scene",
        versioned_id="scene",
        settings={
            "custom_size": False,
            "id_counter": id_counter,
            "items": items
        },
        extra={
            "mixers": 0,
            "hotkeys": {"OBSBasic.SelectScene": []},
            "canvas_uuid": DEFAULT_CANVAS_UUID
        }
    )
    return src


def build_obs_json(collection_name: str, camera_ip: str, video_device: str, presets: list[dict], include_media: bool = True, include_black: bool = False, transition: str = "Stinger") -> dict:
    """
    presets: list of {"name": str, "position": int}
    Returns the full OBS scene collection dict.
    """
    sources = []
    scene_order = []

    # ── Display Capture source + Media scene (optional) ─────────────────────
    if include_media:
        scene_order.append({"name": "Media"})
        display_uuid = make_uuid()
        display_source = make_source_base(
            name="Display Capture",
            src_id="monitor_capture",
            versioned_id="monitor_capture",
            settings={"monitor": 0},
            extra={
                "hotkeys": {
                    "libobs.mute": [], "libobs.unmute": [],
                    "libobs.push-to-mute": [], "libobs.push-to-talk": []
                }
            }
        )
        display_source["uuid"] = display_uuid
        sources.append(display_source)

        media_items = [make_scene_item("Display Capture", display_uuid, 1)]
        media_scene = make_scene_source("Media", media_items, id_counter=1)
        sources.append(media_scene)

    # ── Video Capture source (shared across all camera preset scenes) ────────
    video_uuid = make_uuid()
    video_source = make_source_base(
        name=video_device,
        src_id="av_capture_input",
        versioned_id="av_capture_input_v2",
        settings={
            "device_name": video_device
        },
        extra={
            "hotkeys": {
                "libobs.mute": [], "libobs.unmute": [],
                "libobs.push-to-mute": [], "libobs.push-to-talk": []
            }
        }
    )
    video_source["uuid"] = video_uuid
    sources.append(video_source)

    # ── Browser sources + Camera Preset scenes ──────────────────────────────
    for preset in presets:
        scene_name = preset["name"]
        position   = preset["position"]
        url        = f"http://{camera_ip}/cgi-bin/ptzctrl.cgi?ptzcmd&poscall&{position}"

        # Browser source (hidden — fires PTZ URL on scene activation)
        browser_uuid = make_uuid()
        browser_source = make_source_base(
            name=f"PTZ Preset – {scene_name}",
            src_id="browser_source",
            versioned_id="browser_source",
            settings={
                "url": url,
                "width": 1920,
                "height": 1080,
                "restart_when_active": True,  # "Refresh when scene becomes active"
                "shutdown": True
            },
            extra={
                "hotkeys": {
                    "libobs.mute": [], "libobs.unmute": [],
                    "libobs.push-to-mute": [], "libobs.push-to-talk": [],
                    "ObsBrowser.Refresh": []
                }
            }
        )
        browser_source["uuid"] = browser_uuid
        sources.append(browser_source)

        # Scene items:
        #   item 1 (bottom) — browser source, hidden
        #   item 2 (top)    — video capture, visible
        scene_items = [
            make_scene_item(f"PTZ Preset – {scene_name}", browser_uuid, item_id=1, visible=False),
            make_scene_item(video_device, video_uuid, item_id=2, visible=True),
        ]
        preset_scene = make_scene_source(scene_name, scene_items, id_counter=2)
        # Hotkey stubs for both items
        preset_scene["hotkeys"]["libobs.show_scene_item.1"] = []
        preset_scene["hotkeys"]["libobs.hide_scene_item.1"] = []
        preset_scene["hotkeys"]["libobs.show_scene_item.2"] = []
        preset_scene["hotkeys"]["libobs.hide_scene_item.2"] = []
        sources.append(preset_scene)

        scene_order.append({"name": scene_name})

    # ── Optional Black scene (empty — used for fading to black) ─────────────
    if include_black:
        black_scene = make_scene_source("Black", items=[], id_counter=0)
        sources.append(black_scene)
        scene_order.append({"name": "Black"})

    # ── Build transitions list based on selected transition ──────────────────
    STINGER_PATH = r"C:\Program Files (x86)\KH Switcher\Stingers\Stinger120 Quick.mov"
    TRANSITION_DEFS = {
        "Stinger": {
            "name": "Stinger",
            "id": "obs_stinger_transition",
            "settings": {
                "transition_point_type": 0,  # 0 = time-based
                "transition_point": 800,      # 800ms
                "path": STINGER_PATH
            }
        },
        "Fade":    {"name": "Fade", "id": "fade_transition", "settings": {}},
        "Cut":     {"name": "Cut",  "id": "cut_transition",  "settings": {}},
    }
    transitions_list = [TRANSITION_DEFS.get(transition, TRANSITION_DEFS["Stinger"])]

    # ── Assemble collection ─────────────────────────────────────────────────
    collection = {
        "current_scene": scene_order[0]["name"] if scene_order else "Media",
        "current_program_scene": scene_order[0]["name"] if scene_order else "Media",
        "scene_order": scene_order,
        "name": collection_name,
        "groups": [],
        "quick_transitions": [
            {"name": "Cut",  "duration": 300, "hotkeys": [], "id": 1, "fade_to_black": False},
            {"name": "Fade", "duration": 300, "hotkeys": [], "id": 2, "fade_to_black": False},
            {"name": "Fade", "duration": 300, "hotkeys": [], "id": 3, "fade_to_black": True}
        ],
        "transitions": transitions_list,
        "saved_projectors": [],
        "canvases": [],
        "current_transition": transition,
        "transition_duration": 300,
        "preview_locked": False,
        "scaling_enabled": False,
        "scaling_level": -2,
        "scaling_off_x": 0.0,
        "scaling_off_y": 0.0,
        "virtual-camera": {"type2": 3},
        "modules": {
            "auto-scene-switcher": {
                "interval": 300, "non_matching_scene": "",
                "switch_if_not_matching": False, "active": False, "switches": []
            },
            "output-timer": {
                "streamTimerHours": 0, "streamTimerMinutes": 0, "streamTimerSeconds": 30,
                "recordTimerHours": 0, "recordTimerMinutes": 0, "recordTimerSeconds": 30,
                "autoStartStreamTimer": False, "autoStartRecordTimer": False,
                "pauseRecordTimer": True
            },
            "scripts-tool": []
        },
        "version": 1,
        "sources": sources
    }

    return collection


# ═══════════════════════════════════════════════════════════════════════════
#  GUI
# ═══════════════════════════════════════════════════════════════════════════

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("OBS Scene Collection Generator")
        self.resizable(False, False)
        self.configure(bg="#1e1e2e")

        # Styling
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TLabel",   background="#313244", foreground="#a6adc8", font=("Segoe UI", 10))
        style.configure("Header.TLabel", background="#1e1e2e", foreground="#cba6f7", font=("Segoe UI", 13, "bold"))
        style.configure("Sub.TLabel",  background="#313244", foreground="#a6adc8", font=("Segoe UI", 9))
        style.configure("TEntry",      fieldbackground="#313244", foreground="#cdd6f4",
                         insertcolor="#cdd6f4", bordercolor="#45475a", font=("Segoe UI", 10))
        style.configure("TButton",     background="#7f849c", foreground="#1e1e2e",
                         font=("Segoe UI", 10, "bold"), borderwidth=0, padding=6)
        style.map("TButton",
                  background=[("active", "#cba6f7"), ("pressed", "#b4befe")])
        style.configure("Accent.TButton", background="#cba6f7", foreground="#1e1e2e",
                         font=("Segoe UI", 11, "bold"), padding=8)
        style.map("Accent.TButton",
                  background=[("active", "#b4befe"), ("pressed", "#89b4fa")])
        style.configure("TFrame",      background="#1e1e2e")
        style.configure("Card.TFrame", background="#313244", relief="flat")
        style.configure("TSpinbox",    fieldbackground="#313244", foreground="#cdd6f4",
                         insertcolor="#cdd6f4", font=("Segoe UI", 10))

        self.preset_rows: list[dict] = []   # holds per-row widgets & vars
        self._build_ui()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self):
        pad = {"padx": 18, "pady": 6}

        # ── Header ──────────────────────────────────────────────────────────
        hdr = ttk.Frame(self, style="TFrame")
        hdr.pack(fill="x", padx=18, pady=(18, 4))
        ttk.Label(hdr, text="OBS Scene Creator Tool", style="Header.TLabel").pack(anchor="w")
        ttk.Label(hdr, text="Create scences for Media and PTZ Cameras that are compatible with KH Video Switcher",
                  background="#1e1e2e").pack(anchor="w")

        sep = tk.Frame(self, bg="#45475a", height=1)
        sep.pack(fill="x", padx=18, pady=8)

        # ── Global settings card ────────────────────────────────────────────
        card = ttk.Frame(self, style="Card.TFrame", padding=14)
        card.pack(fill="x", padx=18, pady=4)

        ttk.Label(card, text="Scene Collection Name").grid(row=0, column=0, sticky="w", pady=4)
        self.var_name = tk.StringVar(value="My PTZ Collection")
        ttk.Entry(card, textvariable=self.var_name, width=36).grid(row=0, column=1, sticky="ew", padx=(12,0))

        ttk.Label(card, text="Camera IP Address").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.var_ip = tk.StringVar(value="192.168.1.100")
        ttk.Entry(card, textvariable=self.var_ip, width=36).grid(row=1, column=1, sticky="ew", padx=(12,0), pady=(4, 0))

        # URL preview sits directly under the IP field
        self.var_preview = tk.StringVar()
        ttk.Label(card, text="URL Preview:").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Label(card, textvariable=self.var_preview,
                  foreground="#89dceb", background="#313244",
                  font=("Courier New", 9)).grid(row=2, column=1, sticky="w", padx=(12, 0), pady=4)
        self.var_ip.trace_add("write", lambda *_: self._update_preview())
        self._update_preview()

        ttk.Label(card, text="Number of Camera Presets").grid(row=3, column=0, sticky="w", pady=4)
        self.var_count = tk.IntVar(value=3)
        spin = ttk.Spinbox(card, from_=1, to=20, textvariable=self.var_count,
                           width=6, command=self._rebuild_preset_rows)
        spin.grid(row=3, column=1, sticky="w", padx=(12,0))

        # ── Optional scene checkboxes ────────────────────────────────────────
        sep_inner = tk.Frame(card, bg="#45475a", height=1)
        sep_inner.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 6))

        # Media checkbox (checked by default)
        self.var_media = tk.BooleanVar(value=True)
        media_cb = tk.Checkbutton(
            card,
            text='  Include "Media" scene',
            variable=self.var_media,
            command=self._on_media_toggle,
            bg="#313244", fg="#cdd6f4", selectcolor="#45475a",
            activebackground="#313244", activeforeground="#cdd6f4",
            font=("Segoe UI", 10), bd=0, highlightthickness=0,
            cursor="hand2"
        )
        media_cb.grid(row=5, column=0, columnspan=2, sticky="w", pady=(0, 2))
        ttk.Label(card,
                  text="Include a Media scene at the top of the scene list with a Display Capture source\n"
                  "NOTE: Once imported into OBS, you will need to manually select the correct display",
                  style="Sub.TLabel", justify="left"
                  ).grid(row=6, column=0, columnspan=2, sticky="w", padx=(28, 0), pady=(0, 8))

        # Black checkbox (unchecked by default)
        self.var_black = tk.BooleanVar(value=False)
        black_cb = tk.Checkbutton(
            card,
            text='  Include "Black" scene',
            variable=self.var_black,
            command=self._on_black_toggle,
            bg="#313244", fg="#cdd6f4", selectcolor="#45475a",
            activebackground="#313244", activeforeground="#cdd6f4",
            font=("Segoe UI", 10), bd=0, highlightthickness=0,
            cursor="hand2"
        )
        black_cb.grid(row=7, column=0, columnspan=2, sticky="w", pady=(0, 2))
        ttk.Label(card,
                  text="Adds an empty scene that can be used as a fade-to-black.",
                  style="Sub.TLabel", justify="left"
                  ).grid(row=8, column=0, columnspan=2, sticky="w", padx=(28, 0), pady=(0, 4))

        card.columnconfigure(1, weight=1)

        sep2 = tk.Frame(self, bg="#45475a", height=1)
        sep2.pack(fill="x", padx=18, pady=8)

        # ── Preset table header ──────────────────────────────────────────────
        th = ttk.Frame(self, style="TFrame")
        th.pack(fill="x", padx=18)
        ttk.Label(th, text="#",           width=4,  foreground="#a6adc8", background="#1e1e2e").grid(row=0, column=0)
        ttk.Label(th, text="Scene Name",  width=24, foreground="#a6adc8", background="#1e1e2e").grid(row=0, column=1, padx=6)
        ttk.Label(th, text="Position #",  width=10, foreground="#a6adc8", background="#1e1e2e").grid(row=0, column=2)

        # ── Scrollable preset rows ───────────────────────────────────────────
        container = ttk.Frame(self, style="TFrame")
        container.pack(fill="both", expand=True, padx=18, pady=4)

        self.canvas_scroll = tk.Canvas(container, bg="#1e1e2e", highlightthickness=0, height=220)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas_scroll.yview)
        self.canvas_scroll.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas_scroll.pack(side="left", fill="both", expand=True)

        self.rows_frame = ttk.Frame(self.canvas_scroll, style="TFrame")
        self.rows_window = self.canvas_scroll.create_window((0, 0), window=self.rows_frame, anchor="nw")
        self.rows_frame.bind("<Configure>", lambda e: self.canvas_scroll.configure(
            scrollregion=self.canvas_scroll.bbox("all")))
        self.canvas_scroll.bind("<Configure>", lambda e: self.canvas_scroll.itemconfig(
            self.rows_window, width=e.width))

        # ── Fixed greyed-out Media row (shown when Media checkbox is checked) ─
        self.media_row = tk.Frame(self.rows_frame, bg="#252535", pady=5)
        self.media_row.pack(fill="x", pady=(0, 1))
        tk.Label(self.media_row, text="1", width=4, bg="#252535",
                 fg="#585878", font=("Segoe UI", 10)).grid(row=0, column=0, padx=(8, 0))
        media_name = tk.Entry(self.media_row, width=26, bg="#252535", fg="#585878",
                              disabledbackground="#252535", disabledforeground="#585878",
                              relief="flat", font=("Segoe UI", 10), bd=4)
        media_name.insert(0, "Media")
        media_name.configure(state="disabled")
        media_name.grid(row=0, column=1, padx=8)
        tk.Label(self.media_row, text="—", width=8, bg="#252535",
                 fg="#585878", font=("Segoe UI", 10)).grid(row=0, column=2, padx=8)

        self._rebuild_preset_rows()

        # ── Fixed greyed-out Black row (hidden by default, appended last) ────
        self.black_row = tk.Frame(self.rows_frame, bg="#252535", pady=5)
        # Not packed by default — shown only when checkbox is checked
        self.black_num_label = tk.Label(self.black_row, text="—", width=4, bg="#252535",
                                        fg="#585878", font=("Segoe UI", 10))
        self.black_num_label.grid(row=0, column=0, padx=(8, 0))
        black_name = tk.Entry(self.black_row, width=26, bg="#252535", fg="#585878",
                              disabledbackground="#252535", disabledforeground="#585878",
                              relief="flat", font=("Segoe UI", 10), bd=4)
        black_name.insert(0, "Black")
        black_name.configure(state="disabled")
        black_name.grid(row=0, column=1, padx=8)
        tk.Label(self.black_row, text="—", width=8, bg="#252535",
                 fg="#585878", font=("Segoe UI", 10)).grid(row=0, column=2, padx=8)

        sep3 = tk.Frame(self, bg="#45475a", height=1)
        sep3.pack(fill="x", padx=18, pady=8)

        # ── Transition section ───────────────────────────────────────────────
        trans_card = ttk.Frame(self, style="Card.TFrame", padding=14)
        trans_card.pack(fill="x", padx=18, pady=4)

        ttk.Label(trans_card, text="Default Transition").grid(row=0, column=0, sticky="w", pady=4)

        self.var_transition = tk.StringVar(value="Stinger")
        for i, (label, value) in enumerate([("Stinger", "Stinger"), ("Fade", "Fade"), ("Cut", "Cut")]):
            rb = tk.Radiobutton(
                trans_card, text=label, variable=self.var_transition, value=value,
                bg="#313244", fg="#cdd6f4", selectcolor="#45475a",
                activebackground="#313244", activeforeground="#cdd6f4",
                font=("Segoe UI", 10), bd=0, highlightthickness=0, cursor="hand2"
            )
            rb.grid(row=0, column=i + 1, sticky="w", padx=(12, 0))

        ttk.Label(trans_card,
                  text="Sets the default scene transition in OBS. Selecting Stinger will\n"
                       "automatically download the stinger file to C:\\Program Files (x86)\\KH Switcher\\Stingers",
                  style="Sub.TLabel", justify="left"
                  ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 0))

        trans_card.columnconfigure(0, weight=0)

        sep4 = tk.Frame(self, bg="#45475a", height=1)
        sep4.pack(fill="x", padx=18, pady=8)

        # ── Progress bar (hidden until stinger download starts) ──────────────
        self.progress_frame = ttk.Frame(self, style="TFrame")
        self.progress_frame.pack(fill="x", padx=18, pady=(0, 4))
        self.progress_label = ttk.Label(self.progress_frame, text="", style="Sub.TLabel")
        self.progress_label.pack(anchor="w")
        self.progress_bar = ttk.Progressbar(self.progress_frame, orient="horizontal",
                                            mode="determinate", length=400)
        self.progress_bar.pack(fill="x", pady=(4, 0))
        self.progress_frame.pack_forget()  # hidden by default

        # ── Generate button ──────────────────────────────────────────────────
        btn_frame = ttk.Frame(self, style="TFrame")
        btn_frame.pack(pady=(0, 18))
        ttk.Button(btn_frame, text="⬇  Generate & Save Collection",
                   style="Accent.TButton", command=self._generate).pack()

    def _update_preview(self):
        ip = self.var_ip.get().strip() or "<camera-ip>"
        self.var_preview.set(f"http://{ip}/cgi-bin/ptzctrl.cgi?ptzcmd&poscall&1")

    def _on_media_toggle(self):
        """Show or hide the Media row and repack everything in order."""
        self._repack_all()

    def _on_black_toggle(self):
        """Show or hide the Black row and repack everything in order."""
        self._repack_all()

    def _repack_all(self):
        """Unpack all rows then repack in correct order: Media → presets → Black."""
        self.media_row.pack_forget()
        for r in self.preset_rows:
            r["widget"].pack_forget()
        if hasattr(self, "black_row"):
            self.black_row.pack_forget()

        if self.var_media.get():
            self.media_row.pack(fill="x", pady=(0, 1))
        for r in self.preset_rows:
            r["widget"].pack(fill="x", pady=1)
        if hasattr(self, "black_row") and self.var_black.get():
            self.black_row.pack(fill="x", pady=(1, 0))

        self._renumber_rows()

    def _renumber_rows(self):
        """Update all row number labels based on which fixed rows are visible."""
        offset = 2 if self.var_media.get() else 1
        for i, row_data in enumerate(self.preset_rows):
            row_data["num_label"].config(text=str(i + offset))
        # Black row always last
        if hasattr(self, "black_row") and self.var_black.get():
            total = (1 if self.var_media.get() else 0) + len(self.preset_rows) + 1
            self.black_num_label.config(text=str(total))

    def _rebuild_preset_rows(self):
        # Preserve existing values from editable rows only
        old_names = [r["name"].get() for r in self.preset_rows]
        old_pos   = [r["pos"].get()  for r in self.preset_rows]

        # Destroy only the editable preset rows (keep media_row and black_row)
        for widget in self.rows_frame.winfo_children():
            if widget is not self.media_row and widget is not self.black_row:
                widget.destroy()
        self.preset_rows.clear()

        try:
            count = int(self.var_count.get())
        except (ValueError, tk.TclError):
            count = 1
        count = max(1, min(20, count))

        offset = 2 if self.var_media.get() else 1

        for i in range(count):
            default_name = old_names[i] if i < len(old_names) else f"Preset {i+1}"
            default_pos  = old_pos[i]   if i < len(old_pos)   else i + 1

            row_bg = "#313244" if i % 2 == 0 else "#2a2a3e"
            row = tk.Frame(self.rows_frame, bg=row_bg, pady=5)
            row.pack(fill="x", pady=1)

            num_label = tk.Label(row, text=str(i + offset), width=4, bg=row_bg,
                                 fg="#a6adc8", font=("Segoe UI", 10))
            num_label.grid(row=0, column=0, padx=(8, 0))

            var_name = tk.StringVar(value=default_name)
            name_entry = tk.Entry(row, textvariable=var_name, width=26,
                                  bg="#45475a", fg="#cdd6f4", insertbackground="#cdd6f4",
                                  relief="flat", font=("Segoe UI", 10), bd=4)
            name_entry.grid(row=0, column=1, padx=8)

            var_pos = tk.IntVar(value=default_pos)
            pos_spin = tk.Spinbox(row, from_=1, to=255, textvariable=var_pos, width=8,
                                  bg="#45475a", fg="#cdd6f4", insertbackground="#cdd6f4",
                                  relief="flat", font=("Segoe UI", 10), buttonbackground="#313244",
                                  bd=4)
            pos_spin.grid(row=0, column=2, padx=8)

            self.preset_rows.append({"name": var_name, "pos": var_pos, "num_label": num_label, "widget": row})

        self._repack_all()

    # ── Stinger download ────────────────────────────────────────────────────

    STINGER_URL    = "https://raw.githubusercontent.com/aaroned/KH-Video-Switcher/master/Support/Stinger%20Files/Stinger120%20Quick.mov"
    STINGER_FOLDER = r"C:\Program Files (x86)\KH Switcher\Stingers"
    STINGER_FILE   = "Stinger120 Quick.mov"

    def _download_stinger(self, on_complete):
        """Download stinger file in a background thread, updating the progress bar."""
        dest_folder = self.STINGER_FOLDER
        dest_path   = os.path.join(dest_folder, self.STINGER_FILE)

        try:
            os.makedirs(dest_folder, exist_ok=True)
        except OSError as e:
            self.after(0, lambda: messagebox.showerror("Folder Error",
                f"Could not create stinger folder:\n{dest_folder}\n\n{e}"))
            self.after(0, self.progress_frame.pack_forget)
            return

        def reporthook(block_num, block_size, total_size):
            if total_size > 0:
                pct = min(100, block_num * block_size * 100 // total_size)
                self.after(0, lambda p=pct: self._update_progress(p))

        try:
            self.after(0, lambda: self.progress_label.config(text="Downloading stinger file…"))
            self.after(0, lambda: self.progress_frame.pack(fill="x", padx=18, pady=(0, 4),
                                                           before=self.winfo_children()[-1]))
            urllib.request.urlretrieve(self.STINGER_URL, dest_path, reporthook)
            self.after(0, lambda: self._update_progress(100))
            self.after(0, lambda: self.progress_label.config(text=f"✓ Stinger saved to {dest_path}"))
            self.after(500, lambda: self.progress_frame.pack_forget())
            self.after(500, on_complete)
        except Exception as e:
            self.after(0, self.progress_frame.pack_forget)
            self.after(0, lambda err=e: messagebox.showerror("Download Failed",
                f"Could not download stinger file:\n\n{err}\n\n"
                f"You can download it manually from:\n{self.STINGER_URL}"))

    def _update_progress(self, pct):
        self.progress_bar["value"] = pct

    # ── Generation ─────────────────────────────────────────────────────────

    def _generate(self):
        name       = self.var_name.get().strip()
        cam_ip     = self.var_ip.get().strip()
        video_dev  = "PTZ Camera"  # hardcoded

        if not name:
            messagebox.showerror("Missing Info", "Please enter a collection name.")
            return
        if not cam_ip:
            messagebox.showerror("Missing Info", "Please enter the camera IP address.")
            return

        presets = []
        seen_names = set()
        seen_pos   = set()
        for i, row in enumerate(self.preset_rows):
            pname = row["name"].get().strip()
            try:
                ppos = int(row["pos"].get())
            except (ValueError, tk.TclError):
                messagebox.showerror("Invalid Input", f"Preset {i+1}: position must be a number.")
                return
            if not pname:
                messagebox.showerror("Missing Info", f"Preset {i+1}: scene name cannot be empty.")
                return
            if pname in seen_names:
                messagebox.showerror("Duplicate Name", f'Scene name "{pname}" is used more than once.')
                return
            if ppos in seen_pos:
                if not messagebox.askyesno("Duplicate Position",
                        f"Position {ppos} is used more than once. Continue anyway?"):
                    return
            seen_names.add(pname)
            seen_pos.add(ppos)
            presets.append({"name": pname, "position": ppos})

        transition = self.var_transition.get()
        collection = build_obs_json(name, cam_ip, video_dev, presets,
                                    include_media=self.var_media.get(),
                                    include_black=self.var_black.get(),
                                    transition=transition)

        # Ask where to save
        filepath = filedialog.asksaveasfilename(
            title="Save OBS Scene Collection",
            defaultextension=".json",
            initialfile=f"{name}.json",
            filetypes=[("OBS Scene Collection", "*.json"), ("All Files", "*.*")]
        )
        if not filepath:
            return

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(collection, f, indent=4)

        def show_success():
            media_line = "  • Media\n" if self.var_media.get() else ""
            black_line = "  • Black\n" if self.var_black.get() else ""
            messagebox.showinfo("Success",
                f"Scene collection saved!\n\n"
                f"📁 {filepath}\n\n"
                f"Scenes created:\n" +
                media_line +
                "".join(f"  • {p['name']} (PTZ pos {p['position']})\n" for p in presets) +
                black_line +
                f"\nTransition: {transition}\n"
                f"Video source: PTZ Camera (shared across all preset scenes)\n\n"
                f"Import in OBS via:\n"
                f"Scene Collection → Import")

        # If Stinger selected, download file first then show success
        if transition == "Stinger":
            threading.Thread(
                target=self._download_stinger,
                args=(show_success,),
                daemon=True
            ).start()
        else:
            show_success()


# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = App()
    app.mainloop()
