package com.saudi.privatevault

import android.text.InputType
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Setting the Gemini key, which lives on the linked vault so every device uses it. */
object AiKey {
    fun ask(a: AppCompatActivity) {
        if (!LaptopClient.isLinked(a)) {
            Toast.makeText(a, R.string.ai_link_first, Toast.LENGTH_LONG).show()
            return
        }
        val input = EditText(a).apply {
            setSingleLine()
            hint = "AIza…"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD
        }
        val pad = (a.resources.displayMetrics.density * 20).toInt()
        val box = LinearLayout(a).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad / 2, pad, 0)
            addView(input)
        }
        MaterialAlertDialogBuilder(a)
            .setTitle(R.string.ai_key_title)
            .setMessage(R.string.ai_key_help)
            .setView(box)
            .setPositiveButton(R.string.ok) { _, _ -> save(a, input.text.toString().trim()) }
            .setNeutralButton(R.string.ai_key_remove) { _, _ -> save(a, "") }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun save(a: AppCompatActivity, key: String) {
        a.lifecycleScope.launch {
            val st = withContext(Dispatchers.IO) { LaptopClient.setAiKey(a, key) }
            val msg = when {
                st == null -> a.getString(R.string.ai_offline_or_old)
                st.optBoolean("gemini") -> a.getString(R.string.ai_key_saved)
                else -> a.getString(R.string.ai_key_removed)
            } + if (st != null) "\n" + a.getString(if (st.optBoolean("local")) R.string.ai_local_ready else R.string.ai_local_not_ready) else ""
            Toast.makeText(a, msg, Toast.LENGTH_LONG).show()
        }
    }
}
