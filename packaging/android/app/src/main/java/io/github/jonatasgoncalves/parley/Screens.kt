package io.github.jonatasgoncalves.parley

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.style.ForegroundColorSpan
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.core.content.ContextCompat
import java.io.File
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/** Base class for a page inside the navigation host. */
abstract class Screen(val activity: MainActivity) {
    val ui: Ui get() = activity.ui
    val prefs: Prefs get() = activity.prefs
    val scores: ScoreHistory get() = activity.scores

    abstract fun build(): View

    open fun shutdown() = Unit

    open fun onMicPermission(granted: Boolean) = Unit

    open fun onBackPressed(): Boolean = false

    protected fun requestMic(): Boolean {
        if (ContextCompat.checkSelfPermission(activity, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED
        ) {
            return true
        }
        activity.requestMicPermission()
        return false
    }
}

// -- welcome -------------------------------------------------------------

class WelcomeScreen(activity: MainActivity) : Screen(activity) {
    override fun build(): View {
        // Keep the heading and the language grid together as one centred block.
        val holder = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL or Gravity.CENTER_VERTICAL
            setBackgroundColor(ui.palette.background)
            setPadding(ui.dp(24), ui.dp(20), ui.dp(24), ui.dp(20))
        }

        val heading = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
        }
        val hero = ui.hero(ui.t("welcome_title"))
        hero.gravity = Gravity.CENTER_HORIZONTAL
        heading.addView(hero)
        val prompt = ui.muted(ui.t("welcome_prompt"))
        prompt.gravity = Gravity.CENTER_HORIZONTAL
        prompt.setPadding(0, ui.dp(8), 0, ui.dp(56))
        heading.addView(prompt)
        holder.addView(heading, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ))

        val buttons = PRACTICE_LANGUAGES.map { code ->
            val name = when (code) {
                "ja" -> ui.t("language_ja")
                "ko" -> ui.t("language_ko")
                "zh" -> ui.t("language_zh")
                else -> LANGUAGE_NATIVE_NAMES[code] ?: code
            }
            val label = "${LANGUAGE_FLAGS[code] ?: "🌐"}  $name"
            ui.button(label, primary = code == prefs.target, onClick = { choose(code) }).apply {
                minHeight = ui.dp(62)
                setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, 16f)
            }
        }
        val grid = ui.grid(buttons, columns = 2)
        for (index in 1 until grid.childCount) {
            (grid.getChildAt(index).layoutParams as LinearLayout.LayoutParams).topMargin = ui.dp(20)
        }
        holder.addView(grid, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ))

        return ScrollView(activity).apply {
            isFillViewport = true
            setBackgroundColor(ui.palette.background)
            addView(holder, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT,
            ))
        }
    }

    private fun choose(code: String) {
        var native = prefs.native
        if (code == native) {
            native = if (code != "pt") "pt" else "en"
        }
        prefs.target = code
        prefs.native = native
        activity.openPractice()
    }
}

// -- practice hub --------------------------------------------------------

class PracticeScreen(activity: MainActivity) : Screen(activity) {
    override fun build(): View {
        val body = ui.body()
        body.addView(ui.hero(ui.t("practice_title")))
        body.addView(ui.section(ui.t("voice_practice")))

        body.addView(modeCard("voice_practice", "voice_practice_desc", "voice_practice"), topMargin(10))
        body.addView(modeCard("pronunciation", "pronunciation_desc", "pronunciation"), topMargin(10))

        body.addView(ui.section(ui.t("supplements")))
        body.addView(supplementsCard(), topMargin(10))
        body.addView(progressCard(), topMargin(14))
        return ui.scroll(body)
    }

    private fun topMargin(value: Int): LinearLayout.LayoutParams =
        LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(value) }

    private fun modeCard(titleKey: String, subtitleKey: String, mode: String): LinearLayout {
        val card = ui.card()
        card.addView(ui.cardTitle(ui.t(titleKey)))
        card.addView(ui.muted(ui.t(subtitleKey)).apply { setPadding(0, ui.dp(4), 0, ui.dp(10)) })
        val row = LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        val bands = listOf("beginner", "intermediate", "advanced")
        bands.forEachIndexed { index, band ->
            val button = ui.button(ui.t(band), compact = true) {
                activity.showScenarios(mode, band)
            }
            val params = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            if (index > 0) params.marginStart = ui.dp(8)
            row.addView(button, params)
        }
        card.addView(row)
        return card
    }

    private fun supplementsCard(): LinearLayout {
        val card = ui.card()
        card.addView(supplementRow(ui.t("spoken_stories"), ui.t("spoken_stories_desc"), "▶") {
            activity.showStories()
        })
        card.addView(ui.divider())
        card.addView(supplementRow(ui.t("complete_sentence"), ui.t("complete_sentence_desc"), "✎") {
            activity.showSentence()
        })
        return card
    }

    private fun supplementRow(title: String, subtitle: String, icon: String, onClick: () -> Unit): LinearLayout {
        val row = LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        val text = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
        text.addView(ui.cardTitle(title))
        text.addView(ui.muted(subtitle).apply { setPadding(0, ui.dp(2), 0, 0) })
        row.addView(text, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        val action = ui.ghostButton(icon, onClick)
        val params = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        )
        params.marginStart = ui.dp(10)
        row.addView(action, params)
        return row
    }

    private fun progressCard(): LinearLayout {
        val card = ui.card()
        card.addView(ui.cardTitle(ui.t("progress_title")))
        card.addView(ui.muted(ui.t("progress_desc")).apply { setPadding(0, ui.dp(4), 0, ui.dp(8)) })

        val history = scores.load()
        val current = history.filter { it["language"] == prefs.target }
        val summary = scores.summarize(current)
        val languageLabel = languageChoiceLabel(prefs.target)

        if (current.isEmpty()) {
            card.addView(ui.muted(ui.t("progress_empty", "language" to languageLabel)))
        } else {
            card.addView(
                ui.textView(
                    ui.t(
                        "progress_sessions",
                        "count" to summary["count"],
                        "average" to summary["average"],
                        "best" to summary["best"],
                    ),
                    15f,
                    ui.palette.text,
                    bold = true,
                ),
            )
            card.addView(
                ui.muted(
                    ui.t(
                        "progress_level",
                        "level" to ui.t(summary["band_key"]?.toString() ?: "score_band_1"),
                    ),
                ).apply { setPadding(0, ui.dp(4), 0, 0) },
            )
            card.addView(ui.cardTitle(ui.t("progress_recent")).apply { setPadding(0, ui.dp(10), 0, ui.dp(2)) })
            current.takeLast(5).reversed().forEach { record ->
                val row = LinearLayout(activity).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                }
                row.addView(ui.muted(shortDate(record["date"]?.toString().orEmpty())))
                val title = ui.textView(
                    record["scenario_label"]?.toString() ?: record["scenario"]?.toString().orEmpty(),
                    14f,
                    ui.palette.text,
                )
                row.addView(title, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
                row.addView(
                    ui.textView(
                        "${(record["score"] as? Number)?.toInt() ?: 0}/100",
                        14f,
                        ui.palette.text,
                        bold = true,
                    ),
                )
                card.addView(row, topMargin(4))
            }
        }

        val grouped = history.groupBy { it["language"]?.toString().orEmpty() }
            .filterKeys { it.isNotEmpty() }
        if (grouped.size > 1) {
            card.addView(ui.cardTitle(ui.t("progress_overall")).apply { setPadding(0, ui.dp(12), 0, ui.dp(2)) })
            grouped.toSortedMap().forEach { (language, records) ->
                val data = scores.summarize(records)
                card.addView(
                    ui.muted(
                        ui.t(
                            "progress_language_row",
                            "language" to languageChoiceLabel(language),
                            "count" to data["count"],
                            "average" to data["average"],
                        ),
                    ).apply { setPadding(0, ui.dp(2), 0, 0) },
                )
            }
        }

        card.addView(
            ui.button(ui.t("progress_level_test"), primary = true) { activity.showLevelTest() },
            topMargin(12),
        )
        return card
    }

    private fun shortDate(raw: String): String = try {
        val date = Instant.parse(raw).atZone(ZoneId.systemDefault()).toLocalDate()
        date.format(DateTimeFormatter.ISO_LOCAL_DATE)
    } catch (_: Exception) {
        raw.take(10)
    }
}

// -- scenario picker -----------------------------------------------------

