# Building Parley

Everything is built from this repository; no generated sources are committed
except the story manifest and the packaged copy of that manifest.

## Checks

```sh
python -m pip install pytest ruff requests
ruff check src scripts tests packaging
python -m pytest
```

The test suite does not import GTK, so it runs on a headless machine. The
interface itself needs GTK 4 and PyGObject:

```sh
# openSUSE
sudo zypper install python313-gobject python313-gobject-Gdk gtk4 typelib-1_0-Gtk-4_0 libportaudio2 libsndfile1

# Debian / Ubuntu
sudo apt install python3-gi gir1.2-gtk-4.0 libportaudio2 libsndfile1
```

## Native run

```sh
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
pip install -e ".[dev]"
python -m parley
```

On a headless machine use `GDK_BACKEND=x11` with an X server or Xvfb.

## Linux packages

All Linux packages share `packaging/linux/stage-app.sh`. It installs the
launcher, the source tree, the icon set and the desktop metadata under `/usr`.
The launcher creates a private virtual environment on first start and installs
`requirements.txt` there; GTK and PyGObject come from the distribution.

### Debian and Ubuntu

```sh
bash packaging/linux/build-deb.sh
# dist/parley_<version>_all.deb
```

Requires `dpkg-deb` and `fakeroot`. The package is architecture independent
because only Python and data files are installed. `fonts-noto-cjk` is a runtime
dependency, so Chinese, Japanese and Korean text renders after installation.

### openSUSE Leap and Tumbleweed

```sh
bash packaging/linux/build-rpm.sh
# dist/parley-<version>-1.noarch.rpm
```

Requires `rpmbuild`. `packaging/linux/parley.spec` selects `python311-gobject`
and `python311-gobject-Gdk` on Leap (detected through `sle_version`), and
`python313-gobject` plus `python313-gobject-Gdk` on Tumbleweed.
`google-noto-sans-cjk-fonts` is a runtime dependency for CJK practice languages.
Build each variant inside the matching distribution, as the release workflow
does with the `opensuse/leap` and `opensuse/tumbleweed` containers. The output
name includes the flavour (`...-1.leap.noarch.rpm` or
`...-1.tumbleweed.noarch.rpm`) so both can live in the same release. Set
`PARLEY_RPM_FLAVOR` to override the detection.

### AppImage

```sh
bash packaging/appimage/build-appimage.sh
# dist/Parley-<version>-x86_64.AppImage
```

The AppImage still needs the host GTK 4, PyGObject and Python, because shipping
a complete GTK stack plus a speech model in one file is not useful. The
`AppRun` script points the launcher at the payload inside the AppDir. If FUSE
is unavailable the build retries with `APPIMAGE_EXTRACT_AND_RUN`.

The build downloads **Noto Sans CJK** and its licence, verifies their SHA-256
checksums and places them in `usr/share/fonts/noto-cjk`. `AppRun` writes a
small fontconfig file that adds that folder to the normal system configuration,
so the bundled font is found even when the host has none.

### Flatpak

```sh
bash packaging/flatpak/build-flatpak.sh            # build and install locally
bash packaging/flatpak/build-flatpak.sh --export   # dist/Parley-<version>.flatpak
```

The manifest uses `org.gnome.Platform` 48. The speech packages are installed
into `/app` at build time, so the Flatpak has no first-run pip step. Build
dependencies are downloaded from Flathub. A `noto-cjk` module downloads **Noto
Sans CJK** with a pinned SHA-256 checksum and installs it into
`/app/share/fonts/noto-cjk`, which the runtime font configuration scans.

## Windows

The Windows build uses micromamba with conda-forge, which provides GTK 4,
PyGObject and Python. PyInstaller creates a `onedir` build and Inno Setup wraps
it in an installer.

```powershell
pwsh -ExecutionPolicy Bypass -File packaging/windows/install-windows.ps1
pwsh -ExecutionPolicy Bypass -File packaging/windows/build-installer.ps1 -SkipBuild
# packaging/windows/release/Parley-Setup-<version>.exe
```

`install-windows.ps1` downloads micromamba into `packaging/windows/.micromamba`
and creates the environment in `packaging/windows/.conda`. The first run takes
a while; pass `-Force` to recreate the environment. It also downloads **Noto
Sans CJK** and its licence into `assets/fonts/noto-cjk`, verifying both
SHA-256 checksums before the PyInstaller step.

`parley.spec` copies the conda GTK runtime next to `Parley.exe`:

- DLLs and helper executables from `Library/bin`
- typelibs into `girepository-1.0`
- GSettings schemas into `glib-2.0/schemas`
- icon themes, GTK settings and fonts
- the bundled CJK font into `share/fonts/noto-cjk`

`packaging/windows/launcher.py` runs before the GTK import. It registers the
bundled font privately with GDI and writes a fontconfig file that adds the
bundled folder, the Windows font folder and the per-user font folder. This
keeps CJK text working on Windows editions that do not ship the relevant
language fonts.

`src/parley/__main__.py` sets `GI_TYPELIB_PATH`, `GSETTINGS_SCHEMA_DIR`,
`GTK_DATA_PREFIX` and `GTK_EXE_PREFIX` for the frozen build. It also generates
the gdk-pixbuf loader cache in `%LOCALAPPDATA%\Parley` on first launch, because
the cache stores absolute DLL paths.

## Android

The Android companion is a separate Kotlin/Gradle project under
`packaging/android`. It is not part of the Python package or the desktop release
artifacts. It needs JDK 17, Android SDK platform 34 and build-tools 34:

```sh
cd packaging/android
./gradlew assembleDebug
# app/build/outputs/apk/debug/app-debug.apk
```

The app uses the system speech recogniser and text-to-speech engine and sends
chat requests to `llama-server` from `llama.cpp`, normally started inside Termux
on the same phone. Neither the model nor the inference engine is bundled in the
APK. The interface mirrors the desktop app: language buttons, Voice Practice
(continuous and push-to-talk), Pronunciation, Spoken Stories, Complete the
Sentence, conversation progress, a personal level test and Settings.

Translations, scenarios and the story catalogue are generated from the desktop
sources before building:

```sh
python scripts/export_android_assets.py
```

This writes `i18n.json`, `scenarios.json` and `stories.json` under
`packaging/android/app/src/main/assets`. See
[packaging/android/README.md](../packaging/android/README.md) for the Termux
offline instructions, the optional LAN setup and current limitations.

## Continuous integration

`.github/workflows/ci.yml` runs lint, a syntax check and the test suite on every
push and pull request.

`.github/workflows/release.yml` runs on every push to `main`. It builds all six
artifacts (deb, Leap rpm, Tumbleweed rpm, AppImage, Flatpak and Windows
installer), writes `SHA256SUMS`, and publishes a GitHub release tagged
`v<version>-<short-sha>`.

## Story audio

Story recordings are committed under `assets/stories` and are never included in
a package. Regenerate the manifest after adding a file:

```sh
python scripts/build_stories_manifest.py
```

See [stories.md](stories.md).
