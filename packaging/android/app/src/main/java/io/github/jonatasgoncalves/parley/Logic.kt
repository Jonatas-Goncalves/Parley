package io.github.jonatasgoncalves.parley

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.text.Normalizer
import java.time.Instant
import java.util.Locale
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

// -- scenarios -----------------------------------------------------------

data class Scenario(
    val id: String,
    val label: String,
    val description: String,
    val persona: String,
    val band: String,
) {
    val level: String
        get() = when (band) {
            "beginner" -> "A2"
            "intermediate" -> "B1"
            else -> "C1"
        }

    companion object {
        fun load(context: Context): List<Scenario> {
            val raw = context.assets.open("scenarios.json").bufferedReader(Charsets.UTF_8)
                .use { it.readText() }
            val array = JSONArray(raw)
            val items = ArrayList<Scenario>(array.length())
            for (index in 0 until array.length()) {
                val item = array.optJSONObject(index) ?: continue
                val id = item.optString("id")
                if (id.isBlank()) continue
                items.add(
                    Scenario(
                        id = id,
                        label = item.optString("label", id),
                        description = item.optString("description"),
                        persona = item.optString("persona"),
                        band = item.optString("band", "beginner"),
                    ),
                )
            }
            return items
        }

        fun get(context: Context, id: String): Scenario {
            val items = load(context)
            return items.firstOrNull { it.id == id } ?: items.first()
        }

        fun forBand(context: Context, band: String): List<Scenario> =
            load(context).filter { it.band == band }
    }
}

// -- text helpers --------------------------------------------------------

object TextKit {
    val WORD_RE = Regex("[\\p{L}\\p{M}]+(?:['’\\-][\\p{L}\\p{M}]+)*")
    private val CJK_RE = Regex("[\\u3040-\\u30ff\\u3400-\\u4dbf\\u4e00-\\u9fff\\uac00-\\ud7af]")
    private val TERMINAL = setOf('.', '!', '?', '…', '。', '！', '？', ')', ']', '"', '\'', '”', '’')
    private val HYPHEN_RUN = Regex("(?<!\\S)([^\\s\\-]+(?:-[^\\s\\-]+){2,})(?!\\S)")
    private val SENTENCE_BOUNDARY = Regex("(?<=[.!?…])\\s+|(?<=[。！？])\\s*")
    private val MIXED_CJK_TAIL = Regex("(?<=[。！？])[、，,.;:!?]+")
    private val TERMINAL_RUN = Regex("([。！？!?])[。！？、，,.;:!?]+")
    private val SPACE_BEFORE_PUNCTUATION = Regex("\\s+([,.!?;:。！？、，])")
    private val SPACE_AFTER_CJK_TERMINAL = Regex("(?<=[。！？])\\s+")

    val STOPWORDS = setOf(
        "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be",
        "been", "am", "do", "does", "did", "have", "has", "had", "to", "of", "in",
        "on", "at", "for", "with", "from", "by", "as", "that", "this", "these",
        "those", "it", "its", "i", "you", "he", "she", "we", "they", "my", "your",
        "our", "their", "me", "him", "her", "us", "them", "not", "no", "yes",
        "o", "os", "um", "uma", "uns", "umas", "e", "ou", "mas", "é",
        "são", "foi", "ser", "estar", "está", "estou", "tem", "tenho", "de", "da",
        "dos", "das", "em", "na", "nos", "nas", "para", "por", "com",
        "que", "isso", "este", "esta", "eu", "você", "ele", "ela", "nós", "eles",
        "elas", "meu", "minha", "seu", "sua", "não", "sim", "el", "la", "los",
        "las", "un", "una", "unos", "unas", "y", "pero", "es", "son", "fue",
        "tiene", "tengo", "del", "al", "en", "con", "esto", "yo", "tú", "él", "ella",
        "le", "les", "des", "du", "une", "et", "mais", "est", "sont",
        "être", "avoir", "ai", "avons", "avez", "ont", "dans", "sur", "avec",
        "pour", "par", "pas", "oui", "je", "tu", "il", "elle", "nous", "vous",
        "ils", "elles", "mon", "ma", "mes", "ton", "ta", "tes", "sa",
        "ses", "ce", "cette", "ces", "qui",
        "lo", "gli", "uno", "ed",
        "è", "sono", "era", "essere", "avere", "ho", "hai", "ha", "abbiamo",
        "avete", "hanno", "di", "della", "dei", "delle", "nel",
        "nella", "su", "per", "che", "questo", "questa", "io", "lui", "lei", "noi",
        "voi", "loro", "mio", "mia", "tuo", "tua", "suo",
        "non", "sì",
    )

