package io.github.jonatasgoncalves.parley

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.graphics.Typeface
import android.net.Uri
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
 * use the system text-to-speech engine. The language model is served by
 * `llama-server` from llama.cpp, normally started inside Termux on the same
 * phone. No model and no inference engine are bundled in the APK.
 */
class MainActivity : AppCompatActivity() {

    lateinit var prefs: Prefs
        private set
    lateinit var scores: ScoreHistory
        private set
    lateinit var ui: Ui
        private set

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
        setContentView(shell())
        log(
            "app",
            "Parley ${versionName()} started on Android " +
                android.os.Build.VERSION.RELEASE,
        )
        showLastCrash()
        if (prefs.target.isBlank()) prefs.target = "en"
        showWelcome()
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
        box.addView(ui.muted(ui.t("android_offline_intro")).apply {
            setPadding(0, ui.dp(8), 0, ui.dp(10))
        })

        val commands = TextView(this).apply {
            text = """
                1. Install Termux from F-Droid. The Play Store build is outdated.

                2. In Termux run:
                   pkg update && pkg upgrade
                   pkg install llama-cpp
                   termux-wake-lock
                   termux-setup-storage

                3. Copy a GGUF model into the Termux downloads folder, for example
                   ~/storage/downloads/qwen2.5-3b-instruct-q4_K_M.gguf

                4. Start the server:
                   llama-server -m ~/storage/downloads/qwen2.5-3b-instruct-q4_K_M.gguf --host 127.0.0.1 --port 8080

                5. Keep http://127.0.0.1:8080 and the model name local in Settings.

                termux-wake-lock prevents Android from stopping Termux in the
                background while you practice. The smaller 1.5B model is faster
                on phones; the 3B model gives better answers. Everything stays
                on the device.
            """.trimIndent()
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            typeface = Typeface.MONOSPACE
            setTextColor(palette.text)
            setTextIsSelectable(true)
            setLineSpacing(0f, 1.15f)
        }
        box.addView(ScrollView(this).apply { addView(commands) }, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            ui.dp(320),
        ))

        val actions = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END
        }
        val dialog = styledDialog(box)
        actions.addView(ui.button("Open Termux", primary = true) {
            dialog.dismiss()
            openTermux()
        })
        actions.addView(ui.button("F-Droid") {
            dialog.dismiss()
            openUrl("https://f-droid.org/packages/com.termux/")
        }, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        ).apply { marginStart = ui.dp(8) })
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
        box.addView(ui.muted("Parley ${versionName()} · ${prefs.baseUrl} · ${prefs.model}").apply {
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
        packageManager.getPackageInfo(packageName, 0).versionName ?: "0.3.1"
    } catch (_: Exception) {
        "0.3.1"
    }

    private fun openTermux() {
        try {
            val intent = packageManager.getLaunchIntentForPackage(TERMUX_PACKAGE)
            if (intent == null) {
                openUrl("https://f-droid.org/packages/com.termux/")
            } else {
                startActivity(intent)
            }
        } catch (exc: Exception) {
            openUrl("https://f-droid.org/packages/com.termux/")
        }
    }

    private fun openUrl(url: String) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        } catch (exc: Exception) {
            log("link", "could not open $url")
        }
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
        current = null
        stack.clear()
        super.onDestroy()
    }

    private companion object {
        const val REQUEST_AUDIO = 1001
        const val MAX_LOG_LINES = 800
        const val CRASH_LOG = "crash.log"
        const val TERMUX_PACKAGE = "com.termux"
        val TIME_FORMAT: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm:ss")
    }
}