class ScenariosScreen(
    activity: MainActivity,
    private val mode: String,
    private val band: String,
) : Screen(activity) {
    override fun build(): View {
        val body = ui.body()
        body.addView(ui.hero(ui.t(if (mode == "voice_practice") "voice_practice" else "pronunciation")))
        body.addView(
            ui.textView(
                "  ${ui.t(band)}  ",
                14f,
                ui.palette.text,
                bold = true,
            ).apply {
                background = ui.rounded(ui.palette.surfaceAlt, 20f, ui.palette.border)
                setPadding(ui.dp(10), ui.dp(5), ui.dp(10), ui.dp(5))
                val params = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT,
                    LinearLayout.LayoutParams.WRAP_CONTENT,
                )
                params.topMargin = ui.dp(10)
                layoutParams = params
            },
        )
        body.addView(ui.section(ui.t("what_topic")))
        if (mode != "voice_practice") {
            body.addView(ui.muted(ui.t("pronunciation_hint")))
        }
        val list = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
        Scenario.forBand(activity, band).forEach { scenario ->
            val button = ui.button(scenario.label) { open(scenario) }
            button.gravity = Gravity.START or Gravity.CENTER_VERTICAL
            val params = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            )
            params.topMargin = ui.dp(8)
            list.addView(button, params)
        }
        body.addView(list)
        return ui.scroll(body)
    }

    private fun open(scenario: Scenario) {
        prefs.scenario = scenario.id
        if (mode == "voice_practice") {
            activity.showSession(scenario.id)
        } else {
            activity.showPronunciation(scenario.id)
        }
    }
}

// -- voice practice ------------------------------------------------------

