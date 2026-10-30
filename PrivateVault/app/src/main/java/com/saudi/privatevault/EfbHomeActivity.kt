package com.saudi.privatevault

import android.content.Intent
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import androidx.lifecycle.lifecycleScope
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * The flight bag's front page: the home airport's weather at a glance, and
 * every tool a tile away — the moving map, airport diagrams, the nav log,
 * weight and balance, the logbook with its 61.109 progress and currency,
 * the E6B and the checklists.
 */
class EfbHomeActivity : BaseActivity() {

    private lateinit var col: LinearLayout
    private lateinit var wx: LinearLayout
    private val prefs get() = VaultLock.prefs(this)
    private fun dp(v: Int) = EfbUi.dp(this, v)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        col = EfbUi.screen(this, getString(R.string.efb_title)) { bar ->
            bar.menu.add(R.string.lang_switch).setOnMenuItemClickListener { Lang.choose(this); true }
        }
        wx = EfbUi.card(this)
        col.addView(wx)
        EfbUi.pressable(wx) { askHome() }

        val tiles = listOf(
            Triple("🗺", R.string.efb_map) { open(MapActivity::class.java) },
            Triple("🛬", R.string.efb_diagram) { diagram() },
            Triple("🧭", R.string.plan_title) { startActivity(Intent(this, MapActivity::class.java).putExtra(MapActivity.EXTRA_NAVLOG, true)) },
            Triple("⚖️", R.string.wb_title) { open(WeightBalanceActivity::class.java) },
            Triple("📒", R.string.log_title) { open(LogbookActivity::class.java) },
            Triple("🎓", R.string.log_109) { startActivity(Intent(this, LogbookActivity::class.java).putExtra(LogbookActivity.EXTRA_TAB, 1)) },
            Triple("⏱", R.string.log_currency) { startActivity(Intent(this, LogbookActivity::class.java).putExtra(LogbookActivity.EXTRA_TAB, 2)) },
            Triple("🧮", R.string.e6b_title) { open(E6bActivity::class.java) },
            Triple("✅", R.string.ck_title) { open(ChecklistActivity::class.java) },
        )
        var row: LinearLayout? = null
        for ((i, t) in tiles.withIndex()) {
            if (i % 3 == 0) {
                row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
                col.addView(row, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) })
            }
            val tile = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                gravity = Gravity.CENTER
                background = EfbUi.cardBg(this@EfbHomeActivity)
                setPadding(dp(6), dp(16), dp(6), dp(14))
                addView(EfbUi.text(this@EfbHomeActivity, t.first, 30f).apply { gravity = Gravity.CENTER })
                addView(EfbUi.text(this@EfbHomeActivity, getString(t.second).replace(Regex("^\\S+\\s"), ""), 13f, EfbUi.TEXT, bold = true).apply {
                    gravity = Gravity.CENTER
                    setPadding(0, dp(6), 0, 0)
                    maxLines = 2
                })
            }
            EfbUi.pressable(tile) { t.third() }
            row!!.addView(tile, LinearLayout.LayoutParams(0, dp(112), 1f).apply {
                marginStart = if (i % 3 == 0) 0 else dp(6)
                marginEnd = if (i % 3 == 2) 0 else dp(6)
            })
        }
        col.addView(EfbUi.text(this, getString(R.string.map_disclaimer), 11f, EfbUi.DIM).apply {
            setPadding(dp(4), dp(18), dp(4), 0)
        })
        EfbUi.stagger(col)
    }

    override fun onResume() {
        super.onResume()
        showWeather()
    }

    private fun home() = prefs.getString("efb_home", "KBVU")!!

    private fun open(c: Class<*>) = startActivity(Intent(this, c))

    private fun showWeather() {
        val station = home()
        wx.removeAllViews()
        wx.addView(EfbUi.text(this, station, 26f, EfbUi.ACCENT, bold = true))
        val line = EfbUi.ltr(EfbUi.text(this, getString(R.string.map_loading_wx), 14f, EfbUi.DIM, mono = true))
        wx.addView(line)
        lifecycleScope.launch {
            val m = withContext(Dispatchers.IO) { AviationData.metar(station) }
            if (m == null) {
                line.text = getString(R.string.map_no_metar)
                return@launch
            }
            wx.removeAllViews()
            val head = LinearLayout(this@EfbHomeActivity).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
            head.addView(EfbUi.text(this@EfbHomeActivity, station, 26f, EfbUi.ACCENT, bold = true), LinearLayout.LayoutParams(0, -2, 1f))
            head.addView(EfbUi.text(this@EfbHomeActivity, " ${m.category.ifEmpty { "—" }} ", 15f, 0xFFFFFFFF.toInt(), bold = true).apply {
                background = EfbUi.cardBg(this@EfbHomeActivity, AviationData.categoryColor(m.category), 10)
                setPadding(dp(10), dp(3), dp(10), dp(3))
            })
            wx.addView(head)
            val j = m.json
            val parts = ArrayList<String>()
            j?.opt("wdir")?.toString()?.let { d ->
                val s = j.opt("wspd")?.toString()?.toDoubleOrNull()?.toInt() ?: 0
                val g = j.opt("wgst")?.toString()?.toDoubleOrNull()?.toInt()
                parts.add(if (s == 0) "Calm" else "${if (d == "VRB") "VRB" else "%03d°".format(d.toDoubleOrNull()?.toInt() ?: 0)} ${s}${g?.let { "G$it" } ?: ""} kt")
            }
            j?.opt("temp")?.toString()?.toDoubleOrNull()?.let { parts.add("%.0f°C".format(it)) }
            j?.opt("altim")?.toString()?.toDoubleOrNull()?.let { parts.add("%.2f\"".format(if (it > 100) it * 0.02953 else it)) }
            j?.opt("visib")?.toString()?.let { parts.add("$it sm") }
            wx.addView(EfbUi.ltr(EfbUi.text(this@EfbHomeActivity, parts.joinToString("  ·  "), 17f, EfbUi.TEXT, bold = true)).apply { setPadding(0, dp(6), 0, dp(4)) })
            wx.addView(EfbUi.ltr(EfbUi.text(this@EfbHomeActivity, m.raw, 12f, EfbUi.DIM, mono = true)))
        }
    }

    private fun askHome() {
        val input = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS
            setText(home())
        }
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.efb_home)
            .setView(FrameLayout(this).apply { setPadding(dp(20), dp(8), dp(20), 0); addView(input) })
            .setPositiveButton(R.string.ok) { _, _ ->
                input.text.toString().trim().uppercase().takeIf { it.length in 3..4 }?.let {
                    prefs.edit().putString("efb_home", if (it.length == 3) "K$it" else it).apply()
                    showWeather()
                }
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun diagram() {
        val input = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS
            setText(home())
        }
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.efb_diagram)
            .setView(FrameLayout(this).apply { setPadding(dp(20), dp(8), dp(20), 0); addView(input) })
            .setPositiveButton(R.string.ok) { _, _ ->
                val t = input.text.toString().trim().uppercase()
                lifecycleScope.launch {
                    val list = withContext(Dispatchers.IO) { AviationData.airports(this@EfbHomeActivity) }
                    val a = list.firstOrNull { it.icao == t || it.ident == t }
                        ?: list.firstOrNull { t.length == 4 && t.startsWith("K") && it.ident == t.substring(1) }
                    if (a == null) android.widget.Toast.makeText(this@EfbHomeActivity, R.string.map_not_found, android.widget.Toast.LENGTH_SHORT).show()
                    else AirportDiagramActivity.open(this@EfbHomeActivity, a)
                }
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }
}
