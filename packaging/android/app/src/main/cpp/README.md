# Bundled inference library

`llama.cpp` is vendored here at tag `v0.9.0` from
<https://github.com/ggml-org/llama.cpp>. Only the sources needed for the
Android static/shared library are kept: `cmake/`, `ggml/`, `include/`, `src/`,
`vendor/`, the root CMake files and the licence texts.

The application build is defined in `CMakeLists.txt` in this directory. It
creates `libparley_llama_jni.so`, which exposes the JNI entry points declared in
`LlamaEngine.kt`, and links against the `llama` target from the vendored tree.

The 16 KB page-size linker flag is applied to the JNI library so the same APK
loads on devices with 4 KB and 16 KB memory pages.

To refresh the vendored source, replace the `llama.cpp` directory with a fresh
checkout of the same tag, then rebuild. Check the `llama.h` API used by
`llama_jni.cpp` before moving to a newer tag.