class SessionScreen(
    activity: MainActivity,
    private val scenarioId: String,
) : Screen(activity) {
    private val scenario = Scenario.get(activity, scenarioId)
    private val turns = ArrayList<TurnMetrics>()
    private val messages = ArrayList<ChatClient.Message>()
    private val askedQuestions = ArrayList<String>()
    private val chatBox = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
    private lateinit var chatScroll: ScrollView
    private lateinit var statusDot: View
    private lateinit var statusLabel: TextView
    private lateinit var banner: LinearLayout
    private lateinit var bannerText: TextView
    private lateinit var micButton: Button
    private lateinit var modeContinuous: Button
    private lateinit var modePtt: Button
    private lateinit var entry: EditText
    private lateinit var sendButton: Button
    private var aiBubble: TextView? = null
    private var lastAiText = ""
    private var ttsMissingShown = false

    private var tts: TtsController? = null
    private var recognizer: RecognizerController? = null
    private var backendReady = false
    private var destroyed = false
    private var busy = false
    private var paused = false
    private var listening = false
    private var recordingPtt = false
    private var pttHeld = false
    private var spokenChars = 0
    private var pendingSpeech = 0
    private var replyComplete = false

    override fun build(): View {
        val root = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
        root.setBackgroundColor(ui.palette.background)

        root.addView(header(), LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ))

        banner = ui.card(12).apply { visibility = View.GONE }
        bannerText = ui.muted(ui.t("ai_not_ready"))
        banner.addView(bannerText)
        root.addView(banner, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply {
            marginStart = ui.dp(16)
            marginEnd = ui.dp(16)
            bottomMargin = ui.dp(6)
        })

        chatScroll = ScrollView(activity).apply {
            isFillViewport = true
            setPadding(ui.dp(16), ui.dp(4), ui.dp(16), ui.dp(8))
            addView(chatBox)
        }
        root.addView(chatScroll, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            0,
            1f,
        ))

        root.addView(controls())
        tts = TtsController(activity) { ready -> if (!ready) log("text-to-speech unavailable") }
        recognizer = RecognizerController(
            activity,
            onReadyForSpeech = { setState("listening") },
            onPartial = { setStatus(it) },
            onFinal = ::handleFinal,
            onErrorCallback = ::handleRecognitionError,
        )
        boot()
        return root
    }

    private fun log(message: String) = activity.log("session: $message")

    private fun header(): View {
        val row = LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(ui.dp(18), ui.dp(10), ui.dp(12), ui.dp(4))
        }
        statusDot = View(activity).apply {
            background = ui.rounded(ui.palette.accent, 5f)
            layoutParams = LinearLayout.LayoutParams(ui.dp(10), ui.dp(10))
            val params = LinearLayout.LayoutParams(ui.dp(10), ui.dp(10))
            params.marginEnd = ui.dp(8)
            layoutParams = params
        }
        statusLabel = ui.muted(ui.t("loading"))
        row.addView(statusDot)
        row.addView(statusLabel, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        row.addView(ui.ghostButton(ui.t("end_session")) { endSession() })
        return row
    }

    private fun controls(): View {
        val bar = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(ui.dp(16), ui.dp(4), ui.dp(16), ui.dp(16))
        }

        val modes = LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        modeContinuous = ui.button(ui.t("continuous_mode"), compact = true) { setMode("continuous") }
        modePtt = ui.button(ui.t("push_to_talk"), compact = true) { setMode("push_to_talk") }
        modes.addView(modeContinuous, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        modes.addView(modePtt, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f).apply {
            marginStart = ui.dp(8)
        })
        bar.addView(modes)

        val top = LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }

        micButton = Button(activity).apply {
            text = "🎙"
            isAllCaps = false
            setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, 22f)
            setTextColor(ui.palette.onAccent)
            background = ui.ripple(ui.palette.accent, 32f)
            stateListAnimator = null
            gravity = Gravity.CENTER
        }
        val micParams = LinearLayout.LayoutParams(ui.dp(64), ui.dp(64))
        top.addView(micButton, micParams)
        micButton.setOnClickListener { micClicked() }
        micButton.setOnTouchListener { _, event -> micTouched(event) }

        top.addView(ui.ghostButton("🔁") { replay() }, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { marginStart = ui.dp(8) })

        val hint = ui.muted(ui.t("listeners_note"))
        hint.setPadding(ui.dp(10), 0, 0, 0)
        top.addView(hint, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        bar.addView(top, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(10) })

        val entryRow = LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        entry = ui.field("", ui.t("type_message"))
        entryRow.addView(entry, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        sendButton = ui.button(ui.t("send"), primary = true) { sendTyped() }
        val sendParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        )
        sendParams.marginStart = ui.dp(8)
        entryRow.addView(sendButton, sendParams)
        bar.addView(entryRow, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(10) })
        updateModeButtons()
        updateMicLabel()
        return bar
    }

    private fun boot() {
        setState("thinking")
        Thread {
            val available = ChatClient.ping(prefs.baseUrl)
            activity.runOnUiThread {
                if (destroyed) return@runOnUiThread
                backendReady = available
                if (!available) {
                    banner.visibility = View.VISIBLE
                    bannerText.text = ui.t("android_backend_unreachable", "url" to prefs.baseUrl)
                    if (banner.childCount == 1) {
                        banner.addView(
                            ui.button(ui.t("android_offline_setup"), compact = true) {
                                activity.showOfflineHelp()
                            },
                            LinearLayout.LayoutParams(
                                LinearLayout.LayoutParams.WRAP_CONTENT,
                                LinearLayout.LayoutParams.WRAP_CONTENT,
                            ).apply { topMargin = ui.dp(8) },
                        )
                    }
                    setState("paused")
                    setStatus(ui.t("paused"))
                    addBubble(ui.t("android_backend_unreachable", "url" to prefs.baseUrl), BubbleKind.NOTE)
                } else {
                    banner.visibility = View.GONE
                    startConversation()
                }
            }
        }.start()
    }

    private fun startConversation() {
        messages.clear()
        messages.add(
            ChatClient.Message(
                "system",
                Prompts.systemPrompt(
                    scenario,
                    prefs.target,
                    prefs.native,
                    askedQuestions,
                    opening = true,
                ),
            ),
        )
        messages.add(ChatClient.Message("user", Prompts.openingGreeting(prefs.target)))
        requestReply(opening = true)
    }

    private fun requestReply(opening: Boolean) {
        if (!backendReady || busy) return
        busy = true
        paused = false
        spokenChars = 0
        pendingSpeech = 0
        replyComplete = false
        setState("thinking")
        val currentMessages = messages.toList()
        aiBubble = addBubble("…", BubbleKind.AI)
        var streamed = ""
        Thread {
            try {
                val raw = ChatClient.chatStream(
                    prefs.baseUrl,
                    prefs.model,
                    currentMessages,
                    onDelta = { visible ->
                        streamed = visible
                        activity.runOnUiThread {
                            if (!destroyed) {
                                aiBubble?.text = visible.ifBlank { "…" }
                                ui.scrollToBottom(chatScroll)
                                speakReadyPart(visible)
                            }
                        }
                    },
                    isCancelled = { destroyed },
                    maxTokens = 140,
                )
                if (destroyed) return@Thread
                val parsed = ReplyParser.parse(raw)
                val main = parsed.main.trim().ifBlank { streamed.trim().ifBlank { raw.trim() } }
                val note = parsed.note.trim()
                activity.runOnUiThread {
                    if (destroyed) return@runOnUiThread
                    aiBubble?.text = main
                    messages.add(ChatClient.Message("assistant", main))
                    askedQuestions.clear()
                    askedQuestions.addAll(TextKit.extractQuestions(main).takeLast(12))
                    refreshSystemPrompt()
                    if (note.isNotEmpty()) {
                        addBubble("💡  ${note.replace("**", "").trim()}", BubbleKind.NOTE)
                    }
                    lastAiText = main
                    busy = false
                    aiBubble = null
                    activity.log("session: assistant reply, ${main.length} chars")
                    finishSpeech(main)
                }
            } catch (exc: Exception) {
                val error = exc.message ?: exc.javaClass.simpleName
                activity.log("session: chat failed: $error")
                activity.runOnUiThread {
                    if (destroyed) return@runOnUiThread
                    busy = false
                    aiBubble?.text = ui.t("error_backend", "error" to error)
                    aiBubble = null
                    setState("paused")
                    setStatus(ui.t("paused"))
                }
            }
        }.start()
    }

    /** Speak complete sentences as soon as they arrive instead of waiting for the whole reply. */
    private fun speakReadyPart(text: String) {
        val from = spokenChars.coerceAtMost(text.length)
        val rest = text.substring(from)
        var cut = -1
        for (index in rest.indices) {
            val char = rest[index]
            val boundary = char == '.' || char == '?' || char == '!' ||
                char == '。' || char == '？' || char == '！'
            if (boundary && (index + 1 == rest.length || rest[index + 1].isWhitespace())) {
                cut = index + 1
            }
        }
        if (cut <= 0) return
        val sentence = rest.substring(0, cut).trim()
        spokenChars = from + cut
        if (sentence.isBlank()) return
        pendingSpeech++
        tts?.speakChunk(sentence, prefs.target) { speechFinished() }
        setState("speaking")
    }

    /** Speak the tail of the reply and restart listening once all parts finished. */
    private fun finishSpeech(fullText: String) {
        replyComplete = true
        val rest = fullText.substring(spokenChars.coerceAtMost(fullText.length)).trim()
        if (rest.isNotBlank()) {
            pendingSpeech++
            tts?.speakChunk(rest, prefs.target) { speechFinished() }
            setState("speaking")
        }
        if (tts == null || (pendingSpeech == 0 && rest.isBlank())) {
            onSpeechDone()
            return
        }
        micButton.postDelayed({
            if (!destroyed && replyComplete && pendingSpeech > 0) {
                activity.log("session: speech callback timeout")
                pendingSpeech = 0
                onSpeechDone()
            }
        }, 20_000)
    }

    private fun speechFinished() {
        activity.runOnUiThread {
            if (destroyed) return@runOnUiThread
            pendingSpeech--
            if (replyComplete && pendingSpeech <= 0) onSpeechDone()
        }
    }

    private fun refreshSystemPrompt() {
        if (messages.isEmpty()) return
        if (messages[0].role != "system") return
        messages[0] = ChatClient.Message(
            "system",
            Prompts.systemPrompt(scenario, prefs.target, prefs.native, askedQuestions),
        )
        val system = messages.filter { it.role == "system" }
        val rest = messages.filter { it.role != "system" }
        messages.clear()
        messages.addAll(system)
        messages.addAll(rest.takeLast(10))
    }

    private fun speak(text: String) {
        if (text.isBlank()) {
            onSpeechDone()
            return
        }
        val current = tts
        if (current == null || !current.ready) {
            setState("listening")
            onSpeechDone()
            return
        }
        setState("speaking")
        current.speak(text, prefs.target, slow = false) { ok ->
            activity.runOnUiThread {
                if (destroyed) return@runOnUiThread
                if (!ok && !ttsMissingShown) {
                    ttsMissingShown = true
                    addBubble(ui.t("android_tts_missing"), BubbleKind.NOTE)
                }
                onSpeechDone()
            }
        }
    }

    private fun onSpeechDone() {
        if (destroyed) return
        if (prefs.voiceMode == "continuous" && !paused && backendReady) {
            setState("listening")
            micButton.postDelayed({ autoListen() }, 200)
        } else {
            setState("paused")
        }
    }

    private fun autoListen() {
        if (destroyed || busy || paused || !backendReady) return
        if (prefs.voiceMode != "continuous") return
        if (!startRecognition()) return
    }

    private fun startRecognition(): Boolean {
        if (listening) return true
        if (!requestMic()) return false
        val current = recognizer ?: return false
        if (!current.ensure()) {
            setStatus(ui.t("android_speech_unavailable"))
            addBubble(ui.t("android_speech_unavailable"), BubbleKind.NOTE)
            return false
        }
        tts?.stop()
        val started = current.start(prefs.target)
        listening = started
        if (started) {
            setState("listening")
            updateMicLabel()
        }
        return started
    }

    private fun handleFinal(text: String, confidence: Float) {
        listening = false
        if (destroyed) return
        updateMicLabel()
        val spoken = text.trim()
        if (spoken.isEmpty()) {
            setStatus(ui.t("android_not_understood"))
            setState("paused")
            if (prefs.voiceMode == "continuous" && !paused) {
                micButton.postDelayed({ autoListen() }, 700)
            }
            return
        }
        val elapsed = 1.0.coerceAtLeast((System.currentTimeMillis() - (recognizer?.startedAt ?: 0)) / 1000.0)
        val wordCount = max(1, spoken.split(Regex("\\s+")).size)
        val wpm = wordCount / elapsed * 60.0
        val pauseRatio = (1.0 - min(1.0, wpm / 150.0)).coerceIn(0.0, 1.0)
        turns.add(
            TurnMetrics(
                text = spoken,
                words = wordCount,
                speechSeconds = elapsed,
                pauseRatio = pauseRatio,
                wordsPerMinute = wpm,
                confidence = confidence.toDouble(),
            ),
        )
        addBubble("🧑  $spoken", BubbleKind.USER)
        messages.add(ChatClient.Message("user", spoken))
        refreshSystemPrompt()
        requestReply(opening = false)
    }

    private fun handleRecognitionError(code: Int) {
        listening = false
        if (destroyed) return
        updateMicLabel()
        val friendly = code == android.speech.SpeechRecognizer.ERROR_NO_MATCH ||
            code == android.speech.SpeechRecognizer.ERROR_SPEECH_TIMEOUT
        setStatus(if (friendly) ui.t("android_not_understood") else recognitionErrorMessage(code))
        setState("paused")
        activity.log("session: recogniser error $code")
        if (prefs.voiceMode == "continuous" && !paused && backendReady) {
            // Reset the engine before starting again; some devices misbehave if
            // startListening follows a timeout without an explicit cancel.
            recognizer?.cancel()
            activity.log("session: restarting listening after error $code")
            micButton.postDelayed({ autoListen() }, 1500)
        }
    }

    private fun setMode(mode: String) {
        if (prefs.voiceMode == mode) return
        prefs.voiceMode = mode
        if (mode == "push_to_talk" && listening) {
            recognizer?.cancel()
            listening = false
        }
        paused = false
        updateModeButtons()
        updateMicLabel()
        setState("paused")
        if (mode == "continuous") autoListen()
    }

    private fun updateModeButtons() {
        val continuous = prefs.voiceMode == "continuous"
        styleMode(modeContinuous, continuous)
        styleMode(modePtt, !continuous)
    }

    private fun styleMode(button: Button, selected: Boolean) {
        button.background = if (selected) {
            ui.ripple(ui.palette.accent, 12f)
        } else {
            ui.ripple(ui.palette.surfaceAlt, 12f, ui.palette.border)
        }
        button.setTextColor(if (selected) ui.palette.onAccent else ui.palette.text)
    }

    private fun updateMicLabel() {
        micButton.text = when {
            prefs.voiceMode == "push_to_talk" && recordingPtt -> "■"
            prefs.voiceMode == "push_to_talk" -> "🎙"
            paused -> "▶"
            else -> "⏸"
        }
    }

    private fun micClicked() {
        if (prefs.voiceMode == "push_to_talk") return
        if (!backendReady || busy) return
        if (paused) {
            paused = false
            setState("listening")
            updateMicLabel()
            autoListen()
        } else {
            paused = true
            if (listening) {
                recognizer?.cancel()
                listening = false
            }
            setState("paused")
            updateMicLabel()
        }
    }

    private fun micTouched(event: MotionEvent): Boolean {
        if (prefs.voiceMode != "push_to_talk") return false
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                if (busy || !backendReady) return true
                paused = false
                pttHeld = true
                recordingPtt = true
                micButton.text = "■"
                val current = recognizer
                if (current != null && requestMic() && current.ensure()) {
                    if (current.start(prefs.target)) {
                        listening = true
                        setState("listening")
                    }
                }
                return true
            }

            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                pttHeld = false
                recordingPtt = false
                if (listening) recognizer?.stop()
                updateMicLabel()
                micButton.performClick()
                return true
            }
        }
        return false
    }

    private fun replay() {
        if (lastAiText.isNotBlank()) speak(lastAiText)
    }

    private fun sendTyped() {
        val text = entry.text.toString().trim()
        if (text.isEmpty()) {
            setStatus(ui.t("android_empty_message"))
            return
        }
        if (!backendReady) {
            banner.visibility = View.VISIBLE
            bannerText.text = ui.t("android_backend_unreachable", "url" to prefs.baseUrl)
            return
        }
        entry.setText("")
        if (listening) {
            recognizer?.cancel()
            listening = false
        }
        addBubble("🧑  $text", BubbleKind.USER)
        messages.add(ChatClient.Message("user", text))
        refreshSystemPrompt()
        requestReply(opening = false)
    }

    private fun endSession() {
        val result = scoreTurns(turns)
        if (turns.isNotEmpty()) {
            scores.save(prefs.target, scenario.id, scenario.label, result)
        }
        showScoreDialog(result)
    }

    private fun showScoreDialog(result: SessionScore) {
        val box = ui.body(22, 22, 18)
        box.addView(ui.hero(ui.t("session_score_title")))
        box.addView(
            ui.textView("${result.score}/100", 46f, ui.palette.accent, bold = true)
                .apply { setPadding(0, ui.dp(6), 0, 0) },
        )
        box.addView(ui.cardTitle(ui.t(result.bandKey)))
        box.addView(
            ui.muted(
                ui.t(
                    "session_score_body",
                    "score" to result.score,
                    "level" to ui.t(result.bandKey),
                    "turns" to result.turns,
                    "words" to result.words,
                ),
            ).apply { setPadding(0, ui.dp(8), 0, 0) },
        )
        box.addView(ui.muted(ui.t("progress_desc")).apply { setPadding(0, ui.dp(10), 0, 0) })
        if (turns.isNotEmpty()) {
            box.addView(ui.muted(ui.t("android_saved")).apply { setPadding(0, ui.dp(6), 0, 0) })
        }
        val actions = LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END
        }
        val dialog = activity.styledDialog(box)
        actions.addView(ui.button(ui.t("close"), primary = true) {
            dialog.dismiss()
            activity.resetToPractice()
        })
        box.addView(actions, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(16) })
        dialog.setCancelable(false)
        dialog.show()
    }

    private fun addBubble(text: String, kind: BubbleKind): TextView {
        val row = LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = if (kind == BubbleKind.USER) Gravity.END else Gravity.START
        }
        val bubble = ui.bubble(text, kind)
        bubble.maxWidth = (activity.resources.displayMetrics.widthPixels * 0.84f).toInt()
        row.addView(bubble)
        val params = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        )
        params.topMargin = ui.dp(8)
        chatBox.addView(row, params)
        ui.scrollToBottom(chatScroll)
        return bubble
    }

    private fun setState(mode: String) {
        val color = when (mode) {
            "listening" -> ui.palette.good
            "thinking" -> ui.palette.accent
            "speaking" -> ui.palette.accent
            else -> ui.palette.muted
        }
        statusDot.background = ui.rounded(color, 5f)
        val key = when (mode) {
            "listening" -> "listening"
            "thinking" -> "thinking"
            "speaking" -> "speaking"
            "error" -> "error_generic"
            else -> "paused"
        }
        if (key == "error_generic") {
            setStatus(ui.t("paused"))
        } else {
            setStatus(ui.t(key))
        }
    }

    private fun setStatus(text: String) {
        statusLabel.text = text
    }

    override fun onMicPermission(granted: Boolean) {
        if (granted) {
            if (prefs.voiceMode == "push_to_talk" && !pttHeld) {
                updateMicLabel()
                return
            }
            if (prefs.voiceMode == "push_to_talk") {
                recordingPtt = true
                micButton.text = "■"
            }
            startRecognition()
        } else {
            setStatus(ui.t("android_mic_denied"))
            addBubble(ui.t("android_mic_denied"), BubbleKind.NOTE)
        }
    }

    override fun shutdown() {
        destroyed = true
        recognizer?.destroy()
        recognizer = null
        tts?.shutdown()
        tts = null
    }
}

