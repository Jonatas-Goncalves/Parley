package io.github.jonatasgoncalves.parley

/**
 * Chat client backed by the llama.cpp library bundled in the APK.
 *
 * Prompts are rendered in ChatML, the format used by the Qwen2.5 Instruct
 * models shipped with the app. Replies arrive one token piece at a time from
 * the native layer and are rendered through the same parser as before.
 */
object ChatClient {

    data class Message(val role: String, val content: String)

    /** Load a model or a list of ordered split files. Call from a worker thread. */
    fun load(paths: Array<String>) {
        LlamaEngine.load(paths)
    }

    fun ready(): Boolean = LlamaEngine.isReady()

    /** Wait for a model that is still being loaded when the app starts. */
    fun awaitReady(timeoutMs: Long = 120_000): Boolean {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            if (ready()) return true
            if (!LlamaEngine.loading) return false
            Thread.sleep(200)
        }
        return ready()
    }

    fun version(): String = LlamaEngine.version()

    /** Native llama state, counters and the loaded model details. */
    fun diagnostics(): String = LlamaEngine.diagnostics()

    /** Stop a generation that is taking too long. */
    fun cancel() = LlamaEngine.cancel()

    /** True while a generation is queued or running on another thread. */
    fun generating(): Boolean = LlamaEngine.isGenerating()

    /**
     * Cancel the active turn and wait until the native loop has really exited.
     * Returns false if it is still busy after [timeoutMs].
     */
    fun cancelAndWait(timeoutMs: Long = 10_000): Boolean {
        if (!generating()) return true
        cancel()
        val deadline = System.currentTimeMillis() + timeoutMs
        while (generating()) {
            if (System.currentTimeMillis() >= deadline) return false
            Thread.sleep(50)
        }
        return true
    }

    fun unload() = LlamaEngine.free()

    fun chat(
        messages: List<Message>,
        maxTokens: Int = DEFAULT_MAX_TOKENS,
    ): String {
        val raw = StringBuilder()
        LlamaEngine.generate(prompt(messages), maxTokens, { raw.append(it) })
        val clean = ReplyParser.stripNullPrefix(raw.toString())
        if (clean.isEmpty()) {
            if (LlamaEngine.wasLastCancelled()) {
                throw IllegalStateException("The model generation was cancelled")
            }
            throw IllegalStateException("The model returned an empty reply")
        }
        return clean
    }

    /**
     * Stream a reply, calling [onDelta] with the accumulated visible text.
     * Returns the full raw answer, including the note section.
     */
    fun chatStream(
        messages: List<Message>,
        onDelta: (visible: String) -> Unit,
        onToken: (piece: String) -> Unit = {},
        isCancelled: () -> Boolean = { false },
        maxTokens: Int = DEFAULT_MAX_TOKENS,
    ): String {
        val raw = StringBuilder()
        var visible = ""
        LlamaEngine.generate(
            prompt(messages),
            maxTokens,
            { piece ->
                raw.append(piece)
                onToken(piece)
                val next = ReplyParser.renderStream(raw.toString())
                if (next != visible) {
                    visible = next
                    onDelta(next)
                }
            },
            isCancelled,
        )
        val result = ReplyParser.stripNullPrefix(raw.toString())
        if (result.isEmpty()) {
            if (LlamaEngine.wasLastCancelled()) {
                throw IllegalStateException("The model generation was cancelled")
            }
            throw IllegalStateException("The model returned an empty reply")
        }
        return result
    }

    /** Format the conversation the way Qwen2.5 Instruct expects. */
    private fun prompt(messages: List<Message>): String {
        val body = StringBuilder()
        for (message in messages) {
            val role = when (message.role) {
                "system" -> "system"
                "assistant" -> "assistant"
                else -> "user"
            }
            body.append("<|im_start|>").append(role).append('\n')
            body.append(message.content.trim()).append("<|im_end|>\n")
        }
        body.append("<|im_start|>assistant\n")
        // Qwen3's own chat template pre-fills an empty think block when
        // thinking is disabled. We render ChatML here instead of using the
        // bundled Jinja templates, so do the same to make it answer directly.
        if (LlamaEngine.isThinkingModel()) {
            body.append("<think>\n\n</think>\n\n")
        }
        return body.toString()
    }

    /** Keep answers short so a phone CPU does not spend minutes on one turn. */
    const val DEFAULT_MAX_TOKENS = 100
}
