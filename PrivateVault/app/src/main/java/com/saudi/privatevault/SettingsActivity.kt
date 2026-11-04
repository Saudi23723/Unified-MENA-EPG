package com.saudi.privatevault

import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatDelegate
import androidx.core.os.LocaleListCompat

/**
 * Settings, laid out as an EFB lays them out: sections of rows, each with
 * its choices side by side (Auto · Light · Dark), the pilot and their
 * personal minimums, and where the rest lives.
 */
class SettingsActivity : BaseActivity() {
    private lateinit var col: LinearLayout
    private val prefs get() = VaultLock.prefs(this)
    private fun dp(v: Int) = EfbUi.dp(this, v)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        col = EfbUi.screen(this, getString(R.string.set_title))
        build()
    }

    private fun build() {
        col.removeAllViews()
        val version = try { packageManager.getPackageInfo(packageName, 0).versionName } catch (e: Exception) { "" }

        section(R.string.set_general)
        val card = card()
        segmented(card, getString(R.string.theme_title), null, listOf("auto" to "AUTO", "light" to "LIGHT", "dark" to "DARK"), prefs.getString("theme_mode", "dark") ?: "dark") {
            prefs.edit().putString("theme_mode", it).apply(); EfbUi.applyTheme(this)
        }
        val lang = AppCompatDelegate.getApplicationLocales().toLanguageTags().ifEmpty { "ar" }
        segmented(card, getString(R.string.set_language), null, listOf("ar" to "العربية", "en" to "ENGLISH"), if (lang.startsWith("en")) "en" else "ar") {
            AppCompatDelegate.setApplicationLocales(LocaleListCompat.forLanguageTags(it))
        }
        segmented(card, getString(R.string.set_screen_on), getString(R.string.set_screen_on_sub), listOf("auto" to "AUTO", "on" to "ON", "off" to "OFF"), prefs.getString("screen_on", "auto") ?: "auto") {
            prefs.edit().putString("screen_on", it).apply(); BaseActivity.keepScreen(this)
        }
        toggle(card, getString(R.string.qt_toggle).removePrefix("✎ "), getString(R.string.set_tools_sub), QuickTools.enabled(this)) {
            QuickTools.setEnabled(this, it); QuickTools.attach(this)
        }
        toggle(card, getString(R.string.set_voice), getString(R.string.set_voice_sub), Voice.enabled(this)) {
            prefs.edit().putBoolean("voice_on", it).apply()
        }

        section(R.string.set_pilot)
        val p = card()
        field(p, getString(R.string.log_pilot_name), "pilot_name", false)
        field(p, getString(R.string.log_pilot_cert), "pilot_cert", false)
        field(p, getString(R.string.set_home), "efb_home", false, caps = true)

        section(R.string.set_minimums)
        val m = card()
        m.addView(EfbUi.text(this, getString(R.string.set_minimums_sub), 12.5f, EfbUi.DIM).apply { setPadding(0, 0, 0, dp(6)) })
        field(m, getString(R.string.set_min_ceiling), "min_ceiling", true)
        field(m, getString(R.string.set_min_vis), "min_vis", true)
        field(m, getString(R.string.set_min_wind), "min_wind", true)
        field(m, getString(R.string.set_min_gust), "min_gust", true)

        section(R.string.set_data)
        val d = card()
        link(d, "⬆️  " + getString(R.string.tv_update)) { Updater.check(this, quiet = false) }
        link(d, "🔑  " + getString(R.string.set_ai_key)) { AiKey.ask(this) }
        link(d, "🗓  " + getString(R.string.set_charts)) { ChartUpdates.autoUpdate(this) }
        link(d, "📒  " + getString(R.string.set_logbook)) { startActivity(android.content.Intent(this, LogbookActivity::class.java)) }
        link(d, "✅  " + getString(R.string.set_efb_check)) { startActivity(android.content.Intent(this, EfbCheckActivity::class.java)) }

        section(R.string.set_about)
        val a = card()
        a.addView(EfbUi.text(this, getString(R.string.app_name) + "  " + version, 15f, EfbUi.TEXT, bold = true))
        a.addView(EfbUi.text(this, getString(R.string.set_about_sub), 12.5f, EfbUi.DIM).apply { setPadding(0, dp(4), 0, 0) })
    }

    private fun section(res: Int) = col.addView(EfbUi.section(this, getString(res)))

    private fun card(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        background = EfbUi.cardBg(this@SettingsActivity, EfbUi.CARD, 14).apply { setStroke(0, 0) }
        setPadding(dp(16), dp(10), dp(16), dp(10))
        col.addView(this)
    }

    private fun rowTitle(parent: LinearLayout, title: String, sub: String?): LinearLayout {
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(0, dp(8), 0, dp(8)) }
        val t = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        t.addView(EfbUi.text(this, title, 15f, EfbUi.TEXT))
        if (sub != null) t.addView(EfbUi.text(this, sub, 12f, EfbUi.DIM))
        row.addView(t, LinearLayout.LayoutParams(0, -2, 1f))
        if (parent.childCount > 0) parent.addView(View(this).apply { setBackgroundColor(EfbUi.CARD_LINE) }, LinearLayout.LayoutParams(-1, 1))
        parent.addView(row)
        return row
    }

    /** Choices side by side, the one in use filled. */
    private fun segmented(parent: LinearLayout, title: String, sub: String?, choices: List<Pair<String, String>>, now: String, onPick: (String) -> Unit) {
        val row = rowTitle(parent, title, sub)
        val seg = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; layoutDirection = View.LAYOUT_DIRECTION_LTR
            background = EfbUi.cardBg(this@SettingsActivity, EfbUi.BG, 10).apply { setStroke(dp(1), EfbUi.ACCENT) }
            setPadding(dp(2), dp(2), dp(2), dp(2))
        }
        var current = now
        val views = ArrayList<Pair<String, TextView>>()
        fun paint() = views.forEach { (k, v) ->
            val on = k == current
            v.setTextColor(if (on) 0xFFFFFFFF.toInt() else EfbUi.ACCENT)
            v.background = if (on) EfbUi.cardBg(this, EfbUi.ACCENT, 8).apply { setStroke(0, 0) } else null
        }
        for ((k, label) in choices) {
            val v = EfbUi.text(this, label, 12.5f, EfbUi.ACCENT, bold = true).apply {
                gravity = Gravity.CENTER; setPadding(dp(12), dp(7), dp(12), dp(7))
                setOnClickListener { current = k; paint(); onPick(k) }
            }
            views.add(k to v)
            seg.addView(v)
        }
        paint()
        row.addView(seg)
    }

    private fun toggle(parent: LinearLayout, title: String, sub: String?, on: Boolean, onChange: (Boolean) -> Unit) {
        val row = rowTitle(parent, title, sub)
        row.addView(com.google.android.material.materialswitch.MaterialSwitch(this).apply {
            isChecked = on
            setOnCheckedChangeListener { _, v -> onChange(v) }
        })
    }

    private fun field(parent: LinearLayout, title: String, key: String, number: Boolean, caps: Boolean = false) {
        val row = rowTitle(parent, title, null)
        row.addView(EditText(this).apply {
            setText(prefs.getString(key, "") ?: "")
            setTextColor(EfbUi.ACCENT); setHintTextColor(EfbUi.DIM); hint = "—"
            gravity = Gravity.END; setSingleLine(); minWidth = dp(110)
            inputType = if (number) InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
                else if (caps) InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS else InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_WORDS
            addTextChangedListener(object : android.text.TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
                override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
                override fun afterTextChanged(s: android.text.Editable?) { prefs.edit().putString(key, s.toString().trim()).apply() }
            })
        })
    }

    private fun link(parent: LinearLayout, title: String, onClick: () -> Unit) {
        val row = rowTitle(parent, title, null)
        row.addView(EfbUi.text(this, "›", 20f, EfbUi.DIM))
        row.setOnClickListener { onClick() }
    }
}