// -- pronunciation -------------------------------------------------------

class PronunciationScreen(
    activity: MainActivity,
    private val scenarioId: String,
) : Screen(activity) {
    private val scenario = Scenario.get(activity, scenarioId)
    private lateinit var phraseLabel: TextView
    private lateinit var playButton: Button
    private lateinit var recordButton: Button
    private lateinit var nextButton: Button
    private lateinit var scoreLabel: TextView
    private lateinit var resultLabel: TextView
    private lateinit var heardLabel: TextView
    private lateinit var banner: TextView
    private lateinit var card: LinearLayout
    private var phrase = ""
    private var recording = false
    private var busy = false
    private var destroyed = false
    private var tts: TtsController? = null
    private var recognizer: RecognizerController? = null

    override fun build(): View {
        val body = ui.body()
        body.addView(ui.hero(ui.t("pronunciation")))
        body.addView(
            ui.muted("${languageChoiceLabel(prefs.target)} · ${scenario.label}"),
        )
        body.addView(ui.muted(ui.t("pronunciation_hint")).apply { setPadding(0, ui.dp(4), 0, 0) })

        card = ui.card()
        phraseLabel = ui.cardTitle(ui.t("loading"))
        card.addView(phraseLabel)
        val row = LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        playButton = ui.button("🔊  ${ui.t("play_audio")}", compact = true) { listen() }
        recordButton = ui.button("🎙  ${ui.t("your_turn")}", primary = true, compact = true) { toggleRecord() }
        nextButton = ui.button("↻  ${ui.t("new_exercise")}", compact = true) { generate() }
        row.addView(playButton)
        row.addView(recordButton, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { marginStart = ui.dp(8) })
        row.addView(nextButton, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { marginStart = ui.dp(8) })
        card.addView(row, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(12) })
        body.addView(card, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(12) })

        val resultCard = ui.card()
        scoreLabel = ui.textView("", 40f, ui.palette.accent, bold = true)
        resultLabel = ui.textView("", 18f)
        heardLabel = ui.muted("")
        resultCard.addView(scoreLabel)
        resultCard.addView(resultLabel)
        resultCard.addView(heardLabel.apply { setPadding(0, ui.dp(6), 0, 0) })
        body.addView(resultCard, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(12) })

        banner = ui.muted("")
        banner.setPadding(0, ui.dp(10), 0, 0)
        body.addView(banner)

        tts = TtsController(activity)
        recognizer = RecognizerController(
            activity,
            onPartial = { banner.text = it },
            onFinal = ::showResult,
            onErrorCallback = { code -> onRecognitionError(code) },
        )
        boot()
        return ui.scroll(body)
    }

    private fun boot() {
        banner.text = ui.t("loading")
        Thread {
            val available = ChatClient.ping(prefs.baseUrl)
            activity.runOnUiThread {
                if (destroyed) return@runOnUiThread
                if (available) {
                    banner.text = ""
                    generate()
                } else {
                    banner.text = ui.t("android_backend_unreachable", "url" to prefs.baseUrl)
                    phraseLabel.text = ui.t("ai_not_ready")
                }
            }
        }.start()
    }

    private fun generate() {
        if (busy) return
        busy = true
        phrase = ""
        phraseLabel.text = ui.t("loading")
        scoreLabel.text = ""
        resultLabel.text = ""
        heardLabel.text = ""
        banner.text = ""
        Thread {
            try {
                val messages = Prompts.textMessages(scenario, prefs.target, 1, 18)
                val raw = ChatClient.chat(prefs.baseUrl, prefs.model, messages)
                var text = TextKit.normalizeGeneratedText(raw)
                text = TextKit.limitSentences(text, 1)
                text = TextKit.shortenToWords(text, 18).trim().trim('"')
                activity.runOnUiThread {
                    if (destroyed) return@runOnUiThread
                    phrase = text
                    phraseLabel.text = text.ifBlank { ui.t("error_generic", "error" to "empty") }
                    busy = false
                }
            } catch (exc: Exception) {
                val error = exc.message ?: exc.javaClass.simpleName
                activity.runOnUiThread {
                    if (destroyed) return@runOnUiThread
                    busy = false
                    phraseLabel.text = ui.t("error_generic", "error" to error)
                }
            }
        }.start()
    }

    private fun listen() {
        if (phrase.isBlank()) return
        val current = tts ?: return
        current.speak(phrase, prefs.target, slow = true) { ok ->
            if (!ok) activity.runOnUiThread { banner.text = ui.t("android_tts_missing") }
        }
    }

    private fun toggleRecord() {
        if (phrase.isBlank() || busy) return
        if (!recording) {
            if (!requestMic()) return
            val current = recognizer ?: return
            if (!current.ensure()) {
                banner.text = ui.t("android_speech_unavailable")
                return
            }
            tts?.stop()
            if (current.start(prefs.target)) {
                recording = true
                recordButton.text = "■  ${ui.t("finish")}"
                banner.text = ui.t("listening")
            }
        } else {
            recording = false
            recordButton.text = "🎙  ${ui.t("your_turn")}"
            recognizer?.stop()
        }
    }

    private fun showResult(text: String, confidence: Float) {
        recording = false
        recordButton.text = "🎙  ${ui.t("your_turn")}"
        if (destroyed) return
        if (text.isBlank()) {
            banner.text = ui.t("android_not_understood")
            return
        }
        banner.text = ""
        val (results, accuracy) = compareReading(phrase, text)
        scoreLabel.text = "${accuracy.roundToInt()}%  ${ui.t("accuracy")}"
        resultLabel.text = ""
        val builder = SpannableStringBuilder()
        results.forEachIndexed { index, result ->
            if (index > 0) builder.append(" ")
            val start = builder.length
            builder.append(result.word)
            builder.setSpan(
                ForegroundColorSpan(if (result.ok) ui.palette.good else ui.palette.bad),
                start,
                builder.length,
                Spanned.SPAN_EXCLUSIVE_EXCLUSIVE,
            )
        }
        resultLabel.text = builder
        heardLabel.text = text
        activity.log("pronunciation: ${accuracy.roundToInt()}% accuracy")
    }

    private fun onRecognitionError(code: Int) {
        recording = false
        recordButton.text = "🎙  ${ui.t("your_turn")}"
        banner.text = if (code == android.speech.SpeechRecognizer.ERROR_NO_MATCH ||
            code == android.speech.SpeechRecognizer.ERROR_SPEECH_TIMEOUT
        ) {
            ui.t("android_not_understood")
        } else {
            recognitionErrorMessage(code)
        }
    }

    override fun onMicPermission(granted: Boolean) {
        if (granted) {
            toggleRecord()
        } else {
            banner.text = ui.t("android_mic_denied")
        }
    }

    override fun shutdown() {
        destroyed = true
        recognizer?.destroy()
        recognizer = null
        tts?.shutdown()
        tts = null
    }
}

