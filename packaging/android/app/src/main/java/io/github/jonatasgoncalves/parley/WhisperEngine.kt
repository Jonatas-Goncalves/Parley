package io.github.jonatasgoncalves.parley

import android.content.Context
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Local whisper.cpp speech-to-text engine.
 *
 * Separate from [LlamaEngine] because it uses a different model/context. The
 * native library is the same shared lib (parley_llama_jni) which also contains
 * whisper symbols.
 */
class WhisperEngine {
    companion object {
        init {
            try {
                System.loadLibrary("parley_llama_jni")
            } catch (_: UnsatisfiedLinkError) {
                // Loaded by LlamaEngine or not available in unit tests.
            }
        }
    }

    private val loaded = AtomicBoolean(false)
    @Volatile private var loadedPath: String? = null
    @Volatile private var handle: Long = 0L

    private external fun nativeLoad(modelPath: String): Long
    private external fun nativeFree(handle: Long)
    private external fun nativeIsReady(): Boolean
    private external fun nativeTranscribe(samples: FloatArray, language: String, translate: Boolean): String
    external fun nativeInfo(): String

    @Synchronized
    fun load(path: String): Boolean {
        val file = File(path)
        if (!file.isFile) return false
        val newHandle = nativeLoad(file.absolutePath)
        val ok = newHandle != 0L
        handle = if (ok) newHandle else 0L
        loaded.set(ok)
        loadedPath = if (ok) file.absolutePath else null
        return ok
    }

    @Synchronized
    fun unload() {
        val old = handle
        handle = 0L
        loaded.set(false)
        loadedPath = null
        if (old != 0L) {
            try { nativeFree(old) } catch (_: Exception) {}
        }
    }

    fun isReady(): Boolean = loaded.get() && nativeIsReady()

    fun loadedModelPath(): String? = loadedPath

    fun transcribe(samples: FloatArray, language: String): String {
        if (!isReady() || samples.isEmpty()) return ""
        return try {
            nativeTranscribe(samples, language, false).trim()
        } catch (_: Exception) {
            ""
        }
    }

    fun info(): String = try { nativeInfo() } catch (_: Exception) { "none" }
}
