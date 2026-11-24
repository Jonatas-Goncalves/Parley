# Parley for Android

This folder contains the Android companion app for Parley. It mirrors the
desktop experience and keeps the model outside the APK: the language model is
served by `llama.cpp` (`llama-server`), normally running inside Termux on the
phone itself.

No model and no inference engine are bundled in the APK, and no cloud service is
used. Everything stays on the device.

## What it does

The app follows the same flow as the desktop application:

- **Home:** pick one of the eight practice languages with a button.
- **Practice hub:** Voice Practice, Pronunciation, the supplements and the
  conversation progress card.
- **Voice Practice:** continuous listening or push-to-talk, streamed replies,
  spoken answers, a spoken turn history and a personal session score.
- **Pronunciation:** a generated phrase, playback, a spoken attempt and a
  word-by-word comparison in green and red.
- **Spoken Stories:** a catalogue shipped with the app; the MP3 files are
  downloaded only when you ask for them, with SHA-256 verification, and can be
  deleted again.
- **Complete the Sentence:** a generated text is spoken and played with seeking
  and playback speed; answers are marked in green and red.
- **Progress:** per-language history, averages, a personal level estimate and a
  five-prompt level test. The score only measures spoken conversation and is
  inspired by IELTS/TOEFL speaking tasks without having any official value.
- **Settings:** interface language, light/dark/system theme, practice and native
  language, llama.cpp address and model name, connection test, voice hints,
  story pack controls, session history and diagnostics.
- **Offline setup:** short Termux instructions with buttons that open Termux or
  the F-Droid page.

Speech input uses the recogniser installed on the device and spoken replies use
the system text-to-speech engine. The llama.cpp client talks to the
OpenAI-compatible `/v1/chat/completions` endpoint exposed by `llama-server`.

## Shared data assets

The desktop application is the source of truth for translations, role-play
scenarios and the spoken-story catalogue. The Android app ships them as JSON
assets generated from the desktop sources:

```sh
python scripts/export_android_assets.py
```

This writes:

```
packaging/android/app/src/main/assets/i18n.json
packaging/android/app/src/main/assets/scenarios.json
packaging/android/app/src/main/assets/stories.json
```

Run the script after changing `src/parley/core/i18n.py`, the scenario list or the
story manifest, then rebuild the APK.

## Licensing

The whole Android route is licence-friendly:

- **llama.cpp** is distributed under the MIT licence. You can run it, bundle it
  or link against it without releasing your app under a copyleft licence. The
  Termux package `llama-cpp` ships the same MIT-licensed code.
- **Qwen2.5** model weights are released under the Apache 2.0 licence. You may
  download and run them locally, including in a commercial product, as long as
  the licence and attribution notices are kept.

On-device inference could also be compiled into the APK, but that makes it much
larger, complicates the GPU backends and requires a native build for every ABI.
The app therefore keeps the engine and the model outside the APK and uses
Termux, which is the simplest route that works without a network while
travelling.

## Requirements

- JDK 17 or newer.
- Android SDK with platform 34 and build-tools 34.
- Android Studio (recommended) or a local Gradle installation.
- Termux from F-Droid with the `llama-cpp` package and a GGUF model, as
  described below.

## Build

Open this folder in Android Studio and let it sync, or run:

```sh
cd packaging/android
./gradlew assembleDebug
```

The APK is written to:

```
app/build/outputs/apk/debug/app-debug.apk
```

Install it with:

```sh
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

The wrapper downloads Gradle 8.7 on first use. The project uses Android Gradle
Plugin 8.5.2 and Kotlin 1.9.24.

## Offline use with Termux

Termux is an Android terminal that can install a full `llama.cpp` build from its
package repository. This route needs no computer and no network after the
one-time setup, so it works during trips.

1. Install Termux from F-Droid:

   <https://f-droid.org/packages/com.termux/>

   Use the F-Droid build. The Play Store build is outdated and is no longer
   maintained.

2. Open Termux and update the packages:

   ```sh
   pkg update && pkg upgrade
   pkg install llama-cpp
   ```

3. Copy a GGUF model to the phone. You can download it in Termux, copy it over
   USB, or place it in `Download` with a file manager. The Parley model tiers
   are:

   | Tier | File |
   | --- | --- |
   | weak | `qwen2.5-1.5b-instruct-q4_K_M.gguf` |
   | medium | `qwen2.5-3b-instruct-q4_K_M.gguf` |
   | strong | `qwen2.5-7b-instruct-q4_K_M.gguf` |

4. Start the OpenAI-compatible server from Termux:

   ```sh
   llama-server \
     -m /sdcard/Download/qwen2.5-3b-instruct-q4_K_M.gguf \
     --host 127.0.0.1 --port 8080
   ```

   On a phone the 1.5B model is noticeably faster and uses less memory; the 3B
   model gives better answers. The 7B model needs a recent device with plenty of
   RAM.

5. Open Parley. The address defaults to `http://127.0.0.1:8080` and the model
   name to `local`, which is all `llama-server` needs.

Keep Termux running while you practice. Android may stop background processes;
open Termux again if the connection drops. Everything stays on the device, so
no data leaves the phone.

The **Set up offline with Termux** entry in Settings shows a short version of
these instructions and can launch Termux or the F-Droid page directly.

If you run `llama-server` on a computer instead, start it with
`--host 0.0.0.0` and enter that computer's LAN address in Parley. This needs a
network, so it is only useful at home; do not expose the port to the internet.

## Local app data

The app keeps everything in its private storage:

- `scores.json` stores the session history used by the progress card and the
  level test. It is capped at the 500 most recent sessions.
- `stories/` stores the MP3 files you chose to download.
- Shared preferences store the interface language, theme, practice and native
  language, llama.cpp address, model name and the last Voice Practice mode.

Removing the app deletes all of it. Story audio can also be removed from the
Spoken Stories screen or from Settings.

## Limitations

- The recognised language depends on the speech recogniser installed on the
  device; some devices only ship one or two languages.
- Text-to-speech quality depends on the installed system voices.
- No background service, notifications or widget.
- Inference relies on Termux and a manually downloaded GGUF file.
- The level estimate is a personal practice score, not an official IELTS or
  TOEFL result.
