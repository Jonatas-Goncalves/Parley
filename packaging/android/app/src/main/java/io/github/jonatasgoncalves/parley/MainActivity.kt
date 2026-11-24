package io.github.jonatasgoncalves.parley

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.graphics.Typeface
import android.os.Bundle
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.view.WindowInsetsControllerCompat
import java.io.File
import java.time.LocalTime
import java.time.format.DateTimeFormatter

/**
 * Android host for the Parley interface.
 *
 * The activity owns the navigation stack and the shared pieces every page needs:
 * preferences, the theme palette, the score history, the JavaScript-free view
 * factory and the diagnostics log. Pages themselves live in `Screens.kt`.
 *
 * Speech input uses the recogniser installed on the device and spoken replies
 * use the system text-to-speech engine. The language model runs inside Parley
 * through the bundled llama.cpp library. No local server is used.
 */
class MainActivity : AppCompatActivity() {

    lateinit var prefs: Prefs
        private set
    lateinit var scores: ScoreHistory
        private set
    lateinit var ui: Ui
        private set

    val whisperEngine = WhisperEngine()

    /** Current theme palette, recomputed when the interface theme changes. */
    lateinit var palette: Palette
        private set

    private lateinit var contentHost: FrameLayout
    private lateinit var rootView: LinearLayout
    private lateinit var topBarView: FrameLayout
    private lateinit var backButton: TextView
    private lateinit var titleLabel: TextView
    private lateinit var settingsButton: TextView

    private val stack = ArrayList<() -> Screen>()
    private var current: Screen? = null
    private var currentBuilder: (() -> Screen)? = null

