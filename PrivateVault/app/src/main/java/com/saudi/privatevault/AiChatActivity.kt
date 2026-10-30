package com.saudi.privatevault

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.graphics.Typeface
import android.os.Bundle
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.style.RelativeSizeSpan
import android.text.style.StyleSpan
import android.view.Gravity
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.lifecycle.lifecycleScope
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * A conversation with Gemini about the page being read, laid out like
 * Gemini itself: the page goes with the first question (as a picture, so
 * figures and tables are read too), answers are written out as they come,
 * follow-up questions keep the conversation, and one tap switches the
 * answers between Arabic and English.
 */
class AiChatActivity : BaseActivity() {
    companion object {
        // The page and the selected words, handed over in memory (a page picture is too big for an Intent).
        var pageImage: ByteArray? = null
        var selected: String? = null
        var bookTitle: String = ""
        var pageNumber: Int = 0
        const val EXTRA_START = "start"

        // A trainer (radio, weather): its own instructions, greeting and shortcuts, and the radio read aloud.
        var trainerSystem: String? = null
        var trainerHello: String? = null
        var trainerChips: List<Pair<String, String>>? = null
        var speakRadio = false

        fun openTrainer(ctx: Context, title: String, system: String, hello: String, chips: List<Pair<String, String>>, radio: Boolean, start: String?) {
            pageImage = null; selected = null; bookTitle = title; pageNumber = 0
            trainerSystem = system; trainerHello = hello; trainerChips = chips; speakRadio = radio
            ctx.startActivity(Intent(ctx, AiChatActivity::class.java).apply { start?.let { putExtra(EXTRA_START, it) } })
        }

        fun open(ctx: Context, image: ByteArray?, sel: String?, title: String, page: Int, start: String? = null) {
            pageImage = image; selected = sel; bookTitle = title; pageNumber = page
            trainerSystem = null; trainerHello = null; trainerChips = null; speakRadio = false
            ctx.startActivity(Intent(ctx, AiChatActivity::class.java).apply { start?.let { putExtra(EXTRA_START, it) } })
        }
    }

    private val turns = ArrayList<Gemini.Turn>()
    // What is on screen, to draw again in the other theme: (from the pilot?, text).
    private val shown = ArrayList<Pair<Boolean, String>>()
    private lateinit var list: LinearLayout
    private lateinit var scroll: ScrollView
    private lateinit var input: EditText
    private lateinit var chips: View
    private lateinit var langChip: TextView
    private var busy: Job? = null
    private var deep = false
    private lateinit var deepChip: TextView

    // Gemini's two looks.
    private var light = false
    private val bg get() = if (light) 0xFFFFFFFF.toInt() else 0xFF131314.toInt()
    private val ink get() = if (light) 0xFF1F1F1F.toInt() else 0xFFE3E3E3.toInt()
    private val dim get() = if (light) 0xFF5F6368.toInt() else 0xFF9AA0A6.toInt()
    private val bubble get() = if (light) 0xFFE9EEF6.toInt() else 0xFF282A2C.toInt()
    private val field get() = if (light) 0xFFF0F4F9.toInt() else 0xFF1E1F20.toInt()
    private val accent get() = if (light) 0xFF0B57D0.toInt() else 0xFF8AB4F8.toInt()
    private val bad get() = if (light) 0xFFB3261E.toInt() else 0xFFF28B82.toInt()