// -- complete the sentence ----------------------------------------------

class SentenceScreen(activity: MainActivity) : Screen(activity) {
    private lateinit var textLabel: TextView
    private lateinit var entriesBox: LinearLayout
    private lateinit var banner: TextView
    private lateinit var finishButton: Button
    private lateinit var card: LinearLayout
    private val entries = ArrayList<EditText>()
    private var fullText = ""
    private var maskedText = ""
    private var answers: List<String> = emptyList()
    private var generating = false
    private var destroyed = false
    private var tts: TtsController? = null
    private val player = SimpleAudioPlayer()
    private lateinit var audioBar: AudioBarView

    override fun build(): View {
        val body = ui.body()
        body.addView(ui.hero(ui.t("complete_sentence")))
        body.addView(ui.muted(ui.t("listen_and_fill")))

        audioBar = AudioBarView(ui)
        audioBar.bind(player)
        body.addView(audioBar.root, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(10) })

        card = ui.card()
        textLabel = ui.textView(ui.t("loading"), 18f)
        card.addView(textLabel)
        entriesBox = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
        card.addView(entriesBox, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(10) })
        banner = ui.muted("")
        banner.setPadding(0, ui.dp(8), 0, 0)
        card.addView(banner)
        body.addView(card, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(12) })

        val actions = LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        finishButton = ui.button(ui.t("finish"), primary = true) { finish() }
        finishButton.isEnabled = false
        actions.addView(finishButton)
        actions.addView(ui.button("↻  ${ui.t("new_exercise")}") { generate() }, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { marginStart = ui.dp(8) })
        body.addView(actions, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(12) })

        tts = TtsController(activity)
        boot()
        return ui.scroll(body)
    }

    private fun boot() {
        banner.text = ui.t("loading")
        Thread {
            val available = ChatClient.ping(prefs.baseUrl)
            activity.runOnUiThread {
                if (destroyed) return@runOnUiThread
                if (available) {
                    generate()
                } else {
                    banner.text = ui.t("android_backend_unreachable", "url" to prefs.baseUrl)
                    textLabel.text = ui.t("ai_not_ready")
                }
            }
        }.start()
    }

    private fun generate() {
        if (generating) return
        generating = true
        banner.text = ui.t("loading")
        textLabel.text = ui.t("loading")
        finishButton.isEnabled = false
        entriesBox.removeAllViews()
        entries.clear()
        fullText = ""
        maskedText = ""
        answers = emptyList()
        player.release()
        Thread {
            try {
                val scenario = Scenario.get(activity, prefs.scenario)
                val messages = Prompts.textMessages(scenario, prefs.target, 4)
                val raw = ChatClient.chatStream(
                    prefs.baseUrl,
                    prefs.model,
                    messages,
                    onDelta = { visible ->
                        activity.runOnUiThread {
                            if (!destroyed) {
                                textLabel.text = TextKit.normalizeGeneratedText(visible)
                            }
                        }
                    },
                    maxTokens = 120,
                )
                var text = TextKit.normalizeGeneratedText(raw)
                text = TextKit.limitSentences(text, 4)
                activity.runOnUiThread {
                    if (destroyed) return@runOnUiThread
                    ready(text)
                }
            } catch (exc: Exception) {
                val error = exc.message ?: exc.javaClass.simpleName
                activity.runOnUiThread {
                    if (destroyed) return@runOnUiThread
                    generating = false
                    banner.text = ui.t("error_generic", "error" to error)
                    textLabel.text = ""
                }
            }
        }.start()
    }

    private fun ready(text: String) {
        generating = false
        fullText = text.trim()
        val (masked, blanks) = makeCloze(fullText, 6)
        maskedText = masked
        answers = blanks
        if (answers.isEmpty()) {
            banner.text = ui.t("error_generic", "error" to "no blanks")
            textLabel.text = fullText
            return
        }

        val parts = maskedText.split("____")
        val builder = SpannableStringBuilder()
        parts.forEachIndexed { index, part ->
            builder.append(part)
            if (index < parts.size - 1) {
                builder.append(" (${index + 1}) ")
                val start = builder.length
                builder.append("____")
                builder.setSpan(
                    ForegroundColorSpan(ui.palette.accent),
                    start,
                    builder.length,
                    Spanned.SPAN_EXCLUSIVE_EXCLUSIVE,
                )
            }
        }
        textLabel.text = builder
        entries.clear()
        entriesBox.removeAllViews()
        answers.forEachIndexed { index, _ ->
            val row = LinearLayout(activity).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
            }
            row.addView(
                ui.muted("${index + 1}.").apply { minWidth = ui.dp(28) },
            )
            val entry = ui.field("", "…")
            row.addView(entry, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            entry.setOnEditorActionListener { _, _, _ ->
                val next = entries.getOrNull(index + 1)
                next?.requestFocus()
                false
            }
            entries.add(entry)
            entriesBox.addView(row, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            ).apply { topMargin = ui.dp(6) })
        }
        finishButton.isEnabled = true
        banner.text = ""
        synthesize()
    }

    private fun synthesize() {
        val current = tts ?: return
        val file = File(activity.cacheDir, "parley-sentence.wav")
        current.synthesizeToFile(fullText, prefs.target, file) { ok ->
            activity.runOnUiThread {
                if (destroyed) return@runOnUiThread
                if (!ok) {
                    banner.text = ui.t("android_tts_missing")
                    return@runOnUiThread
                }
                player.load(file) { ready ->
                    if (destroyed) return@load
                    banner.text = if (ready) "" else ui.t("android_tts_missing")
                }
            }
        }
    }

    private fun finish() {
        if (answers.isEmpty()) return
        val values = entries.map { it.text.toString().trim() }
        val results = checkCloze(answers, values)
        val parts = maskedText.split("____")
        val builder = SpannableStringBuilder()
        var correct = 0
        parts.forEachIndexed { index, part ->
            builder.append(part)
            if (index < parts.size - 1) {
                val given = values.getOrElse(index) { "" }
                val expected = answers.getOrElse(index) { "" }
                if (results.getOrElse(index) { false }) {
                    correct += 1
                    val start = builder.length
                    builder.append(expected)
                    builder.setSpan(
                        ForegroundColorSpan(ui.palette.good),
                        start,
                        builder.length,
                        Spanned.SPAN_EXCLUSIVE_EXCLUSIVE,
                    )
                } else {
                    val start = builder.length
                    builder.append(given.ifBlank { "—" })
                    builder.setSpan(
                        ForegroundColorSpan(ui.palette.bad),
                        start,
                        builder.length,
                        Spanned.SPAN_EXCLUSIVE_EXCLUSIVE,
                    )
                    builder.append(" (")
                    val mutedStart = builder.length
                    builder.append(expected)
                    builder.setSpan(
                        ForegroundColorSpan(ui.palette.muted),
                        mutedStart,
                        builder.length,
                        Spanned.SPAN_EXCLUSIVE_EXCLUSIVE,
                    )
                    builder.append(")")
                }
            }
        }
        textLabel.text = builder
        banner.text = ui.t("bullets", "correct" to correct, "wrong" to results.size - correct)
    }

    override fun shutdown() {
        destroyed = true
        tts?.shutdown()
        tts = null
        player.release()
    }
}

