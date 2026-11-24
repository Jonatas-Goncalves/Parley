# Parley Android (Termux)

Android-only source for the Parley Termux variant. This variant uses `llama-server` (llama.cpp) running in Termux on-device, with Android system STT/TTS.

## Build

```sh
cd packaging/android
./gradlew assembleDebug
```

APK output: `packaging/android/app/build/outputs/apk/debug/`.

## Release

Publishing a GitHub release triggers the Android workflow, which builds the APK and uploads it to release assets.


## Android (in development)

The Android APKs (`Parley-llama` and `Parley-Termux`) are still in development and **are not considered stable** in this release. Bugs, behavior changes, and compatibility issues may occur. Use them for testing and feedback.
