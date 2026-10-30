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

        fun open(ctx: Context, image: ByteArray?, sel: String?, title: String, page: Int, start: String? = null) {
            pageImage = image; selected = sel; bookTitle = title; pageNumber = page
            ctx.startActivity(Intent(ctx, AiChatActivity::class.java).apply { start?.let { putExtra(EXTRA_START, it) } })
        }
    }

    private val turns = ArrayList<Gemini.Turn>()
    private lateinit var list: LinearLayout
    private lateinit var scroll: ScrollView
    private lateinit var input: EditText
    private lateinit var chips: View
    private lateinit var langChip: TextView
    private var busy: Job? = null

    private fun dp(v: Int) = EfbUi.dp(this, v)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val bg = 0xFF131314.toInt()
        window.statusBarColor = bg
        window.navigationBarColor = bg
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(bg) }

        // Top bar: back, Gemini, the language switch, the key.
        val bar = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(6), dp(6), dp(10), dp(6)) }
        bar.addView(TextView(this).apply {
            text = "‹"; textSize = 30f; setTextColor(0xFFE3E3E3.toInt()); setPadding(dp(12), 0, dp(12), dp(4))
            setOnClickListener { finish() }
        })
        bar.addView(TextView(this).apply {
            text = "✦ Gemini"; textSize = 20f; setTextColor(0xFFE3E3E3.toInt()); setTypeface(typeface, Typeface.BOLD)
        }, LinearLayout.LayoutParams(0, -2, 1f))
        langChip = pill("", 0xFF282A2C.toInt()) { Gemini.setEnglish(this, !Gemini.english(this)); showLang() }
        bar.addView(langChip)
        bar.addView(pill("🔑", 0xFF282A2C.toInt()) { AiKey.ask(this) }, LinearLayout.LayoutParams(-2, -2).apply { marginStart = dp(8) })
        root.addView(bar)
        showLang()

        list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(8), dp(16), dp(16)) }
        scroll = ScrollView(this).apply { addView(list); isFillViewport = true }
        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))

        // What the page is, then a greeting.
        val about = (if (bookTitle.isNotEmpty()) "📖 $bookTitle · ${getString(R.string.pdf_page_short, pageNumber)}" else "") +
            (selected?.let { "\n“" + it.replace('\n', ' ').take(160) + (if (it.length > 160) "…" else "") + "”" } ?: "")
        if (about.isNotBlank()) list.addView(TextView(this).apply {
            text = about; textSize = 13f; setTextColor(0xFF9AA0A6.toInt()); setPadding(0, dp(4), 0, dp(14))
        })
        list.addView(TextView(this).apply {
            text = getString(R.string.ai_hello); textSize = 26f; setTextColor(0xFF8AB4F8.toInt())
            setTypeface(typeface, Typeface.BOLD); setPadding(0, dp(18), 0, dp(10))
        })

        // Suggestions, like Gemini's, gone once the conversation starts.
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(dp(12), dp(4), dp(12), dp(4)) }
        for ((label, prompt) in listOf(
            R.string.ai_s_summary to R.string.ai_p_summary, R.string.ai_s_explain to R.string.ai_p_explain,
            R.string.ai_s_quiz to R.string.ai_p_quiz, R.string.ai_s_example to R.string.ai_p_example,
            R.string.ai_s_checkride to R.string.ai_p_checkride,
        )) row.addView(pill(getString(label), 0xFF1E1F20.toInt()) { send(getString(prompt)) }, LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(8) })
        chips = HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; addView(row) }
        root.addView(chips)

        // The input: a rounded box and a send button.
        val inBar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(14), dp(8), dp(8), dp(8))
            background = EfbUi.cardBg(this@AiChatActivity, 0xFF1E1F20.toInt(), 28)
        }
        input = EditText(this).apply {
            hint = getString(R.string.ai_ask_hint); setHintTextColor(0xFF9AA0A6.toInt()); setTextColor(0xFFE3E3E3.toInt())
            background = null; maxLines = 5; textSize = 16f
            imeOptions = EditorInfo.IME_ACTION_SEND
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE or android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
        }
        inBar.addView(input, LinearLayout.LayoutParams(0, -2, 1f))
        inBar.addView(TextView(this).apply {
            text = "↑"; textSize = 22f; setTextColor(0xFF131314.toInt()); gravity = Gravity.CENTER
            background = android.graphics.drawable.GradientDrawable().apply { shape = android.graphics.drawable.GradientDrawable.OVAL; setColor(0xFFE3E3E3.toInt()) }
            setOnClickListener { input.text.toString().trim().takeIf { it.isNotEmpty() }?.let { input.setText(""); send(it) } }
        }, LinearLayout.LayoutParams(dp(42), dp(42)))
        root.addView(inBar, LinearLayout.LayoutParams(-1, -2).apply { setMargins(dp(12), dp(6), dp(12), dp(12)) })

        setContentView(root)
        androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val b = insets.getInsets(androidx.core.view.WindowInsetsCompat.Type.systemBars() or androidx.core.view.WindowInsetsCompat.Type.ime())
            v.setPadding(0, b.top, 0, b.bottom)
            insets
        }
        if (!Gemini.hasKey(this)) {
            Toast.makeText(this, R.string.ai_key_first, Toast.LENGTH_LONG).show()
            AiKey.ask(this)
        }
        intent.getStringExtra(EXTRA_START)?.let { send(it) }
    }

    private fun pill(label: String, color: Int, onClick: () -> Unit) = TextView(this).apply {
        text = label; textSize = 14f; setTextColor(0xFFE3E3E3.toInt())
        background = EfbUi.cardBg(this@AiChatActivity, color, 20)
        setPadding(dp(14), dp(9), dp(14), dp(9))
        setOnClickListener { onClick() }
    }

    private fun showLang() {
        langChip.text = if (Gemini.english(this)) "🇺🇸 English" else "🇯🇴 عربي"
    }

    private fun send(question: String) {
        if (busy?.isActive == true) return
        if (!Gemini.hasKey(this)) { AiKey.ask(this); return }
        chips.visibility = View.GONE
        // The page (and any selected words) go with the first question.
        val first = turns.isEmpty()
        val text = if (first) (selected?.let { "Selected text:\n$it\n\n" } ?: "") + question else question
        turns.add(Gemini.Turn(true, text, if (first) pageImage else null))
        list.addView(TextView(this).apply {
            this.text = question; textSize = 16f; setTextColor(0xFFE3E3E3.toInt())
            background = EfbUi.cardBg(this@AiChatActivity, 0xFF282A2C.toInt(), 20)
            setPadding(dp(16), dp(10), dp(16), dp(10))
            textDirection = View.TEXT_DIRECTION_FIRST_STRONG
        }, LinearLayout.LayoutParams(-2, -2).apply { gravity = Gravity.END; topMargin = dp(14); marginStart = dp(48) })

        val head = TextView(this).apply { this.text = "✦"; textSize = 20f; setTextColor(0xFF8AB4F8.toInt()); setPadding(0, dp(16), 0, dp(2)) }
        list.addView(head)
        val reply = TextView(this).apply {
            this.text = "…"; textSize = 16f; setTextColor(0xFFE3E3E3.toInt()); setLineSpacing(0f, 1.3f)
            setTextIsSelectable(true); textDirection = View.TEXT_DIRECTION_FIRST_STRONG
        }
        list.addView(reply)
        scrollDown()
        busy = lifecycleScope.launch {
            val a = withContext(Dispatchers.IO) {
                Gemini.chat(this@AiChatActivity, turns) { soFar -> runOnUiThread { reply.text = md(soFar); scrollDown() } }
            }
            if (a.text != null) {
                reply.text = md(a.text)
                turns.add(Gemini.Turn(false, a.text))
                list.addView(pill("⧉ " + getString(R.string.sel_copy), 0xFF1E1F20.toInt()) {
                    (getSystemService(CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("answer", a.text))
                    Toast.makeText(this@AiChatActivity, R.string.sel_copied, Toast.LENGTH_SHORT).show()
                }, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(6) })
            } else {
                // Not answered: the question is taken back so it can be asked again.
                turns.removeAt(turns.size - 1)
                reply.setTextColor(0xFFF28B82.toInt())
                reply.text = getString(if (a.problem == "offline") R.string.ai_offline else R.string.ai_failed) +
                    if (a.detail.isNotEmpty()) "\n\n" + a.detail else ""
            }
            scrollDown()
        }
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
