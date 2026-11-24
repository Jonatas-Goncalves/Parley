package io.github.jonatasgoncalves.parley

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.media.MediaPlayer
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import java.io.File
import java.util.Locale

/**
 * Thin wrapper around the system text-to-speech engine.
 *
 * Speech is either spoken directly or synthesised into a file so the exercise
 * player can offer seeking and playback speed, like the desktop player.
 */
class TtsController(context: Context, private val onReady: (Boolean) -> Unit = {}) :
    TextToSpeech.OnInitListener {

    private val pending = ArrayList<() -> Unit>()
    private val callbacks = HashMap<String, (Boolean) -> Unit>()
    private var engine: TextToSpeech? = TextToSpeech(context.applicationContext, this)
    private var counter = 0

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
                    val callback = utteranceId?.let { callbacks.remove(it) }
                    Handler(Looper.getMainLooper()).post { callback?.invoke(true) }
                }

                @Deprecated("Deprecated in Java")
                override fun onError(utteranceId: String?) {
                    val callback = utteranceId?.let { callbacks.remove(it) }
                    Handler(Looper.getMainLooper()).post { callback?.invoke(false) }
                }

                override fun onError(utteranceId: String?, errorCode: Int) {
                    val callback = utteranceId?.let { callbacks.remove(it) }
                    Handler(Looper.getMainLooper()).post { callback?.invoke(false) }
                }
            })
        }
        val queued = pending.toList()
        pending.clear()
        if (ready) queued.forEach { it() }
        onReady(ready)
    }

    private fun withEngine(action: (TextToSpeech) -> Unit) {
        val current = engine
        if (current == null) return
        if (!ready) {
            pending.add { if (ready) action(current) }
            return
        }
        action(current)
    }

    fun applyLanguage(language: String): Boolean {
        val current = engine ?: return false
        val result = current.setLanguage(Locale.forLanguageTag(speechTag(language)))
        languageSupported = result != TextToSpeech.LANG_MISSING_DATA &&
            result != TextToSpeech.LANG_NOT_SUPPORTED
        if (!languageSupported) {
            current.setLanguage(Locale.getDefault())
        }
        return languageSupported
    }

    fun speak(
        text: String,
        language: String,
        slow: Boolean = false,
        onDone: ((Boolean) -> Unit)? = null,
    ) {
        if (text.isBlank()) return
        withEngine { current ->
            applyLanguage(language)
            current.stop()
            current.setSpeechRate(if (slow) 0.82f else 1.0f)
            val id = "parley-${counter++}"
            if (onDone != null) callbacks[id] = onDone
            current.speak(text, TextToSpeech.QUEUE_FLUSH, null, id)
        }
    }

    /** Queue one fragment of a streaming reply without flushing earlier parts. */
    fun speakChunk(
        text: String,
        language: String,
        onDone: ((Boolean) -> Unit)? = null,
    ) {
        if (text.isBlank()) return
        withEngine { current ->
            applyLanguage(language)
            current.setSpeechRate(1.0f)
            val id = "parley-${counter++}"
            if (onDone != null) callbacks[id] = onDone
            current.speak(text, TextToSpeech.QUEUE_ADD, null, id)
        }
    }

    /** Synthesise into a file so it can be played with seek and speed control. */
    fun synthesizeToFile(
        text: String,
        language: String,
        target: File,
        onDone: (Boolean) -> Unit,
    ) {
        if (text.isBlank()) {
            onDone(false)
            return
        }
        withEngine { current ->
            applyLanguage(language)
            current.setSpeechRate(1.0f)
            target.parentFile?.mkdirs()
            if (target.exists()) target.delete()
            val id = "parley-file-${counter++}"
            callbacks[id] = onDone
            val params = Bundle().apply {
                putFloat(TextToSpeech.Engine.KEY_PARAM_VOLUME, 1.0f)
            }
            val result = current.synthesizeToFile(text, params, target, id)
            if (result != TextToSpeech.SUCCESS) {
                callbacks.remove(id)
                onDone(false)
            }
        }
    }

    fun stop() {
        engine?.stop()
    }

    fun shutdown() {
        callbacks.clear()
        pending.clear()
        engine?.stop()
        engine?.shutdown()
        engine = null
        ready = false
    }
}

/** Single-shot and push-to-talk speech recognition. */
class RecognizerController(
    private val activity: Activity,
    private val onReadyForSpeech: () -> Unit = {},
    private val onPartial: (String) -> Unit = {},
    private val onFinal: (text: String, confidence: Float) -> Unit,
    private val onErrorCallback: (code: Int) -> Unit,
    private val onEnd: () -> Unit = {},
) {
    private var recognizer: SpeechRecognizer? = null
    private var listening = false
    private var discardNext = false

    var startedAt: Long = 0L
        private set

    fun ensure(): Boolean {
        if (!SpeechRecognizer.isRecognitionAvailable(activity)) return false
        if (recognizer != null) return true
        recognizer = SpeechRecognizer.createSpeechRecognizer(activity).also {
            it.setRecognitionListener(listener)
        }
        return true
    }

    fun start(language: String): Boolean {
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

    fun stop() {
        if (!listening) return
        recognizer?.stopListening()
    }

    fun cancel() {
        discardNext = true
        listening = false
        recognizer?.cancel()
    }

    fun destroy() {
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
