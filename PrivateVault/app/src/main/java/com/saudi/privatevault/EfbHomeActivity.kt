package com.saudi.privatevault

import android.content.Intent
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.graphics.drawable.toBitmap
import androidx.lifecycle.lifecycleScope
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * The flight bag's front page, laid out like a modern EFB: the clocks, the
 * home airport's weather decoded, quick actions, and every tool in a
 * grouped list (plan, fly, training, data), with a tab bar at the bottom.
 */
class EfbHomeActivity : BaseActivity() {

    private lateinit var col: LinearLayout
    private lateinit var wx: LinearLayout
    private lateinit var clock: TextView
    private val prefs get() = VaultLock.prefs(this)
    private fun dp(v: Int) = EfbUi.dp(this, v)

    private class Item(val icon: String, val color: Int, val title: Int, val sub: Int, val go: () -> Unit)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        col = EfbUi.screen(this, getString(R.string.app_name)) { bar ->
            bar.menu.add(R.string.set_title).setOnMenuItemClickListener { startActivity(Intent(this, SettingsActivity::class.java)); true }
            bar.menu.add(R.string.lang_switch).setOnMenuItemClickListener { Lang.choose(this); true }
            bar.menu.add(R.string.theme_title).setOnMenuItemClickListener { EfbUi.chooseTheme(this); true }
            bar.menu.add(R.string.qt_toggle).setOnMenuItemClickListener {
                QuickTools.setEnabled(this, !QuickTools.enabled(this)); QuickTools.attach(this); true
            }
            getDrawable(R.mipmap.ic_launcher_round)?.let { bar.logo = android.graphics.drawable.BitmapDrawable(resources, it.toBitmap(dp(30), dp(30))) }
            bar.titleMarginStart = dp(12)
        }
        CrashReport.showIfAny(this)
        Updater.checkQuietly(this)
        ChartUpdates.autoUpdate(this)