// -- spoken stories ------------------------------------------------------

class StoriesScreen(activity: MainActivity) : Screen(activity) {
    private lateinit var summary: TextView
    private lateinit var listBox: LinearLayout
    private lateinit var emptyLabel: TextView
    private lateinit var downloadButton: Button
    private lateinit var removeButton: Button
    private var stories: List<Story> = emptyList()
    private var downloading = false
    private var destroyed = false
    private val player = SimpleAudioPlayer()
    private lateinit var audioBar: AudioBarView
    private var selected = 0

    override fun build(): View {
        val body = ui.body()
        body.addView(ui.hero(ui.t("stories_title")))
        summary = ui.muted("")
        summary.setPadding(0, ui.dp(6), 0, 0)
        body.addView(summary)

        audioBar = AudioBarView(ui)
        audioBar.bind(player)
        body.addView(audioBar.root, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(8) })

        listBox = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
        body.addView(listBox, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(8) })

        emptyLabel = ui.muted(ui.t("spoken_stories_desc"))
        emptyLabel.setPadding(0, ui.dp(10), 0, 0)
        body.addView(emptyLabel)

        val actions = LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        downloadButton = ui.button(ui.t("stories_download"), primary = true) { askDownload() }
        removeButton = ui.button(ui.t("stories_remove")) { askRemove() }
        actions.addView(downloadButton)
        actions.addView(removeButton, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { marginStart = ui.dp(8) })
        body.addView(actions, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(12) })

        stories = StoryStore.manifest(activity)
        refresh()
        return ui.scroll(body)
    }

    private fun refresh() {
        listBox.removeAllViews()
        var installed = 0
        stories.forEachIndexed { index, story ->
            val available = StoryStore.isInstalled(activity, story)
            if (available) installed += 1
            val row = LinearLayout(activity).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(ui.dp(12), ui.dp(10), ui.dp(12), ui.dp(10))
                background = ui.ripple(ui.palette.surface, 14f, ui.palette.border)
            }
            val text = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
            text.addView(ui.textView(story.title, 16f, ui.palette.text, bold = true))
            text.addView(
                ui.muted(story.author.ifBlank { ui.t("spoken_stories") }).apply {
                    setPadding(0, ui.dp(2), 0, 0)
                },
            )
            row.addView(text, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            val duration = if (story.seconds > 0) {
                "${(story.seconds.toInt()) / 60}:${"%02d".format(story.seconds.toInt() % 60)}"
            } else {
                "—"
            }
            row.addView(ui.muted(duration))
            row.addView(
                ui.muted(if (available) "▶" else "⬇").apply {
                    setPadding(ui.dp(10), 0, 0, 0)
                },
            )
            row.setOnClickListener { select(index, available) }
            listBox.addView(row, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            ).apply { topMargin = ui.dp(6) })
        }
        val megabytes = StoryStore.totalMegabytes(stories)
        summary.text = ui.t(
            "stories_available",
            "count" to stories.size,
            "size" to String.format("%.1f", megabytes),
        ) + "  ·  $installed/${stories.size} " + ui.t("stories_installed").lowercase()
        val missing = installed < stories.size
        downloadButton.visibility = if (missing) View.VISIBLE else View.GONE
        removeButton.visibility = if (installed > 0) View.VISIBLE else View.GONE
        emptyLabel.visibility = if (stories.isEmpty()) View.VISIBLE else View.GONE
        if (stories.isNotEmpty() && installed > 0 && selected < stories.size) {
            val story = stories[selected]
            if (StoryStore.isInstalled(activity, story)) {
                player.load(StoryStore.localPath(activity, story)) { }
            }
        }
    }

    private fun select(index: Int, available: Boolean) {
        selected = index
        if (!available) {
            askDownload()
            return
        }
        val file = StoryStore.localPath(activity, stories[index])
        player.load(file) { ready ->
            if (!destroyed && ready) {
                audioBar.play()
                activity.log("stories: playing ${stories[index].title}")
            }
        }
    }

    private fun askDownload() {
        if (downloading) return
        val count = stories.size
        val size = String.format("%.1f", StoryStore.totalMegabytes(stories))
        val box = ui.body(22, 22, 18)
        box.addView(ui.hero(ui.t("stories_download")))
        box.addView(ui.muted(ui.t("stories_download_confirm", "count" to count, "size" to size)))
        val actions = LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END
        }
        val dialog = activity.styledDialog(box)
        actions.addView(ui.button(ui.t("cancel")) { dialog.dismiss() })
        val confirm = ui.button(ui.t("download"), primary = true) {
            dialog.dismiss()
            download()
        }
        actions.addView(confirm, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { marginStart = ui.dp(8) })
        box.addView(actions, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(14) })
        dialog.show()
    }

    private fun download() {
        if (downloading) return
        downloading = true
        downloadButton.isEnabled = false
        summary.text = ui.t("loading")
        Thread {
            val errors = StoryStore.download(activity, stories, onProgress = { position, count, _, _, title ->
                activity.runOnUiThread {
                    if (destroyed) return@runOnUiThread
                    summary.text = ui.t(
                        "android_story_downloading",
                        "current" to position,
                        "total" to count,
                        "title" to title,
                    )
                }
            })
            activity.runOnUiThread {
                if (destroyed) return@runOnUiThread
                downloading = false
                downloadButton.isEnabled = true
                if (errors.isNotEmpty()) {
                    summary.text = errors.first()
                    activity.log("stories: download error ${errors.first()}")
                }
                refresh()
            }
        }.start()
    }

    private fun askRemove() {
        val box = ui.body(22, 22, 18)
        box.addView(ui.hero(ui.t("stories_remove")))
        box.addView(ui.muted(ui.t("android_remove_stories_confirm")))
        val dialog = activity.styledDialog(box)
        val actions = LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END
        }
        actions.addView(ui.button(ui.t("cancel")) { dialog.dismiss() })
        actions.addView(ui.button(ui.t("stories_remove"), primary = true) {
            player.stop()
            StoryStore.removeAll(activity)
            dialog.dismiss()
            refresh()
        }, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { marginStart = ui.dp(8) })
        box.addView(actions, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(14) })
        dialog.show()
    }

    override fun shutdown() {
        destroyed = true
        player.release()
    }
}

// -- level test ----------------------------------------------------------

class LevelTestScreen(activity: MainActivity) : Screen(activity) {
    private val promptCount = 5
    private val turns = ArrayList<TurnMetrics>()
    private var index = 0
    private var recording = false
    private var busy = false
    private var finished = false
    private var destroyed = false

    private lateinit var counterLabel: TextView
    private lateinit var promptLabel: TextView
    private lateinit var recordButton: Button
    private lateinit var retryButton: Button
    private lateinit var statusLabel: TextView
    private lateinit var resultCard: LinearLayout
    private lateinit var resultScore: TextView
    private lateinit var resultLevel: TextView
    private lateinit var resultDetail: TextView
    private var recognizer: RecognizerController? = null

