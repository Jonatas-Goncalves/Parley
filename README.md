# Parley

Parley is a local language tutor for the Linux and Windows desktop. You speak,
Parley answers, and the whole conversation stays on your computer.

The interface is built with GTK 4, the speech recognition runs through
faster-whisper, and the spoken replies use Piper voices. The tutor itself is a
small language model served by Ollama or llama.cpp; Parley can detect, start and
preload that service for you.

<p align="center">
  <img src="assets/icons/parley-256.png" alt="Parley icon" width="128">
</p>

## What you can do

- **Voice Practice** — role-play one of 19 everyday situations with a tutor that
  replies in the language you are learning. Choose continuous listening or
  push-to-talk, speak or type, and read a short note about your mistakes after
  each turn.
- **Pronunciation** — read a generated phrase out loud and see which words were
  recognised. Correct words turn green, missed words turn red.
- **Spoken Stories** — listen to 49 short public-domain stories. The audio pack
  is downloaded only when you ask for it in Settings.
- **Complete the Sentence** — listen to a short generated text and fill in the
  blanks. The player above the text has seek and speed controls; **Finish**
  highlights each answer in green or red.
- **Conversation progress** — every Voice Practice session gets a personal
  0-100 score based only on speaking and listening: pace, pauses, vocabulary
  variety, answer length and recogniser confidence. History is stored per
  language, and a short guided level test gives a first estimate. The scale is
  inspired by IELTS and TOEFL speaking tasks but is not an official exam result.
- **Eight languages** — Portuguese, English, Spanish, French, Italian, Japanese,
  Korean and Mandarin Chinese. The interface language is independent from the
  language you are practising.

Everything is local: speech recognition, text generation and speech synthesis.
No account, no cloud service and no telemetry.

## Install

### Linux

Parley is available as a `.deb`, an `.rpm` for openSUSE Leap and Tumbleweed, an
AppImage and a Flatpak. Download the file that matches your distribution from
the latest release and follow [docs/install-linux.md](docs/install-linux.md).

The Linux packages reuse the GTK 4 and PyGObject libraries shipped by your
distribution. On first start Parley creates a private Python environment in
`~/.local/share/parley/venv` and installs the remaining speech dependencies
there. This is a one-time step and needs an internet connection.

### Windows

Download the `Parley-Setup-*.exe` installer from the latest release. It bundles
Python, GTK 4 and the speech libraries, so no separate setup is required. See
[docs/install-windows.md](docs/install-windows.md).

### First run

Onboarding offers two ways to run the model:

| Backend | Best for |
| --- | --- |
| **Ollama** | The easiest option. Install it from [ollama.com](https://ollama.com); Parley starts it and pulls the selected model. |
| **llama.cpp** | A lighter, self-contained option. Parley downloads a GGUF file and starts `llama-server` itself. |

Parley then asks for one of three quality tiers:

| Tier | Model | RAM |
| --- | --- | --- |
| Weak | `qwen2.5:1.5b-instruct-q4_K_M` | 4 GB |
| Medium | `qwen2.5:3b-instruct-q4_K_M` | 8 GB |
| Strong | `qwen2.5:7b-instruct-q4_K_M` | 16 GB |

Conversation quality depends on the tier. A weaker model is faster but makes
more grammar and vocabulary mistakes.

Onboarding also chooses the initial model for the detected hardware. From the
second launch onward the same backend is started and the model is preloaded
automatically, so the first screen is ready to use.

#### Conversations and models

Parley only opens a conversation when a backend is running with a model loaded.
If a compatible Ollama or llama.cpp service is already running, Parley reuses it
instead of starting another one. If nothing is running, the setup chosen during
onboarding is started, the model is downloaded once, and the session begins when
the model is ready.

## Fonts

Chinese, Japanese and Korean text needs a CJK font. The `.deb` and `.rpm`
packages declare `fonts-noto-cjk` / `google-noto-sans-cjk-fonts` as a
dependency, and the AppImage, Flatpak and Windows installer bundle
**Noto Sans CJK** (SIL Open Font License 1.1), so a normal installation shows
those characters without extra steps. The bundled font is placed next to the
application and registered with the system font stack at startup.

If you run Parley from a source checkout and see empty squares, install a CJK
font package and restart:

```sh
# openSUSE
sudo zypper install google-noto-sans-cjk-fonts

# Debian / Ubuntu
sudo apt install fonts-noto-cjk

# Fedora
sudo dnf install google-noto-sans-cjk-fonts

# Arch
sudo pacman -S noto-fonts-cjk
```

Settings also shows a hint when the selected practice language is Chinese,
Japanese or Korean and no CJK font is found. The bundled font and its licence
are downloaded and checksum-verified at build time, so the repository does not
store the 19 MB font file.

## Build from source

Linux needs Python 3.11 or newer, GTK 4, PyGObject and PortAudio:

```sh
# openSUSE
sudo zypper install python313 python313-gobject python313-gobject-Gdk gtk4 \
    typelib-1_0-Gtk-4_0 libportaudio2 libsndfile1 ffmpeg

# Debian / Ubuntu
sudo apt install python3 python3-venv python3-gi gir1.2-gtk-4.0 \
    libportaudio2 libsndfile1 ffmpeg
```

Then:

```sh
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
pip install -e ".[dev]"
python -m parley
```

On a headless machine use `GDK_BACKEND=x11` and an X server.

The project uses `ruff` for linting and `pytest` for the test suite:

```sh
ruff check src scripts tests packaging
pytest
```

Packaging instructions for every artifact live in [docs/build.md](docs/build.md).

## Spoken Stories

The story recordings are committed under `assets/stories`. Installers never
include them; Settings downloads the pack to the user data folder only after the
user confirms. The list, count and total size are read from
`assets/stories/manifest.json`, so adding a new MP3 and regenerating the
manifest is enough to update the interface:

```sh
python scripts/build_stories_manifest.py
```

See [docs/stories.md](docs/stories.md) for details.

## Android (in development)

The Android APKs (`Parley-llama` and `Parley-Termux`) are still in development and **are not considered stable**. Bugs, behavior changes, and compatibility issues may occur. Use them for testing and feedback.

- **`Parley-llama`**: Parley with integrated `llama.cpp`.
- **`Parley-Termux`**: Parley that connects to a `llama.cpp` server running in Termux.

## License

Parley is released under the MIT License. See [LICENSE](LICENSE).

The Spoken Stories recordings are public-domain works read aloud. The audio
files are distributed with the project for personal listening practice.