        // The header: a dusk-to-day sky with the name, and Zulu and local time large, as an EFB opens.
        val hero = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = GradientDrawable(GradientDrawable.Orientation.TL_BR, intArrayOf(0xFF0B1A33.toInt(), 0xFF153A6B.toInt(), 0xFF1F6FC4.toInt())).apply { cornerRadius = dp(18).toFloat() }
            setPadding(dp(20), dp(18), dp(20), dp(18))
            elevation = dp(4).toFloat()
        }
        hero.addView(TextView(this).apply {
            text = android.text.SpannableString("PILOT COMPANION").apply { setSpan(android.text.style.ForegroundColorSpan(0xFF8CC8FF.toInt()), 6, 15, 0) }
            textSize = 13f; letterSpacing = 0.18f; setTextColor(0xFFFFFFFF.toInt()); typeface = EfbUi.MEDIUM
        })
        clock = EfbUi.ltr(TextView(this).apply {
            textSize = 30f; setTextColor(0xFFFFFFFF.toInt()); typeface = Typeface.create("sans-serif-light", Typeface.NORMAL)
            setPadding(0, dp(6), 0, 0)
        })
        hero.addView(clock)
        hero.addView(EfbUi.ltr(TextView(this).apply {
            text = getString(R.string.home_hero_sub, home()); textSize = 13f; setTextColor(0xCCFFFFFF.toInt()); setPadding(0, dp(2), 0, 0)
        }))
        col.addView(hero, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(6); bottomMargin = dp(12) })

        // Search, the first thing on the page.
        val search = EfbUi.text(this, getString(R.string.search_hint), 16f, EfbUi.DIM).apply {
            background = EfbUi.cardBg(this@EfbHomeActivity, EfbUi.CARD, 12).apply { setStroke(0, 0) }
            setPadding(dp(16), dp(13), dp(16), dp(13))
            setCompoundDrawablesRelativeWithIntrinsicBounds(R.drawable.ic_search, 0, 0, 0)
            compoundDrawablePadding = dp(12)
            compoundDrawablesRelative[0]?.setTint(EfbUi.DIM)
        }
        col.addView(search, LinearLayout.LayoutParams(-1, -2))
        EfbUi.pressable(search) { searchAirport { a -> startActivity(Intent(this, MapActivity::class.java).putExtra(MapActivity.EXTRA_AIRPORT, a.ident)) } }

        // The home airport's weather, decoded.
        wx = EfbUi.card(this)
        col.addView(wx)
        EfbUi.pressable(wx) { askHome() }

        // Quick actions.
        val quick = android.widget.GridLayout(this).apply { columnCount = 4 }
        for ((i, q) in listOf(
            Triple(R.drawable.ic_map, R.string.efb_map) { open(MapActivity::class.java) },
            Triple(R.drawable.ic_check, R.string.ck_title) { open(ChecklistActivity::class.java) },
            Triple(R.drawable.ic_doc, R.string.log_title) { open(LogbookActivity::class.java) },
            Triple(R.drawable.ic_sos, R.string.nrst_title) { startActivity(Intent(this, MapActivity::class.java).putExtra(MapActivity.EXTRA_NRST, true)) },
            Triple(R.drawable.ic_fab_pencil, R.string.notes_title) { open(ScratchPadActivity::class.java) },
            Triple(R.drawable.ic_contents, R.string.lib_title) { open(LibraryActivity::class.java) },
            Triple(R.drawable.ic_ruler, R.string.wb_title) { open(WeightBalanceActivity::class.java) },
            Triple(R.drawable.ic_more, R.string.set_title) { open(SettingsActivity::class.java) },
        ).withIndex()) {
            val grad = when (i) {
                3 -> intArrayOf(0xFFFF6B5E.toInt(), 0xFFD62D20.toInt())
                1 -> intArrayOf(0xFF4CD97B.toInt(), 0xFF1E9E4A.toInt())
                2, 4 -> intArrayOf(0xFFFFC24D.toInt(), 0xFFE08A00.toInt())
                5 -> intArrayOf(0xFFA98BFF.toInt(), 0xFF6C47E0.toInt())
                else -> intArrayOf(0xFF4DB2FF.toInt(), 0xFF0A72E0.toInt())
            }
            val b = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                gravity = Gravity.CENTER
                background = EfbUi.cardBg(this@EfbHomeActivity, EfbUi.CARD, 14)
                setPadding(dp(4), dp(14), dp(4), dp(12))
                addView(android.widget.ImageView(this@EfbHomeActivity).apply {
                    setImageResource(q.first)
                    setColorFilter(0xFFFFFFFF.toInt())
                    setPadding(dp(10), dp(10), dp(10), dp(10))
                    background = GradientDrawable(GradientDrawable.Orientation.TL_BR, grad).apply { shape = GradientDrawable.OVAL }
                    elevation = dp(2).toFloat()
                }, LinearLayout.LayoutParams(dp(46), dp(46)))
                addView(EfbUi.text(this@EfbHomeActivity, label(q.second), 12f, EfbUi.TEXT, bold = true).apply {
                    gravity = Gravity.CENTER; maxLines = 1; ellipsize = android.text.TextUtils.TruncateAt.END; setPadding(dp(2), dp(8), dp(2), 0)
                })
            }
            EfbUi.pressable(b) { q.third() }
            quick.addView(b, android.widget.GridLayout.LayoutParams().apply {
                width = 0; columnSpec = android.widget.GridLayout.spec(android.widget.GridLayout.UNDEFINED, 1f)
                setMargins(dp(4), dp(4), dp(4), dp(4))
            })
        }
        col.addView(quick, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) })

        // Every tool, grouped as a pilot uses them.
        group(R.string.home_plan, listOf(
            Item("🧭", 0xFF2D7FF9.toInt(), R.string.plan_title, R.string.sub_plan) { startActivity(Intent(this, MapActivity::class.java).putExtra(MapActivity.EXTRA_NAVLOG, true)) },
            Item("⚖️", 0xFF8E5CF7.toInt(), R.string.wb_title, R.string.sub_wb) { open(WeightBalanceActivity::class.java) },
            Item("🧮", 0xFF00A6A6.toInt(), R.string.e6b_title, R.string.sub_e6b) { open(E6bActivity::class.java) },
            Item("📻", 0xFF34C759.toInt(), R.string.freq_title, R.string.sub_freq) { open(FrequenciesActivity::class.java) },
            Item("📈", 0xFFFF9F0A.toInt(), R.string.map_profile, R.string.sub_profile) { startActivity(Intent(this, MapActivity::class.java).putExtra(MapActivity.EXTRA_PROFILE, true)) },
        ))
        group(R.string.home_fly, listOf(
            Item("✅", 0xFF34C759.toInt(), R.string.ck_title, R.string.sub_ck) { open(ChecklistActivity::class.java) },
            Item("🛬", 0xFF2D7FF9.toInt(), R.string.efb_diagram, R.string.sub_diagram) { diagram() },
            Item("🛩", 0xFF5E5CE6.toInt(), R.string.efb_svt, R.string.sub_svt) { open(SvtActivity::class.java) },
            Item("🆘", 0xFFFF453A.toInt(), R.string.nrst_title, R.string.sub_nrst) { startActivity(Intent(this, MapActivity::class.java).putExtra(MapActivity.EXTRA_NRST, true)) },
            Item("📝", 0xFFFFB020.toInt(), R.string.notes_title, R.string.sub_notes) { startActivity(Intent(this, ScratchPadActivity::class.java)) },
        ))
        group(R.string.home_training, listOf(
            Item("📒", 0xFFFF9F0A.toInt(), R.string.log_title, R.string.sub_log) { open(LogbookActivity::class.java) },
            Item("📚", 0xFFFFB020.toInt(), R.string.log_ground_school, R.string.sub_ground) { startActivity(Intent(this, LogbookActivity::class.java).putExtra(LogbookActivity.EXTRA_TAB, 5)) },
            Item("🎓", 0xFF8E5CF7.toInt(), R.string.log_109, R.string.sub_109) { startActivity(Intent(this, LogbookActivity::class.java).putExtra(LogbookActivity.EXTRA_TAB, 2)) },
            Item("⏱", 0xFF00A6A6.toInt(), R.string.log_currency, R.string.sub_currency) { startActivity(Intent(this, LogbookActivity::class.java).putExtra(LogbookActivity.EXTRA_TAB, 3)) },
        ))
        group(R.string.home_study, listOf(
            Item("🎧", 0xFF5E5CE6.toInt(), R.string.tr_title, R.string.sub_trainer) { open(TrainerActivity::class.java) },
            Item("📚", 0xFF2D7FF9.toInt(), R.string.lib_title, R.string.sub_library) { open(LibraryActivity::class.java) },
        ))
        group(R.string.home_data, listOf(
            Item("🗂", 0xFF2D7FF9.toInt(), R.string.charts_title, R.string.sub_charts) { ChartUpdates.show(this) },
            Item("🛡", 0xFF34C759.toInt(), R.string.efbc_title, R.string.sub_efbc) { open(EfbCheckActivity::class.java) },
        ))
        col.addView(EfbUi.text(this, getString(R.string.map_disclaimer), 11f, EfbUi.DIM).apply { setPadding(dp(4), dp(18), dp(4), 0) })
        tabBar()
        EfbUi.stagger(col)
    }

    /** A title without the emoji that starts it. */
    private fun label(res: Int) = getString(res).replace(Regex("^\\S+\\s"), "")

    /** A section: its small header, then rows in one card (icon, title, what it does, ›). */
    private fun group(title: Int, items: List<Item>) {
        col.addView(EfbUi.section(this, getString(title)))
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = EfbUi.cardBg(this@EfbHomeActivity, EfbUi.CARD, 16).apply { setStroke(0, 0) }
        }
        for ((i, it) in items.withIndex()) {
            if (i > 0) card.addView(View(this).apply { setBackgroundColor(EfbUi.CARD_LINE) },
                LinearLayout.LayoutParams(-1, 1).apply { marginStart = dp(62) })
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(14), dp(11), dp(12), dp(11))
            }
            row.addView(EfbUi.text(this, it.icon, 18f).apply {
                gravity = Gravity.CENTER
                background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor((it.color and 0x00FFFFFF) or 0x2E000000); setStroke(dp(1), (it.color and 0x00FFFFFF) or 0x66000000) }
            }, LinearLayout.LayoutParams(dp(40), dp(40)))
            val texts = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(12), 0, dp(8), 0) }
            texts.addView(EfbUi.text(this, label(it.title), 16f, EfbUi.TEXT).apply { setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL)) })
            texts.addView(EfbUi.text(this, getString(it.sub), 12.5f, EfbUi.DIM).apply { maxLines = 1; ellipsize = android.text.TextUtils.TruncateAt.END })
            row.addView(texts, LinearLayout.LayoutParams(0, -2, 1f))
            row.addView(EfbUi.text(this, "›", 24f, EfbUi.ACCENT).apply { scaleX = if (isRtl()) -1f else 1f })
            row.setBackgroundResource(R.drawable.item_focus_bg)
            val go = it.go
            row.setOnClickListener { go() }
            card.addView(row)
        }
        col.addView(card)
    }

    private fun isRtl() = resources.configuration.layoutDirection == View.LAYOUT_DIRECTION_RTL

    /** The tab bar at the bottom, as an EFB's: home, map, airports, logbook, scratch pad, more. */
    private fun tabBar() {
        val scroll = col.parent as? View ?: return
        val root = scroll.parent as? LinearLayout ?: return
        root.addView(View(this).apply { setBackgroundColor(EfbUi.CARD_LINE) }, LinearLayout.LayoutParams(-1, 1))
        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(EfbUi.BAR)
            setPadding(dp(4), dp(6), dp(4), dp(8))
        }
        for ((i, t) in listOf(
            Triple(R.drawable.ic_compass, R.string.home_tab_home) { },
            Triple(R.drawable.ic_map, R.string.efb_map) { open(MapActivity::class.java) },
            Triple(R.drawable.ic_search, R.string.home_tab_airports) { searchAirport { a -> startActivity(Intent(this, MapActivity::class.java).putExtra(MapActivity.EXTRA_AIRPORT, a.ident)) } },
            Triple(R.drawable.ic_doc, R.string.log_title) { open(LogbookActivity::class.java) },
            Triple(R.drawable.ic_fab_pencil, R.string.notes_title) { open(ScratchPadActivity::class.java) },
            Triple(R.drawable.ic_more, R.string.set_title) { open(SettingsActivity::class.java) },
        ).withIndex()) {
            val on = i == 0
            val color = if (on) EfbUi.ACCENT else EfbUi.DIM
            val cell = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                gravity = Gravity.CENTER_HORIZONTAL
                // The tab in use: its icon on a soft pill, as Material and the EFBs mark it.
                addView(android.widget.ImageView(this@EfbHomeActivity).apply {
                    setImageResource(t.first); setColorFilter(color)
                    setPadding(dp(16), dp(4), dp(16), dp(4))
                    if (on) background = GradientDrawable().apply { cornerRadius = dp(16).toFloat(); setColor((EfbUi.ACCENT and 0x00FFFFFF) or 0x2E000000) }
                }, LinearLayout.LayoutParams(dp(58), dp(30)))
                addView(EfbUi.text(this@EfbHomeActivity, label(t.second), 11f, color, bold = on).apply {
                    gravity = Gravity.CENTER; maxLines = 1; ellipsize = android.text.TextUtils.TruncateAt.END; setPadding(dp(2), dp(3), dp(2), 0)
                }, LinearLayout.LayoutParams(-1, -2))
                setOnClickListener { t.third() }
            }
            bar.addView(cell, LinearLayout.LayoutParams(0, -2, 1f))
        }
        root.addView(bar)
    }

    private val tick = object : Runnable {
        override fun run() {
            val now = Date()
            val z = SimpleDateFormat("HH:mm", Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") }.format(now)
            val l = SimpleDateFormat("HH:mm", Locale.US).format(now)
            val d = SimpleDateFormat("EEE d MMM", Locale.US).format(now)
            clock.text = android.text.SpannableStringBuilder().apply {
                append("${z}Z")
                setSpan(android.text.style.StyleSpan(Typeface.BOLD), 0, length, 0)
                val from = length
                append("   $l LCL  ·  $d")
                setSpan(android.text.style.RelativeSizeSpan(0.55f), from, length, 0)
            }
            clock.postDelayed(this, 15000)
        }
    }

    override fun onResume() {
        super.onResume()
        clock.removeCallbacks(tick)
        tick.run()
        showWeather()
    }

    override fun onPause() {
        super.onPause()
        clock.removeCallbacks(tick)
    }

    private fun home() = prefs.getString("efb_home", "KBVU")!!

    private fun open(c: Class<*>) = startActivity(Intent(this, c))

    /** One labelled value of the weather. */
    private fun cell(parent: LinearLayout, label: String, value: String, color: Int = EfbUi.TEXT) {
        val c = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        c.addView(EfbUi.text(this, label, 11f, EfbUi.DIM).apply { letterSpacing = 0.06f })
        c.addView(EfbUi.ltr(EfbUi.text(this, value, 17f, color, bold = true)).apply { maxLines = 1 })
        parent.addView(c, LinearLayout.LayoutParams(0, -2, 1f))
    }

    private fun showWeather() {
        val station = home()
        wx.removeAllViews()
        wx.addView(EfbUi.text(this, station, 24f, EfbUi.TEXT, bold = true))
        val line = EfbUi.ltr(EfbUi.text(this, getString(R.string.map_loading_wx), 14f, EfbUi.DIM, mono = true))
        wx.addView(line)
        lifecycleScope.launch {
            val m = withContext(Dispatchers.IO) { AviationData.metar(station) }
            if (m == null) {
                line.text = getString(R.string.map_no_metar)
                return@launch
            }
            wx.removeAllViews()
            // The card edged in the flight category's colour.
            wx.background = EfbUi.cardBg(this@EfbHomeActivity, EfbUi.CARD, 14).apply { setStroke(dp(2), AviationData.categoryColor(m.category)) }
            val j = m.json
            val head = LinearLayout(this@EfbHomeActivity).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
            val names = LinearLayout(this@EfbHomeActivity).apply { orientation = LinearLayout.VERTICAL }
            names.addView(EfbUi.text(this@EfbHomeActivity, station, 24f, EfbUi.TEXT, bold = true))
            val age = ((System.currentTimeMillis() / 1000 - m.time) / 60).takeIf { m.time > 0 }
            names.addView(EfbUi.text(this@EfbHomeActivity, (j?.optString("name")?.takeIf { it.isNotEmpty() && it != "null" } ?: "METAR") +
                (age?.let { "  ·  ${it} min" } ?: ""), 12f, EfbUi.DIM).apply { maxLines = 1; ellipsize = android.text.TextUtils.TruncateAt.END })
            head.addView(names, LinearLayout.LayoutParams(0, -2, 1f))
            head.addView(EfbUi.text(this@EfbHomeActivity, m.category.ifEmpty { "—" }, 14f, 0xFFFFFFFF.toInt(), bold = true).apply {
                background = EfbUi.cardBg(this@EfbHomeActivity, AviationData.categoryColor(m.category), 8).apply { setStroke(0, 0) }
                setPadding(dp(12), dp(4), dp(12), dp(4))
            })
            wx.addView(head)

            val g1 = LinearLayout(this@EfbHomeActivity).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(12), 0, 0) }
            val g2 = LinearLayout(this@EfbHomeActivity).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(10), 0, dp(8)) }
            val spd = j?.opt("wspd")?.toString()?.toDoubleOrNull()?.toInt() ?: 0
            val gust = j?.opt("wgst")?.toString()?.toDoubleOrNull()?.toInt()
            val dir = j?.opt("wdir")?.toString()
            val wind = if (spd == 0) "Calm" else "${if (dir == "VRB") "VRB" else "%03d°".format(dir?.toDoubleOrNull()?.toInt() ?: 0)} ${spd}${gust?.let { "G$it" } ?: ""}"
            cell(g1, "WIND", wind, if (spd >= 16 || (gust ?: 0) >= 20) EfbUi.WARN else EfbUi.TEXT)
            cell(g1, "VIS", (j?.opt("visib")?.toString() ?: "—") + " sm")
            val clouds = j?.optJSONArray("clouds")
            val ceiling = (0 until (clouds?.length() ?: 0)).mapNotNull { clouds!!.optJSONObject(it) }
                .firstOrNull { it.optString("cover") in setOf("BKN", "OVC", "OVX") }
            cell(g1, "CEILING", ceiling?.let { "${it.optString("cover")} ${it.optInt("base")}" } ?: "None")
            val altim = j?.opt("altim")?.toString()?.toDoubleOrNull()
            cell(g2, "ALTIMETER", altim?.let { "%.2f\"".format(if (it > 100) it * 0.02953 else it) } ?: "—")
            val t = j?.opt("temp")?.toString()?.toDoubleOrNull()
            val dp2 = j?.opt("dewp")?.toString()?.toDoubleOrNull()
            cell(g2, "TEMP / DEW", "${t?.let { "%.0f".format(it) } ?: "—"}° / ${dp2?.let { "%.0f".format(it) } ?: "—"}°")
            // Density altitude, from the field elevation, the altimeter and the temperature.
            val elevFt = j?.opt("elev")?.toString()?.toDoubleOrNull()?.times(3.28084)
            val da = if (elevFt != null && altim != null && t != null) {
                val hpa = if (altim > 100) altim else altim * 33.8639
                val pa = elevFt + (1013.25 - hpa) * 30
                Math.round(pa + 120 * (t - (15 - 2 * pa / 1000))).toInt()
            } else null
            cell(g2, "DENSITY ALT", da?.let { "%,d ft".format(it) } ?: "—", if ((da ?: 0) >= 6000) EfbUi.WARN else EfbUi.TEXT)
            wx.addView(g1)
            wx.addView(g2)
            wx.addView(EfbUi.ltr(EfbUi.text(this@EfbHomeActivity, m.raw, 11.5f, EfbUi.DIM, mono = true)))
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

    private fun searchAirport(onPick: (AviationData.Airport) -> Unit) {
        lifecycleScope.launch {
            val list = withContext(Dispatchers.IO) { AviationData.airports(this@EfbHomeActivity) }
            AirportSearch.show(this@EfbHomeActivity, list, null, onPick)
        }
    }

    private fun diagram() = searchAirport { a -> AirportDiagramActivity.open(this, a) }
}