    private fun dp(v: Int) = EfbUi.dp(this, v)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        light = VaultLock.prefs(this).getBoolean("ai_light", false)
        build()
        Gemini.warmUp()
        if (!Gemini.hasKey(this)) {
            Toast.makeText(this, R.string.ai_key_first, Toast.LENGTH_LONG).show()
            AiKey.ask(this)
        }
        intent.getStringExtra(EXTRA_START)?.let { send(it) }
    }

    /** The whole screen, in the current look; the conversation so far is drawn again. */
    private fun build() {
        window.statusBarColor = bg
        window.navigationBarColor = bg
        androidx.core.view.WindowCompat.getInsetsController(window, window.decorView).apply {
            isAppearanceLightStatusBars = light
            isAppearanceLightNavigationBars = light
        }
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(bg) }

        // Top bar: back, Gemini, light or dark, the language, the key.
        val bar = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(6), dp(6), dp(10), dp(6)) }
        bar.addView(TextView(this).apply {
            text = "‹"; textSize = 30f; setTextColor(ink); setPadding(dp(12), 0, dp(12), dp(4))
            setOnClickListener { finish() }
        })
        bar.addView(TextView(this).apply {
            text = "✦ Gemini"; textSize = 20f; setTextColor(ink); setTypeface(typeface, Typeface.BOLD)
        }, LinearLayout.LayoutParams(0, -2, 1f))
        bar.addView(pill(if (light) "🌙" else "☀️", bubble) {
            light = !light
            VaultLock.prefs(this).edit().putBoolean("ai_light", light).apply()
            build()
        })
        langChip = pill("", bubble) { Gemini.setEnglish(this, !Gemini.english(this)); showLang() }
        bar.addView(langChip, LinearLayout.LayoutParams(-2, -2).apply { marginStart = dp(8) })
        bar.addView(pill("🔑", bubble) { AiKey.ask(this) }, LinearLayout.LayoutParams(-2, -2).apply { marginStart = dp(8) })
        root.addView(bar)
        showLang()

        list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(8), dp(16), dp(16)) }
        scroll = ScrollView(this).apply { addView(list); isFillViewport = true }
        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))

        // What the page is, then a greeting.
        val about = (if (trainerSystem != null) bookTitle else if (bookTitle.isNotEmpty()) "📖 $bookTitle" + (if (pageNumber > 0) " · ${getString(R.string.pdf_page_short, pageNumber)}" else "") else "") +
            (selected?.let { "\n“" + it.replace('\n', ' ').take(160) + (if (it.length > 160) "…" else "") + "”" } ?: "")
        if (about.isNotBlank()) list.addView(TextView(this).apply {
            text = about; textSize = 13f; setTextColor(dim); setPadding(0, dp(4), 0, dp(14))
        })
        list.addView(TextView(this).apply {
            text = trainerHello ?: getString(R.string.ai_hello); textSize = if (trainerHello != null) 20f else 26f; setTextColor(accent)
            setTypeface(typeface, Typeface.BOLD); setPadding(0, dp(18), 0, dp(10))
        })
        for ((mine, text) in shown) if (mine) userBubble(text) else answerView(text, done = true)

        // Shortcuts, like Gemini's suggestions, always a tap away above the question box.
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(dp(12), dp(4), dp(12), dp(4)) }
        val shortcuts = trainerChips ?: listOf(
            R.string.ai_s_summary to R.string.ai_p_summary, R.string.ai_s_explain to R.string.ai_p_explain,
            R.string.ai_s_extended to R.string.ai_p_extended, R.string.ai_s_examples to R.string.ai_p_examples,
            R.string.ai_s_written to R.string.ai_p_written, R.string.ai_s_checkride to R.string.ai_p_checkride,
            R.string.ai_s_example to R.string.ai_p_example, R.string.ai_s_quiz to R.string.ai_p_quiz,
        ).map { getString(it.first) to getString(it.second) }
        for ((label, prompt) in shortcuts) row.addView(pill(label, field) { send(prompt) }, LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(8) })
        chips = HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; addView(row) }
        root.addView(chips)

        // The input: a rounded box and a send button.
        val inBar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(14), dp(8), dp(8), dp(8))
            background = EfbUi.cardBg(this@AiChatActivity, field, 28).apply { setStroke(0, 0) }
        }
        val old = if (::input.isInitialized) input.text.toString() else ""
        input = EditText(this).apply {
            hint = getString(R.string.ai_ask_hint); setHintTextColor(dim); setTextColor(ink)
            background = null; maxLines = 5; textSize = 16f; setText(old)
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE or android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
        }
        deepChip = TextView(this).apply {
            textSize = 13f; gravity = Gravity.CENTER; setPadding(dp(10), dp(6), dp(10), dp(6))
            setOnClickListener {
                deep = !deep
                showDeep()
                Toast.makeText(this@AiChatActivity, if (deep) R.string.ai_deep_on else R.string.ai_deep_off, Toast.LENGTH_SHORT).show()
            }
        }
        inBar.addView(deepChip, LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(6) })
        showDeep()
        inBar.addView(input, LinearLayout.LayoutParams(0, -2, 1f))
        if (speakRadio) inBar.addView(TextView(this).apply {
            text = "🎙"; textSize = 22f; gravity = Gravity.CENTER; setPadding(dp(8), 0, dp(8), 0)
            setOnClickListener { listen() }
        })
        inBar.addView(TextView(this).apply {
            text = "↑"; textSize = 22f; setTextColor(bg); gravity = Gravity.CENTER
            background = android.graphics.drawable.GradientDrawable().apply { shape = android.graphics.drawable.GradientDrawable.OVAL; setColor(ink) }
            setOnClickListener { input.text.toString().trim().takeIf { it.isNotEmpty() }?.let { input.setText(""); send(it) } }
        }, LinearLayout.LayoutParams(dp(42), dp(42)))
        root.addView(inBar, LinearLayout.LayoutParams(-1, -2).apply { setMargins(dp(12), dp(6), dp(12), dp(12)) })

        setContentView(root)
        androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val b = insets.getInsets(androidx.core.view.WindowInsetsCompat.Type.systemBars() or androidx.core.view.WindowInsetsCompat.Type.ime())
            v.setPadding(0, b.top, 0, b.bottom)
            insets
        }
        scrollDown()
    }

    private fun pill(label: String, color: Int, onClick: () -> Unit) = TextView(this).apply {
        text = label; textSize = 14f; setTextColor(ink)
        background = EfbUi.cardBg(this@AiChatActivity, color, 20).apply { setStroke(0, 0) }
        setPadding(dp(14), dp(9), dp(14), dp(9))
        setOnClickListener { onClick() }
    }

    private fun showDeep() {
        deepChip.text = "🧠 " + getString(R.string.ai_deep)
        deepChip.setTextColor(if (deep) bg else dim)
        deepChip.background = EfbUi.cardBg(this, if (deep) accent else bubble, 16).apply { setStroke(0, 0) }
    }

    private fun showLang() {
        langChip.text = if (Gemini.english(this)) "🇺🇸 English" else "🇯🇴 عربي"
    }

    private fun userBubble(text: String) = list.addView(TextView(this).apply {
        this.text = text; textSize = 16f; setTextColor(ink)
        background = EfbUi.cardBg(this@AiChatActivity, bubble, 20).apply { setStroke(0, 0) }
        setPadding(dp(16), dp(10), dp(16), dp(10))
        textDirection = View.TEXT_DIRECTION_FIRST_STRONG
    }, LinearLayout.LayoutParams(-2, -2).apply { gravity = Gravity.END; topMargin = dp(14); marginStart = dp(48) })

    /** An answer: the ✦, the text, and (once complete) a copy button. */
    private fun answerView(text: String, done: Boolean): TextView {
        list.addView(TextView(this).apply { this.text = "✦"; textSize = 20f; setTextColor(accent); setPadding(0, dp(16), 0, dp(2)) })
        val reply = TextView(this).apply {
            this.text = md(text); textSize = 16f; setTextColor(ink); setLineSpacing(0f, 1.3f)
            setTextIsSelectable(true); textDirection = View.TEXT_DIRECTION_FIRST_STRONG
        }
        list.addView(reply)
        if (done) copyButton(text)
        return reply
    }

    private fun copyButton(text: String) = list.addView(pill("⧉ " + getString(R.string.sel_copy), field) {
        (getSystemService(CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("answer", text))
        Toast.makeText(this, R.string.sel_copied, Toast.LENGTH_SHORT).show()
    }, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(6) })

    private fun send(question: String) {
        if (busy?.isActive == true) return
        if (!Gemini.hasKey(this)) { AiKey.ask(this); return }
        // Deep thinking is for this one question; the next goes back to quick.
        val thinkHard = deep
        if (deep) { deep = false; showDeep() }
        // The page (and any selected words) go with the first question.
        val first = turns.isEmpty()
        val text = if (first) (selected?.let { "Selected text:\n$it\n\n" } ?: "") + question else question
        turns.add(Gemini.Turn(true, text, if (first) pageImage else null))
        shown.add(true to question)
        userBubble(question)
        val reply = answerView("…", done = false)
        // Under the answer: which model, and the seconds, so a wait is never a mystery.
        val status = TextView(this).apply { textSize = 12f; setTextColor(dim); setPadding(0, dp(6), 0, 0) }
        list.addView(status)
        val t0 = System.currentTimeMillis()
        var model = ""
        var got = false
        val tick = object : Runnable {
            override fun run() {
                if (busy?.isActive != true) return
                val sec = (System.currentTimeMillis() - t0) / 1000
                status.text = (if (got) "✦ " else if (thinkHard) "🧠 " else "⏳ ") + model + "  ·  ${sec}s"
                status.postDelayed(this, 500)
            }
        }
        scrollDown()
        busy = lifecycleScope.launch {
            status.post(tick)
            val a = withContext(Dispatchers.IO) {
                Gemini.chat(this@AiChatActivity, turns, thinkHard, { m -> runOnUiThread { model = m } }, trainerSystem) { soFar ->
                    runOnUiThread { got = true; reply.text = md(soFar); scrollDown() }
                }
            }
            status.text = if (a.text != null) (if (thinkHard) "🧠 " else "✦ ") + "${Gemini.lastModel}  ·  %.1fs".format((System.currentTimeMillis() - t0) / 1000.0) else ""
            if (a.text != null) {
                reply.text = md(a.text)
                turns.add(Gemini.Turn(false, a.text))
                shown.add(false to a.text)
                if (speakRadio) speakRadioLines(a.text)
                copyButton(a.text)
            } else {
                // Not answered: the question is taken back so it can be asked again.
                turns.removeAt(turns.size - 1)
                shown.removeAt(shown.size - 1)
                reply.setTextColor(bad)
                reply.text = getString(if (a.problem == "nonet") R.string.ai_nonet else R.string.ai_failed) +
                    if (a.detail.isNotEmpty()) "\n\n" + a.detail else ""
            }
            scrollDown()
        }
    }

    // ---- the radio trainer: the controller's words aloud, the pilot's call by voice ----

    private var tts: android.speech.tts.TextToSpeech? = null

    private fun speakRadioLines(text: String) {
        val lines = text.lines().map { it.replace("*", "").trim() }
            .filter { Regex("^(TOWER|GROUND|APPROACH|DEPARTURE|CENTER|CLEARANCE|ATIS|AWOS|TRAFFIC|UNICOM|RADIO|ATC)[^:]{0,20}:").containsMatchIn(it) }
            .map { it.substringAfter(':').trim() }
        if (lines.isEmpty()) return
        val say = { t: android.speech.tts.TextToSpeech -> lines.forEachIndexed { i, l -> t.speak(l, if (i == 0) android.speech.tts.TextToSpeech.QUEUE_FLUSH else android.speech.tts.TextToSpeech.QUEUE_ADD, null, "r$i") } }
        tts?.let { say(it); return }
        var t: android.speech.tts.TextToSpeech? = null
        t = android.speech.tts.TextToSpeech(this) { ok ->
            if (ok == android.speech.tts.TextToSpeech.SUCCESS) t?.let { it.language = java.util.Locale.US; it.setSpeechRate(1.1f); tts = it; say(it) }
        }
    }

    private val speech = registerForActivityResult(androidx.activity.result.contract.ActivityResultContracts.StartActivityForResult()) { r ->
        val heard = r.data?.getStringArrayListExtra(android.speech.RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()
        if (!heard.isNullOrBlank()) send(heard)
    }

    /** The pilot's call, spoken (English, as on the radio). */
    private fun listen() {
        try {
            VaultLock.keepUnlockedOnce = true
            speech.launch(Intent(android.speech.RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                .putExtra(android.speech.RecognizerIntent.EXTRA_LANGUAGE_MODEL, android.speech.RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                .putExtra(android.speech.RecognizerIntent.EXTRA_LANGUAGE, "en-US")
                .putExtra(android.speech.RecognizerIntent.EXTRA_PROMPT, "Your radio call"))
        } catch (e: Exception) {
            VaultLock.keepUnlockedOnce = false
            Toast.makeText(this, R.string.tr_no_mic, Toast.LENGTH_LONG).show()
        }
    }

    override fun onDestroy() {
        tts?.shutdown()
        super.onDestroy()
    }

    private fun scrollDown() = scroll.post { scroll.fullScroll(View.FOCUS_DOWN) }

    /** Gemini's markdown, enough of it: headings, bold, and bullets. */
    private fun md(src: String): CharSequence {
        val out = SpannableStringBuilder()
        for ((n, raw) in src.lines().withIndex()) {
            if (n > 0) out.append('\n')
            var line = raw
            var heading = false
            Regex("^#{1,6}\\s+").find(line)?.let { line = line.substring(it.value.length); heading = true }
            Regex("^(\\s*)[*-]\\s+").find(line)?.let { line = it.groupValues[1] + "•  " + line.substring(it.value.length) }
            val start = out.length
            var i = 0
            while (i < line.length) {
                val b = line.indexOf("**", i)
                if (b < 0) { out.append(line.substring(i)); break }
                val e = line.indexOf("**", b + 2)
                if (e < 0) { out.append(line.substring(i)); break }
                out.append(line.substring(i, b))
                val s = out.length
                out.append(line.substring(b + 2, e))
                out.setSpan(StyleSpan(Typeface.BOLD), s, out.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                i = e + 2
            }
            if (heading) {
                out.setSpan(StyleSpan(Typeface.BOLD), start, out.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                out.setSpan(RelativeSizeSpan(1.15f), start, out.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            }
        }
        return out
    }
}
