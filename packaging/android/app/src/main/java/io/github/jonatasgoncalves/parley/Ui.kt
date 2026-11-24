package io.github.jonatasgoncalves.parley

import android.content.Context
import android.content.res.ColorStateList
import android.content.res.Configuration
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.text.SpannableString
import android.text.Spanned
import android.text.style.ForegroundColorSpan
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.PopupMenu
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.SeekBar
import android.widget.TextView
import kotlin.math.max

data class Palette(
    val background: Int,
    val surface: Int,
    val surfaceAlt: Int,
    val text: Int,
    val muted: Int,
    val accent: Int,
    val onAccent: Int,
    val good: Int,
    val bad: Int,
    val border: Int,
    val bubbleUser: Int,
    val bubbleAi: Int,
    val bubbleNote: Int,
    val dark: Boolean,
)

fun systemDark(context: Context): Boolean =
    (context.resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) ==
        Configuration.UI_MODE_NIGHT_YES

fun paletteFor(context: Context, prefs: Prefs): Palette {
    val dark = when (prefs.theme) {
        "light" -> false
        "dark" -> true
        else -> systemDark(context)
    }
    return if (dark) {
        Palette(
            background = 0xFF11151C.toInt(),
            surface = 0xFF1C222C.toInt(),
            surfaceAlt = 0xFF232B37.toInt(),
            text = 0xFFE8EEF8.toInt(),
            muted = 0xFFA3B0C4.toInt(),
            accent = 0xFF7FB0FF.toInt(),
            onAccent = 0xFF0B1220.toInt(),
            good = 0xFF6EE7A0.toInt(),
            bad = 0xFFFF9B9B.toInt(),
            border = 0xFF2E3947.toInt(),
            bubbleUser = 0xFF25384F.toInt(),
            bubbleAi = 0xFF1C222C.toInt(),
            bubbleNote = 0xFF3A3320.toInt(),
            dark = true,
        )
    } else {
        Palette(
            background = 0xFFF2F5FA.toInt(),
            surface = 0xFFFFFFFF.toInt(),
            surfaceAlt = 0xFFE9EDF4.toInt(),
            text = 0xFF111827.toInt(),
            muted = 0xFF465266.toInt(),
            accent = 0xFF2F6FD0.toInt(),
            onAccent = 0xFFFFFFFF.toInt(),
            good = 0xFF17803D.toInt(),
            bad = 0xFFB42318.toInt(),
            border = 0xFFD8DEE9.toInt(),
            bubbleUser = 0xFFDCE9FB.toInt(),
            bubbleAi = 0xFFFFFFFF.toInt(),
            bubbleNote = 0xFFFFF6D9.toInt(),
            dark = false,
        )
    }
}

/** Small view factory shared by every screen. */
class Ui(val activity: MainActivity) {
    val context: Context get() = activity
    val palette: Palette get() = activity.palette
    private val prefs: Prefs get() = activity.prefs

    fun dp(value: Int): Int = (value * activity.resources.displayMetrics.density).toInt()

    fun t(key: String, vararg placeholders: Pair<String, Any?>): String =
        prefs.t(key, *placeholders)

    fun textView(
        text: String = "",
        sizeSp: Float = 16f,
        color: Int = palette.text,
        bold: Boolean = false,
        wrap: Boolean = true,
    ): TextView = TextView(context).apply {
        this.text = text
        setTextSize(TypedValue.COMPLEX_UNIT_SP, sizeSp)
        setTextColor(color)
        if (bold) typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        if (wrap) {
            setLineSpacing(0f, 1.22f)
        } else {
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
        }
        includeFontPadding = false
    }

    fun hero(text: String): TextView = textView(text, 28f, palette.text, bold = true)

    fun section(text: String): TextView = textView(text, 18f, palette.text, bold = true).apply {
        setPadding(0, dp(10), 0, dp(2))
    }

    fun cardTitle(text: String): TextView = textView(text, 17f, palette.text, bold = true)

    fun muted(text: String = ""): TextView = textView(text, 14f, palette.muted)

