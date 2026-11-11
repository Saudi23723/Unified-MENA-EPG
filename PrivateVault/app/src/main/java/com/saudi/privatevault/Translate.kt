package com.saudi.privatevault

import android.app.Activity
import android.view.View
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import com.google.android.material.dialog.MaterialAlertDialogBuilder

/** Selected text to Arabic, as an aviation translator would: the terms kept in English beside the Arabic. */
object Translate {
    private const val SYSTEM = "You translate aviation study text (FAA handbooks, regulations, POH, AIM) from English into clear " +
        "Modern Standard Arabic for a student pilot. Translate faithfully and completely, sentence by sentence; do not explain, " +
        "summarise or add anything. Keep each technical term, abbreviation, number, unit and regulation reference in English, " +
        "giving the Arabic once with the English in brackets, e.g. قوة الرفع (Lift), سرعة الانهيار (stall speed, Vs). " +
        "No LaTeX, no markdown headings. Output only the translation."

    fun show(act: Activity, text: String) {
        if (!Gemini.hasKey(act)) { (act as? androidx.appcompat.app.AppCompatActivity)?.let { AiKey.ask(it) }; return }
        val d = act.resources.displayMetrics.density
        val col = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; setPadding((20 * d).toInt(), (8 * d).toInt(), (20 * d).toInt(), 0) }
        col.addView(TextView(act).apply {
            this.text = text.trim().take(600); textSize = 13f; setTextColor(EfbUi.DIM); textDirection = View.TEXT_DIRECTION_LTR
            setPadding(0, 0, 0, (10 * d).toInt())
        })
        val out = TextView(act).apply {
            this.text = "…"; textSize = 18f; setTextColor(EfbUi.TEXT); setLineSpacing(0f, 1.3f)
            textDirection = View.TEXT_DIRECTION_ANY_RTL; setTextIsSelectable(true)
        }
        col.addView(out)
        val dialog = MaterialAlertDialogBuilder(act)
            .setTitle(R.string.sel_translate)
            .setView(ScrollView(act).apply { addView(col) })
            .setPositiveButton(R.string.sel_copy) { _, _ ->
                act.getSystemService(android.content.ClipboardManager::class.java)?.setPrimaryClip(android.content.ClipData.newPlainText("ar", out.text))
            }
            .setNegativeButton(android.R.string.ok, null)
            .show()
        Thread {
            val a = try {
                Gemini.chat(act, listOf(Gemini.Turn(true, text)), system = SYSTEM) { soFar -> act.runOnUiThread { if (dialog.isShowing) out.text = MathText.clean(soFar) } }
            } catch (e: Exception) { LaptopClient.AiAnswer(null, null, e.message) }
            act.runOnUiThread {
                if (!dialog.isShowing) return@runOnUiThread
                if (a.text != null) out.text = MathText.clean(a.text) else out.text = "⚠ " + (a.problem ?: "?")
            }
        }.start()
    }
}
