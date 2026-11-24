package io.github.jonatasgoncalves.parley

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Chat client for a local llama.cpp server.
 *
 * It talks to the OpenAI-compatible `/v1/chat/completions` endpoint exposed by
 * `llama-server`, which is what the Termux package `llama-cpp` provides. No
 * cloud service and no model hosted elsewhere are involved.
 */
object ChatClient {

    data class Message(val role: String, val content: String)

    fun chat(
        baseUrl: String,
        model: String,
        messages: List<Message>,
        maxTokens: Int = DEFAULT_MAX_TOKENS,
    ): String {
        val payload = payload(model, messages, stream = false, maxTokens = maxTokens)
        val body = postJson(openAiEndpoint(baseUrl), payload)
        val reply = JSONObject(body)
            .optJSONArray("choices")
            ?.optJSONObject(0)
            ?.optJSONObject("message")
            ?.optString("content")
            ?.trim()
            .orEmpty()
        val clean = ReplyParser.stripNullPrefix(reply)
        if (clean.isEmpty()) {
            throw IllegalStateException("llama.cpp returned an empty reply")
        }
        return clean
    }

    /**
     * Stream a reply, calling [onDelta] with the accumulated visible text.
     * Returns the full raw answer, including the note section.
     */
    fun chatStream(
        baseUrl: String,
        model: String,
        messages: List<Message>,
        onDelta: (visible: String) -> Unit,
        isCancelled: () -> Boolean = { false },
        maxTokens: Int = DEFAULT_MAX_TOKENS,
    ): String {
        val connection = connect(
            openAiEndpoint(baseUrl),
            payload(model, messages, stream = true, maxTokens = maxTokens),
        )
        val raw = StringBuilder()
        var visible = ""
        try {
            val code = connection.responseCode
            if (code !in 200..299) {
                val detail = connection.errorStream?.bufferedReader(Charsets.UTF_8)
                    ?.use { it.readText() }
                    .orEmpty()
                throw IllegalStateException("llama.cpp returned HTTP $code: ${detail.take(300)}")
            }
            connection.inputStream.bufferedReader(Charsets.UTF_8).use { reader ->
                while (true) {
                    if (isCancelled()) break
                    val line = reader.readLine() ?: break
                    if (!line.startsWith("data:")) continue
                    val data = line.removePrefix("data:").trim()
                    if (data.isEmpty() || data == "[DONE]") continue
                    val chunk = try {
                        JSONObject(data)
                            .optJSONArray("choices")
                            ?.optJSONObject(0)
                            ?.optJSONObject("delta")
                            ?.optString("content")
                            .orEmpty()
                    } catch (_: Exception) {
                        ""
                    }
                    if (chunk.isEmpty()) continue
                    raw.append(chunk)
                    val next = ReplyParser.renderStream(raw.toString())
                    if (next != visible) {
                        visible = next
                        onDelta(next)
                    }
                }
            }
        } finally {
            connection.disconnect()
        }
        val result = ReplyParser.stripNullPrefix(raw.toString())
        if (result.isEmpty()) {
            throw IllegalStateException("llama.cpp returned an empty reply")
        }
        return result
    }

    /** True when the server answers the models endpoint. */
    fun ping(baseUrl: String): Boolean {
        val endpoint = openAiEndpoint(baseUrl).removeSuffix("/chat/completions") + "/models"
        val url = try {
            URL(endpoint)
        } catch (_: Exception) {
            return false
        }
        val connection = try {
            (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "GET"
                connectTimeout = 4_000
                readTimeout = 4_000
                setRequestProperty("Accept", "application/json")
            }
        } catch (_: Exception) {
            return false
        }
        return try {
            connection.responseCode in 200..299
        } catch (_: Exception) {
            false
        } finally {
            connection.disconnect()
        }
    }

    fun openAiEndpoint(baseUrl: String): String {
        var base = baseUrl.trim().trimEnd('/')
        if (base.isEmpty()) {
            base = DEFAULT_BASE_URL
        }
        if (base.endsWith("/chat/completions")) {
            base = base.removeSuffix("/chat/completions").trimEnd('/')
        }
        if (!base.endsWith("/v1")) {
            base += "/v1"
        }
        return "$base/chat/completions"
    }

    private fun payload(
        model: String,
        messages: List<Message>,
        stream: Boolean,
        maxTokens: Int,
    ): JSONObject =
        JSONObject().apply {
            put("model", model.ifBlank { "local" })
            put("stream", stream)
            put("max_tokens", maxTokens)
            put("messages", messageArray(messages))
        }

    private fun messageArray(messages: List<Message>): JSONArray =
        JSONArray().apply {
            for (message in messages) {
                put(
                    JSONObject().apply {
                        put("role", message.role)
                        put("content", message.content)
                    },
                )
            }
        }

    private fun connect(endpoint: String, payload: JSONObject): HttpURLConnection {
        val url = try {
            URL(endpoint)
        } catch (exc: Exception) {
            throw IllegalArgumentException("Invalid llama.cpp address: $endpoint", exc)
        }
        if (url.protocol != "http" && url.protocol != "https") {
            throw IllegalArgumentException("The llama.cpp address must start with http:// or https://")
        }
        val connection = (url.openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 15_000
            readTimeout = 180_000
            doOutput = true
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
            setRequestProperty("Accept", "text/event-stream")
        }
        try {
            connection.outputStream.use { stream ->
                stream.write(payload.toString().toByteArray(Charsets.UTF_8))
            }
        } catch (exc: Exception) {
            connection.disconnect()
            throw exc
        }
        return connection
    }

    private fun postJson(endpoint: String, payload: JSONObject): String {
        val connection = connect(endpoint, payload)
        try {
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val body = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            if (code !in 200..299) {
                throw IllegalStateException("llama.cpp returned HTTP $code: ${body.take(300)}")
            }
            return body
        } finally {
            connection.disconnect()
        }
    }

    const val DEFAULT_BASE_URL = "http://127.0.0.1:8080"

    /** Keep answers short so a phone CPU does not spend minutes on one turn. */
    const val DEFAULT_MAX_TOKENS = 180
}