    fun hasCjk(text: String): Boolean = CJK_RE.containsMatchIn(text)

    fun words(text: String): List<String> = WORD_RE.findAll(text).map { it.value }.toList()

    fun normalizeWord(value: String): String {
        val decomposed = Normalizer.normalize(value.lowercase(Locale.ROOT), Normalizer.Form.NFD)
        return decomposed.replace(Regex("\\p{M}+"), "").replace(Regex("[^\\p{L}\\p{N}]"), "")
    }

    fun expandHyphenRuns(text: String): String = HYPHEN_RUN.replace(text) { match ->
        val token = match.groupValues[1]
        val parts = token.split("-")
        if (parts.size < 3 || parts.any { it.isEmpty() }) token else parts.joinToString(" ")
    }

    fun ensureTerminal(text: String): String {
        val value = text.trim().trimEnd(',', ';', ':', '、', '，')
        if (value.isEmpty()) return ""
        return if (TERMINAL.contains(value.last())) value else value + terminalFor(value)
    }

    private fun terminalFor(text: String): String = if (hasCjk(text)) "。" else "."

    fun cleanCjkPunctuation(text: String): String {
        var value = text
        if (!hasCjk(value)) return SPACE_BEFORE_PUNCTUATION.replace(value, "$1")
        value = MIXED_CJK_TAIL.replace(value, "")
        value = TERMINAL_RUN.replace(value, "$1")
        value = Regex("([、，,])(?:[、，,]+)").replace(value, "$1")
        value = SPACE_AFTER_CJK_TERMINAL.replace(value, "")
        return SPACE_BEFORE_PUNCTUATION.replace(value, "$1")
    }

    fun splitSentences(text: String): List<String> =
        SENTENCE_BOUNDARY.split(text).map { it.trim() }.filter { it.isNotEmpty() }

    fun limitSentences(text: String, count: Int): String {
        if (count <= 0) return ""
        val sentences = splitSentences(text)
        if (sentences.size <= count) return text
        val kept = sentences.take(count).map { ensureTerminal(it) }
        val joiner = if (hasCjk(text)) "" else " "
        return kept.joinToString(joiner)
    }

    fun shortenToWords(text: String, maxWords: Int?): String {
        if (maxWords == null || maxWords <= 0 || text.isBlank()) return text
        if (hasCjk(text)) {
            val limit = maxWords * 2
            val characters = text.replace(Regex("[\\s\\W_]+"), "")
            if (characters.length <= limit) return text
            var chosen = ""
            for (sentence in splitSentences(text)) {
                val candidate = if (chosen.isEmpty()) sentence else chosen + sentence
                if (candidate.replace(Regex("[\\s\\W_]+"), "").length > limit) break
                chosen = candidate
            }
            return if (chosen.isEmpty()) text else ensureTerminal(chosen)
        }
        if (text.split(Regex("\\s+")).size <= maxWords) return text
        val clauses = Regex("(?<=[,;:])\\s+").split(text)
        val chosen = ArrayList<String>()
        var length = 0
        for (clause in clauses) {
            val clauseWords = clause.split(Regex("\\s+")).filter { it.isNotEmpty() }
            if (length + clauseWords.size > maxWords && chosen.isNotEmpty()) break
            chosen.add(clause)
            length += clauseWords.size
        }
        var result = chosen.joinToString(" ").trim()
        val parts = result.split(Regex("\\s+")).filter { it.isNotEmpty() }
        if (parts.size > maxWords) result = parts.take(maxWords).joinToString(" ")
        return ensureTerminal(result)
    }

    fun normalizeGeneratedText(text: String): String {
        var value = expandHyphenRuns(text)
        value = Regex("(?m)^\\s*(?:#{1,6}|[-*•]|\\d+[.)])\\s+").replace(value, "")
        val lines = value.lines()
            .map { it.replace(Regex("\\s+"), " ").trim() }
            .filter { it.isNotEmpty() }
        if (lines.isEmpty()) return ""
        return cleanCjkPunctuation(lines.joinToString(" ") { ensureTerminal(it) })
    }

    fun extractQuestions(text: String): List<String> =
        splitSentences(text).filter { it.endsWith("?") || it.endsWith("？") }
}

data class ComparisonWord(val word: String, val heard: String, val ok: Boolean)

