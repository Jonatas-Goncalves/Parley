package io.github.jonatasgoncalves.parley

/**
 * Receives each decoded piece of a native reply.
 *
 * The callback runs on the thread that called [LlamaEngine.generate], so callers
 * must move UI work to the main thread themselves.
 */
fun interface LlamaTokenSink {
    fun onToken(text: String)
}

/**
 * Thin Kotlin wrapper around the bundled llama.cpp library.
 *
 * The model runs fully inside the application process. There is no local HTTP
 * server and no other application is involved.
 */
object LlamaEngine {

    init {
        System.loadLibrary("parley_llama_jni")
    }

    @Volatile
    private var handle: Long = 0L

    @Volatile
    private var backendsReady = false

    /**
     * Point llama.cpp at the directory where Android extracted the CPU backend
     * modules. Call from the main thread before loading a model.
     */
    @Synchronized
    fun initBackends(nativeLibraryDir: String) {
        if (backendsReady) return
        nativeInitBackends(nativeLibraryDir)
        backendsReady = true
    }

    /** True while a startup or Settings load is still reading the GGUF file. */
    @Volatile
    var loading: Boolean = false
        private set

    /**
     * Replace the loaded model. Splits must be supplied in the correct order.
     *
     * Load, free and generate share one monitor so two model switches can never
     * overlap with a generation. The native layer has the same guarantee, which
     * also protects callers that reach it from other threads.
     */
    @Synchronized
    fun load(paths: Array<String>): Long {
        loading = true
        try {
            val next = nativeInitModel(paths)
            handle = next
            return next
        } finally {
            loading = false
        }
    }

    /** Stop the current generation loop. Safe to call from any thread. */
    fun cancel() {
        nativeCancel(handle)
    }

    @Synchronized
    fun generate(
        prompt: String,
        maxTokens: Int,
        onDelta: (String) -> Unit,
        isCancelled: () -> Boolean = { false },
    ) {
        val current = handle
        if (current == 0L) {
            throw IllegalStateException("No model is loaded")
        }
        nativeGenerate(
            current,
            prompt,
            maxTokens,
            LlamaTokenSink { text ->
                onDelta(text)
                if (isCancelled()) nativeCancel(current)
            },
        )
    }

    fun isReady(): Boolean {
        val current = handle
        return current != 0L && nativeIsReady(current)
    }

    /** True while a generation is queued or running on any thread. */
    fun isGenerating(): Boolean = nativeIsGenerating()

    /** True if the last native generation ended due to cancellation. */
    fun wasLastCancelled(): Boolean = nativeWasLastCancelled()

    /** Call from a worker thread: freeing a model can block on generation. */
    @Synchronized
    fun free() {
        val current = handle
        handle = 0L
        if (current != 0L) nativeFreeModel(current)
    }

    fun version(): String = nativeVersion()

    /** Native state, load details and generation counters for Diagnostics. */
    fun diagnostics(): String = nativeDiagnostics()

    /** True for Qwen3-style models that emit <think> reasoning by default. */
    fun isThinkingModel(): Boolean {
        val current = handle
        return current != 0L && nativeIsThinkingModel(current)
    }

    private external fun nativeInitBackends(path: String)

    private external fun nativeInitModel(paths: Array<String>): Long

    private external fun nativeGenerate(
        handle: Long,
        prompt: String,
        maxTokens: Int,
        sink: LlamaTokenSink,
    )

    private external fun nativeCancel(handle: Long)

    private external fun nativeFreeModel(handle: Long)

    private external fun nativeIsReady(handle: Long): Boolean

    private external fun nativeIsGenerating(): Boolean

    private external fun nativeWasLastCancelled(): Boolean

    private external fun nativeIsThinkingModel(handle: Long): Boolean

    private external fun nativeVersion(): String

    private external fun nativeDiagnostics(): String
}
