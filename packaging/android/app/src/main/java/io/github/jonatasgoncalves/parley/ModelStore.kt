package io.github.jonatasgoncalves.parley

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.nio.file.Files
import java.nio.file.StandardCopyOption

data class ModelFile(val name: String, val url: String, val expectedBytes: Long = 0L)

data class ModelOption(
    val id: String,
    val tierKey: String,
    val modelName: String,
    val files: List<ModelFile>,
    val sizeGb: Double,
    val ramGb: Double,
    val descriptionKey: String,
) {
    val isSharded: Boolean get() = files.size > 1
}

enum class ModelStatus { MISSING, INCOMPLETE, READY, DOWNLOADING }

/**
 * The three built-in model tiers and the downloaded files in app-private
 * storage. A split model is stored as several files and loaded in list order.
 *
 * Downloads are guarded so the same file can never be written by two threads.
 * Every built-in file has its exact byte size; a truncated copy is treated as
 * not installed instead of being handed to llama.cpp.
 */
object ModelStore {

    private const val BASE = "https://huggingface.co/Qwen"

    private val lock = Any()
    private val active = mutableSetOf<String>()
    private var activeTicket: DownloadTicket? = null

    /** Cancel applies to one transfer, not to every future download. */
    private class DownloadTicket {
        @Volatile
        var cancelled: Boolean = false
    }

    val TIERS = listOf(
        ModelOption(
            id = "basic",
            tierKey = "model_tier_basic",
            modelName = "Qwen2.5 1.5B",
            files = listOf(
                ModelFile(
                    "qwen2.5-1.5b-instruct-q4_k_m.gguf",
                    "$BASE/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
                    1_117_320_736L,
                ),
            ),
            sizeGb = 1.1,
            ramGb = 1.0,
            descriptionKey = "android_model_basic_desc",
        ),
        ModelOption(
            id = "normal",
            tierKey = "model_tier_normal",
            modelName = "Qwen2.5 3B",
            files = listOf(
                ModelFile(
                    "qwen2.5-3b-instruct-q4_k_m.gguf",
                    "$BASE/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf",
                    2_104_932_768L,
                ),
            ),
            sizeGb = 2.0,
            ramGb = 2.0,
            descriptionKey = "android_model_normal_desc",
        ),
    )

    fun find(id: String): ModelOption? = TIERS.firstOrNull { it.id == id }

    fun directory(context: Context): File =
        File(context.filesDir, "models").apply { mkdirs() }

    fun paths(context: Context, option: ModelOption): Array<String> =
        option.files.map { File(directory(context), it.name).absolutePath }.toTypedArray()

    private fun complete(context: Context, file: ModelFile): Boolean {
        val target = File(directory(context), file.name)
        if (!target.exists()) return false
        if (file.expectedBytes <= 0L) return target.length() > 1024L
        // A completed split must match the published size; allow a tiny margin
        // for servers that change the file by a few bytes.
        return target.length() >= file.expectedBytes - 4096L
    }

    fun isInstalled(context: Context, option: ModelOption): Boolean =
        option.files.all { complete(context, it) }

    fun status(context: Context, option: ModelOption): ModelStatus = synchronized(lock) {
        when {
            option.files.any { it.name in active } -> ModelStatus.DOWNLOADING
            isInstalled(context, option) -> ModelStatus.READY
            option.files.any { File(directory(context), "${it.name}.part").exists() } ->
                ModelStatus.INCOMPLETE
            else -> ModelStatus.MISSING
        }
    }

    fun customOption(url: String, fileName: String): ModelOption = ModelOption(
        id = "custom",
        tierKey = "model_tier_custom",
        modelName = fileName.removeSuffix(".gguf"),
        files = listOf(ModelFile(fileName, url.trim())),
        sizeGb = 0.0,
        ramGb = 0.0,
        descriptionKey = "android_model_custom_desc",
    )

    fun cancelDownload() {
        synchronized(lock) { activeTicket?.cancelled = true }
    }

