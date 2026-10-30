package com.saudi.privatevault

import android.content.Intent
import android.os.Bundle
import android.view.Gravity
import android.widget.EditText
import android.widget.LinearLayout
import com.google.android.material.button.MaterialButton
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.tabs.TabLayout
import org.json.JSONObject
import java.util.Calendar

/**
 * The logbook: every flight with its times and landings, the private pilot
 * requirements of 14 CFR 61.109(a) filled in from it, and what keeps the
 * pilot current (61.56, 61.57, the medical, the student solo endorsement).
 */
class LogbookActivity : BaseActivity() {

    private lateinit var col: LinearLayout
    private lateinit var body: LinearLayout
    private var entries = mutableListOf<LogEntry>()
    private val prefs get() = VaultLock.prefs(this)
    private fun dp(v: Int) = EfbUi.dp(this, v)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        col = EfbUi.screen(this, getString(R.string.log_title)) { bar ->
            bar.menu.add(R.string.log_export).setOnMenuItemClickListener { export(); true }
        }
        val tabs = TabLayout(this).apply {
            setBackgroundColor(EfbUi.BG)
            setTabTextColors(EfbUi.DIM, EfbUi.ACCENT)
            setSelectedTabIndicatorColor(EfbUi.ACCENT)
            addTab(newTab().setText(R.string.log_flights))
            addTab(newTab().setText(R.string.log_109))
            addTab(newTab().setText(R.string.log_currency))
        }
        col.addView(tabs)
        body = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        col.addView(body)
        entries = Logbook.all(this)
        tabs.addOnTabSelectedListener(object : TabLayout.OnTabSelectedListener {
            override fun onTabSelected(t: TabLayout.Tab) = show(t.position)
            override fun onTabUnselected(t: TabLayout.Tab) {}
            override fun onTabReselected(t: TabLayout.Tab) {}
        })
        val start = intent.getIntExtra(EXTRA_TAB, 0)
        intent.getStringExtra(EXTRA_NEW)?.let { edit(LogEntry.fromJson(JSONObject(it)), isNew = true); return }
        if (start == 0) show(0) else tabs.getTabAt(start)?.select()
    }

    private fun show(tab: Int) {
        body.removeAllViews()
        when (tab) {
            0 -> flights()
            1 -> requirements()
            else -> currency()
        }
        EfbUi.stagger(body)
    }

    // ---- flights ----

    private fun flights() {
        val sum = EfbUi.card(this)
        val total = entries.sumOf { it.total }
        val month = entries.filter { System.currentTimeMillis() - it.dateMillis() < 30L * 86400000 }.sumOf { it.total }
        sum.addView(EfbUi.text(this, "%.1f h".format(total), 32f, EfbUi.ACCENT, bold = true))
        sum.addView(EfbUi.ltr(EfbUi.text(this,
            "Dual %.1f · Solo %.1f · XC %.1f · Night %.1f\nLandings %d · Last 30 days %.1f h".format(
                entries.sumOf { it.dual }, entries.sumOf { it.solo }, entries.sumOf { it.xc }, entries.sumOf { it.night },
                entries.sumOf { it.dayLdg + it.nightLdg }, month,
            ), 13f, EfbUi.DIM, mono = true)))
        body.addView(sum)
        if (FlightRecorder.inProgress(this)) {
            val rec = EfbUi.card(this).apply { background = EfbUi.cardBg(this@LogbookActivity, 0xFF0D3B2E.toInt()) }
            rec.addView(EfbUi.text(this, "● " + getString(R.string.log_recording), 15f, EfbUi.GOOD, bold = true))
            rec.addView(EfbUi.ltr(EfbUi.text(this, FlightRecorder.summary(this), 13f, EfbUi.TEXT, mono = true)))
            rec.addView(MaterialButton(this).apply {
                text = getString(R.string.log_finish)
                setOnClickListener { FlightRecorder.finishNow(this@LogbookActivity)?.let { edit(it, isNew = true) } }
            })
            body.addView(rec)
        }
        body.addView(MaterialButton(this).apply {
            text = getString(R.string.log_add)
            setOnClickListener { edit(LogEntry(aircraft = prefs.getString("log_last_ac", "SportStar")!!), isNew = true) }
        }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) })
        if (entries.isEmpty()) body.addView(EfbUi.text(this, getString(R.string.log_empty), 14f, EfbUi.DIM).apply { setPadding(dp(4), dp(16), dp(4), 0) })
        for (e in entries) {
            val c = EfbUi.card(this)
            val head = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutDirection = android.view.View.LAYOUT_DIRECTION_LTR }
            head.addView(EfbUi.text(this, "${e.from} → ${e.to}", 17f, EfbUi.TEXT, bold = true), LinearLayout.LayoutParams(0, -2, 1f))
            head.addView(EfbUi.text(this, "%.1f".format(e.total), 17f, EfbUi.ACCENT, bold = true, mono = true))
            c.addView(head)
            val tags = listOfNotNull(
                e.date, e.aircraft.ifEmpty { null },
                if (e.dual > 0) "Dual" else null, if (e.solo > 0) "Solo" else null, if (e.xc > 0) "XC" else null,
                if (e.night > 0) "Night" else null, if (e.dayLdg + e.nightLdg > 0) "${e.dayLdg + e.nightLdg} ldg" else null,
            )
            c.addView(EfbUi.ltr(EfbUi.text(this, tags.joinToString("  ·  "), 12f, EfbUi.DIM)))
            if (e.remarks.isNotEmpty()) c.addView(EfbUi.text(this, e.remarks, 12f, EfbUi.DIM))
            EfbUi.pressable(c) { edit(e, isNew = false) }
            body.addView(c)
        }
    }

    private fun edit(e: LogEntry, isNew: Boolean) {
        body.removeAllViews()
        val c = EfbUi.card(this)
        body.addView(c)
        c.addView(EfbUi.text(this, getString(if (isNew) R.string.log_add else R.string.log_edit), 18f, EfbUi.ACCENT, bold = true))
        fun f(label: String, v: Any, number: Boolean = true): EditText =
            EfbUi.field(this, c, label, if (v is Double) (if (v == 0.0) "" else EfbUi.num(v)) else if (v is Int) (if (v == 0) "" else v.toString()) else v.toString(), number)
        val date = f("Date (yyyy-mm-dd)", e.date, false)
        val ac = f("Aircraft", e.aircraft, false)
        val from = f("From", e.from, false)
        val to = f("To", e.to, false)
        val route = f("Route / stops", e.route, false)
        val total = f("Total time", e.total)
        val dual = f("Dual received", e.dual)
        val solo = f("Solo", e.solo)
        val pic = f("PIC", e.pic)
        val xc = f("Cross-country", e.xc)
        val night = f("Night", e.night)
        val inst = f("Instrument (hood)", e.instrument)
        val dl = f("Day landings", e.dayLdg)
        val nl = f("Night landings (full stop)", e.nightLdg)
        val tl = f("Towered landings (full stop)", e.toweredLdg)
        val far = f("Farthest from departure (nm)", e.farthestNm)
        val dist = f("Total distance (nm)", e.distanceNm)
        val rem = f("Remarks", e.remarks, false)
        val quick = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        fun quickButton(label: String, onClick: () -> Unit) = quick.addView(MaterialButton(this, null, com.google.android.material.R.attr.materialButtonOutlinedStyle).apply {
            text = label
            isAllCaps = false
            setOnClickListener { onClick() }
        }, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(6) })
        // One tap fills the column from the total time.
        quickButton("Dual") { dual.setText(total.text) }
        quickButton("Solo") { solo.setText(total.text); pic.setText(total.text) }
        quickButton("XC") { xc.setText(total.text) }
        c.addView(quick)
        val buttons = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.END; setPadding(0, dp(12), 0, 0) }
        if (!isNew) buttons.addView(MaterialButton(this, null, com.google.android.material.R.attr.borderlessButtonStyle).apply {
            text = getString(R.string.delete)
            setTextColor(EfbUi.BAD)
            setOnClickListener {
                MaterialAlertDialogBuilder(this@LogbookActivity).setMessage(R.string.log_delete_q)
                    .setPositiveButton(R.string.delete) { _, _ -> entries.removeAll { it.id == e.id }; Logbook.save(this@LogbookActivity, entries); show(0) }
                    .setNegativeButton(R.string.cancel, null).show()
            }
        })
        buttons.addView(MaterialButton(this, null, com.google.android.material.R.attr.borderlessButtonStyle).apply {
            text = getString(R.string.cancel)
            setOnClickListener { show(0) }
        })
        buttons.addView(MaterialButton(this).apply {
            text = getString(R.string.log_save)
            setOnClickListener {
                fun d(x: EditText) = x.text.toString().toDoubleOrNull() ?: 0.0
                fun i(x: EditText) = x.text.toString().toIntOrNull() ?: 0
                e.date = date.text.toString().trim().ifEmpty { LogEntry.today() }
                e.aircraft = ac.text.toString().trim(); e.from = from.text.toString().trim().uppercase(); e.to = to.text.toString().trim().uppercase()
                e.route = route.text.toString().trim().uppercase()
                e.total = d(total); e.dual = d(dual); e.solo = d(solo); e.pic = d(pic); e.xc = d(xc); e.night = d(night); e.instrument = d(inst)
                e.dayLdg = i(dl); e.nightLdg = i(nl); e.toweredLdg = i(tl); e.farthestNm = d(far); e.distanceNm = d(dist)
                e.remarks = rem.text.toString().trim()
                entries.removeAll { it.id == e.id }
                entries.add(e)
                entries.sortByDescending { it.date }
                Logbook.save(this@LogbookActivity, entries)
                prefs.edit().putString("log_last_ac", e.aircraft).apply()
                show(0)
            }
        })
        c.addView(buttons)
        EfbUi.stagger(body)
    }

    // ---- 61.109(a): private pilot, airplane single-engine land ----

    private fun requirements() {
        val e = entries
        fun card(title: String): LinearLayout = EfbUi.card(this).also {
            it.addView(EfbUi.text(this, title, 16f, EfbUi.ACCENT, bold = true))
            body.addView(it)
        }
        val total = e.sumOf { it.total }
        val dual = e.sumOf { it.dual }
        val solo = e.sumOf { it.solo }
        val head = card("61.109(a) · Private Pilot ASEL")
        EfbUi.progress(this, head, "Total flight time", total, 40.0, "h")
        val d = card(getString(R.string.log_dual_part))
        EfbUi.progress(this, d, "Dual instruction", dual, 20.0, "h")
        EfbUi.progress(this, d, "Dual cross-country", e.sumOf { minOf(it.dual, it.xc) }, 3.0, "h")
        EfbUi.progress(this, d, "Dual night", e.sumOf { minOf(it.dual, it.night) }, 3.0, "h")
        EfbUi.progress(this, d, "Night XC over 100 nm total", if (e.any { it.night > 0 && it.dual > 0 && it.distanceNm > 100 }) 1.0 else 0.0, 1.0, "")
        EfbUi.progress(this, d, "Night takeoffs & full-stop landings", e.sumOf { it.nightLdg }.toDouble(), 10.0, "")
        EfbUi.progress(this, d, "Instrument (hood)", e.sumOf { it.instrument }, 3.0, "h")
        EfbUi.progress(this, d, "Checkride prep, last 2 calendar months", e.filter { inLastCalendarMonths(it, 2) }.sumOf { it.dual }, 3.0, "h")
        val s = card(getString(R.string.log_solo_part))
        EfbUi.progress(this, s, "Solo", solo, 10.0, "h")
        EfbUi.progress(this, s, "Solo cross-country", e.sumOf { minOf(it.solo, it.xc) }, 5.0, "h")
        EfbUi.progress(this, s, "Solo XC 150 nm, 3 stops, one leg > 50 nm",
            if (e.any { it.solo > 0 && it.distanceNm >= 150 && it.farthestNm > 50 && it.route.split(' ').filter { r -> r.isNotBlank() }.size >= 3 }) 1.0 else 0.0, 1.0, "")
        EfbUi.progress(this, s, "Solo full-stop landings at a towered airport", e.filter { it.solo > 0 }.sumOf { it.toweredLdg }.toDouble(), 3.0, "")
        body.addView(EfbUi.text(this, getString(R.string.log_109_note), 11f, EfbUi.DIM).apply { setPadding(dp(4), dp(14), dp(4), 0) })
    }

    private fun inLastCalendarMonths(e: LogEntry, months: Int): Boolean {
        val c = Calendar.getInstance()
        c.add(Calendar.MONTH, -months)
        c.set(Calendar.DAY_OF_MONTH, 1)
        return e.dateMillis() >= c.timeInMillis
    }

    // ---- currency ----

    private fun currency() {
        val day90 = System.currentTimeMillis() - 90L * 86400000
        val recent = entries.filter { it.dateMillis() >= day90 }
        val c = EfbUi.card(this)
        body.addView(c)
        c.addView(EfbUi.text(this, getString(R.string.log_currency), 16f, EfbUi.ACCENT, bold = true))
        fun line(label: String, ok: Boolean, detail: String) {
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(0, dp(10), 0, 0) }
            row.addView(EfbUi.text(this, if (ok) "✅" else "⛔", 18f), LinearLayout.LayoutParams(dp(34), -2))
            row.addView(LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                addView(EfbUi.text(this@LogbookActivity, label, 15f, if (ok) EfbUi.TEXT else EfbUi.BAD, bold = true))
                addView(EfbUi.text(this@LogbookActivity, detail, 12f, EfbUi.DIM))
            })
            c.addView(row)
        }
        val day = recent.sumOf { it.dayLdg + it.nightLdg }
        val night = recent.sumOf { it.nightLdg }
        line(getString(R.string.cur_day), day >= 3, "61.57(a) · $day / 3 in 90 days")
        line(getString(R.string.cur_night), night >= 3, "61.57(b) · $night / 3 in 90 days")
        fun dated(key: String, label: String, rule: String, months: Int, days: Int) {
            val v = prefs.getString(key, "") ?: ""
            val t = try { LogEntry.FMT.parse(v)?.time } catch (e: Exception) { null }
            if (t == null) { line(label, false, "$rule · ${getString(R.string.cur_set)}"); return }
            val cal = Calendar.getInstance().apply { timeInMillis = t }
            if (months > 0) { cal.add(Calendar.MONTH, months + 1); cal.set(Calendar.DAY_OF_MONTH, 1); cal.add(Calendar.DAY_OF_MONTH, -1) }
            else cal.add(Calendar.DAY_OF_MONTH, days)
            val left = (cal.timeInMillis - System.currentTimeMillis()) / 86400000
            line(label, left >= 0, "$rule · ${LogEntry.FMT.format(cal.time)} · " + if (left >= 0) "$left days left" else "expired")
        }
        dated("cur_review", getString(R.string.cur_review), "61.56 · 24 calendar months", 24, 0)
        dated("cur_solo", getString(R.string.cur_solo), "61.87(n) · 90 days", 0, 90)
        dated("cur_medical", getString(R.string.cur_medical), getString(R.string.cur_medical_rule), 0, 0)
        val edit = EfbUi.card(this)
        body.addView(edit)
        edit.addView(EfbUi.text(this, getString(R.string.cur_dates), 15f, EfbUi.ACCENT, bold = true))
        for ((key, label) in listOf("cur_review" to R.string.cur_review, "cur_solo" to R.string.cur_solo, "cur_medical" to R.string.cur_medical_date)) {
            EfbUi.field(this, edit, getString(label), prefs.getString(key, "") ?: "", number = false) { v ->
                prefs.edit().putString(key, v.trim()).apply()
            }
        }
        edit.addView(MaterialButton(this).apply {
            text = getString(R.string.ok)
            setOnClickListener { show(2) }
        })
    }

    private fun export() {
        startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply {
            type = "text/csv"
            putExtra(Intent.EXTRA_SUBJECT, "Logbook.csv")
            putExtra(Intent.EXTRA_TEXT, Logbook.csv(entries))
        }, null))
    }

    companion object {
        const val EXTRA_TAB = "tab"
        const val EXTRA_NEW = "new"
    }
}
