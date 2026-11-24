package io.github.jonatasgoncalves.parley

import android.content.Context
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

data class WhisperModelOption(
    val id: String,
    val labelKey: String,
    val modelName: String,
    val url: String,
    val fileName: String,
    val sizeMb: Int,
    val ramGb: Double,
)

object WhisperModelStore {
    private const val BASE = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"

    val MODELS = listOf(
        WhisperModelOption(
            id = "tiny",
            labelKey = "whisper_tiny",
            modelName = "Whisper Tiny",
            url = "$BASE/ggml-tiny.bin",
            fileName = "ggml-tiny.bin",
            sizeMb = 75,
            ramGb = 1.0,
        ),
        WhisperModelOption(
            id = "base",
            labelKey = "whisper_base",
            modelName = "Whisper Base",
            url = "$BASE/ggml-base.bin",
            fileName = "ggml-base.bin",
            sizeMb = 142,
            ramGb = 1.0,
        ),
        WhisperModelOption(
            id = "small",
            labelKey = "whisper_small",
            modelName = "Whisper Small",
            url = "$BASE/ggml-small.bin",
            fileName = "ggml-small.bin",
            sizeMb = 466,
            ramGb = 2.0,
        ),
    )

    private val lock = Any()
    private val downloading = mutableSetOf<String>()

    fun find(id: String): WhisperModelOption? = MODELS.firstOrNull { it.id == id }

    fun directory(context: Context): File =
        File(context.filesDir, "whisper-models").apply { mkdirs() }

    fun file(context: Context, option: WhisperModelOption): File =
        File(directory(context), option.fileName)

    fun isInstalled(context: Context, option: WhisperModelOption): Boolean =
        file(context, option).let { it.isFile && it.length() > 1024 * 1024 }

    fun isDownloading(option: WhisperModelOption): Boolean = synchronized(lock) { option.id in downloading }

    fun installedModels(context: Context): List<WhisperModelOption> = MODELS.filter { isInstalled(context, it) }

    fun delete(context: Context, option: WhisperModelOption): Boolean {
        val f = file(context, option)
        return !f.exists() || f.delete()
    }

    @Throws(IOException::class)
    fun download(
        context: Context,
        option: WhisperModelOption,
        onProgress: (downloaded: Long, total: Long) -> Unit = { _, _ -> },
    ): File {
        synchronized(lock) {
            check(option.id !in downloading) { "already downloading" }
            downloading.add(option.id)
        }
        try {
            val target = file(context, option)
            if (isInstalled(context, option)) return target
            val tmp = File(target.parentFile, target.name + ".part")
            val connection = URL(option.url).openConnection() as HttpURLConnection
            connection.connectTimeout = 20_000
            connection.readTimeout = 30_000
            connection.instanceFollowRedirects = true
            connection.setRequestProperty("User-Agent", "Parley-Android")
            connection.connect()
            val code = connection.responseCode
            if (code !in 200..299) throw IOException("HTTP $code")
            val total = connection.contentLengthLong
            connection.inputStream.use { input ->
                FileOutputStream(tmp).use { output ->
                    val buffer = ByteArray(64 * 1024)
                    var downloaded = 0L
                    while (true) {
                        val read = input.read(buffer)
                        if (read <= 0) break
                        output.write(buffer, 0, read)
                        downloaded += read
                        onProgress(downloaded, total)
                    }
                    output.fd.sync()
                }
            }
            if (!tmp.renameTo(target)) {
                tmp.copyTo(target, overwrite = true)
                tmp.delete()
            }
            return target
        } finally {
            synchronized(lock) { downloading.remove(option.id) }
        }
    }
}