    fun scroll(body: LinearLayout): ScrollView = ScrollView(context).apply {
        isFillViewport = true
        setBackgroundColor(palette.background)
        addView(
            body,
            ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT),
        )
    }

    fun body(top: Int = 18, horizontal: Int = 18, bottom: Int = 28): LinearLayout =
        LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(horizontal), dp(top), dp(horizontal), dp(bottom))
            setBackgroundColor(palette.background)
        }

    fun card(padding: Int = 16): LinearLayout = LinearLayout(context).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(padding), dp(padding), dp(padding), dp(padding))
        background = rounded(palette.surface, 18f, palette.border)
        if (!palette.dark) elevation = dp(1).toFloat()
    }

    fun add(parent: LinearLayout, child: View, topMargin: Int = 10, weight: Float = 0f) {
        val params = LinearLayout.LayoutParams(
            if (weight > 0f) 0 else LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        )
        params.topMargin = dp(topMargin)
        if (weight > 0f) params.weight = weight
        parent.addView(child, params)
    }

    fun rounded(fill: Int, radiusDp: Float, stroke: Int? = null, strokeWidthDp: Int = 1): GradientDrawable =
        GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = dp(radiusDp.toInt()).toFloat()
            setColor(fill)
            if (stroke != null) setStroke(dp(strokeWidthDp), stroke)
        }

    fun ripple(fill: Int, radiusDp: Float, stroke: Int? = null): RippleDrawable {
        val content = rounded(fill, radiusDp, stroke)
        val mask = GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = dp(radiusDp.toInt()).toFloat()
            setColor(Color.WHITE)
        }
        val rippleColor = ColorStateList.valueOf(
            if (palette.dark) 0x33FFFFFF else 0x22000000,
        )
        return RippleDrawable(rippleColor, content, mask)
    }

    fun button(
        text: String,
        primary: Boolean = false,
        compact: Boolean = false,
        onClick: () -> Unit,
    ): Button = Button(context).apply {
        this.text = text
        isAllCaps = false
        setTextSize(TypedValue.COMPLEX_UNIT_SP, if (compact) 14f else 16f)
        setTextColor(if (primary) palette.onAccent else palette.text)
        background = if (primary) {
            ripple(palette.accent, 14f)
        } else {
            ripple(palette.surfaceAlt, 14f, palette.border)
        }
        stateListAnimator = null
        minHeight = dp(if (compact) 38 else 48)
        minimumHeight = dp(if (compact) 38 else 48)
        setPadding(dp(if (compact) 12 else 18), dp(6), dp(if (compact) 12 else 18), dp(6))
        gravity = Gravity.CENTER
        setOnClickListener { onClick() }
    }

    /** A compact action button for dense Settings rows. */
    fun smallButton(
        text: String,
        primary: Boolean = false,
        enabled: Boolean = true,
        onClick: () -> Unit,
    ): Button = button(text, primary = primary, compact = true, onClick = onClick).apply {
        isEnabled = enabled
        minHeight = dp(32)
        minimumHeight = dp(32)
        setPadding(dp(10), dp(4), dp(10), dp(4))
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
    }

    fun ghostButton(text: String, onClick: () -> Unit): Button =
        button(text, primary = false, compact = true, onClick = onClick)

    /** Small square button used for icon-only actions such as delete. */
    fun iconButton(glyph: String, description: String, onClick: () -> Unit): Button =
        button(glyph, primary = false, compact = true, onClick = onClick).apply {
            contentDescription = description
            minWidth = dp(44)
            minimumWidth = dp(44)
            layoutParams = LinearLayout.LayoutParams(dp(44), dp(40))
            setPadding(0, dp(4), 0, dp(4))
        }

    /** Small circular spinner shown while a single model is downloading. */
    fun spinner(): ProgressBar = ProgressBar(context).apply {
        isIndeterminate = true
        indeterminateTintList = ColorStateList.valueOf(palette.accent)
        layoutParams = LinearLayout.LayoutParams(dp(20), dp(20))
    }

    fun row(spacing: Int = 8, center: Boolean = true): LinearLayout =
        LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = if (center) Gravity.CENTER_VERTICAL else Gravity.TOP
            val gap = dp(spacing)
            setPadding(0, 0, 0, 0)
            this.tag = gap
        }

    fun rowAdd(row: LinearLayout, child: View, weight: Float = 0f, end: Boolean = false) {
        val gap = (row.tag as? Int) ?: 0
        val params = LinearLayout.LayoutParams(
            if (weight > 0f) 0 else LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        )
        params.weight = weight
        if (row.childCount > 0) {
            if (end) params.marginStart = gap else params.marginEnd = gap
        }
        row.addView(child, params)
    }

    fun spacedRow(spacing: Int = 8): LinearLayout = LinearLayout(context).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
        tag = dp(spacing)
    }

    fun grid(items: List<View>, columns: Int = 2): LinearLayout {
        val container = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
        var index = 0
        while (index < items.size) {
            val row = LinearLayout(context).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
            }
            for (column in 0 until columns) {
                val item = items.getOrNull(index) ?: break
                val params = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
                if (column > 0) params.marginStart = dp(10)
                row.addView(item, params)
                index += 1
            }
            val rowParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            )
            if (container.childCount > 0) rowParams.topMargin = dp(10)
            container.addView(row, rowParams)
        }
        return container
    }

    fun divider(): View = View(context).apply {
        setBackgroundColor(palette.border)
        layoutParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            dp(1),
        ).apply { topMargin = dp(12); bottomMargin = dp(4) }
    }

    /** A dropdown built from a plain TextView so colours follow the app theme. */
    fun dropdown(
        items: List<String>,
        selected: Int,
        onSelect: (Int) -> Unit,
    ): TextView {
        val view = textView("", 16f, palette.text).apply {
            text = "${items.getOrElse(selected) { "" }}   ▾"
            setPadding(dp(14), dp(12), dp(14), dp(12))
            background = ripple(palette.surfaceAlt, 12f, palette.border)
            minHeight = dp(48)
            gravity = Gravity.CENTER_VERTICAL
        }
        view.setOnClickListener {
            val popup = PopupMenu(context, view)
            items.forEachIndexed { index, item ->
                popup.menu.add(0, index, index, item)
            }
            popup.setOnMenuItemClickListener { menuItem ->
                val index = menuItem.itemId
                view.text = "${items.getOrElse(index) { "" }}   ▾"
                onSelect(index)
                true
            }
            popup.show()
        }
        return view
    }

    fun field(initial: String, hint: String): android.widget.EditText =
        android.widget.EditText(context).apply {
            setText(initial)
            this.hint = hint
            setSingleLine(true)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            setTextColor(palette.text)
            setHintTextColor(palette.muted)
            background = rounded(palette.surfaceAlt, 12f, palette.border)
            setPadding(dp(14), dp(12), dp(14), dp(12))
        }

    fun progressBar(): ProgressBar = ProgressBar(context, null, android.R.attr.progressBarStyleHorizontal).apply {
        progressTintList = ColorStateList.valueOf(palette.accent)
        progressBackgroundTintList = ColorStateList.valueOf(palette.surfaceAlt)
    }

    fun wordMarkup(text: String, ok: Boolean): SpannableString =
        SpannableString(text).apply {
            setSpan(
                ForegroundColorSpan(if (ok) palette.good else palette.bad),
                0,
                length,
                Spanned.SPAN_EXCLUSIVE_EXCLUSIVE,
            )
        }

    fun bubble(text: String, kind: BubbleKind): TextView {
        val fill = when (kind) {
            BubbleKind.USER -> palette.bubbleUser
            BubbleKind.AI -> palette.bubbleAi
            BubbleKind.NOTE -> palette.bubbleNote
        }
        val color = when (kind) {
            BubbleKind.USER -> palette.text
            BubbleKind.AI -> palette.text
            BubbleKind.NOTE -> palette.text
        }
        return textView(text, 16f, color).apply {
            setPadding(dp(14), dp(10), dp(14), dp(10))
            background = rounded(fill, 16f, if (kind == BubbleKind.AI) palette.border else null)
            setTextIsSelectable(true)
        }
    }

    fun scrollToBottom(scroll: ScrollView) {
        scroll.post { scroll.fullScroll(View.FOCUS_DOWN) }
    }

    fun dialog(title: String, message: String): android.app.AlertDialog {
        val box = body(20, 22, 18)
        box.addView(hero(title))
        box.addView(muted(message).apply { setPadding(0, dp(10), 0, dp(8)) })
        val dialog = android.app.AlertDialog.Builder(context)
            .setView(scroll(box))
            .create()
        dialog.setOnShowListener {
            dialog.window?.setBackgroundDrawable(rounded(palette.surface, 20f, palette.border))
        }
        return dialog
    }

    fun padded(view: View, top: Int): View = view.apply {
        val params = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT,
        )
        params.topMargin = dp(top)
        layoutParams = params
    }
}

