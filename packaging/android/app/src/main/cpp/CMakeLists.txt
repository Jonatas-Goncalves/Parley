cmake_minimum_required(VERSION 3.22.1)
project(parley_llama)

# AGP builds Debug variants with -O0. llama.cpp is far too slow under -O0:
# a 233-token prompt took over a minute on a phone while the same model in a
# Release build answered in seconds. Always optimize the native stack, even
# for the installable debug APK used for device testing.
if (NOT CMAKE_BUILD_TYPE STREQUAL "Release")
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Optimized native build" FORCE)
endif()

# llama.cpp 1.0.0 can ship one arm64-v8a APK with several CPU backends and pick
# the fastest one the phone actually supports (dotprod, i8mm, SVE, ...).
# GGML_CPU_ALL_VARIANTS requires GGML_BACKEND_DL and BUILD_SHARED_LIBS.
set(BUILD_SHARED_LIBS         ON CACHE BOOL "" FORCE)
set(GGML_BACKEND_DL           ON CACHE BOOL "" FORCE)
set(GGML_CPU_ALL_VARIANTS     ON CACHE BOOL "" FORCE)
set(GGML_NATIVE               OFF CACHE BOOL "" FORCE)
# llamafile adds ARM NEON/DOTPROD runtime-dispatched matrix kernels.
set(GGML_LLAMAFILE            ON CACHE BOOL "" FORCE)
set(GGML_OPENMP               OFF CACHE BOOL "" FORCE)
# KleidiAI is fetched at configure time by upstream; use the vendored copy so
# the build works offline and is reproducible.
set(GGML_CPU_KLEIDIAI         ON CACHE BOOL "" FORCE)
set(FETCHCONTENT_SOURCE_DIR_KLEIDIAI
    "${CMAKE_CURRENT_SOURCE_DIR}/kleidiai" CACHE PATH "" FORCE)

# The app only needs the inference library. Everything else in llama.cpp is
# either a host tool or a backend that is not available on Android.
set(LLAMA_BUILD_IS_DEV    OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_TESTS     OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_EXAMPLES  OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_SERVER    OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_TOOLS     OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_COMMON    OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_APP       OFF CACHE BOOL "" FORCE)
set(LLAMA_OPENSSL         OFF CACHE BOOL "" FORCE)
set(LLAMA_CURL            OFF CACHE BOOL "" FORCE)
set(GGML_BUILD_TESTS      OFF CACHE BOOL "" FORCE)
set(GGML_BUILD_EXAMPLES   OFF CACHE BOOL "" FORCE)
set(GGML_RPC              OFF CACHE BOOL "" FORCE)
set(GGML_VULKAN           OFF CACHE BOOL "" FORCE)
set(GGML_OPENCL           OFF CACHE BOOL "" FORCE)
set(GGML_METAL            OFF CACHE BOOL "" FORCE)
set(GGML_CUDA             OFF CACHE BOOL "" FORCE)
set(GGML_BLAS             OFF CACHE BOOL "" FORCE)
set(GGML_SYCL             OFF CACHE BOOL "" FORCE)
set(GGML_HIP              OFF CACHE BOOL "" FORCE)
set(GGML_MUSA             OFF CACHE BOOL "" FORCE)

add_subdirectory(llama.cpp)

add_library(parley_llama_jni SHARED
    llama_jni.cpp
    whisper.cpp/src/whisper.cpp
    whisper.cpp/src/aneforge/whisper-aneforge.cpp
)
target_include_directories(parley_llama_jni PRIVATE
    llama.cpp/include
    llama.cpp/ggml/include
    whisper.cpp/include
    whisper.cpp/src
)
target_compile_definitions(parley_llama_jni PRIVATE WHISPER_VERSION="1.9.5")
find_library(log-lib log)
target_link_libraries(parley_llama_jni llama ${log-lib})
target_compile_features(parley_llama_jni PRIVATE cxx_std_17)

# Keep the library loadable on both 4 KB and 16 KB page-size devices.
target_link_options(parley_llama_jni PRIVATE "-Wl,-z,max-page-size=16384")
