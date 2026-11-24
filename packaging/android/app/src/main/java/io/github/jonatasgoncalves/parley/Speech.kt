package io.github.jonatasgoncalves.parley

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import java.io.File
import com.k2fsa.sherpa.onnx.OfflineTts
import com.k2fsa.sherpa.onnx.OfflineTtsConfig
import com.k2fsa.sherpa.onnx.OfflineTtsModelConfig
import com.k2fsa.sherpa.onnx.OfflineTtsVitsModelConfig
import java.util.Locale
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread
import kotlin.math.sqrt

/**
 * Thin wrapper around the system text-to-speech engine.
 *
 * Speech is either spoken directly or synthesised into a file so the exercise
 * player can offer seeking and playback speed, like the desktop player.
 */
class TtsController(private val context: Context, private val onReady: (Boolean) -> Unit = {}) :
    TextToSpeech.OnInitListener {

    private val appContext = context.applicationContext
    private val handler = Handler(Looper.getMainLooper())
    private val pending = ArrayList<() -> Unit>()
    private val callbacks = HashMap<String, (Boolean) -> Unit>()
    private var engine: TextToSpeech? = TextToSpeech(appContext, this)
    private var counter = 0
    private var player: MediaPlayer? = null

    @Volatile private var piperTts: OfflineTts? = null
    @Volatile private var piperVoiceId: String? = null

    private fun activePiper(): OfflineTts? {
        val want = Prefs(appContext).piperVoice
        return if (want.isNotBlank() && want == piperVoiceId) piperTts else null
    }

    var ready: Boolean = false
        private set
    var languageSupported: Boolean = true
        private set

    override fun onInit(status: Int) {
        ready = status == TextToSpeech.SUCCESS
        if (ready) {
            engine?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
                override fun onStart(utteranceId: String?) = Unit
                override fun onDone(utteranceId: String?) {
                    val cb = utteranceId?.let { callbacks.remove(it) }
                    handler.post { cb?.invoke(true) }
                }
                @Deprecated("Deprecated in Java")
                override fun onError(utteranceId: String?) {
                    val cb = utteranceId?.let { callbacks.remove(it) }
                    handler.post { cb?.invoke(false) }
                }
                override fun onError(utteranceId: String?, errorCode: Int) {
                    val cb = utteranceId?.let { callbacks.remove(it) }
                    handler.post { cb?.invoke(false) }
                }
            })
        }
        val queued = pending.toList()
        pending.clear()
        if (ready) queued.forEach { it() }
        onReady(ready)
    }

    fun setPiperVoice(voiceId: String?, voiceDir: File?) {
        if (voiceId.isNullOrBlank() || voiceDir == null || !voiceDir.isDirectory) {
            piperTts = null
            piperVoiceId = null
            return
        }
        if (piperVoiceId == voiceId && piperTts != null) return
        Thread({
            try {
                val model = voiceDir.walkTopDown().firstOrNull { it.isFile && it.name.endsWith(".onnx") && !it.name.contains("encoder") }
                val tokens = File(voiceDir, "tokens.txt")
                val dataDir = File(voiceDir, "espeak-ng-data")
                if (model == null || !tokens.isFile) {
                    piperTts = null; piperVoiceId = null; return@Thread
                }
                val config = OfflineTtsConfig(
                    model = OfflineTtsModelConfig(
                        vits = OfflineTtsVitsModelConfig(
                            model = model.absolutePath,
                            tokens = tokens.absolutePath,
                            dataDir = if (dataDir.isDirectory) dataDir.absolutePath else "",
                        ),
                        numThreads = 2,
                        debug = false,
                        provider = "cpu",
                    ),
                )
                val tts = OfflineTts(config = config)
                piperTts = tts
                piperVoiceId = voiceId
            } catch (e: Exception) {
                android.util.Log.w("ParleyTTS", "Piper load failed", e)
                piperTts = null
                piperVoiceId = null
            }
        }, "parley-piper-load").start()
    }

    private fun withEngine(action: (TextToSpeech) -> Unit) {
        val current = engine ?: return
        if (!ready) { pending.add { if (ready) action(current) }; return }
        action(current)
    }

    fun applyLanguage(language: String): Boolean {
        val current = engine ?: return false
        val result = current.setLanguage(Locale.forLanguageTag(speechTag(language)))
        languageSupported = result != TextToSpeech.LANG_MISSING_DATA &&
            result != TextToSpeech.LANG_NOT_SUPPORTED
        if (!languageSupported) current.setLanguage(Locale.getDefault())
        return languageSupported
    }

    private fun speakWithSystem(text: String, language: String, slow: Boolean, onDone: ((Boolean) -> Unit)?) {
        withEngine { current ->
            applyLanguage(language)
            current.stop()
            current.setSpeechRate(if (slow) 0.82f else 1.0f)
            val id = "parley-${counter++}"
            if (onDone != null) callbacks[id] = onDone
            current.speak(text, TextToSpeech.QUEUE_FLUSH, null, id)
        }
    }

    private fun speakWithPiper(text: String, language: String, slow: Boolean, onDone: ((Boolean) -> Unit)?) {
        val tts = piperTts
        if (tts == null) { speakWithSystem(text, language, slow, onDone); return }
        Thread({
            try {
                val audio = tts.generate(text = text, sid = 0, speed = if (slow) 0.85f else 1.0f)
                val file = File(appContext.cacheDir, "parley-tts-${counter++}.wav")
                audio.save(file.absolutePath)
                handler.post { playFile(file, onDone) { speakWithSystem(text, language, slow, onDone) } }
            } catch (e: Exception) {
                android.util.Log.w("ParleyTTS", "Piper speak failed", e)
                handler.post { speakWithSystem(text, language, slow, onDone) }
            }
        }, "parley-piper-speak").start()
    }

    private fun playFile(file: File, onDone: ((Boolean) -> Unit)?, onFail: (() -> Unit)? = null) {
        try { player?.stop(); player?.release() } catch (_: Exception) {}
        val mp = MediaPlayer()
        player = mp
        try {
            mp.setDataSource(file.absolutePath)
            mp.setOnCompletionListener {
                try { it.release() } catch (_: Exception) {}
                if (player === it) player = null
                file.delete()
                onDone?.invoke(true)
            }
            mp.setOnErrorListener { _, _, _ ->
                try { mp.release() } catch (_: Exception) {}
                if (player === mp) player = null
                file.delete()
                if (onFail != null) onFail() else onDone?.invoke(false)
                true
            }
            mp.prepare()
            mp.start()
        } catch (e: Exception) {
            try { mp.release() } catch (_: Exception) {}
            if (player === mp) player = null
            file.delete()
            if (onFail != null) onFail() else onDone?.invoke(false)
        }
    }

    fun speak(
        text: String,
        language: String,
        slow: Boolean = false,
        onDone: ((Boolean) -> Unit)? = null,
    ) {
        if (text.isBlank()) { onDone?.invoke(true); return }
        val piper = activePiper()
        if (piper != null) {
            stop()
            speakWithPiper(text, language, slow, onDone)
            return
        }
        speakWithSystem(text, language, slow, onDone)
    }

    fun speakChunk(
        text: String,
        language: String,
        onDone: ((Boolean) -> Unit)? = null,
    ) {
        if (text.isBlank()) { onDone?.invoke(true); return }
        val piper = activePiper()
        if (piper != null) { speakWithPiper(text, language, false, onDone); return }
        withEngine { current ->
            applyLanguage(language)
            current.setSpeechRate(1.0f)
            val id = "parley-${counter++}"
            if (onDone != null) callbacks[id] = onDone
            current.speak(text, TextToSpeech.QUEUE_ADD, null, id)
        }
    }

    fun synthesizeToFile(
        text: String,
        language: String,
        target: File,
        onDone: (Boolean) -> Unit,
    ) {
        if (text.isBlank()) { onDone(false); return }
        val piper = activePiper()
        if (piper != null) {
            Thread({
                try {
                    val audio = piper.generate(text = text, sid = 0, speed = 1.0f)
                    target.parentFile?.mkdirs()
                    audio.save(target.absolutePath)
                    handler.post { onDone(true) }
                } catch (_: Exception) {
                    handler.post { onDone(false) }
                }
            }, "parley-piper-file").start()
            return
        }
        withEngine { current ->
            applyLanguage(language)
            current.setSpeechRate(1.0f)
            target.parentFile?.mkdirs()
            if (target.exists()) target.delete()
            val id = "parley-file-${counter++}"
            callbacks[id] = onDone
            val params = Bundle().apply { putFloat(TextToSpeech.Engine.KEY_PARAM_VOLUME, 1.0f) }
            val result = current.synthesizeToFile(text, params, target, id)
            if (result != TextToSpeech.SUCCESS) { callbacks.remove(id); onDone(false) }
        }
    }

    fun stop() {
        try { player?.stop(); player?.release() } catch (_: Exception) {}
        player = null
        engine?.stop()
    }

    fun shutdown() {
        callbacks.clear()
        pending.clear()
        try { player?.stop(); player?.release() } catch (_: Exception) {}
        player = null
        engine?.stop()
        engine?.shutdown()
        engine = null
        piperTts = null
        piperVoiceId = null
        ready = false
    }
}