    /** Download every split into app-private storage. Returns error messages. */
    fun download(
        context: Context,
        option: ModelOption,
        onProgress: (current: Int, total: Int, name: String, percent: Int) -> Unit,
    ): List<String> {
        val ticket = DownloadTicket()
        synchronized(lock) {
            if (option.files.any { it.name in active }) {
                return listOf("A download is already running for this model")
            }
            // A leftover .part file can only come from a killed process; the
            // in-memory guard above rules out a live writer.
            for (file in option.files) {
                if (!complete(context, file)) {
                    File(directory(context), "${file.name}.part").delete()
                }
            }
            option.files.forEach { active.add(it.name) }
            activeTicket = ticket
        }
        val errors = mutableListOf<String>()
        val dir = directory(context)
        try {
            for ((index, file) in option.files.withIndex()) {
                if (ticket.cancelled) break
                if (complete(context, file)) {
                    onProgress(index + 1, option.files.size, file.name, 100)
                    continue
                }
                val target = File(dir, file.name)
                val partial = File(dir, "${file.name}.part")
                var connection: HttpURLConnection? = null
                try {
                    var address = file.url
                    for (attempt in 0..5) {
                        val candidate = URL(address).openConnection() as HttpURLConnection
                        candidate.instanceFollowRedirects = false
                        candidate.connectTimeout = 20_000
                        candidate.readTimeout = 60_000
                        when (candidate.responseCode) {
                            HttpURLConnection.HTTP_MOVED_PERM,
                            HttpURLConnection.HTTP_MOVED_TEMP,
                            307,
                            308,
                            -> {
                                val next = candidate.getHeaderField("Location")
                                candidate.disconnect()
                                if (next.isNullOrBlank()) throw IOException("Redirect without a target")
                                address = next
                            }
                            else -> {
                                connection = candidate
                                break
                            }
                        }
                        if (attempt == 5) throw IOException("Too many redirects")
                    }
                    val activeConnection = connection ?: throw IOException("Could not open the model URL")
                    if (activeConnection.responseCode !in 200..299) {
                        throw IOException("HTTP ${activeConnection.responseCode}")
                    }
                    val reported = activeConnection.contentLengthLong
                    val expected = if (file.expectedBytes > 0L) file.expectedBytes else reported
                    val buffer = ByteArray(64 * 1024)
                    var received = 0L
                    var lastPercent = -1
                    activeConnection.inputStream.use { input ->
                        FileOutputStream(partial).use { output ->
                            while (true) {
                                if (ticket.cancelled || Thread.interrupted()) {
                                    throw InterruptedException()
                                }
                                val read = input.read(buffer)
                                if (read < 0) break
                                output.write(buffer, 0, read)
                                received += read
                                if (expected > 0) {
                                    val percent = (received * 100 / expected).toInt().coerceIn(0, 99)
                                    if (percent != lastPercent) {
                                        lastPercent = percent
                                        onProgress(index + 1, option.files.size, file.name, percent)
                                    }
                                }
                            }
                        }
                    }
                    if (expected > 0 && received < expected - 4096L) {
                        throw IOException("Download finished early: $received of $expected bytes")
                    }
                    if (!partial.renameTo(target)) {
                        Files.move(partial.toPath(), target.toPath(), StandardCopyOption.REPLACE_EXISTING)
                    }
                    onProgress(index + 1, option.files.size, file.name, 100)
                } catch (exc: InterruptedException) {
                    partial.delete()
                    Thread.currentThread().interrupt()
                    errors.add("Download cancelled")
                    break
                } catch (exc: Exception) {
                    partial.delete()
                    errors.add("${file.name}: ${exc.message ?: exc.javaClass.simpleName}")
                    break
                } finally {
                    connection?.disconnect()
                }
            }
        } finally {
            synchronized(lock) {
                option.files.forEach { active.remove(it.name) }
                if (activeTicket === ticket) activeTicket = null
            }
        }
        return errors
    }

    /** Copy a file chosen through the system picker into app-private storage. */
    fun importFile(context: Context, uri: Uri): String? {
        val name = displayName(context, uri)?.let { File(it).name }.orEmpty()
        if (!name.endsWith(".gguf", ignoreCase = true)) return null
        val target = File(directory(context), name)
        val partial = File(target.parentFile, "${target.name}.part")
        val input = context.contentResolver.openInputStream(uri)
            ?: throw IOException("Could not open the selected file")
        input.use { stream ->
            FileOutputStream(partial).use { output -> stream.copyTo(output, 64 * 1024) }
        }
        Files.move(partial.toPath(), target.toPath(), StandardCopyOption.REPLACE_EXISTING)
        return target.absolutePath
    }

    private fun displayName(context: Context, uri: Uri): String? {
        val columns = arrayOf(OpenableColumns.DISPLAY_NAME)
        val cursor = context.contentResolver.query(uri, columns, null, null, null) ?: return null
        return cursor.use {
            val index = it.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (index >= 0 && it.moveToFirst()) it.getString(index) else null
        }
    }

    fun remove(context: Context, option: ModelOption) {
        for (file in option.files) {
            File(directory(context), file.name).delete()
            File(directory(context), "${file.name}.part").delete()
        }
    }
}
