# OBS Scene Collection Generator
### Built for KH Video Switcher

A Windows desktop tool that generates OBS Studio scene collection files pre-configured for PTZ camera control. Fill in your camera IP, name your presets, and the tool generates a ready-to-import `.json` file — no manual OBS configuration required.

---

## Features

- **PTZ Camera Preset Scenes** — creates one scene per camera preset, each with a hidden browser source that fires the PTZ HTTP command when the scene becomes active in OBS
- **Media Scene** *(optional)* — a scene with a Display Capture source for showing laptop screens or presentations
- **Black Scene** *(optional)* — an empty scene for clean fade-to-black transitions
- **Transition Configuration** — choose between Stinger, Fade, or Cut as the default OBS transition
- **Stinger Auto-Download** — if Stinger is selected, the stinger video file is automatically downloaded and saved to the correct folder
- **Live URL Preview** — shows the PTZ URL as you type the camera IP so you can verify it before generating

---

## Requirements

- Windows x64
- OBS Studio (any recent version)
- A PTZ camera accessible over HTTP on your local network
- Internet connection (only required if using the Stinger transition)

---

## Installation

1. Go to the [Releases](../../releases) page
2. Download `OBS_Scene_Generator.exe`
3. Run it — Windows will prompt for Administrator permission, which is required to save the stinger file to `C:\Program Files (x86)\KH Switcher\Stingers`

No installation needed. The `.exe` is fully self-contained.

---

## How to Use

### Step 1 — Fill in the settings

| Field | Description |
|---|---|
| **Scene Collection Name** | The name that will appear in OBS under Scene Collection |
| **Camera IP Address** | The local IP of your PTZ camera (e.g. `192.168.1.100`) |
| **Number of Camera Presets** | How many preset scenes to create |

### Step 2 — Choose optional scenes

- **Include "Media" scene** — checked by default. Adds a scene with a Display Capture source at the top of the list. After importing into OBS you will need to manually select the correct display in the source settings.
- **Include "Black" scene** — unchecked by default. Adds an empty scene at the bottom of the list, useful for fading to black by transitioning to it with a Fade.

### Step 3 — Name your presets

Each row in the scene list represents one camera preset scene. Give each scene a name (e.g. *Wide*, *Podium*, *Close-up*) and set its PTZ position number. The position number maps to the preset stored on the camera.

### Step 4 — Choose a transition

| Transition | Description |
|---|---|
| **Stinger** *(default)* | Uses a custom stinger video. The file is automatically downloaded and configured at 800ms. |
| **Fade** | Standard OBS fade transition |
| **Cut** | Instant cut with no transition effect |

### Step 5 — Generate

Click **Generate & Save Collection**. Choose where to save the `.json` file. If Stinger is selected, the stinger file will download automatically before the success message appears.

### Step 6 — Import into OBS

1. Open OBS Studio
2. Go to **Scene Collection → Import**
3. Browse to and select the generated `.json` file
4. Click **Import**

---

## How PTZ Control Works

Each camera preset scene contains a hidden browser source configured with the URL:

```
http://[camera-ip]/cgi-bin/ptzctrl.cgi?ptzcmd&poscall&[position]
```

The browser source has **"Refresh browser when scene becomes active"** enabled. When you switch to a scene in OBS, the browser source silently fires the HTTP request, which moves the camera to that preset position. The visible output is the PTZ Camera video capture source, which is shared across all preset scenes.

---

## How the Stinger Works

When Stinger is selected:

- The stinger video file (`Stinger120 Quick.mov`) is downloaded from the KH Video Switcher repository
- It is saved to `C:\Program Files (x86)\KH Switcher\Stingers\`
- The folder is created automatically if it doesn't exist
- The transition is pre-configured in the scene collection with an 800ms transition point
- OBS will use this file automatically when the collection is imported — no manual browsing required

> **Note:** Administrator privileges are required to write to `Program Files`. The tool will prompt for this automatically on launch.

---

## Troubleshooting

**The tool won't open / closes immediately**
Accept the Administrator prompt when Windows asks. The tool requires elevated permissions to save the stinger file.

**Stinger download failed**
Check your internet connection. You can download the file manually from the [KH Video Switcher repository](https://github.com/aaroned/KH-Video-Switcher) and place it at:
`C:\Program Files (x86)\KH Switcher\Stingers\Stinger120 Quick.mov`

**Camera doesn't move when switching scenes**
- Verify the camera IP address is correct
- Confirm the camera is reachable on the network (try the URL in a browser)
- Check that the position numbers match the presets stored on the camera

**OBS shows "Missing file" for the stinger**
Make sure the tool was run as Administrator so it had permission to create the folder and download the file. Re-run the tool and accept the UAC prompt.

**Media scene shows the wrong display**
After importing, click the Display Capture source in OBS and select the correct monitor from the dropdown.

---

## Building from Source

Requires Python 3.12+ and PyInstaller.

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "OBS_Scene_Generator" obs_scene_generator.py
```

The executable will be in the `dist/` folder.

Releases are built automatically for Windows x64 via GitHub Actions when a version tag is pushed.

---

## License

This project is part of the KH Video Switcher suite.
