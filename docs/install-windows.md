# Installing Parley on Windows

## Installer

1. Download `Parley-Setup-<version>.exe` from the latest release.
2. Run the installer. Windows SmartScreen may warn about an unsigned build;
   choose **More info → Run anyway**.
3. Start Parley from the Start menu.

The installer bundles Python, GTK 4, PyGObject, the speech libraries and Noto
Sans CJK, so no separate setup is needed. It installs for the current user under
`%LOCALAPPDATA%\Programs\Parley`, so no administrator prompt appears. The
uninstaller is available from **Settings → Apps**.

Preferences, models and downloaded audio are stored in:

```
%APPDATA%\Parley
```

Set `PARLEY_DATA_DIR` before starting Parley to use another folder.

## Backend setup

Parley runs the language model locally with one of two services:

- **Ollama** — install it from [ollama.com](https://ollama.com/download). Parley
  starts `ollama serve` and pulls the model selected during onboarding.
- **llama.cpp** — no separate install is required. Parley downloads a GGUF model
  and starts its own `llama-server` on the next launch.

A conversation only starts when the backend is running with a model loaded.
Parley reuses an already-running service when it finds one. On the second launch
the chosen backend and model are started and preloaded automatically.

If Windows Firewall asks about the local server, allow access on private
networks only. Parley listens on `127.0.0.1` and does not accept remote
connections.

## Microphone and audio

Parley uses the default recording and playback devices from Windows sound
settings. If no device is found:

1. Open **Settings → System → Sound** and confirm an input device is enabled.
2. Allow microphone access under **Privacy & security → Microphone**.
3. Restart Parley.

## Development build

The release build uses conda-forge for GTK. To recreate it locally, install
[micromamba](https://mamba.readthedocs.io/en/latest/installation/micromamba-installation.html)
and run:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/install-windows.ps1
```

The script creates `packaging/windows/.conda`, installs `gtk4`, `pygobject`,
Python, PyInstaller and the speech packages, then builds
`packaging/windows/dist/Parley/Parley.exe`. It downloads micromamba on the first
run, so a separate micromamba installation is not required.

To produce the installer, install [Inno Setup](https://jrsoftware.org/isinfo.php)
and run:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build-installer.ps1
```

## Troubleshooting

**The window looks unstyled.** The GTK runtime expects its `share/icons`,
`share/glib-2.0` and `lib/girepository-1.0` folders next to `Parley.exe`. These
are included by the installer; a manual copy of an incomplete folder can break
the theme.

**The model is very slow.** Choose the weak tier in Settings, or close other
memory-heavy applications. A 16 GB machine should use the strong tier; 8 GB
machines are happiest with medium.

**Antivirus flags the installer.** PyInstaller executables are sometimes flagged
by heuristics. The build is reproducible from this repository; the workflow
attaches the SHA-256 sums to every release.