/** Compare a phrase with what the recogniser heard and mark each word. */
fun compareReading(expected: String, heard: String): Pair<List<ComparisonWord>, Double> {
    val expectedWords = TextKit.words(expected)
    val heardWords = TextKit.words(heard)
    val a = expectedWords.map(TextKit::normalizeWord)
    val b = heardWords.map(TextKit::normalizeWord)
    val n = a.size
    val m = b.size
    val table = Array(n + 1) { IntArray(m + 1) }
    for (i in n - 1 downTo 0) {
        for (j in m - 1 downTo 0) {
            table[i][j] = if (a[i].isNotEmpty() && a[i] == b[j]) {
                table[i + 1][j + 1] + 1
            } else {
                max(table[i + 1][j], table[i][j + 1])
            }
        }
    }
    val matched = HashMap<Int, String>()
    var i = 0
    var j = 0
    while (i < n && j < m) {
        if (a[i].isNotEmpty() && a[i] == b[j] && table[i][j] == table[i + 1][j + 1] + 1) {
            matched[i] = heardWords[j]
            i += 1
            j += 1
        } else if (table[i + 1][j] >= table[i][j + 1]) {
            i += 1
        } else {
            j += 1
        }
    }
    val results = expectedWords.mapIndexed { index, word ->
        ComparisonWord(word, matched[index].orEmpty(), matched.containsKey(index))
    }
    val accuracy = if (expectedWords.isEmpty()) 0.0 else 100.0 * matched.size / expectedWords.size
    return results to accuracy
}

/** Remove fill-in-the-blank words from a short text. */
fun makeCloze(text: String, count: Int = 6): Pair<String, List<String>> {
    val matches = TextKit.WORD_RE.findAll(text).toList()
    val candidates = matches.indices.filter { index ->
        val word = matches[index].value
        word.length >= 4 && TextKit.normalizeWord(word) !in TextKit.STOPWORDS
    }
    if (candidates.isEmpty()) return text to emptyList()

    val step = max(1, candidates.size / count)
    val chosen = candidates.filterIndexed { index, _ -> index % step == 0 }.take(count).toSet()
    val output = StringBuilder()
    val answers = ArrayList<String>()
    var last = 0
    for ((index, match) in matches.withIndex()) {
        if (index !in chosen) continue
        output.append(text, last, match.range.first)
        output.append("____")
        answers.add(match.value)
        last = match.range.last + 1
    }
    output.append(text.substring(last))
    return output.toString() to answers
}

fun checkCloze(answers: List<String>, values: List<String>): List<Boolean> =
    answers.indices.map { index ->
        val given = values.getOrElse(index) { "" }
        given.isNotBlank() && TextKit.normalizeWord(answers[index]) == TextKit.normalizeWord(given)
    }

// -- conversation scoring ------------------------------------------------

data class TurnMetrics(
    val text: String = "",
    val words: Int = 0,
    val speechSeconds: Double = 0.0,
    val pauseRatio: Double = 0.0,
    val wordsPerMinute: Double = 0.0,
    val confidence: Double = 1.0,
)

data class SessionScore(
    val score: Int,
    val bandKey: String,
    val turns: Int,
    val words: Int,
    val uniqueRatio: Double = 0.0,
    val speakingSeconds: Double = 0.0,
    val wordsPerMinute: Double = 0.0,
    val pauseRatio: Double = 0.0,
    val confidence: Double = 0.0,
)

private fun clamp(value: Double, low: Double = 0.0, high: Double = 100.0): Double =
    max(low, min(high, value))

fun bandKeyForScore(score: Int): String = when {
    score >= 85 -> "score_band_6"
    score >= 70 -> "score_band_5"
    score >= 55 -> "score_band_4"
    score >= 40 -> "score_band_3"
    score >= 25 -> "score_band_2"
    else -> "score_band_1"
}

private fun tokenWords(text: String): List<String> =
    text.split(Regex("\\s+"))
        .map { it.trim(' ', '.', ',', '!', '?', ';', ':', '"', '\'', '(', ')', '[', ']', '{', '}', '…', '¿', '¡', '。', '！', '？', '、').lowercase(Locale.ROOT) }
        .filter { it.isNotEmpty() }

