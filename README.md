# Parley Android

Android-only source for Parley (llama.cpp variant).

## Build

```sh
cd packaging/android
./gradlew assembleDebug
```

The APK is written to `packaging/android/app/build/outputs/apk/debug/`.

## Release

Publishing a GitHub release triggers the Android workflow, which builds the debug APK and uploads it to the release assets.


## Android (in development)

The Android APKs (`Parley-llama` and `Parley-Termux`) are still in development and **are not considered stable** in this release. Bugs, behavior changes, and compatibility issues may occur. Use them for testing and feedback.
