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

/**
 * Setting the Gemini key: kept on the phone, which then asks Gemini itself,
 * and sent to the linked vault too (when there is one) for the laptop.
 */
object AiKey {
    fun ask(a: AppCompatActivity) {
        val input = EditText(a).apply {
            setSingleLine()
            setText(Gemini.key(a))
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
        Gemini.setKey(a, key)
        if (!LaptopClient.isLinked(a)) {
            Toast.makeText(a, if (key.isNotEmpty()) R.string.ai_key_saved else R.string.ai_key_removed, Toast.LENGTH_LONG).show()
            return
        }
        a.lifecycleScope.launch {
            val st = withContext(Dispatchers.IO) { LaptopClient.setAiKey(a, key) }
            val msg = when {
                st == null -> a.getString(if (key.isNotEmpty()) R.string.ai_key_saved else R.string.ai_key_removed)
                st.optBoolean("gemini") -> a.getString(R.string.ai_key_saved)
                else -> a.getString(R.string.ai_key_removed)
            }
            Toast.makeText(a, msg, Toast.LENGTH_LONG).show()
        }
    }
}