    override fun build(): View {
        val body = ui.body()
        body.addView(ui.hero(ui.t("level_test_title")))
        body.addView(ui.muted(ui.t("level_test_desc")).apply { setPadding(0, ui.dp(6), 0, ui.dp(14)) })

        counterLabel = ui.cardTitle("")
        promptLabel = ui.textView("", 20f, ui.palette.text, bold = true).apply {
            setPadding(0, ui.dp(6), 0, ui.dp(10))
        }
        body.addView(counterLabel)
        body.addView(promptLabel)

        val controls = LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        recordButton = ui.button(ui.t("level_test_record"), primary = true) { toggleRecord() }
        retryButton = ui.button(ui.t("level_test_retry")) { restart() }
        retryButton.visibility = View.GONE
        controls.addView(recordButton)
        controls.addView(retryButton, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { marginStart = ui.dp(8) })
        body.addView(controls)

        statusLabel = ui.muted("")
        statusLabel.setPadding(0, ui.dp(10), 0, 0)
        body.addView(statusLabel)

        resultCard = ui.card()
        resultScore = ui.textView("", 42f, ui.palette.accent, bold = true)
        resultLevel = ui.cardTitle("")
        resultDetail = ui.muted("")
        resultCard.addView(resultScore)
        resultCard.addView(resultLevel)
        resultCard.addView(resultDetail.apply { setPadding(0, ui.dp(6), 0, 0) })
        resultCard.visibility = View.GONE
        body.addView(resultCard, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(14) })

        body.addView(ui.muted(ui.t("level_test_disclaimer")).apply {
            setPadding(0, ui.dp(14), 0, 0)
        })

        recognizer = RecognizerController(
            activity,
            onPartial = { statusLabel.text = it },
            onFinal = ::acceptAnswer,
            onErrorCallback = { code ->
                busy = false
                recording = false
                recordButton.text = ui.t("level_test_record")
                recordButton.isEnabled = true
                statusLabel.text = if (code == android.speech.SpeechRecognizer.ERROR_NO_MATCH ||
                    code == android.speech.SpeechRecognizer.ERROR_SPEECH_TIMEOUT
                ) {
                    ui.t("android_not_understood")
                } else {
                    recognitionErrorMessage(code)
                }
            },
        )
        showPrompt()
        return ui.scroll(body)
    }

    private fun showPrompt() {
        counterLabel.text = ui.t(
            "level_test_prompt_counter",
            "current" to min(index + 1, promptCount),
            "total" to promptCount,
        )
        promptLabel.text = ui.t("level_test_prompt_${index + 1}")
        statusLabel.text = ""
        recordButton.text = ui.t("level_test_record")
        recordButton.isEnabled = true
        recordButton.visibility = View.VISIBLE
        recording = false
        busy = false
    }

    private fun toggleRecord() {
        if (finished || busy) return
        if (!recording) {
            if (!requestMic()) return
            val current = recognizer ?: return
            if (!current.ensure()) {
                statusLabel.text = ui.t("android_speech_unavailable")
                return
            }
            if (current.start(prefs.target)) {
                recording = true
                recordButton.text = ui.t("level_test_stop")
                statusLabel.text = ui.t("listening")
            }
        } else {
            recording = false
            busy = true
            recordButton.isEnabled = false
            statusLabel.text = ui.t("level_test_thinking")
            recognizer?.stop()
        }
    }

    private fun acceptAnswer(text: String, confidence: Float) {
        if (destroyed) return
        val spoken = text.trim()
        recording = false
        if (spoken.isEmpty()) {
            busy = false
            recordButton.isEnabled = true
            recordButton.text = ui.t("level_test_record")
            statusLabel.text = ui.t("android_not_understood")
            return
        }
        val words = max(1, spoken.split(Regex("\\s+")).size)
        val elapsed = 1.0.coerceAtLeast((System.currentTimeMillis() - (recognizer?.startedAt ?: 0)) / 1000.0)
        val wpm = words / elapsed * 60.0
        turns.add(
            TurnMetrics(
                text = spoken,
                words = words,
                speechSeconds = elapsed,
                pauseRatio = (1.0 - min(1.0, wpm / 150.0)).coerceIn(0.0, 1.0),
                wordsPerMinute = wpm,
                confidence = confidence.toDouble(),
            ),
        )
        index += 1
        if (index >= promptCount) {
            finishTest()
        } else {
            showPrompt()
        }
    }

    private fun finishTest() {
        finished = true
        busy = false
        val result = scoreTurns(turns)
        scores.save(prefs.target, "level_test", ui.t("level_test_title"), result, mode = "level_test")
        counterLabel.text = ui.t("level_test_done")
        promptLabel.text = ui.t(
            "level_test_result",
            "score" to result.score,
            "level" to ui.t(result.bandKey),
        )
        statusLabel.text = ""
        recordButton.visibility = View.GONE
        retryButton.visibility = View.VISIBLE
        resultScore.text = "${result.score}/100"
        resultLevel.text = ui.t(result.bandKey)
        resultDetail.text = ui.t(
            "session_score_body",
            "score" to result.score,
            "level" to ui.t(result.bandKey),
            "turns" to result.turns,
            "words" to result.words,
        ) + "\n" + ui.t("progress_desc")
        resultCard.visibility = View.VISIBLE
        activity.log("level test: score ${result.score}")
    }

    private fun restart() {
        index = 0
        turns.clear()
        finished = false
        resultCard.visibility = View.GONE
        retryButton.visibility = View.GONE
        recordButton.visibility = View.VISIBLE
        showPrompt()
    }

    override fun onMicPermission(granted: Boolean) {
        if (granted) toggleRecord() else statusLabel.text = ui.t("android_mic_denied")
    }

    override fun shutdown() {
        destroyed = true
        recognizer?.destroy()
        recognizer = null
    }
}

// -- settings ------------------------------------------------------------

class SettingsScreen(activity: MainActivity) : Screen(activity) {
    private lateinit var serverField: EditText
    private lateinit var modelField: EditText
    private lateinit var connectionLabel: TextView
    private lateinit var storiesLabel: TextView
    private lateinit var awakeButton: Button
    private var destroyed = false

    private val uiLanguages = listOf("en", "pt", "es", "fr", "it", "ja", "ko", "zh")
    private val themeModes = listOf("system", "light", "dark")

