package io.github.jonatasgoncalves.parley

import android.content.Context
import org.apache.commons.compress.archivers.tar.TarArchiveInputStream
import org.apache.commons.compress.compressors.bzip2.BZip2CompressorInputStream
import java.io.BufferedInputStream
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

data class PiperVoiceOption(
    val id: String,
    val language: String,
    val label: String,
    val archiveUrl: String,
    val archiveName: String,
    val sizeMb: Int,
)

object PiperVoiceStore {
    private const val BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models"

    val VOICES = listOf(
        PiperVoiceOption("en_US-lessac-medium-int8", "en", "English (US) — Lessac Medium", "$BASE/vits-piper-en_US-lessac-medium-int8.tar.bz2", "vits-piper-en_US-lessac-medium-int8.tar.bz2", 21),
        PiperVoiceOption("pt_BR-faber-medium-int8", "pt", "Português (BR) — Faber Medium", "$BASE/vits-piper-pt_BR-faber-medium-int8.tar.bz2", "vits-piper-pt_BR-faber-medium-int8.tar.bz2", 20),
        PiperVoiceOption("es_ES-sharvard-medium-int8", "es", "Español (ES) — Sharvard Medium", "$BASE/vits-piper-es_ES-sharvard-medium-int8.tar.bz2", "vits-piper-es_ES-sharvard-medium-int8.tar.bz2", 22),
        PiperVoiceOption("fr_FR-siwis-medium-int8", "fr", "Français (FR) — Siwis Medium", "$BASE/vits-piper-fr_FR-siwis-medium-int8.tar.bz2", "vits-piper-fr_FR-siwis-medium-int8.tar.bz2", 20),
        PiperVoiceOption("it_IT-paola-medium-int8", "it", "Italiano (IT) — Paola Medium", "$BASE/vits-piper-it_IT-paola-medium-int8.tar.bz2", "vits-piper-it_IT-paola-medium-int8.tar.bz2", 20),
        PiperVoiceOption("zh_CN-xiao_ya-medium-int8", "zh", "中文 (CN) — Xiao Ya Medium", "$BASE/vits-piper-zh_CN-xiao_ya-medium-int8.tar.bz2", "vits-piper-zh_CN-xiao_ya-medium-int8.tar.bz2", 13),
    )

    private val lock = Any()
    private val downloading = mutableSetOf<String>()

    fun find(id: String): PiperVoiceOption? = VOICES.firstOrNull { it.id == id }
    fun forLanguage(lang: String): List<PiperVoiceOption> = VOICES.filter { it.language == lang }

    fun directory(context: Context): File = File(context.filesDir, "piper-voices").apply { mkdirs() }
    fun voiceDir(context: Context, option: PiperVoiceOption): File = File(directory(context), option.id)

    fun isInstalled(context: Context, option: PiperVoiceOption): Boolean {
        val dir = voiceDir(context, option)
        val onnx = dir.walkTopDown().firstOrNull { it.isFile && it.name.endsWith(".onnx") }
        val tokens = File(dir, "tokens.txt")
        return onnx != null && tokens.isFile
    }

    fun isDownloading(option: PiperVoiceOption): Boolean = synchronized(lock) { option.id in downloading }

    fun delete(context: Context, option: PiperVoiceOption): Boolean {
        val dir = voiceDir(context, option)
        return !dir.exists() || dir.deleteRecursively()
    }

    fun modelFile(context: Context, option: PiperVoiceOption): File? {
        val dir = voiceDir(context, option)
        return dir.walkTopDown().firstOrNull { it.isFile && it.name.endsWith(".onnx") && !it.name.contains("encoder") }
    }

    fun tokensFile(context: Context, option: PiperVoiceOption): File = File(voiceDir(context, option), "tokens.txt")
    fun dataDir(context: Context, option: PiperVoiceOption): File = File(voiceDir(context, option), "espeak-ng-data")

    @Throws(IOException::class)
    fun download(
        context: Context,
        option: PiperVoiceOption,
        onProgress: (downloaded: Long, total: Long) -> Unit = { _, _ -> },
    ): File {
        synchronized(lock) {
            check(option.id !in downloading) { "already downloading" }
            downloading.add(option.id)
        }
        try {
            val dir = voiceDir(context, option)
            if (isInstalled(context, option)) return dir
            dir.mkdirs()
            val tmp = File(directory(context), option.archiveName + ".part")
            val connection = URL(option.archiveUrl).openConnection() as HttpURLConnection
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
            extractTarBz2(tmp, directory(context), option.id)
            tmp.delete()
            if (!isInstalled(context, option)) throw IOException("Voice archive extracted but model files not found")
            return dir
        } finally {
            synchronized(lock) { downloading.remove(option.id) }
        }
    }

    private fun extractTarBz2(archive: File, targetRoot: File, voiceId: String) {
        BufferedInputStream(archive.inputStream()).use { bin ->
            BZip2CompressorInputStream(bin).use { bz2 ->
                TarArchiveInputStream(bz2).use { tar ->
                    var entry = tar.nextTarEntry
                    while (entry != null) {
                        val name = entry.name.removePrefix("./")
                        val parts = name.split('/').filter { it.isNotBlank() }
                        val relative = if (parts.isNotEmpty()) parts.drop(1).joinToString("/") else name
                        if (relative.isNotBlank()) {
                            val out = File(File(targetRoot, voiceId), relative)
                            if (entry.isDirectory) {
                                out.mkdirs()
                            } else {
                                out.parentFile?.mkdirs()
                                FileOutputStream(out).use { output ->
                                    tar.copyTo(output)
                                }
                            }
                        }
                        entry = tar.nextTarEntry
                    }
                }
            }
        }
    }
}