interface SpeechInput {
    val startedAt: Long
    fun ensure(): Boolean
    fun start(language: String): Boolean
    fun stop()
    fun cancel()
    fun destroy()
}

/** Single-shot and push-to-talk speech recognition. */
class RecognizerController(
    private val activity: Activity,
    private val onReadyForSpeech: () -> Unit = {},
    private val onPartial: (String) -> Unit = {},
    private val onFinal: (text: String, confidence: Float) -> Unit,
    private val onErrorCallback: (code: Int) -> Unit,
    private val onEnd: () -> Unit = {},
) : SpeechInput {
    private var recognizer: SpeechRecognizer? = null
    private var listening = false
    private var discardNext = false

    override var startedAt: Long = 0L
        private set

    override fun ensure(): Boolean {
        if (recognizer != null) return true
        // Some devices/ROMs report no recognition service but can still create one.
        if (!SpeechRecognizer.isRecognitionAvailable(activity)) {
            android.util.Log.w("ParleySpeech", "SpeechRecognizer.isRecognitionAvailable=false; trying anyway")
        }
        return try {
            recognizer = SpeechRecognizer.createSpeechRecognizer(activity).also {
                it.setRecognitionListener(listener)
            }
            true
        } catch (exc: Exception) {
            android.util.Log.w("ParleySpeech", "Recognizer unavailable", exc)
            recognizer = null
            false
        }
    }

    override fun start(language: String): Boolean {
        if (!ensure()) return false
        if (listening) return true
        discardNext = false
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(
                RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                RecognizerIntent.LANGUAGE_MODEL_FREE_FORM,
            )
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, speechTag(language))
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
            putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, activity.packageName)
            // Give short thinking pauses time to finish instead of ending the turn.
            putExtra("android.speech.extra.SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS", 2500L)
        }
        listening = true
        startedAt = System.currentTimeMillis()
        recognizer?.startListening(intent)
        return true
    }

    override fun stop() {
        if (!listening) return
        recognizer?.stopListening()
    }

    override fun cancel() {
        discardNext = true
        listening = false
        recognizer?.cancel()
    }

    override fun destroy() {
        discardNext = true
        listening = false
        recognizer?.destroy()
        recognizer = null
    }

    private val listener = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {
            startedAt = System.currentTimeMillis()
            onReadyForSpeech()
        }

        override fun onBeginningOfSpeech() = Unit

        override fun onRmsChanged(rmsdB: Float) = Unit

        override fun onBufferReceived(buffer: ByteArray?) = Unit

        override fun onEndOfSpeech() = Unit

        override fun onError(error: Int) {
            listening = false
            if (discardNext) {
                discardNext = false
                onEnd()
                return
            }
            onErrorCallback(error)
            onEnd()
        }

        override fun onResults(results: Bundle?) {
            listening = false
            if (discardNext) {
                discardNext = false
                onEnd()
                return
            }
            val text = results
                ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                ?.firstOrNull()
                ?.trim()
                .orEmpty()
            val confidence = results
                ?.getFloatArray(SpeechRecognizer.CONFIDENCE_SCORES)
                ?.firstOrNull()
                ?.takeIf { it > 0f }
                ?: 0.8f
            onFinal(text, confidence)
            onEnd()
        }

        override fun onPartialResults(partialResults: Bundle?) {
            val text = partialResults
                ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                ?.firstOrNull()
                ?.trim()
                .orEmpty()
            if (text.isNotEmpty()) onPartial(text)
        }

        override fun onEvent(eventType: Int, params: Bundle?) = Unit
    }
}

