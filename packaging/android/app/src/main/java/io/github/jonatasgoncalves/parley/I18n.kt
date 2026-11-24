package io.github.jonatasgoncalves.parley

import android.content.Context
import org.json.JSONObject
import java.util.Locale

/**
 * Interface translations.
 *
 * The Android app ships the same translation table as the desktop app, exported
 * by `scripts/export_android_assets.py`. A missing key falls back to English so
 * the interface never shows a raw key.
 */
object I18n {
    private var table: JSONObject? = null

    private fun load(context: Context): JSONObject {
        table?.let { return it }
        val loaded = context.assets.open("i18n.json").bufferedReader(Charsets.UTF_8).use {
            JSONObject(it.readText())
        }
        table = loaded
        return loaded
    }

    fun t(
        context: Context,
        language: String,
        key: String,
        vararg placeholders: Pair<String, Any?>,
    ): String {
        val entry = load(context).optJSONObject(key)
        var value = entry?.optString(language).orEmpty()
        if (value.isBlank()) {
            value = entry?.optString("en").orEmpty()
        }
        if (value.isBlank()) {
            value = key
        }
        for ((name, replacement) in placeholders) {
            value = value.replace("{$name}", replacement?.toString().orEmpty())
        }
        return value
    }
}

/** Languages offered for practice, in the order used by the home screen. */
val PRACTICE_LANGUAGES = listOf("pt", "en", "es", "fr", "it", "ja", "ko", "zh")

val LANGUAGE_FLAGS = mapOf(
    "pt" to "🇧🇷",
    "en" to "🇬🇧",
    "es" to "🇪🇸",
    "fr" to "🇫🇷",
    "it" to "🇮🇹",
    "ja" to "🇯🇵",
    "ko" to "🇰🇷",
    "zh" to "🇨🇳",
)

val LANGUAGE_NATIVE_NAMES = mapOf(
    "pt" to "Português",
    "en" to "English",
    "es" to "Español",
    "fr" to "Français",
    "it" to "Italiano",
    "ja" to "日本語",
    "ko" to "한국어",
    "zh" to "中文",
)

/** English names used inside model prompts. */
val LANGUAGE_NAMES = mapOf(
    "pt" to "Portuguese",
    "en" to "English",
    "es" to "Spanish",
    "fr" to "French",
    "it" to "Italian",
    "ja" to "Japanese",
    "ko" to "Korean",
    "zh" to "Mandarin Chinese",
)

fun languageName(code: String): String = LANGUAGE_NAMES[code] ?: "English"

fun languageChoiceLabel(code: String): String = LANGUAGE_NATIVE_NAMES[code] ?: code

/** Full BCP-47 tags that the speech recogniser and TTS engines expect. */
val SPEECH_TAGS = mapOf(
    "pt" to "pt-BR",
    "en" to "en-US",
    "es" to "es-ES",
    "fr" to "fr-FR",
    "it" to "it-IT",
    "ja" to "ja-JP",
    "ko" to "ko-KR",
    "zh" to "zh-CN",
)

fun speechTag(code: String): String = SPEECH_TAGS[code] ?: "en-US"

fun normalizeLanguageCode(code: String?): String {
    val value = (code ?: "").trim().lowercase(Locale.ROOT).replace('_', '-')
    val base = value.substringBefore('-')
    return if (base in PRACTICE_LANGUAGES) base else ""
}

/** Persistent settings, stored in a single shared-preferences file. */
class Prefs(context: Context) {
    private val context = context.applicationContext
    private val store = this.context.getSharedPreferences("parley", Context.MODE_PRIVATE)

    var uiLanguage: String
        get() = normalizeUiLanguage(store.getString(KEY_UI_LANGUAGE, "en"))
        set(value) = store.edit().putString(KEY_UI_LANGUAGE, normalizeUiLanguage(value)).apply()

    var target: String
        get() = normalizeLanguageCode(store.getString(KEY_TARGET, "en")).ifBlank { "en" }
        set(value) = store.edit().putString(KEY_TARGET, normalizeLanguageCode(value)).apply()

    var native: String
        get() = normalizeLanguageCode(store.getString(KEY_NATIVE, "pt")).ifBlank { "pt" }
        set(value) = store.edit().putString(KEY_NATIVE, normalizeLanguageCode(value)).apply()

    /** One of `system`, `light` or `dark`. */
    var theme: String
        get() = when (store.getString(KEY_THEME, "system")) {
            "light" -> "light"
            "dark" -> "dark"
            else -> "system"
        }
        set(value) = store.edit().putString(KEY_THEME, value).apply()

    var baseUrl: String
        get() = store.getString(KEY_BASE_URL, ChatClient.DEFAULT_BASE_URL)
            ?.trim()
            ?.ifBlank { ChatClient.DEFAULT_BASE_URL }
            ?: ChatClient.DEFAULT_BASE_URL
        set(value) = store.edit().putString(KEY_BASE_URL, value.trim()).apply()

    var model: String
        get() = store.getString(KEY_MODEL, "local")?.trim()?.ifBlank { "local" } ?: "local"
        set(value) = store.edit().putString(KEY_MODEL, value.trim().ifBlank { "local" }).apply()

    /** `continuous` or `push_to_talk`, last used in Voice Practice. */
    var voiceMode: String
        get() = if (store.getString(KEY_VOICE_MODE, "continuous") == "push_to_talk") {
            "push_to_talk"
        } else {
            "continuous"
        }
        set(value) = store.edit().putString(KEY_VOICE_MODE, value).apply()

    var scenario: String
        get() = store.getString(KEY_SCENARIO, "meeting_someone_new")
            ?: "meeting_someone_new"
        set(value) = store.edit().putString(KEY_SCENARIO, value).apply()

    /** When true the activity holds a wake lock so the screen stays on. */
    var keepAwake: Boolean
        get() = store.getBoolean(KEY_KEEP_AWAKE, false)
        set(value) = store.edit().putBoolean(KEY_KEEP_AWAKE, value).apply()

    fun t(key: String, vararg placeholders: Pair<String, Any?>): String =
        I18n.t(context, uiLanguage, key, *placeholders)

    companion object {
        private const val KEY_UI_LANGUAGE = "ui_language"
        private const val KEY_TARGET = "target"
        private const val KEY_NATIVE = "native"
        private const val KEY_THEME = "theme"
        private const val KEY_BASE_URL = "base_url"
        private const val KEY_MODEL = "model"
        private const val KEY_VOICE_MODE = "voice_mode"
        private const val KEY_SCENARIO = "scenario"
        private const val KEY_KEEP_AWAKE = "keep_awake"

        fun normalizeUiLanguage(code: String?): String {
            val value = (code ?: "").trim().lowercase(Locale.ROOT).substringBefore('-')
            return if (value in PRACTICE_LANGUAGES) value else "en"
        }
    }
}