    private val logLines = ArrayDeque<String>()
    private var nightMode = Configuration.UI_MODE_NIGHT_NO

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = Prefs(this)
        scores = ScoreHistory(this)
        nightMode = resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK
        palette = paletteFor(this, prefs)
        ui = Ui(this)
        installCrashLogger()
        refreshKeepAwake()
        val nativeDir = applicationInfo.nativeLibraryDir
        try {
            LlamaEngine.initBackends(nativeDir)
        } catch (exc: Exception) {
            log("backend", "init failed: ${exc.message ?: exc.javaClass.simpleName}")
        }
        val diag = LlamaEngine.diagnostics()
        log("backend", "nativeDir=$nativeDir")
        diag.lineSequence().firstOrNull { it.startsWith("backends:") }?.let { log("backend", it) }
        diag.lineSequence().firstOrNull { it.startsWith("backend search:") }?.let { log("backend", it) }
        setContentView(shell())
        log(
            "app",
            "Parley ${versionName()} started on Android " +
                android.os.Build.VERSION.RELEASE,
        )
        showLastCrash()
        if (prefs.target.isBlank()) prefs.target = "en"
        showWelcome()
        loadSavedModel()
        loadSavedWhisperModel()
    }

    /** Incremented for every model switch so stale callbacks are ignored. */
    private var loadSerial = 0

    /** Load the model selected in Settings in the background. */
    fun loadSavedModel(onDone: ((String?) -> Unit)? = null) {
        val serial = synchronized(this) { ++loadSerial }
        ChatClient.cancel()
        val preset = prefs.modelPreset
        val option = ModelStore.find(preset) ?: if (
            preset == "custom" && prefs.customFileName.isNotBlank()
        ) {
            ModelStore.customOption(prefs.customUrl, prefs.customFileName)
        } else {
            null
        }
        if (option == null || !ModelStore.isInstalled(this, option)) {
            log("model", "no installed model for preset $preset")
            runOnUiThread { onDone?.invoke(ui.t("android_model_not_loaded")) }
            return
        }
        Thread({
            try {
                ChatClient.load(ModelStore.paths(this, option))
                log("model", "loaded ${option.modelName}")
                log("model", ChatClient.diagnostics().replace('\n', ' '))
            } catch (exc: Throwable) {
                val error = if (exc is OutOfMemoryError) {
                    "not enough memory for this model - choose a smaller tier"
                } else {
                    exc.message ?: exc.javaClass.simpleName
                }
                log("model", "load failed: ${exc.javaClass.simpleName}: $error")
                runOnUiThread {
                    if (serial == loadSerial) {
                        onDone?.invoke(ui.t("android_model_load_failed", "error" to error))
                    }
                }
                return@Thread
            }
            runOnUiThread {
                if (serial == loadSerial) onDone?.invoke(null)
            }
        }, "parley-model-load").start()
    }

    fun loadSavedWhisperModel(onDone: ((Boolean) -> Unit)? = null) {
        val id = prefs.whisperModel
        val option = WhisperModelStore.find(id)
        if (option == null) {
            whisperEngine.unload()
            onDone?.invoke(false)
            return
        }
        if (!WhisperModelStore.isInstalled(this, option)) {
            log("whisper", "model not installed: ${option.id}")
            onDone?.invoke(false)
            return
        }
        Thread({
            val ok = try {
                whisperEngine.load(WhisperModelStore.file(this, option).absolutePath)
            } catch (_: Exception) {
                false
            }
            log("whisper", if (ok) "loaded ${option.modelName}" else "failed to load ${option.modelName}")
            runOnUiThread { onDone?.invoke(ok) }
        }, "parley-whisper-load").start()
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        (current as? SettingsScreen)?.handleFileResult(requestCode, resultCode, data)
    }

    /** Store unexpected failures on disk so they survive the app being killed. */
    private fun installCrashLogger() {
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            runCatching {
                val lines = buildList {
                    add("${thread.name}: ${error.javaClass.simpleName}: ${error.message}")
                    error.stackTrace.take(12).forEach { add(it.toString()) }
                }
                lines.forEach { log("crash", it) }
                File(filesDir, CRASH_LOG).writeText(lines.joinToString("\n"))
            }
            previous?.uncaughtException(thread, error)
        }
    }

    /** Surface a previous crash in Diagnostics after the app is opened again. */
    private fun showLastCrash() {
        val file = File(filesDir, CRASH_LOG)
        if (!file.exists()) return
        runCatching {
            file.readText().lineSequence().take(20).forEach { log("last-crash", it) }
            file.delete()
        }
    }

    /** Apply the screen-on preference to the activity window. */
    fun refreshKeepAwake() {
        val flag = WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
        if (prefs.keepAwake) {
            window.addFlags(flag)
        } else {
            window.clearFlags(flag)
        }
    }

    // -- shell -----------------------------------------------------------

    private fun shell(): View {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(palette.background)
        }
        rootView = root
        root.addView(topBar())

        contentHost = FrameLayout(this).apply {
            setBackgroundColor(palette.background)
        }
        root.addView(
            contentHost,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                0,
                1f,
            ),
        )
        return root
    }

    private fun topBar(): FrameLayout {
        val bar = FrameLayout(this).apply {
            setPadding(ui.dp(8), ui.dp(8), ui.dp(8), ui.dp(6))
            setBackgroundColor(palette.background)
        }
        topBarView = bar

        // Logo and name stay together, centred independently of the two actions.
        val identity = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        val logo = TextView(this).apply {
            text = "P"
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
            setTextColor(palette.onAccent)
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
            gravity = Gravity.CENTER
            background = ui.rounded(palette.accent, 12f)
        }
        identity.addView(logo, LinearLayout.LayoutParams(ui.dp(30), ui.dp(30)))
        titleLabel = TextView(this).apply {
            text = "Parley"
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 20f)
            setTextColor(palette.text)
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
            setPadding(ui.dp(10), 0, 0, 0)
        }
        identity.addView(titleLabel)
        bar.addView(identity, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.WRAP_CONTENT,
            FrameLayout.LayoutParams.WRAP_CONTENT,
            Gravity.CENTER,
        ))

        backButton = ui.ghostButton("←") { handleBack() }
        backButton.contentDescription = ui.t("back")
        backButton.minWidth = ui.dp(46)
        bar.addView(backButton, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.WRAP_CONTENT,
            FrameLayout.LayoutParams.WRAP_CONTENT,
            Gravity.START or Gravity.CENTER_VERTICAL,
        ))

        settingsButton = ui.ghostButton("⚙") { showSettings() }
        settingsButton.contentDescription = ui.t("settings")
        bar.addView(settingsButton, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.WRAP_CONTENT,
            FrameLayout.LayoutParams.WRAP_CONTENT,
            Gravity.END or Gravity.CENTER_VERTICAL,
        ))
        return bar
    }

    private fun updateChrome() {
        backButton.visibility =
            if (stack.isNotEmpty() || current !is WelcomeScreen) View.VISIBLE else View.INVISIBLE
        settingsButton.visibility = if (current is SettingsScreen) View.INVISIBLE else View.VISIBLE
        titleLabel.text = "Parley"
        titleLabel.setTextColor(palette.text)
        window.statusBarColor = palette.background
        window.navigationBarColor = palette.background
        WindowInsetsControllerCompat(window, window.decorView).apply {
            isAppearanceLightStatusBars = !palette.dark
            isAppearanceLightNavigationBars = !palette.dark
        }
    }

    // -- navigation ------------------------------------------------------

    fun showWelcome() = navigate({ WelcomeScreen(this) }, push = false)

    fun openPractice() = navigate({ PracticeScreen(this) })

    fun showPractice() = navigate({ PracticeScreen(this) })

    fun showScenarios(mode: String, band: String) =
        navigate({ ScenariosScreen(this, mode, band) })

    fun showSession(scenarioId: String) = navigate({ SessionScreen(this, scenarioId) })

    fun showPronunciation(scenarioId: String) =
        navigate({ PronunciationScreen(this, scenarioId) })

    fun showSentence() = navigate({ SentenceScreen(this) })

    fun showStories() = navigate({ StoriesScreen(this) })

    fun showLevelTest() = navigate({ LevelTestScreen(this) })

    fun showSettings() = navigate({ SettingsScreen(this) })

    /** Return to the practice hub and forget the previous history. */
    fun resetToPractice() {
        stack.clear()
        show({ PracticeScreen(this) })
    }

    private fun navigate(builder: () -> Screen, push: Boolean = true) {
        if (push) {
            currentBuilder?.let { stack.add(it) }
        }
        show(builder)
    }

    private fun show(builder: () -> Screen) {
        current?.shutdown()
        currentBuilder = builder
        val next = builder()
        current = next
        contentHost.removeAllViews()
        contentHost.addView(
            next.build(),
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT,
            ),
        )
        updateChrome()
    }

    private fun rebuildCurrent() {
        val builder = currentBuilder ?: return
        current?.shutdown()
        current = null
        show(builder)
    }

    private fun handleBack() {
        if (current?.onBackPressed() == true) return
        if (stack.isNotEmpty()) {
            show(stack.removeAt(stack.lastIndex))
            return
        }
        if (current !is WelcomeScreen) {
            show { WelcomeScreen(this) }
            return
        }
        finish()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        handleBack()
    }

    // -- theme and language ----------------------------------------------

    /** Recompute the palette and rebuild the chrome and page in place. */
    fun refreshTheme() {
        palette = paletteFor(this, prefs)
        getWindow().setBackgroundDrawable(ui.rounded(palette.background, 0f))
        rebuildTopBar()
        rebuildCurrent()
    }

    /**
     * Recreate the action bar: the buttons and logo bake their colours in when
     * they are built, so repainting the page alone leaves them on the old theme.
     */
    private fun rebuildTopBar() {
        if (!::rootView.isInitialized) return
        val index = rootView.indexOfChild(topBarView)
        if (index < 0) return
        rootView.removeView(topBarView)
        topBarView = topBar()
        rootView.addView(
            topBarView,
            index,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            ),
        )
    }

    /** Rebuild the page after the interface or practice language changed. */
    fun refreshLanguage() {
        rebuildCurrent()
    }

    // -- permissions -----------------------------------------------------

    fun requestMicPermission() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED
        ) {
            current?.onMicPermission(true)
            return
        }
        ActivityCompat.requestPermissions(
            this,
            arrayOf(Manifest.permission.RECORD_AUDIO),
            REQUEST_AUDIO,
        )
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQUEST_AUDIO) return
        val granted = grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED
        log("mic", if (granted) "permission granted" else "permission denied")
        current?.onMicPermission(granted)
    }

    // -- dialogs ---------------------------------------------------------

    /** A themed dialog that wraps [view] in the app surface colour. */
    fun styledDialog(view: View): AlertDialog {
        val dialog = AlertDialog.Builder(this)
            .setView(view)
            .create()
        dialog.setOnShowListener {
            dialog.window?.setBackgroundDrawable(ui.rounded(palette.surface, 20f, palette.border))
        }
        return dialog
    }

    fun showOfflineHelp() {
        val box = ui.body(22, 22, 18)
        box.addView(ui.hero(ui.t("android_offline_setup")))
        box.addView(ui.muted(ui.t("android_model_info")).apply {
            setPadding(0, ui.dp(8), 0, ui.dp(10))
        })

        val lines = StringBuilder()
        for (option in ModelStore.TIERS) {
            lines.append(ui.t(option.tierKey)).append(" - ").append(option.modelName).append('\n')
            lines.append("  ").append(
                ui.t("android_model_size", "size" to String.format("%.1f", option.sizeGb)),
            ).append('\n')
            lines.append("  ").append(
                ui.t("android_model_ram", "ram" to String.format("%.1f", option.ramGb)),
            ).append('\n')
            if (option.isSharded) {
                lines.append("  ").append(
                    ui.t("android_model_split_count", "count" to option.files.size),
                ).append('\n')
            }
            lines.append('\n')
        }
        lines.append(ui.t("model_quality_warning"))

        val details = TextView(this).apply {
            text = lines.toString().trimEnd()
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            setTextColor(palette.text)
            setTextIsSelectable(true)
            setLineSpacing(0f, 1.15f)
        }
        box.addView(ScrollView(this).apply { addView(details) }, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            ui.dp(300),
        ))

        val actions = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END
        }
        val dialog = styledDialog(box)
        actions.addView(ui.button(ui.t("settings"), primary = true) {
            dialog.dismiss()
            showSettings()
        })
        actions.addView(ui.button(ui.t("close")) { dialog.dismiss() }, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { marginStart = ui.dp(8) })
        box.addView(actions, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(14) })
        dialog.show()
        dialog.window?.setLayout(
            (resources.displayMetrics.widthPixels * 0.94f).toInt(),
            ViewGroup.LayoutParams.WRAP_CONTENT,
        )
    }

    fun showDiagnostics() {
        val box = ui.body(22, 22, 18)
        box.addView(ui.hero(ui.t("diagnostics")))
        box.addView(ui.muted("Parley ${versionName()} · ${ChatClient.version()} · ${prefs.modelLabel()}").apply {
            setPadding(0, ui.dp(4), 0, ui.dp(10))
        })

        val body = TextView(this).apply {
            text = snapshotLog()
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            typeface = Typeface.MONOSPACE
            setTextColor(palette.text)
            setTextIsSelectable(true)
            setLineSpacing(0f, 1.12f)
        }
        val scroller = ScrollView(this).apply {
            addView(body)
        }
        box.addView(scroller, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            ui.dp(360),
        ).apply { topMargin = ui.dp(4) })

        // A live check of the native engine: load state plus a tiny generation.
        val check = ui.button(ui.t("android_model_check"), compact = true) { }
        check.setOnClickListener {
            check.isEnabled = false
            check.text = ui.t("android_model_checking")
            Thread {
                val state = runCatching { ChatClient.diagnostics() }
                    .getOrElse { "diagnostics failed: ${it.message ?: it.javaClass.simpleName}" }
                // A probe would wait behind an active Voice Practice turn on the
                // same native monitor. Ask that turn to stop first, but never
                // leave the button stuck on "Checking..." if it cannot stop.
                val busy = runCatching { ChatClient.generating() }.getOrDefault(false)
                val stopped = !busy || ChatClient.cancelAndWait(10_000)
                val probe = if (!stopped) {
                    "probe skipped: generation is still active after 10s"
                } else {
                    runCatching {
                        val startedAt = System.currentTimeMillis()
                        val reply = ChatClient.chat(
                            listOf(ChatClient.Message("user", "Reply with OK only.")),
                            maxTokens = 16,
                        )
                        "reply (${System.currentTimeMillis() - startedAt} ms): ${reply.take(160)}"
                    }.getOrElse { "probe failed: ${it.message ?: it.javaClass.simpleName}" }
                }
                val after = runCatching { ChatClient.diagnostics() }
                    .getOrElse { "state unavailable: ${it.message ?: it.javaClass.simpleName}" }
                runOnUiThread {
                    log("diagnostics", "model check: $state")
                    log("diagnostics", probe)
                    log("diagnostics", "after probe: ${after.replace('\n', ' ')}")
                    body.text = snapshotLog()
                    check.text = ui.t("android_model_check")
                    check.isEnabled = true
                }
            }.start()
        }
        box.addView(check, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(8) })

        val cancel = ui.button(ui.t("android_cancel_generation"), compact = true) {
            ChatClient.cancel()
            log("diagnostics", "generation cancel requested")
        }
        box.addView(cancel, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(6) })

        val close = ui.button(ui.t("close"), primary = true) { }
        box.addView(close, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { topMargin = ui.dp(12) })
        val dialog = styledDialog(box)
        close.setOnClickListener { dialog.dismiss() }
        dialog.show()
        dialog.window?.setLayout(
            (resources.displayMetrics.widthPixels * 0.94f).toInt(),
            ViewGroup.LayoutParams.WRAP_CONTENT,
        )
    }

    // -- diagnostics -----------------------------------------------------

    fun log(message: String) = log("app", message)

    fun log(tag: String, message: String) {
        val stamp = LocalTime.now().format(TIME_FORMAT)
        synchronized(logLines) {
            if (logLines.size >= MAX_LOG_LINES) logLines.removeFirst()
            logLines.addLast("$stamp  $tag  $message")
        }
    }

    private fun snapshotLog(): String = synchronized(logLines) {
        logLines.joinToString("\n").ifEmpty { ui.t("android_diagnostics_empty") }
    }

    // -- helpers ---------------------------------------------------------

    fun versionName(): String = try {
        packageManager.getPackageInfo(packageName, 0).versionName ?: "1.0.0"
    } catch (_: Exception) {
        "1.0.0"
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        val mode = newConfig.uiMode and Configuration.UI_MODE_NIGHT_MASK
        if (mode != nightMode) {
            nightMode = mode
            if (prefs.theme == "system") refreshTheme()
        }
    }

    override fun onDestroy() {
        current?.shutdown()
        ChatClient.cancel()
        current = null
        stack.clear()
        // Freeing the GGUF can take a second; never do it on the main thread.
        Thread({ ChatClient.unload() }, "parley-model-free").start()
        super.onDestroy()
    }

    private companion object {
        const val REQUEST_AUDIO = 1001
        const val MAX_LOG_LINES = 800
        const val CRASH_LOG = "crash.log"
        val TIME_FORMAT: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm:ss")
    }
}