/**
 * Offline speech recognition using whisper.cpp.
 *
 * Records 16 kHz mono PCM16 audio with AudioRecord, converts to float, and
 * transcribes with [WhisperEngine]. Used when a Whisper model is installed.
 */
class WhisperRecognizer(
    private val engine: WhisperEngine,
    private val onReadyForSpeech: () -> Unit = {},
    private val onPartial: (String) -> Unit = {},
    private val onFinal: (text: String, confidence: Float) -> Unit,
    private val onErrorCallback: (code: Int) -> Unit,
    private val onEnd: () -> Unit = {},
) : SpeechInput {
    private val handler = Handler(Looper.getMainLooper())
    private val recording = AtomicBoolean(false)
    private val transcribing = AtomicBoolean(false)
    private var recorder: AudioRecord? = null
    private var worker: Thread? = null
    @Volatile private var language: String = "en"
    @Volatile private var discardNext = false

    override var startedAt: Long = 0L
        private set

    override fun ensure(): Boolean = engine.isReady()

    override fun start(language: String): Boolean {
        if (!engine.isReady()) return false
        if (recording.get() || transcribing.get()) return true
        discardNext = false
        this.language = language

        val sampleRate = 16000
        val minBuffer = AudioRecord.getMinBufferSize(
            sampleRate,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        if (minBuffer <= 0) {
            onErrorCallback(SpeechRecognizer.ERROR_AUDIO)
            onEnd()
            return false
        }
        val bufferSize = maxOf(minBuffer, sampleRate * 2)
        val record = try {
            AudioRecord(
                MediaRecorder.AudioSource.VOICE_RECOGNITION,
                sampleRate,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                bufferSize,
            )
        } catch (_: Exception) {
            null
        }
        if (record == null || record.state != AudioRecord.STATE_INITIALIZED) {
            record?.release()
            onErrorCallback(SpeechRecognizer.ERROR_AUDIO)
            onEnd()
            return false
        }
        recorder = record
        recording.set(true)
        startedAt = System.currentTimeMillis()
        try {
            record.startRecording()
        } catch (_: Exception) {
            recording.set(false)
            recorder = null
            record.release()
            onErrorCallback(SpeechRecognizer.ERROR_AUDIO)
            onEnd()
            return false
        }
        handler.post { onReadyForSpeech() }

        worker = thread(name = "parley-whisper-record") {
            val shortBuffer = ShortArray(1600) // 100ms
            val samples = ArrayList<Float>(sampleRate * 30)
            var speechDetected = false
            var silenceMs = 0L
            val maxMs = 30_000L
            val silenceLimitMs = 1500L
            val speechThreshold = 0.015f
            while (recording.get()) {
                val read = try {
                    record.read(shortBuffer, 0, shortBuffer.size)
                } catch (_: Exception) {
                    -1
                }
                if (read <= 0) continue
                var sumSq = 0.0
                for (i in 0 until read) {
                    val f = shortBuffer[i] / 32768f
                    samples.add(f)
                    sumSq += (f * f).toDouble()
                }
                val rms = sqrt(sumSq / read).toFloat()
                if (rms >= speechThreshold) {
                    speechDetected = true
                    silenceMs = 0L
                } else if (speechDetected) {
                    silenceMs += (read * 1000L / sampleRate)
                }
                val elapsed = System.currentTimeMillis() - startedAt
                if (elapsed >= maxMs || (speechDetected && silenceMs >= silenceLimitMs)) {
                    break
                }
            }
            val shouldTranscribe = !discardNext
            recording.set(false)
            try { record.stop() } catch (_: Exception) {}
            try { record.release() } catch (_: Exception) {}
            recorder = null

            if (!shouldTranscribe) {
                handler.post { onEnd() }
                return@thread
            }
            if (samples.isEmpty()) {
                handler.post {
                    onErrorCallback(SpeechRecognizer.ERROR_NO_MATCH)
                    onEnd()
                }
                return@thread
            }
            transcribing.set(true)
            handler.post { onPartial("…") }
            val text = try {
                engine.transcribe(samples.toFloatArray(), this.language)
            } catch (_: Exception) {
                ""
            } finally {
                transcribing.set(false)
            }
            handler.post {
                if (discardNext) {
                    discardNext = false
                    onEnd()
                    return@post
                }
                if (text.isBlank()) {
                    onErrorCallback(SpeechRecognizer.ERROR_NO_MATCH)
                } else {
                    onFinal(text, 0.9f)
                }
                onEnd()
            }
        }
        return true
    }

    override fun stop() {
        if (!recording.get()) return
        recording.set(false)
        // worker will finish and transcribe
    }

    override fun cancel() {
        discardNext = true
        recording.set(false)
        transcribing.set(false)
        try { recorder?.stop() } catch (_: Exception) {}
        try { recorder?.release() } catch (_: Exception) {}
        recorder = null
    }

    override fun destroy() {
        cancel()
    }
}

/** MediaPlayer with a position ticker, seeking and playback speed. */
class SimpleAudioPlayer {
    private var player: MediaPlayer? = null
    private val handler = Handler(Looper.getMainLooper())
    private var ticker: Runnable? = null
    private var tickerActive = false

    var onTick: ((positionMs: Int, durationMs: Int, playing: Boolean) -> Unit)? = null
    var onComplete: (() -> Unit)? = null

    var speed: Float = 1.0f
        set(value) {
            field = value.coerceIn(0.5f, 2.0f)
            player?.let {
                try {
                    it.playbackParams = it.playbackParams.setSpeed(field)
                } catch (_: Exception) {
                    // Some codecs do not support speed changes.
                }
            }
        }

    val isPlaying: Boolean
        get() = try {
            player?.isPlaying == true
        } catch (_: Exception) {
            false
        }

    /**
     * Prepare [file] for playback. Passing [onReady] prepares asynchronously so
     * decoding never blocks the interface thread; without it the call is
     * synchronous for simple callers.
     */
    fun load(file: File, onReady: ((Boolean) -> Unit)? = null): Boolean {
        release()
        return try {
            val mediaPlayer = MediaPlayer().apply {
                setDataSource(file.absolutePath)
                setOnCompletionListener {
                    stopTicker()
                    onTick?.invoke(duration, duration, false)
                    onComplete?.invoke()
                }
                setOnErrorListener { _, _, _ ->
                    stopTicker()
                    onTick?.invoke(0, 0, false)
                    true
                }
            }
            player = mediaPlayer
            if (onReady != null) {
                mediaPlayer.setOnPreparedListener {
                    try {
                        mediaPlayer.playbackParams = mediaPlayer.playbackParams.setSpeed(speed)
                    } catch (_: Exception) {
                        // Default speed is fine.
                    }
                    onTick?.invoke(0, mediaPlayer.duration, false)
                    onReady(true)
                }
                mediaPlayer.prepareAsync()
            } else {
                mediaPlayer.prepare()
                try {
                    mediaPlayer.playbackParams = mediaPlayer.playbackParams.setSpeed(speed)
                } catch (_: Exception) {
                    // Default speed is fine.
                }
                onTick?.invoke(0, mediaPlayer.duration, false)
            }
            true
        } catch (_: Exception) {
            release()
            onReady?.invoke(false)
            false
        }
    }

    fun play() {
        val current = player ?: return
        try {
            current.start()
            try {
                current.playbackParams = current.playbackParams.setSpeed(speed)
            } catch (_: Exception) {
                // Default speed is fine.
            }
            startTicker()
        } catch (_: Exception) {
            // Ignore a player that is not prepared.
        }
    }

    fun pause() {
        try {
            player?.pause()
        } catch (_: Exception) {
            // Ignore.
        }
        stopTicker()
        onTick?.invoke(player?.currentPosition ?: 0, player?.duration ?: 0, false)
    }

    fun toggle() {
        if (isPlaying) pause() else play()
    }

    fun seekTo(positionMs: Int) {
        player?.let {
            try {
                it.seekTo(positionMs.coerceIn(0, it.duration))
            } catch (_: Exception) {
                // Ignore.
            }
        }
    }

    fun replay() {
        seekTo(0)
        play()
    }

    fun stop() {
        try {
            player?.pause()
            player?.seekTo(0)
        } catch (_: Exception) {
            // Ignore.
        }
        stopTicker()
    }

    fun release() {
        stopTicker()
        try {
            player?.release()
        } catch (_: Exception) {
            // Ignore.
        }
        player = null
    }

    private fun startTicker() {
        if (tickerActive) return
        tickerActive = true
        ticker = object : Runnable {
            override fun run() {
                val current = player ?: return
                val duration = try {
                    current.duration
                } catch (_: Exception) {
                    0
                }
                val position = try {
                    current.currentPosition
                } catch (_: Exception) {
                    0
                }
                onTick?.invoke(position, duration, isPlaying)
                if (tickerActive && isPlaying) handler.postDelayed(this, 300)
            }
        }
        handler.post(ticker!!)
    }

    private fun stopTicker() {
        tickerActive = false
        ticker?.let { handler.removeCallbacks(it) }
        ticker = null
    }
}

/** Human-readable message for a SpeechRecognizer error code. */
fun recognitionErrorMessage(code: Int): String = when (code) {
    SpeechRecognizer.ERROR_AUDIO -> "audio recording error"
    SpeechRecognizer.ERROR_CLIENT -> "recogniser client error"
    SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "microphone permission denied"
    SpeechRecognizer.ERROR_NETWORK -> "network error"
    SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "network timeout"
    SpeechRecognizer.ERROR_NO_MATCH -> "no speech recognised"
    SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> "recogniser busy"
    SpeechRecognizer.ERROR_SERVER -> "recognition server error"
    SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "no speech detected"
    else -> "speech error $code"
}