fun scoreTurns(turns: List<TurnMetrics>): SessionScore {
    val spoken = turns.filter { it.words > 0 || it.text.isNotBlank() }
    if (spoken.isEmpty()) return SessionScore(0, "score_band_1", 0, 0)

    val totalWords = spoken.sumOf { max(it.words, it.text.split(Regex("\\s+")).size) }
    val tokens = spoken.flatMap { tokenWords(it.text) }
    val uniqueRatio = if (tokens.isEmpty()) 0.0 else tokens.toSet().size.toDouble() / tokens.size
    val speakingSeconds = spoken.sumOf { max(0.0, it.speechSeconds) }
    val measured = spoken.filter { it.wordsPerMinute > 0 }
    val wordsPerMinute = if (measured.isEmpty()) 0.0 else measured.sumOf { it.wordsPerMinute } / measured.size
    val pauseRatio = spoken.sumOf { clamp(it.pauseRatio, 0.0, 1.0) } / spoken.size
    val confidence = spoken.sumOf { clamp(it.confidence, 0.0, 1.0) } / spoken.size
    val averageWords = totalWords.toDouble() / spoken.size

    val fluency = when {
        wordsPerMinute <= 0 -> 55.0
        wordsPerMinute in 90.0..175.0 -> 100.0
        else -> {
            val distance = if (wordsPerMinute < 90) 90 - wordsPerMinute else wordsPerMinute - 175
            clamp(100.0 - distance * 0.55)
        }
    }
    val continuity = clamp(105.0 - pauseRatio * 130.0)
    val variety = clamp(uniqueRatio * 145.0)
    val length = clamp(averageWords / 14.0 * 100.0)
    val clarity = clamp(confidence * 115.0)

    val score = clamp(
        fluency * 0.24 + continuity * 0.20 + variety * 0.22 + length * 0.20 + clarity * 0.14,
    ).roundToInt()
    return SessionScore(
        score = score,
        bandKey = bandKeyForScore(score),
        turns = spoken.size,
        words = totalWords,
        uniqueRatio = (uniqueRatio * 1000).roundToInt() / 1000.0,
        speakingSeconds = (speakingSeconds * 10).roundToInt() / 10.0,
        wordsPerMinute = (wordsPerMinute * 10).roundToInt() / 10.0,
        pauseRatio = (pauseRatio * 1000).roundToInt() / 1000.0,
        confidence = (confidence * 1000).roundToInt() / 1000.0,
    )
}

// -- score history -------------------------------------------------------

class ScoreHistory(context: Context) {
    private val file = File(context.filesDir, "scores.json")

    fun load(): List<Map<String, Any?>> {
        return try {
            val payload = JSONObject(file.readText(Charsets.UTF_8))
            val sessions = payload.optJSONArray("sessions") ?: JSONArray()
            (0 until sessions.length()).mapNotNull { index ->
                sessions.optJSONObject(index)?.toMap()
            }
        } catch (_: Exception) {
            emptyList()
        }
    }

    fun save(
        language: String,
        scenarioId: String,
        scenarioLabel: String,
        result: SessionScore,
        mode: String = "practice",
    ) {
        val record = JSONObject().apply {
            put("date", Instant.now().toString())
            put("language", language)
            put("scenario", scenarioId)
            put("scenario_label", scenarioLabel)
            put("mode", mode)
            put("score", result.score)
            put("band_key", result.bandKey)
            put("turns", result.turns)
            put("words", result.words)
            put("unique_ratio", result.uniqueRatio)
            put("speaking_seconds", result.speakingSeconds)
            put("words_per_minute", result.wordsPerMinute)
            put("pause_ratio", result.pauseRatio)
            put("confidence", result.confidence)
        }
        val history = load().map { it.toJson() }.toMutableList()
        history.add(record)
        val trimmed = history.takeLast(500)
        val payload = JSONObject().apply {
            put("version", 1)
            put("sessions", JSONArray(trimmed))
        }
        try {
            file.writeText(payload.toString(2), Charsets.UTF_8)
        } catch (_: Exception) {
            // A full disk should never break a practice session.
        }
    }

    fun forLanguage(language: String): List<Map<String, Any?>> =
        load().filter { it["language"] == language }

    fun languages(): Map<String, List<Map<String, Any?>>> =
        load().groupBy { it["language"]?.toString().orEmpty() }.filterKeys { it.isNotEmpty() }

    fun summarize(history: List<Map<String, Any?>>): Map<String, Any> {
        val scores = history.map { (it["score"] as? Number)?.toInt() ?: 0 }
        if (scores.isEmpty()) {
            return mapOf("count" to 0, "average" to 0, "best" to 0, "band_key" to "score_band_1")
        }
        val average = (scores.sum().toDouble() / scores.size).roundToInt()
        return mapOf(
            "count" to scores.size,
            "average" to average,
            "best" to scores.max(),
            "band_key" to bandKeyForScore(average),
        )
    }
}

