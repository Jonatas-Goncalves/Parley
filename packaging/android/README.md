# Parley for Android

This folder contains the Android companion app for Parley. It mirrors the
desktop experience and runs the language model directly inside the app through
a bundled llama.cpp library. There is no local HTTP server, no Termux and no
cloud service. Everything stays on the device.

## Model tiers

Settings offers three model tiers and a custom option. The RAM values shown in
the app are the memory needed while the model is loaded:

| Tier | Model | Download | RAM needed | Files |
| --- | --- | --- | --- | --- |
| Basic | Qwen2.5 1.5B Instruct Q4_K_M | about 1.1 GB | about 1 GB | 1 |
| Normal | Qwen2.5 3B Instruct Q4_K_M | about 2.0 GB | about 2 GB | 1 |
| Advanced | Qwen2.5 7B Instruct Q4_K_M | about 4.7 GB | about 4.7 GB | 2 |

The Advanced tier is sharded. Its two GGUF files are downloaded in order and
loaded with `llama_model_load_from_splits()`. It needs a high-RAM device and is
much slower than the other tiers on a phone CPU.

You can also load a GGUF file with the system file picker or download one from
a custom HTTPS URL. Downloaded files live in app-private storage and can be
removed from Settings.

## What it does

The app follows the same flow as the desktop application:

- **Home:** pick one of the eight practice languages with a button.
- **Practice hub:** Voice Practice, Pronunciation, the supplements and the
  conversation progress card.
- **Voice Practice:** continuous listening or push-to-talk, token-streamed
  replies, spoken answers, a spoken turn history and a personal session score.
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
  language, model download and selection, keep-screen-on, voice hints, story
  pack controls, session history and diagnostics.

Speech input uses the recogniser installed on the device and spoken replies use
the system text-to-speech engine. Replies are streamed from native code through
a token callback and rendered sentence by sentence.

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

## Requirements

- JDK 17 or newer.
- Android SDK with platform 34, build-tools 34, NDK 27.2 and CMake 3.31.
- A device with ARM64 support. The native library is built for `arm64-v8a`.
- Android 8.0 (API 26) or newer; Android 11 and newer are recommended for the
  larger models.

## Build

The native library is compiled from the pinned llama.cpp checkout in
`app/src/main/cpp/llama.cpp`. Gradle downloads the required CMake and NDK
components if they are not installed yet.

```sh
cd packaging/android
./gradlew assembleDebug
```

The APK is written to:

```
app/build/outputs/apk/debug/app-debug.apk
```

Its application ID is `io.github.jonatasgoncalves.parley.llama`, so it installs
side by side with the current Parley build. The launcher label remains Parley.

Install it with:

```sh
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

The wrapper downloads Gradle 8.7 on first use. The project uses Android Gradle
Plugin 8.5.2 and Kotlin 1.9.24.

## Licensing

- **llama.cpp** is distributed under the MIT licence and is linked into the app.
- **Qwen2.5** model weights are released under the Apache 2.0 licence. The
  licence and attribution notices must be kept when downloading the weights.