enum class BubbleKind { USER, AI, NOTE }

/**
 * Playback bar used by Spoken Stories and Complete the Sentence: play/pause,
 * a seek bar and a speed control.
 */
class AudioBarView(private val ui: Ui, showSpeed: Boolean = true) {
    val root: LinearLayout = LinearLayout(ui.context).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
    }
    private val playButton: Button = ui.button("▶", primary = false, compact = true) { toggle() }
    private val seekBar: SeekBar = SeekBar(ui.context).apply {
        max = 1000
        progressTintList = ColorStateList.valueOf(ui.palette.accent)
        thumbTintList = ColorStateList.valueOf(ui.palette.accent)
        progressBackgroundTintList = ColorStateList.valueOf(ui.palette.surfaceAlt)
        layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
    }
    private val timeLabel: TextView = ui.muted("0:00 / 0:00")
    private val speedButton: Button? = if (showSpeed) {
        ui.ghostButton("1.0×") { cycleSpeed() }
    } else {
        null
    }

    private var player: SimpleAudioPlayer? = null
    private var updating = false
    private var speed = 1.0f

    init {
        root.setPadding(ui.dp(4), ui.dp(4), ui.dp(4), ui.dp(4))
        root.addView(playButton, LinearLayout.LayoutParams(ui.dp(52), ui.dp(46)))
        val seekParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
        seekParams.marginStart = ui.dp(6)
        seekParams.marginEnd = ui.dp(6)
        root.addView(seekBar, seekParams)
        root.addView(timeLabel)
        speedButton?.let {
            val params = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            )
            params.marginStart = ui.dp(6)
            root.addView(it, params)
        }
        seekBar.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(bar: SeekBar?, progress: Int, fromUser: Boolean) {
                if (!fromUser || updating) return
                val current = player ?: return
                current.seekTo((currentDuration * progress / 1000.0).toInt())
            }

            override fun onStartTrackingTouch(bar: SeekBar?) = Unit
            override fun onStopTrackingTouch(bar: SeekBar?) = Unit
        })
    }

    private var currentDuration = 0

    fun bind(target: SimpleAudioPlayer) {
        player = target
        target.onTick = { position, duration, playing ->
            currentDuration = max(1, duration)
            updating = true
            seekBar.progress = if (duration > 0) (position * 1000 / duration) else 0
            updating = false
            timeLabel.text = "${format(position)} / ${format(duration)}"
            playButton.text = if (playing) "❚❚" else "▶"
        }
        target.onComplete = {
            playButton.text = "▶"
            seekBar.progress = 1000
        }
        target.speed = speed
    }

    fun play() {
        player?.play()
    }

    private fun toggle() {
        val current = player ?: return
        if (current.isPlaying) {
            current.pause()
            playButton.text = "▶"
        } else {
            if (seekBar.progress >= 1000) current.seekTo(0)
            current.play()
            playButton.text = "❚❚"
        }
    }

    private fun cycleSpeed() {
        speed = when (speed) {
            1.0f -> 1.25f
            1.25f -> 0.75f
            else -> 1.0f
        }
        player?.speed = speed
        speedButton?.text = String.format("%.2f×", speed).replace(",", ".")
    }

    private fun format(ms: Int): String {
        val total = (ms.coerceAtLeast(0) + 500) / 1000
        return "${total / 60}:${"%02d".format(total % 60)}"
    }
}