private fun JSONObject.toMap(): Map<String, Any?> {
    val map = HashMap<String, Any?>()
    for (key in keys()) {
        map[key] = get(key)
    }
    return map
}

private fun Map<String, Any?>.toJson(): JSONObject {
    val item = JSONObject()
    for ((key, value) in this) {
        item.put(key, value ?: JSONObject.NULL)
    }
    return item
}

// -- prompts -------------------------------------------------------------

object Prompts {
    private val LEVEL_GUIDANCE = mapOf(
        "A2" to "Use short, clear sentences and everyday vocabulary. You may use simple past and future.",
        "B1" to "Use natural everyday language with some idioms and phrasal verbs. Keep sentences manageable.",
        "C1" to "Use fluent, idiomatic and culturally natural language. Challenge the learner with richer vocabulary.",
    )

    /** A short, natural learner greeting used to open the conversation. */
    fun openingGreeting(target: String): String = when (target) {
        "pt" -> "Olá."
        "en" -> "Hello."
        "es" -> "Hola."
        "fr" -> "Bonjour."
        "it" -> "Ciao."
        "ja" -> "こんにちは。"
        "ko" -> "안녕하세요."
        "zh" -> "你好。"
        else -> "Hello."
    }

    fun systemPrompt(
        scenario: Scenario,
        target: String,
        native: String,
        askedQuestions: List<String>,
        opening: Boolean = false,
    ): String {
        val targetName = languageName(target)
        val nativeName = languageName(native)
        val level = scenario.level
        val guidance = LEVEL_GUIDANCE[level] ?: LEVEL_GUIDANCE.getValue("B1")
        val askedBlock = if (askedQuestions.isEmpty()) {
            ""
        } else {
            "\nQUESTIONS ALREADY ASKED (never ask them again):\n" +
                askedQuestions.takeLast(8).joinToString("\n") { "- $it" } + "\n"
        }
        return """
            You are a patient multilingual tutor and conversation partner.
            You are roleplaying with a learner of $targetName whose native language is $nativeName.

            SCENARIO:
            ${scenario.persona}

            LEARNER LEVEL: $level - $guidance

            LANGUAGE RULES:
            - MAIN REPLY LANGUAGE: $targetName. Always reply in this language, in character.
            - Never answer in a language different from $targetName outside the note.
            - If the learner mixes in $nativeName words, understand them, continue in $targetName and explain them in the note.
            - Do not mention that you are an AI, a model or a prompt.

            CONVERSATION RULES:
            - Keep the roleplay moving forward. Never restart the introduction.
            - Never repeat a question the learner has already answered.
            - Ask at most one question per reply, about a new detail or a related topic.
            - React to the learner's last answer with a short comment before asking something new.
            - If the learner gives a short answer, offer a detail or a choice so they can expand.
            - Vary your openings and vocabulary; do not reuse the same phrase twice.
            $askedBlock
            NOTE RULES:
            Always include a short note in $nativeName at the end, even when the learner writes only in one language.
            Use 1 to 3 plain bullets: one useful expression from the conversation written as
            "source expression -> $targetName equivalent", one short explanation and one short example.
            If the learner made an important $targetName error, add one short Correction bullet.
            Correct only what really matters and never interrupt the roleplay to teach.
            Do not use markdown headings, tables or code blocks.

            ${if (opening) "FIRST TURN: Start the roleplay now with your first in-character line, at most two short sentences, ending with a question for the learner. Do not include a note section in this first turn." else ""}

            RESPONSE FORMAT (mandatory):
            <MAIN>
            Your in-character reply in $targetName here. Use 2 to 4 natural sentences. Do not include headings, notes, tags or bullet lists here.
            </MAIN>
            <NOTE>
            Your note in $nativeName here.
            </NOTE>

            Return only the content inside the requested tags. Do not add anything before <MAIN> or after </NOTE>.
        """.trimIndent()
    }

