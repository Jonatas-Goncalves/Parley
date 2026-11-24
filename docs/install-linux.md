# Installing Parley on Linux

Parley reuses the GTK 4 and PyGObject libraries that your distribution already
ships. Pick the package that matches your system.

## Debian and Ubuntu (.deb)

```sh
sudo apt install ./parley_<version>_all.deb
parley
```

The package declares its system dependencies, including `python3-gi`,
`gir1.2-gtk-4.0`, PortAudio, libsndfile and FFmpeg. It also depends on
`fonts-noto-cjk`, so Chinese, Japanese and Korean text renders correctly. On
first start Parley creates `~/.local/share/parley/venv` and installs the speech
packages that distributions do not package. A progress window stays open until
the environment is ready.

To remove Parley and keep your downloaded models:

```sh
sudo apt remove parley
```

To remove everything, delete `~/.local/share/parley` as well.

## openSUSE Leap and Tumbleweed (.rpm)

```sh
sudo zypper install ./parley-<version>-1.leap.noarch.rpm     # Leap
sudo zypper install ./parley-<version>-1.tumbleweed.noarch.rpm  # Tumbleweed
parley
```

The RPM for Leap uses `python311-gobject` and `python311-gobject-Gdk`; the
Tumbleweed build uses `python313-gobject` and `python313-gobject-Gdk`. Both
depend on `google-noto-sans-cjk-fonts`, install the same application payload and
bootstrap the remaining packages on first start.

## AppImage

```sh
chmod +x Parley-<version>-x86_64.AppImage
./Parley-<version>-x86_64.AppImage
```

The AppImage still needs GTK 4 and `python3-gi` from the host, because a language
model and speech stack are already large. It bundles Noto Sans CJK and registers
it at startup, so the CJK practice languages work even on a host without a CJK
font. Everything else is created in the user data folder on first start.

## Flatpak

```sh
flatpak install flathub org.gnome.Platform//48
flatpak install ./parley-<version>.flatpak
flatpak run io.github.jonatasgoncalves.Parley
```

The Flatpak uses the GNOME runtime and ships its own Python packages. It can
reach `~/.ollama` and the local backend over the network, and needs the
microphone through the PulseAudio socket. Preferences and downloaded audio live
in `~/.var/app/io.github.jonatasgoncalves.Parley/data/parley`.

## Where files live

| What | Where |
| --- | --- |
| Preferences | `~/.local/share/parley/config.json` |
| Python environment (deb/rpm/AppImage) | `~/.local/share/parley/venv` |
| Models and voices | `~/.local/share/parley/models` |
| Story audio | `~/.local/share/parley/stories` |
| Cache and temporary recordings | `~/.local/share/parley/cache` |
| Bootstrap log | `~/.local/share/parley/logs/bootstrap.log` |

For the Flatpak every path above is below
`~/.var/app/io.github.jonatasgoncalves.Parley/data/parley`.

Set `PARLEY_DATA_DIR` to move that folder, for example:

```sh
PARLEY_DATA_DIR=/mnt/games/parley parley
```

## Troubleshooting

**The window does not open on Wayland.** Try the X11 backend:

```sh
GDK_BACKEND=x11 parley
```

**No microphone.** Check the input device and, on Flatpak, that the microphone
permission is granted with `flatpak permission-show io.github.jonatasgoncalves.Parley`.

**The first start takes a long time.** The bootstrap downloads faster-whisper,
PyAV and Piper. Watch `~/.local/share/parley/logs/bootstrap.log`. Later starts
reuse the environment and are fast.

**The model does not answer.** Open Settings → Diagnostics. Parley needs either
Ollama (`ollama serve`) or llama.cpp (`llama-server`) running with a model
loaded. The conversation page waits for that state before it starts.