    override fun build(): View {
        val body = ui.body()
        body.addView(ui.hero(ui.t("settings")))

        body.addView(ui.section(ui.t("interface_language")))
        body.addView(
            ui.dropdown(uiLanguages.map { LANGUAGE_NATIVE_NAMES[it] ?: it }, uiLanguages.indexOf(prefs.uiLanguage)) { index ->
                prefs.uiLanguage = uiLanguages[index]
                activity.refreshLanguage()
            },
            topMargin(6),
        )

        body.addView(ui.section(ui.t("theme")))
        body.addView(
            ui.dropdown(themeModes.map { ui.t("theme_$it") }, themeModes.indexOf(prefs.theme)) { index ->
                prefs.theme = themeModes[index]
                activity.refreshTheme()
            },
            topMargin(6),
        )

        body.addView(ui.section(ui.t("android_keep_awake")))
        body.addView(ui.muted(ui.t("android_keep_awake_desc")))
        awakeButton = ui.button(
            if (prefs.keepAwake) ui.t("android_on") else ui.t("android_off"),
            primary = true,
            compact = true,
        ) {
            prefs.keepAwake = !prefs.keepAwake
            activity.refreshKeepAwake()
            awakeButton.text = if (prefs.keepAwake) ui.t("android_on") else ui.t("android_off")
        }
        body.addView(awakeButton, topMargin(8))

        body.addView(ui.section(ui.t("target_language")))
        body.addView(
            ui.dropdown(
                PRACTICE_LANGUAGES.map { languageOptionLabel(it) },
                PRACTICE_LANGUAGES.indexOf(prefs.target),
            ) { index ->
                val code = PRACTICE_LANGUAGES[index]
                var native = prefs.native
                if (code == native) native = if (code != "pt") "pt" else "en"
                prefs.target = code
                prefs.native = native
                activity.refreshLanguage()
            },
            topMargin(6),
        )

        body.addView(ui.section(ui.t("native_language")))
        body.addView(
            ui.dropdown(
                PRACTICE_LANGUAGES.map { languageOptionLabel(it) },
                PRACTICE_LANGUAGES.indexOf(prefs.native),
            ) { index ->
                val code = PRACTICE_LANGUAGES[index]
                if (code == prefs.target) {
                    prefs.native = if (code != "pt") "pt" else "en"
                } else {
                    prefs.native = code
                }
                activity.refreshLanguage()
            },
            topMargin(6),
        )

        body.addView(ui.section(ui.t("ai_backend")))
        body.addView(ui.muted(ui.t("android_server_url")).apply { setPadding(0, ui.dp(4), 0, ui.dp(4)) })
        serverField = ui.field(prefs.baseUrl, ChatClient.DEFAULT_BASE_URL)
        body.addView(serverField)
        body.addView(ui.muted(ui.t("android_model_name")).apply { setPadding(0, ui.dp(10), 0, ui.dp(4)) })
        modelField = ui.field(prefs.model, "local")
        body.addView(modelField)

        val backendActions = LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        backendActions.addView(ui.button(ui.t("save"), primary = true) { saveBackend() })
        backendActions.addView(ui.button(ui.t("android_test_connection")) { testConnection() }, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { marginStart = ui.dp(8) })
        body.addView(backendActions, topMargin(10))
        connectionLabel = ui.muted("")
        connectionLabel.setPadding(0, ui.dp(8), 0, 0)
        body.addView(connectionLabel)
        body.addView(ui.button(ui.t("android_offline_setup")) { activity.showOfflineHelp() }, topMargin(10))

        body.addView(ui.section(ui.t("voice")))
        body.addView(ui.muted(ui.t("android_voice_hint")))
        body.addView(ui.button(ui.t("android_open_tts_settings")) { openTtsSettings() }, topMargin(8))

        body.addView(ui.section(ui.t("stories_section")))
        storiesLabel = ui.muted("")
        body.addView(storiesLabel)
        val storyActions = LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        storyActions.addView(ui.button(ui.t("stories_download"), primary = true) { downloadStories() })
        storyActions.addView(ui.button(ui.t("stories_remove")) { removeStories() }, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { marginStart = ui.dp(8) })
        body.addView(storyActions, topMargin(8))
        refreshStoriesLabel()

        body.addView(ui.section(ui.t("android_history")))
        body.addView(historyView(), topMargin(6))

        body.addView(ui.section(ui.t("diagnostics")))
        body.addView(
            ui.textView("Parley ${activity.versionName()}", 14f, ui.palette.muted).apply {
                setPadding(0, ui.dp(2), 0, ui.dp(6))
            },
        )
        body.addView(ui.button(ui.t("diagnostics")) { activity.showDiagnostics() })

        return ui.scroll(body)
    }

    private fun topMargin(value: Int): LinearLayout.LayoutParams =
        LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(value) }

    private fun languageOptionLabel(code: String): String {
        val name = when (code) {
            "ja" -> ui.t("language_ja")
            "ko" -> ui.t("language_ko")
            "zh" -> ui.t("language_zh")
            else -> LANGUAGE_NATIVE_NAMES[code] ?: code
        }
        return "${LANGUAGE_FLAGS[code] ?: "🌐"}  $name"
    }

    private fun saveBackend() {
        prefs.baseUrl = serverField.text.toString()
        prefs.model = modelField.text.toString()
        serverField.setText(prefs.baseUrl)
        modelField.setText(prefs.model)
        connectionLabel.text = ui.t("android_connection_ok")
        activity.log("settings: backend saved as ${prefs.baseUrl}, model ${prefs.model}")
    }

    private fun testConnection() {
        saveBackend()
        connectionLabel.text = ui.t("loading")
        Thread {
            val ok = ChatClient.ping(prefs.baseUrl)
            activity.runOnUiThread {
                if (destroyed) return@runOnUiThread
                connectionLabel.text = if (ok) {
                    ui.t("android_connection_ok")
                } else {
                    ui.t("android_connection_failed", "error" to prefs.baseUrl)
                }
                activity.log("settings: connection test ${if (ok) "ok" else "failed"}")
            }
        }.start()
    }

    private fun openTtsSettings() {
        val intents = listOf(
            Intent("com.android.settings.TTS_SETTINGS"),
            Intent(Settings.ACTION_SETTINGS),
        )
        for (intent in intents) {
            try {
                activity.startActivity(intent)
                return
            } catch (_: Exception) {
                // Try the next settings screen.
            }
        }
        connectionLabel.text = ui.t("android_tts_unavailable")
    }

    private fun refreshStoriesLabel() {
        val stories = StoryStore.manifest(activity)
        val installed = StoryStore.installedCount(activity, stories)
        val size = String.format("%.1f", StoryStore.totalMegabytes(stories))
        storiesLabel.text = ui.t("stories_available", "count" to stories.size, "size" to size) +
            "  ·  $installed/${stories.size} " + ui.t("stories_installed").lowercase()
    }

    private fun downloadStories() {
        val stories = StoryStore.manifest(activity)
        val box = ui.body(22, 22, 18)
        box.addView(ui.hero(ui.t("stories_download")))
        box.addView(
            ui.muted(
                ui.t(
                    "stories_download_confirm",
                    "count" to stories.size,
                    "size" to String.format("%.1f", StoryStore.totalMegabytes(stories)),
                ),
            ),
        )
        val dialog = activity.styledDialog(box)
        val actions = LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END
        }
        actions.addView(ui.button(ui.t("cancel")) { dialog.dismiss() })
        actions.addView(ui.button(ui.t("download"), primary = true) {
            dialog.dismiss()
            storiesLabel.text = ui.t("loading")
            Thread {
                val errors = StoryStore.download(activity, stories, onProgress = { position, count, _, _, title ->
                    activity.runOnUiThread {
                        if (destroyed) return@runOnUiThread
                        storiesLabel.text = ui.t(
                            "android_story_downloading",
                            "current" to position,
                            "total" to count,
                            "title" to title,
                        )
                    }
                })
                activity.runOnUiThread {
                    if (destroyed) return@runOnUiThread
                    if (errors.isNotEmpty()) {
                        storiesLabel.text = errors.first()
                    } else {
                        refreshStoriesLabel()
                    }
                }
            }.start()
        }, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { marginStart = ui.dp(8) })
        box.addView(actions, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(14) })
        dialog.show()
    }

    private fun removeStories() {
        val box = ui.body(22, 22, 18)
        box.addView(ui.hero(ui.t("stories_remove")))
        box.addView(ui.muted(ui.t("android_remove_stories_confirm")))
        val dialog = activity.styledDialog(box)
        val actions = LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END
        }
        actions.addView(ui.button(ui.t("cancel")) { dialog.dismiss() })
        actions.addView(ui.button(ui.t("stories_remove"), primary = true) {
            StoryStore.removeAll(activity)
            dialog.dismiss()
            refreshStoriesLabel()
        }, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { marginStart = ui.dp(8) })
        box.addView(actions, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(14) })
        dialog.show()
    }

    private fun historyView(): View {
        val container = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
        val history = scores.load()
        if (history.isEmpty()) {
            container.addView(ui.muted(ui.t("android_no_history")))
            return container
        }
        val grouped = history.groupBy { it["language"]?.toString().orEmpty() }
            .filterKeys { it.isNotEmpty() }
            .toSortedMap()
        grouped.forEach { (language, records) ->
            val summary = scores.summarize(records)
            container.addView(
                ui.textView(languageChoiceLabel(language), 15f, ui.palette.text, bold = true)
                    .apply { setPadding(0, ui.dp(6), 0, 0) },
            )
            container.addView(
                ui.muted(
                    ui.t(
                        "progress_sessions",
                        "count" to summary["count"],
                        "average" to summary["average"],
                        "best" to summary["best"],
                    ),
                ),
            )
            container.addView(
                ui.muted(
                    ui.t(
                        "progress_level",
                        "level" to ui.t(summary["band_key"]?.toString() ?: "score_band_1"),
                    ),
                ),
            )
        }
        container.addView(ui.divider())
        history.takeLast(20).reversed().forEach { record ->
            val row = LinearLayout(activity).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
            }
            val label = ui.textView(
                record["scenario_label"]?.toString() ?: record["scenario"]?.toString().orEmpty(),
                14f,
                ui.palette.text,
            )
            row.addView(label, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            row.addView(
                ui.muted(
                    "${(record["score"] as? Number)?.toInt() ?: 0}/100 · " +
                        (record["date"]?.toString()?.take(10) ?: ""),
                ),
            )
            container.addView(row, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            ).apply { topMargin = ui.dp(4) })
        }
        return container
    }

    override fun shutdown() {
        destroyed = true
    }
}