    fun textMessages(
        scenario: Scenario,
        target: String,
        sentenceCount: Int,
        maxWords: Int? = null,
    ): List<ChatClient.Message> {
        val lengthRule = if (sentenceCount == 1) {
            "Write exactly ONE short sentence with 8 to 16 words. " +
                "Do not write a paragraph, a second sentence or a list."
        } else {
            "Write exactly $sentenceCount short sentences. Keep each sentence under 18 words."
        }
        val limit = if (maxWords != null) " Use at most $maxWords words." else ""
        val prompt = buildString {
            append(lengthRule)
            append(limit)
            append(
                " Write it in ${languageName(target)} for a ${scenario.level} learner practicing this situation: " +
                    "${scenario.label}. Use natural, spoken language and everyday vocabulary. " +
                    "Punctuation is essential: use commas, periods, question marks and exclamation marks " +
                    "so the text can be read aloud with natural pauses. Every sentence must start with a " +
                    "capital letter and end with punctuation. Never join words with hyphens; use spaces " +
                    "between words. Separate the sentences with a single space. Return only the sentences, " +
                    "no title, no list, no translation and no quotation marks.",
            )
        }
        return listOf(
            ChatClient.Message(
                "system",
                "You write short language-learning material. Always use correct punctuation and " +
                    "capitalization. Never connect words with hyphens. Never add explanations, headings or notes.",
            ),
            ChatClient.Message("user", prompt),
        )
    }
}

// -- reply parsing -------------------------------------------------------

data class ParsedReply(val main: String, val note: String)

object ReplyParser {
    private val TAG_NOISE = Regex("<\\s*/?\\s*(?:EN|PT|MAIN|NOTE)\\s*>", RegexOption.IGNORE_CASE)
    private val MAIN_TAG = Regex(
        "<\\s*(?:EN|MAIN)\\s*>(.*?)(?=<\\s*(?:PT|NOTE)\\s*>|<\\s*/\\s*(?:EN|MAIN)\\s*>|$)",
        setOf(RegexOption.IGNORE_CASE, RegexOption.DOT_MATCHES_ALL),
    )
    private val NOTE_TAG = Regex(
        "<\\s*(?:PT|NOTE)\\s*>(.*?)(?=<\\s*/\\s*(?:PT|NOTE)\\s*>|$)",
        setOf(RegexOption.IGNORE_CASE, RegexOption.DOT_MATCHES_ALL),
    )
    private val NOTE_HEADING = Regex("(?i)(?:💡|📝|vocabulary\\s+note|nota\\b|note\\b|メモ|提示)")
    private val PARTIAL_TAG = Regex("<[^>]*$")
    private val NULL_PREFIX = Regex("^(?:null\\s*)+", RegexOption.IGNORE_CASE)

    /** Some servers emit a leading JSON `null` token as text; never show it. */
    fun stripNullPrefix(value: String): String = NULL_PREFIX.replace(value.trimStart(), "").trimStart()

    private fun clean(value: String): String =
        TAG_NOISE.replace(value.replace("\r\n", "\n"), "").trim()

    fun parse(raw: String): ParsedReply {
        val text = stripNullPrefix(raw.trim())
        if (text.isEmpty()) return ParsedReply("", "")
        val mainMatch = MAIN_TAG.find(text)
        val noteMatch = NOTE_TAG.find(text)
        var main = mainMatch?.groupValues?.get(1)?.let(::clean).orEmpty()
        var note = noteMatch?.groupValues?.get(1)?.let(::clean).orEmpty()
        if (mainMatch == null && noteMatch == null) {
            val heading = NOTE_HEADING.find(text)
            if (heading != null && heading.range.first > 0) {
                main = clean(text.substring(0, heading.range.first))
                note = clean(text.substring(heading.range.first))
            } else if (heading != null) {
                note = clean(text.substring(heading.range.first))
            } else {
                main = clean(text)
            }
        } else if (note.isEmpty()) {
            val english = clean(main)
            val heading = NOTE_HEADING.find(english)
            if (heading != null) {
                note = clean(english.substring(heading.range.first))
                main = clean(english.substring(0, heading.range.first))
            }
        }
        return ParsedReply(main, note)
    }

    /** Visible main text while the reply is still streaming. */
    fun renderStream(raw: String): String {
        var text = stripNullPrefix(raw)
        val note = Regex("<\\s*(?:PT|NOTE)\\s*>", RegexOption.IGNORE_CASE).find(text)
        if (note != null) {
            text = text.substring(0, note.range.first)
        } else {
            val heading = Regex("(?:💡|📝)").find(text)
            if (heading != null) text = text.substring(0, heading.range.first)
        }
        text = TAG_NOISE.replace(text, "")
        return PARTIAL_TAG.replace(text, "").trim()
    }
}
