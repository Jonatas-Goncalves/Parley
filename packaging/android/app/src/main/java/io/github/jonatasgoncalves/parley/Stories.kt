package io.github.jonatasgoncalves.parley

import android.content.Context
import org.json.JSONArray
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/** One entry of the spoken-story catalogue. */
data class Story(
    val title: String,
    val author: String,
    val filename: String,
    val bytes: Long,
    val seconds: Double,
    val sha256: String,
)

/**
 * Local copy of the spoken-story pack.
 *
 * The catalogue ships inside the APK; the MP3 files are downloaded only when
 * the user asks for them, one at a time, with SHA-256 verification.
 */
object StoryStore {
    const val BASE_URL =
        "https://raw.githubusercontent.com/Jonatas-Goncalves/Parley/main/assets/stories"

    fun manifest(context: Context): List<Story> {
        val raw = context.assets.open("stories.json").bufferedReader(Charsets.UTF_8)
            .use { it.readText() }
        val payload = org.json.JSONObject(raw)
        val stories = payload.optJSONArray("stories") ?: JSONArray()
        val items = ArrayList<Story>(stories.length())
        for (index in 0 until stories.length()) {
            val item = stories.optJSONObject(index) ?: continue
            val filename = item.optString("filename")
            if (filename.isBlank()) continue
            items.add(
                Story(
                    title = item.optString("title", filename),
                    author = item.optString("author"),
                    filename = filename,
                    bytes = item.optLong("bytes"),
                    seconds = item.optDouble("seconds"),
                    sha256 = item.optString("sha256"),
                ),
            )
        }
        return items
    }

    fun directory(context: Context): File =
        File(context.filesDir, "stories").apply { mkdirs() }

    fun localPath(context: Context, story: Story): File =
        File(directory(context), story.filename)

    fun isInstalled(context: Context, story: Story): Boolean {
        val file = localPath(context, story)
        return file.isFile && file.length() > 0
    }

    fun installedCount(context: Context, stories: List<Story>): Int =
        stories.count { isInstalled(context, it) }

    fun installedBytes(context: Context): Long =
        directory(context).listFiles()
            ?.filter { it.isFile && it.name.endsWith(".mp3") }
            ?.sumOf { it.length() }
            ?: 0L

    fun totalMegabytes(stories: List<Story>): Double =
        stories.sumOf { it.bytes } / (1024.0 * 1024.0)

    /**
     * Download every missing story. The callback receives the position, the
     * number of stories, the downloaded bytes, the total bytes and the title.
     */
    fun download(
        context: Context,
        stories: List<Story>,
        onProgress: (position: Int, count: Int, done: Long, total: Long, title: String) -> Unit,
        isCancelled: () -> Boolean = { false },
    ): List<String> {
        val errors = ArrayList<String>()
        val total = stories.sumOf { it.bytes }.coerceAtLeast(1)
        var done = 0L
        for ((offset, story) in stories.withIndex()) {
            if (isCancelled()) break
            val position = offset + 1
            val target = localPath(context, story)
            if (target.isFile && target.length() > 0) {
                done += story.bytes
                onProgress(position, stories.size, done, total, story.title)
                continue
            }
            val temporary = File(target.parentFile, target.name + ".part")
            try {
                val connection = (URL("$BASE_URL/${story.filename}").openConnection() as HttpURLConnection).apply {
                    connectTimeout = 30_000
                    readTimeout = 120_000
                    setRequestProperty("User-Agent", "Parley-Android")
                }
                try {
                    if (connection.responseCode !in 200..299) {
                        throw IllegalStateException("HTTP ${connection.responseCode}")
                    }
                    connection.inputStream.use { input ->
                        temporary.outputStream().use { output ->
                            val buffer = ByteArray(256 * 1024)
                            while (true) {
                                if (isCancelled()) throw InterruptedException("cancelled")
                                val read = input.read(buffer)
                                if (read <= 0) break
                                output.write(buffer, 0, read)
                                done += read
                                onProgress(position, stories.size, done, total, story.title)
                            }
                        }
                    }
                } finally {
                    connection.disconnect()
                }
                if (story.sha256.isNotBlank() && sha256(temporary) != story.sha256) {
                    throw IllegalStateException("checksum mismatch")
                }
                if (!temporary.renameTo(target)) {
                    temporary.copyTo(target, overwrite = true)
                    temporary.delete()
                }
            } catch (exc: InterruptedException) {
                temporary.delete()
                break
            } catch (exc: Exception) {
                temporary.delete()
                errors.add("${story.filename}: ${exc.message ?: exc.javaClass.simpleName}")
            }
            onProgress(position, stories.size, done, total, story.title)
        }
        return errors
    }

    fun removeAll(context: Context) {
        val folder = directory(context)
        folder.listFiles()?.forEach { file ->
            if (file.isFile && (file.name.endsWith(".mp3") || file.name.endsWith(".part"))) {
                file.delete()
            }
        }
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(256 * 1024)
            while (true) {
                val read = input.read(buffer)
                if (read <= 0) break
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}
