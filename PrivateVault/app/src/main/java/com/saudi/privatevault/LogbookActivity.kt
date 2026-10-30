package com.saudi.privatevault

import android.content.Intent
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Paint
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.widget.EditText
import android.widget.HorizontalScrollView
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.FileProvider
import androidx.lifecycle.lifecycleScope
import com.google.android.material.button.MaterialButton
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.tabs.TabLayout
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.util.Calendar

/**
 * The pilot logbook: every flight with the columns of a paper logbook,
 * signed by the instructor on the phone; totals by period, aircraft and
 * month with the 8710-1 figures for the checkride; the 61.109(a) private
 * pilot requirements; currency; and the instructor's endorsements. It
 * prints as a proper logbook PDF and backs up to a single file.
 */
class LogbookActivity : BaseActivity() {

    private lateinit var col: LinearLayout
    private lateinit var body: LinearLayout
    private lateinit var tabs: TabLayout
    private var entries = mutableListOf<LogEntry>()
    private var endorsements = mutableListOf<Endorsement>()
    private var query = ""
    private val prefs get() = VaultLock.prefs(this)
    private fun dp(v: Int) = EfbUi.dp(this, v)

    private val restorePicker = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        uri ?: return@registerForActivityResult
        try {
            val text = contentResolver.openInputStream(uri)!!.bufferedReader().readText()
            val n = Logbook.restore(this, text)
            entries = Logbook.all(this)
            endorsements = Logbook.endorsements(this)
            Toast.makeText(this, getString(R.string.log_restored, n), Toast.LENGTH_LONG).show()
            show(1)
        } catch (e: Exception) {
            Toast.makeText(this, R.string.log_restore_bad, Toast.LENGTH_LONG).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        col = EfbUi.screen(this, getString(R.string.log_title)) { bar ->
            bar.menu.add(R.string.log_sync_now).setOnMenuItemClickListener { syncNow(loud = true); true }
            bar.menu.add(R.string.log_pdf).setOnMenuItemClickListener { exportPdf(); true }
            bar.menu.add(R.string.log_export).setOnMenuItemClickListener { exportCsv(); true }
            bar.menu.add(R.string.log_backup).setOnMenuItemClickListener { backup(); true }
            bar.menu.add(R.string.log_restore).setOnMenuItemClickListener { restorePicker.launch(arrayOf("*/*")); true }
        }
        tabs = TabLayout(this).apply {
            setBackgroundColor(EfbUi.BG)
            setTabTextColors(EfbUi.DIM, EfbUi.ACCENT)
            setSelectedTabIndicatorColor(EfbUi.ACCENT)
            tabMode = TabLayout.MODE_SCROLLABLE
            addTab(newTab().setText(R.string.log_flights))
            addTab(newTab().setText(R.string.log_totals))
            addTab(newTab().setText(R.string.log_checkride))
            addTab(newTab().setText(R.string.log_currency))
            addTab(newTab().setText(R.string.log_endorsements))
        }
        col.addView(tabs)
        body = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        col.addView(body)
        entries = Logbook.all(this)
        endorsements = Logbook.endorsements(this)
        tabs.addOnTabSelectedListener(object : TabLayout.OnTabSelectedListener {
            override fun onTabSelected(t: TabLayout.Tab) = show(t.position)
            override fun onTabUnselected(t: TabLayout.Tab) {}
            override fun onTabReselected(t: TabLayout.Tab) = show(t.position)
        })
        intent.getStringExtra(EXTRA_NEW)?.let { edit(LogEntry.fromJson(JSONObject(it)), isNew = true); return }
        val start = intent.getIntExtra(EXTRA_TAB, 0)
        if (start == 0) show(0) else tabs.getTabAt(start)?.select()
    }

    override fun onResume() {
        super.onResume()
        // The same logbook on every device linked to the vault.
        if (::tabs.isInitialized) syncNow(loud = false)
    }

    /** Sends this device's logbook and takes what is newer elsewhere; [loud] says what happened either way. */
    private fun syncNow(loud: Boolean) {
        if (!LaptopClient.isLinked(this)) {
            if (loud) Toast.makeText(this, R.string.log_sync_unlinked, Toast.LENGTH_LONG).show()
            return
        }
        lifecycleScope.launch {
            val n = withContext(Dispatchers.IO) { try { LogbookSync.sync(this@LogbookActivity) } catch (e: Exception) { LogbookSync.lastError = e.message; -1 } }
            if (n > 0) {
                entries = Logbook.all(this@LogbookActivity)
                endorsements = Logbook.endorsements(this@LogbookActivity)
                show(tabs.selectedTabPosition.coerceAtLeast(0))
            }
            when {
                n > 0 -> Toast.makeText(this@LogbookActivity, getString(R.string.log_synced, n), Toast.LENGTH_SHORT).show()
                loud && n == 0 -> Toast.makeText(this@LogbookActivity, getString(R.string.log_sync_same, LogbookSync.lastSent), Toast.LENGTH_LONG).show()
                loud -> Toast.makeText(this@LogbookActivity, getString(R.string.log_sync_failed, LogbookSync.lastError ?: "?"), Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun show(tab: Int) {
        body.removeAllViews()
        when (tab) {
            0 -> flights()
            1 -> totals()
            2 -> checkrideTab()
            3 -> currency()
            else -> endorsementsTab()
        }
        EfbUi.stagger(body)
    }

    private fun header(text: String) = EfbUi.text(this, text, 13f, EfbUi.ACCENT, bold = true).apply { setPadding(dp(4), dp(18), dp(4), dp(2)) }

    private fun button(text: String, outlined: Boolean = false, onClick: () -> Unit) =
        (if (outlined) MaterialButton(this, null, com.google.android.material.R.attr.materialButtonOutlinedStyle) else MaterialButton(this)).apply {
            this.text = text
            isAllCaps = false
            setOnClickListener { onClick() }
        }

    // ---- flights ----

    private fun flights() {
        if (FlightRecorder.inProgress(this)) {
            val rec = EfbUi.card(this).apply { background = EfbUi.cardBg(this@LogbookActivity, 0xFF0D3B2E.toInt()) }
            rec.addView(EfbUi.text(this, "● " + getString(R.string.log_recording), 15f, EfbUi.GOOD, bold = true))
            rec.addView(EfbUi.ltr(EfbUi.text(this, FlightRecorder.summary(this), 13f, EfbUi.TEXT, mono = true)))
            rec.addView(button(getString(R.string.log_finish)) { FlightRecorder.finishNow(this)?.let { edit(it, isNew = true) } })
            body.addView(rec)
        }
        val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(0, dp(10), 0, 0) }
        val search = EditText(this).apply {
            hint = getString(R.string.log_search)
            setText(query)
            setTextColor(EfbUi.TEXT)
            setHintTextColor(EfbUi.DIM)
            setSingleLine()
            background = EfbUi.cardBg(this@LogbookActivity, EfbUi.CARD, 14)
            setPadding(dp(14), dp(10), dp(14), dp(10))
        }
        top.addView(search, LinearLayout.LayoutParams(0, -2, 1f))
        top.addView(button("➕", outlined = false) { edit(newEntry(), isNew = true) }, LinearLayout.LayoutParams(-2, -2).apply { marginStart = dp(8) })
        body.addView(top)
        val list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        body.addView(list)
        fun fill() {
            list.removeAllViews()
            val q = query.trim().uppercase()
            val shown = if (q.isEmpty()) entries else entries.filter { e ->
                listOf(e.date, e.aircraft, e.tail, e.from, e.to, e.route, e.remarks, e.instructor).any { it.uppercase().contains(q) }
            }
            if (shown.isEmpty()) {
                list.addView(EfbUi.text(this, getString(if (entries.isEmpty()) R.string.log_empty else R.string.empty_search), 14f, EfbUi.DIM).apply { setPadding(dp(4), dp(16), dp(4), 0) })
                return
            }
            var month = ""
            for (e in shown) {
                val m = e.date.take(7)
                if (m != month) {
                    month = m
                    val hours = shown.filter { it.date.startsWith(m) }.sumOf { it.total }
                    list.addView(header("${monthName(m)}  ·  %.1f h".format(hours)))
                }
                list.addView(flightCard(e))
            }
        }
        search.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            override fun afterTextChanged(s: Editable?) { query = s.toString(); fill() }
        })
        fill()
    }

    private fun monthName(ym: String): String = try {
        val c = Calendar.getInstance().apply { time = LogEntry.FMT.parse("$ym-01")!! }
        java.text.SimpleDateFormat("MMMM yyyy", resources.configuration.locales[0]).format(c.time)
    } catch (e: Exception) { ym }

    private fun flightCard(e: LogEntry): View {
        val c = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = EfbUi.cardBg(this@LogbookActivity)
            setPadding(dp(12), dp(12), dp(14), dp(12))
            layoutDirection = View.LAYOUT_DIRECTION_LTR
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8) }
        }
        c.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            background = EfbUi.cardBg(this@LogbookActivity, 0xFF0F1A2E.toInt(), 12)
            setPadding(dp(8), dp(6), dp(8), dp(6))
            addView(EfbUi.text(this@LogbookActivity, e.date.takeLast(2), 20f, EfbUi.TEXT, bold = true).apply { gravity = Gravity.CENTER })
            addView(EfbUi.text(this@LogbookActivity, monthName(e.date.take(7)).take(3).uppercase(), 10f, EfbUi.DIM).apply { gravity = Gravity.CENTER })
        }, LinearLayout.LayoutParams(dp(54), -2))
        val mid = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(12), 0, dp(8), 0) }
        mid.addView(EfbUi.text(this, "${e.from.ifEmpty { "—" }} → ${e.to.ifEmpty { "—" }}", 17f, EfbUi.TEXT, bold = true))
        mid.addView(EfbUi.text(this, listOf(e.aircraft, e.tail, listOf(e.timeOut, e.timeIn).filter { it.isNotEmpty() }.joinToString("–")).filter { it.isNotEmpty() }.joinToString("  ·  "), 12f, EfbUi.DIM))
        val tags = listOfNotNull(
            if (e.dual > 0) "DUAL" else null, if (e.solo > 0) "SOLO" else null, if (e.xc > 0) "XC" else null,
            if (e.night > 0) "NIGHT" else null, if (e.instrument + e.actual > 0) "INST" else null,
            if (e.dayLdg + e.nightLdg > 0) "${e.dayLdg + e.nightLdg} LDG" else null,
        )
        if (tags.isNotEmpty()) mid.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, dp(5), 0, 0)
            for (t in tags) addView(EfbUi.text(this@LogbookActivity, t, 10f, EfbUi.ACCENT, bold = true).apply {
                background = EfbUi.cardBg(this@LogbookActivity, 0xFF0F2A3A.toInt(), 8)
                setPadding(dp(6), dp(2), dp(6), dp(2))
            }, LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(5) })
        })
        c.addView(mid, LinearLayout.LayoutParams(0, -2, 1f))
        c.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.END
            addView(EfbUi.text(this@LogbookActivity, "%.1f".format(e.total), 22f, EfbUi.ACCENT, bold = true, mono = true).apply { gravity = Gravity.END })
            if (e.signed) addView(EfbUi.text(this@LogbookActivity, "✍️ CFI", 11f, EfbUi.GOOD, bold = true).apply { gravity = Gravity.END })
        })
        EfbUi.pressable(c) { edit(e, isNew = false) }
        return c
    }

    private fun newEntry(): LogEntry {
        val last = entries.firstOrNull()
        return LogEntry(aircraft = last?.aircraft ?: "SportStar MAX", tail = last?.tail ?: "", from = prefs.getString("efb_home", "KBVU")!!,
            to = prefs.getString("efb_home", "KBVU")!!, hobbsOut = last?.hobbsIn ?: 0.0)
    }

    private fun edit(e: LogEntry, isNew: Boolean) {
        body.removeAllViews()
        val c = EfbUi.card(this)
        body.addView(c)
        c.addView(EfbUi.text(this, getString(if (isNew) R.string.log_add else R.string.log_edit), 18f, EfbUi.ACCENT, bold = true))
        fun section(t: String) = c.addView(header(t))
        fun f(label: String, v: Any, number: Boolean = true): EditText =
            EfbUi.field(this, c, label, if (v is Double) (if (v == 0.0) "" else EfbUi.num(v)) else if (v is Int) (if (v == 0) "" else v.toString()) else v.toString(), number)

        section(getString(R.string.log_sec_flight))
        val date = f("Date (yyyy-mm-dd)", e.date, false)
        // Aircraft flown before, one tap away.
        val known = entries.filter { it.tail.isNotEmpty() }.distinctBy { it.tail }.take(8)
        lateinit var ac: EditText
        lateinit var tail: EditText
        if (known.isNotEmpty()) c.addView(HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
            addView(LinearLayout(this@LogbookActivity).apply {
                orientation = LinearLayout.HORIZONTAL
                for (k in known) addView(EfbUi.text(this@LogbookActivity, "${k.tail} · ${k.aircraft}", 12f, EfbUi.TEXT, bold = true).apply {
                    background = EfbUi.cardBg(this@LogbookActivity, 0xFF0F2A3A.toInt(), 14)
                    setPadding(dp(10), dp(6), dp(10), dp(6))
                    setOnClickListener { tail.setText(k.tail); ac.setText(k.aircraft) }
                }, LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(6); topMargin = dp(6) })
            })
        })
        ac = f("Aircraft make/model", e.aircraft, false)
        tail = f("Ident (N-number)", e.tail, false)
        val from = f("From", e.from, false)
        val to = f("To", e.to, false)
        val route = f("Route / stops", e.route, false)
        val out = f("Time out (HH:mm)", e.timeOut, false)
        val inn = f("Time in (HH:mm)", e.timeIn, false)
        val ho = f("Hobbs out", e.hobbsOut)
        val hi = f("Hobbs in", e.hobbsIn)

        section(getString(R.string.log_sec_time))
        val total = f("Total time", e.total)
        val pic = f("PIC", e.pic)
        val dual = f("Dual received", e.dual)
        val solo = f("Solo", e.solo)
        val xc = f("Cross-country", e.xc)
        val night = f("Night", e.night)
        val act = f("Actual instrument", e.actual)
        val inst = f("Simulated instrument (hood)", e.instrument)
        val gt = f("Ground trainer / sim", e.groundTrainer)
        // The total follows the Hobbs, or the block times.
        fun auto() {
            val a = ho.text.toString().toDoubleOrNull(); val b = hi.text.toString().toDoubleOrNull()
            if (a != null && b != null && b > a) { total.setText(EfbUi.num(Math.round((b - a) * 10) / 10.0)); return }
            val t0 = out.text.toString().split(':').mapNotNull { it.trim().toIntOrNull() }
            val t1 = inn.text.toString().split(':').mapNotNull { it.trim().toIntOrNull() }
            if (t0.size == 2 && t1.size == 2) {
                var m = (t1[0] * 60 + t1[1]) - (t0[0] * 60 + t0[1])
                if (m < 0) m += 1440
                if (m in 1..900) total.setText(EfbUi.num(Math.round(m / 6.0) / 10.0))
            }
        }
        for (x in listOf(ho, hi, out, inn)) x.setOnFocusChangeListener { _, has -> if (!has) auto() }
        val quick = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(6), 0, 0) }
        fun q(label: String, onClick: () -> Unit) = quick.addView(button(label, outlined = true, onClick = onClick), LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(4) })
        q("Dual") { dual.setText(total.text) }
        q("Solo") { solo.setText(total.text); pic.setText(total.text) }
        q("XC") { xc.setText(total.text) }
        q("Night") { night.setText(total.text) }
        c.addView(quick)

        section(getString(R.string.log_sec_ldg))
        val dl = f("Day landings", e.dayLdg)
        val nl = f("Night landings (full stop)", e.nightLdg)
        val tl = f("Towered landings (full stop)", e.toweredLdg)
        val app = f("Approaches", e.approaches)
        val appt = f("Approach types (e.g. RNAV 27 KHND)", e.approachTypes, false)
        val holds = f("Holds", e.holds)
        val far = f("Farthest from departure (nm)", e.farthestNm)
        val dist = f("Total distance (nm)", e.distanceNm)

        section(getString(R.string.log_sec_cfi))
        val cfi = f("Instructor", e.instructor, false)
        val cfin = f("CFI certificate #", e.instructorCert, false)
        val cfie = f("CFI expiration", e.instructorExp, false)
        if (e.instructor.isEmpty() && prefs.getString("last_cfi", "")!!.isNotEmpty()) c.addView(button(getString(R.string.log_last_cfi, prefs.getString("last_cfi", "")), outlined = true) {
            cfi.setText(prefs.getString("last_cfi", "")); cfin.setText(prefs.getString("last_cfin", "")); cfie.setText(prefs.getString("last_cfie", ""))
        })
        var signature = e.signature
        val sigView = ImageView(this).apply { adjustViewBounds = true; setBackgroundColor(0xFFFFFFFF.toInt()); setPadding(dp(8), dp(4), dp(8), dp(4)) }
        fun showSig() {
            val file = File(Logbook.signatures(this), signature)
            if (signature.isNotEmpty() && file.exists()) {
                sigView.setImageBitmap(BitmapFactory.decodeFile(file.path))
                sigView.visibility = View.VISIBLE
            } else sigView.visibility = View.GONE
        }
        c.addView(sigView, LinearLayout.LayoutParams(-2, dp(60)).apply { topMargin = dp(8) })
        showSig()
        c.addView(button(getString(R.string.log_sign), outlined = true) {
            SignaturePad.ask(this, getString(R.string.log_sign) + (cfi.text.toString().takeIf { it.isNotBlank() }?.let { " · $it" } ?: "")) { name ->
                signature = name
                showSig()
            }
        })
        val rem = f("Remarks", e.remarks, false)
        // The flight's GPS track: to replay in 3D in Google Earth, or to any flight app.
        val pts = if (e.track.isNotEmpty()) Tracks.read(this, e.track) else emptyList()
        if (pts.size > 1) {
            c.addView(header(getString(R.string.log_track, pts.size)))
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            fun export(ext: String, mime: String, text: String) {
                val f = File(File(cacheDir, "exports").apply { mkdirs() }, "Flight_${e.date}_${e.from}-${e.to}.$ext")
                f.writeText(text)
                share(f, mime)
            }
            val name = "${e.date} ${e.from}-${e.to}"
            row.addView(button("🌍 Google Earth 3D (KML)", outlined = true) { export("kml", "application/vnd.google-earth.kml+xml", Tracks.kml(name, pts)) },
                LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(6) })
            row.addView(button("GPX", outlined = true) { export("gpx", "application/gpx+xml", Tracks.gpx(name, pts)) }, LinearLayout.LayoutParams(-2, -2))
            c.addView(row)
        }

        val buttons = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.END; setPadding(0, dp(14), 0, 0) }
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
        buttons.addView(button(getString(R.string.log_save)) {
            auto()
            fun d(x: EditText) = x.text.toString().toDoubleOrNull() ?: 0.0
            fun i(x: EditText) = x.text.toString().toIntOrNull() ?: 0
            e.date = date.text.toString().trim().ifEmpty { LogEntry.today() }
            e.aircraft = ac.text.toString().trim(); e.tail = tail.text.toString().trim().uppercase()
            e.from = from.text.toString().trim().uppercase(); e.to = to.text.toString().trim().uppercase()
            e.route = route.text.toString().trim().uppercase()
            e.timeOut = out.text.toString().trim(); e.timeIn = inn.text.toString().trim()
            e.hobbsOut = d(ho); e.hobbsIn = d(hi)
            e.total = d(total); e.pic = d(pic); e.dual = d(dual); e.solo = d(solo); e.xc = d(xc); e.night = d(night)
            e.actual = d(act); e.instrument = d(inst); e.groundTrainer = d(gt)
            e.dayLdg = i(dl); e.nightLdg = i(nl); e.toweredLdg = i(tl); e.approaches = i(app); e.approachTypes = appt.text.toString().trim(); e.holds = i(holds)
            e.farthestNm = d(far); e.distanceNm = d(dist)
            e.instructor = cfi.text.toString().trim(); e.instructorCert = cfin.text.toString().trim(); e.instructorExp = cfie.text.toString().trim()
            e.signature = signature
            e.remarks = rem.text.toString().trim()
            e.updated = System.currentTimeMillis()
            entries.removeAll { it.id == e.id }
            entries.add(e)
            entries.sortWith(compareByDescending<LogEntry> { it.date }.thenByDescending { it.timeOut })
            Logbook.save(this, entries)
            if (e.instructor.isNotEmpty()) prefs.edit().putString("last_cfi", e.instructor).putString("last_cfin", e.instructorCert).putString("last_cfie", e.instructorExp).apply()
            show(0)
        })
        c.addView(buttons)
        EfbUi.stagger(body)
    }

    // ---- totals ----

    private fun totals() {
        val me = EfbUi.card(this)
        body.addView(me)
        me.addView(EfbUi.text(this, getString(R.string.log_pilot), 15f, EfbUi.ACCENT, bold = true))
        EfbUi.field(this, me, getString(R.string.log_pilot_name), prefs.getString("pilot_name", "") ?: "", number = false) { prefs.edit().putString("pilot_name", it.trim()).apply() }
        EfbUi.field(this, me, getString(R.string.log_pilot_cert), prefs.getString("pilot_cert", "") ?: "", number = false) { prefs.edit().putString("pilot_cert", it.trim()).apply() }

        val big = EfbUi.card(this)
        body.addView(big)
        big.addView(EfbUi.text(this, "%.1f h".format(entries.sumOf { it.total }), 34f, EfbUi.ACCENT, bold = true))
        big.addView(EfbUi.text(this, getString(R.string.log_total_flights, entries.size, entries.sumOf { it.dayLdg + it.nightLdg }), 13f, EfbUi.DIM))
        grid(big, listOf(
            "PIC" to entries.sumOf { it.pic }, "Dual" to entries.sumOf { it.dual }, "Solo" to entries.sumOf { it.solo },
            "XC" to entries.sumOf { it.xc }, "Night" to entries.sumOf { it.night }, "Instrument" to entries.sumOf { it.actual + it.instrument },
        ))

        body.addView(header(getString(R.string.log_periods)))
        val periods = EfbUi.card(this)
        body.addView(periods)
        val now = System.currentTimeMillis()
        val year = Calendar.getInstance().get(Calendar.YEAR).toString()
        grid(periods, listOf(
            "30 days" to entries.filter { now - it.dateMillis() < 30L * 86400000 }.sumOf { it.total },
            "90 days" to entries.filter { now - it.dateMillis() < 90L * 86400000 }.sumOf { it.total },
            "12 months" to entries.filter { now - it.dateMillis() < 365L * 86400000 }.sumOf { it.total },
            year to entries.filter { it.date.startsWith(year) }.sumOf { it.total },
        ))

        body.addView(header(getString(R.string.log_by_month)))
        body.addView(MonthChart(entries), LinearLayout.LayoutParams(-1, dp(170)).apply { topMargin = dp(6) })

        val types = entries.groupBy { it.aircraft.ifEmpty { "—" } }
        if (types.isNotEmpty()) {
            body.addView(header(getString(R.string.log_by_aircraft)))
            val t = EfbUi.card(this)
            body.addView(t)
            for ((k, v) in types.entries.sortedByDescending { it.value.sumOf { e -> e.total } }) {
                val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutDirection = View.LAYOUT_DIRECTION_LTR; setPadding(0, dp(4), 0, dp(4)) }
                row.addView(EfbUi.text(this, k, 15f, EfbUi.TEXT), LinearLayout.LayoutParams(0, -2, 1f))
                row.addView(EfbUi.text(this, "${v.size} flt  ·  %.1f h".format(v.sumOf { it.total }), 14f, EfbUi.ACCENT, mono = true))
                t.addView(row)
            }
        }

        body.addView(header(getString(R.string.log_iacra)))
        val ia = EfbUi.card(this)
        body.addView(ia)
        for ((k, v) in Logbook.iacra(entries)) {
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutDirection = View.LAYOUT_DIRECTION_LTR; setPadding(0, dp(3), 0, dp(3)) }
            row.addView(EfbUi.text(this, k, 13f, EfbUi.TEXT), LinearLayout.LayoutParams(0, -2, 1f))
            row.addView(EfbUi.text(this, if (k.contains("landings") || k.contains("Number")) "%.0f".format(v) else "%.1f".format(v), 14f, EfbUi.ACCENT, bold = true, mono = true))
            ia.addView(row)
        }

        val ex = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(0, dp(14), 0, 0) }
        ex.addView(button(getString(R.string.log_pdf)) { exportPdf() })
        ex.addView(button(getString(R.string.log_export), outlined = true) { exportCsv() })
        ex.addView(button(getString(R.string.log_backup), outlined = true) { backup() })
        ex.addView(button(getString(R.string.log_restore), outlined = true) { restorePicker.launch(arrayOf("*/*")) })
        body.addView(ex)
    }

    private fun grid(parent: LinearLayout, cells: List<Pair<String, Double>>) {
        var row: LinearLayout? = null
        for ((i, cell) in cells.withIndex()) {
            if (i % 3 == 0) {
                row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutDirection = View.LAYOUT_DIRECTION_LTR; setPadding(0, dp(10), 0, 0) }
                parent.addView(row)
            }
            row!!.addView(LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                addView(EfbUi.text(this@LogbookActivity, "%.1f".format(cell.second), 20f, EfbUi.TEXT, bold = true, mono = true))
                addView(EfbUi.text(this@LogbookActivity, cell.first, 11f, EfbUi.DIM))
            }, LinearLayout.LayoutParams(0, -2, 1f))
        }
    }

    /** Hours flown each of the last twelve months. */
    private inner class MonthChart(private val list: List<LogEntry>) : View(this@LogbookActivity) {
        private val bar = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = EfbUi.ACCENT }
        private val dim = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = EfbUi.DIM; textSize = 10 * resources.displayMetrics.density; textAlign = Paint.Align.CENTER }
        private val months: List<Pair<String, Double>> = (11 downTo 0).map { back ->
            val c = Calendar.getInstance().apply { add(Calendar.MONTH, -back) }
            val key = "%04d-%02d".format(c.get(Calendar.YEAR), c.get(Calendar.MONTH) + 1)
            java.text.SimpleDateFormat("MMM", java.util.Locale.US).format(c.time).take(1) to list.filter { it.date.startsWith(key) }.sumOf { it.total }
        }

        init { background = EfbUi.cardBg(this@LogbookActivity) }

        override fun onDraw(c: Canvas) {
            val d = resources.displayMetrics.density
            val max = (months.maxOfOrNull { it.second } ?: 0.0).coerceAtLeast(1.0)
            val left = 12 * d; val right = width - 12 * d; val top = 22 * d; val bottom = height - 22 * d
            val w = (right - left) / months.size
            for ((i, m) in months.withIndex()) {
                val x = left + i * w
                val h = ((m.second / max) * (bottom - top)).toFloat()
                bar.alpha = if (i == months.size - 1) 255 else 170
                c.drawRoundRect(x + w * 0.18f, bottom - h, x + w * 0.82f, bottom, 4 * d, 4 * d, bar)
                c.drawText(m.first, x + w / 2, height - 8 * d, dim)
                if (m.second > 0) c.drawText("%.1f".format(m.second), x + w / 2, bottom - h - 4 * d, dim)
            }
        }
    }

    // ---- checkride: the school's checklists, tied to the logbook ----

    private fun checkrideTab() {
        val sel = prefs.getString("ride_sel", "private")!!
        val chips = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(10), 0, 0) }
        val choices = listOf("presolo" to "Pre-Solo") + Checkride.RIDES.map { it.key to it.title }
        for ((key, label) in choices) chips.addView(EfbUi.text(this, label, 13f, EfbUi.TEXT, bold = true).apply {
            background = EfbUi.cardBg(this@LogbookActivity, if (key == sel) 0xFF00838F.toInt() else EfbUi.CARD, 18)
            setPadding(dp(12), dp(7), dp(12), dp(7))
            setOnClickListener { prefs.edit().putString("ride_sel", key).apply(); show(2) }
        }, LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(6) })
        body.addView(HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; addView(chips) })
        if (sel == "presolo") {
            preSolo()
            return
        }
        val ride = Checkride.RIDES.first { it.key == sel }
        body.addView(header(getString(R.string.ride_endorsements)))
        for (end in (if (ride.key == "private") Checkride.STUDENT else emptyList()) + ride.ends.filter { it !in Checkride.STUDENT }) body.addView(endorsementRow(end))
        body.addView(header(getString(R.string.ride_experience)))
        val ex = EfbUi.card(this)
        body.addView(ex)
        for (x in ride.experience) {
            val m = x.measure
            if (m != null) {
                val (v, t) = m(entries)
                val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(14 * x.depth), 0, 0, 0) }
                EfbUi.progress(this, box, x.title, v, t, if (t == 1.0) "" else "h")
                ex.addView(box)
            } else ex.addView(tick("exp_${ride.key}_${x.title.hashCode()}", x.title, x.depth))
        }
        body.addView(header(getString(R.string.ride_paperwork)))
        val pw = EfbUi.card(this)
        body.addView(pw)
        for (p in ride.paperwork) pw.addView(tick("pw_${ride.key}_${p.hashCode()}", p, 0))
        body.addView(EfbUi.text(this, getString(R.string.log_109_note), 11f, EfbUi.DIM).apply { setPadding(dp(4), dp(14), dp(4), 0) })
    }

    /** A box that remembers the day it was ticked. */
    private fun tick(key: String, label: String, depth: Int): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(14 * depth), dp(8), 0, dp(8))
            layoutDirection = View.LAYOUT_DIRECTION_LTR
        }
        val mark = EfbUi.text(this, "", 20f, EfbUi.DIM)
        val text = EfbUi.text(this, label, 14f, EfbUi.TEXT)
        val date = EfbUi.text(this, "", 11f, EfbUi.GOOD, mono = true)
        fun paint() {
            val d = prefs.getString(key, "") ?: ""
            mark.text = if (d.isEmpty()) "☐" else "☑"
            mark.setTextColor(if (d.isEmpty()) EfbUi.DIM else EfbUi.GOOD)
            text.alpha = if (d.isEmpty()) 1f else 0.6f
            date.text = d
        }
        row.addView(mark, LinearLayout.LayoutParams(dp(30), -2))
        row.addView(text, LinearLayout.LayoutParams(0, -2, 1f))
        row.addView(date)
        row.setOnClickListener {
            val d = prefs.getString(key, "") ?: ""
            prefs.edit().putString(key, if (d.isEmpty()) LogEntry.today() else "").apply()
            paint()
            row.animate().scaleX(0.97f).scaleY(0.97f).setDuration(70).withEndAction { row.animate().scaleX(1f).scaleY(1f).setDuration(120).start() }.start()
        }
        paint()
        return row
    }

    private fun preSolo() {
        body.addView(header("Pre-Solo Checklist 14 CFR 61.87"))
        val c = EfbUi.card(this)
        body.addView(c)
        for ((i, item) in Checkride.PRE_SOLO.withIndex()) {
            if (i == 2) c.addView(EfbUi.text(this, "Pre-Solo Flight Training", 15f, EfbUi.ACCENT, bold = true).apply { setPadding(0, dp(10), 0, 0) })
            c.addView(tick("presolo_$i", item, if (i == 1 || i >= 2) 1 else 0))
        }
        val done = Checkride.PRE_SOLO.indices.count { (prefs.getString("presolo_$it", "") ?: "").isNotEmpty() }
        body.addView(EfbUi.text(this, "$done / ${Checkride.PRE_SOLO.size}", 14f, if (done == Checkride.PRE_SOLO.size) EfbUi.GOOD else EfbUi.DIM, bold = true).apply { setPadding(dp(4), dp(10), 0, 0) })
        body.addView(header(getString(R.string.ride_endorsements)))
        for (end in Checkride.STUDENT.take(6)) body.addView(endorsementRow(end))
    }

    /** One endorsement the checkride needs: signed (green), missing; a tap signs or opens it. */
    private fun endorsementRow(end: Checkride.End): View {
        val have = endorsements.firstOrNull { (end.ac.isNotEmpty() && it.ac == end.ac) || it.title == end.title }
        val required = end.need.startsWith("Required")
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = EfbUi.cardBg(this@LogbookActivity)
            setPadding(dp(12), dp(10), dp(12), dp(10))
            layoutDirection = View.LAYOUT_DIRECTION_LTR
            layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(6) }
        }
        row.addView(EfbUi.text(this, if (have != null) "✅" else if (required) "⭕" else "◻️", 18f), LinearLayout.LayoutParams(dp(34), -2))
        row.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(EfbUi.text(this@LogbookActivity, end.title, 14f, EfbUi.TEXT, bold = true))
            addView(EfbUi.text(this@LogbookActivity, listOf(end.ac, end.far).filter { it.isNotEmpty() }.joinToString("  ·  "), 11f, EfbUi.DIM, mono = true))
        }, LinearLayout.LayoutParams(0, -2, 1f))
        row.addView(EfbUi.text(this, have?.date ?: end.need, 11f, if (have != null) EfbUi.GOOD else if (required) EfbUi.WARN else EfbUi.DIM, bold = true).apply { gravity = Gravity.END })
        EfbUi.pressable(row) {
            if (have != null) editEndorsement(have, isNew = false)
            else editEndorsement(Endorsement(title = end.title, rule = end.far, validDays = end.validDays, ac = end.ac).apply {
                instructor = prefs.getString("last_cfi", "") ?: ""
                instructorCert = prefs.getString("last_cfin", "") ?: ""
                instructorExp = prefs.getString("last_cfie", "") ?: ""
            }, isNew = true)
        }
        return row
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
        fun until(label: String, rule: String, end: Long?) {
            if (end == null) { line(label, false, "$rule · ${getString(R.string.cur_set)}"); return }
            val left = (end - System.currentTimeMillis()) / 86400000
            line(label, left >= 0, "$rule · ${LogEntry.FMT.format(java.util.Date(end))} · " + if (left >= 0) "$left days left" else "expired")
        }
        fun date(key: String) = try { LogEntry.FMT.parse(prefs.getString(key, "") ?: "")?.time } catch (e: Exception) { null }
        val review = date("cur_review")?.let { t ->
            Calendar.getInstance().apply { timeInMillis = t; add(Calendar.MONTH, 25); set(Calendar.DAY_OF_MONTH, 1); add(Calendar.DAY_OF_MONTH, -1) }.timeInMillis
        }
        until(getString(R.string.cur_review), "61.56 · 24 calendar months", review)
        // The solo endorsement: from the signed endorsements, or the date typed below.
        val solo = endorsements.filter { it.rule.startsWith("61.87(n)") || it.rule.startsWith("61.87(p)") || it.ac == "A.6" || it.ac == "A.7" }.mapNotNull { it.expires() }.maxOrNull()
            ?: date("cur_solo")?.plus(90L * 86400000)
        until(getString(R.string.cur_solo), "61.87(n) · 90 days", solo)
        until(getString(R.string.cur_medical), getString(R.string.cur_medical_rule), date("cur_medical"))
        val edit = EfbUi.card(this)
        body.addView(edit)
        edit.addView(EfbUi.text(this, getString(R.string.cur_dates), 15f, EfbUi.ACCENT, bold = true))
        for ((key, label) in listOf("cur_review" to R.string.cur_review, "cur_solo" to R.string.cur_solo, "cur_medical" to R.string.cur_medical_date)) {
            EfbUi.field(this, edit, getString(label), prefs.getString(key, "") ?: "", number = false) { v -> prefs.edit().putString(key, v.trim()).apply() }
        }
        edit.addView(button(getString(R.string.ok)) { show(3) })
    }

    // ---- endorsements ----

    private fun endorsementsTab() {
        body.addView(button(getString(R.string.end_add)) { pickTemplate() }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(10) })
        if (endorsements.isEmpty()) body.addView(EfbUi.text(this, getString(R.string.end_empty), 14f, EfbUi.DIM).apply { setPadding(dp(4), dp(14), dp(4), 0) })
        for (e in endorsements) {
            val c = EfbUi.card(this)
            val exp = e.expires()
            val ok = exp == null || exp >= System.currentTimeMillis()
            c.addView(EfbUi.text(this, e.title, 16f, if (ok) EfbUi.TEXT else EfbUi.BAD, bold = true))
            c.addView(EfbUi.text(this, "${listOf(e.ac, e.rule).filter { it.isNotEmpty() }.joinToString(" · ")} · ${e.date}" + (exp?.let { " → " + LogEntry.FMT.format(java.util.Date(it)) } ?: ""), 12f, EfbUi.DIM))
            if (e.text.isNotBlank()) c.addView(EfbUi.text(this, e.text, 13f, EfbUi.TEXT).apply { maxLines = 3; setPadding(0, dp(6), 0, 0) })
            c.addView(EfbUi.text(this, "${e.instructor} · ${e.instructorCert}", 12f, EfbUi.DIM).apply { setPadding(0, dp(6), 0, 0) })
            File(Logbook.signatures(this), e.signature).takeIf { e.signature.isNotEmpty() && it.exists() }?.let { f ->
                c.addView(ImageView(this).apply {
                    adjustViewBounds = true
                    setBackgroundColor(0xFFFFFFFF.toInt())
                    setImageBitmap(BitmapFactory.decodeFile(f.path))
                }, LinearLayout.LayoutParams(-2, dp(46)).apply { topMargin = dp(6) })
            }
            EfbUi.pressable(c) { editEndorsement(e, isNew = false) }
            body.addView(c)
        }
    }

    private fun pickTemplate() {
        val t = Checkride.TEMPLATES
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.end_add)
            .setItems((t.map { "${it.ac.ifEmpty { "•" }}  ${it.title}" } + getString(R.string.end_custom)).toTypedArray()) { _, i ->
                val e = t.getOrNull(i)?.let { Endorsement(title = it.title, rule = it.far, validDays = it.validDays, ac = it.ac) } ?: Endorsement()
                e.instructor = prefs.getString("last_cfi", "") ?: ""
                e.instructorCert = prefs.getString("last_cfin", "") ?: ""
                e.instructorExp = prefs.getString("last_cfie", "") ?: ""
                editEndorsement(e, isNew = true)
            }
            .show()
    }

    private fun editEndorsement(e: Endorsement, isNew: Boolean) {
        body.removeAllViews()
        val c = EfbUi.card(this)
        body.addView(c)
        val title = EfbUi.field(this, c, "Title", e.title, number = false)
        val rule = EfbUi.field(this, c, "14 CFR", e.rule, number = false)
        val acRef = EfbUi.field(this, c, "AC 61-65", e.ac, number = false)
        c.addView(EfbUi.text(this, getString(R.string.end_text_help), 12f, EfbUi.DIM).apply { setPadding(0, dp(8), 0, 0) })
        val text = EditText(this).apply {
            setText(e.text)
            setTextColor(EfbUi.TEXT)
            minLines = 4
            gravity = Gravity.TOP
            background = EfbUi.cardBg(this@LogbookActivity, 0xFF0F1A2E.toInt(), 10)
            setPadding(dp(10), dp(8), dp(10), dp(8))
        }
        c.addView(text, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(6) })
        val date = EfbUi.field(this, c, "Date (yyyy-mm-dd)", e.date, number = false)
        val days = EfbUi.field(this, c, "Valid days (0 = no limit)", e.validDays.toString())
        val cfi = EfbUi.field(this, c, "Instructor", e.instructor, number = false)
        val cfin = EfbUi.field(this, c, "CFI certificate #", e.instructorCert, number = false)
        val cfie = EfbUi.field(this, c, "CFI expiration", e.instructorExp, number = false)
        var signature = e.signature
        val sig = ImageView(this).apply { adjustViewBounds = true; setBackgroundColor(0xFFFFFFFF.toInt()) }
        fun showSig() {
            val f = File(Logbook.signatures(this), signature)
            if (signature.isNotEmpty() && f.exists()) { sig.setImageBitmap(BitmapFactory.decodeFile(f.path)); sig.visibility = View.VISIBLE } else sig.visibility = View.GONE
        }
        c.addView(sig, LinearLayout.LayoutParams(-2, dp(60)).apply { topMargin = dp(8) })
        showSig()
        c.addView(button(getString(R.string.log_sign), outlined = true) { SignaturePad.ask(this, getString(R.string.log_sign)) { signature = it; showSig() } })
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.END; setPadding(0, dp(12), 0, 0) }
        if (!isNew) row.addView(MaterialButton(this, null, com.google.android.material.R.attr.borderlessButtonStyle).apply {
            this.text = getString(R.string.delete)
            setTextColor(EfbUi.BAD)
            setOnClickListener { endorsements.removeAll { it.id == e.id }; Logbook.saveEndorsements(this@LogbookActivity, endorsements); show(4) }
        })
        row.addView(MaterialButton(this, null, com.google.android.material.R.attr.borderlessButtonStyle).apply { this.text = getString(R.string.cancel); setOnClickListener { show(4) } })
        row.addView(button(getString(R.string.log_save)) {
            e.title = title.text.toString().trim(); e.rule = rule.text.toString().trim(); e.text = text.text.toString().trim()
            e.ac = acRef.text.toString().trim()
            e.date = date.text.toString().trim().ifEmpty { LogEntry.today() }; e.validDays = days.text.toString().toIntOrNull() ?: 0
            e.instructor = cfi.text.toString().trim(); e.instructorCert = cfin.text.toString().trim(); e.instructorExp = cfie.text.toString().trim()
            e.signature = signature
            endorsements.removeAll { it.id == e.id }
            endorsements.add(0, e)
            endorsements.sortByDescending { it.date }
            Logbook.saveEndorsements(this, endorsements)
            show(4)
        })
        c.addView(row)
        EfbUi.stagger(body)
    }

    // ---- export ----

    private fun share(f: File, mime: String) {
        val uri = FileProvider.getUriForFile(this, "$packageName.files", f)
        startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply {
            type = mime
            putExtra(Intent.EXTRA_STREAM, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }, null))
    }

    private fun exportPdf() {
        Toast.makeText(this, R.string.log_pdf_making, Toast.LENGTH_SHORT).show()
        lifecycleScope.launch {
            val f = withContext(Dispatchers.IO) {
                LogbookPdf.write(this@LogbookActivity, entries, endorsements, prefs.getString("pilot_name", "") ?: "", prefs.getString("pilot_cert", "") ?: "")
            }
            share(f, "application/pdf")
        }
    }

    private fun exportCsv() {
        val f = File(File(cacheDir, "exports").apply { mkdirs() }, "Logbook_${LogEntry.today()}.csv")
        f.writeText(Logbook.csv(entries))
        share(f, "text/csv")
    }

    private fun backup() {
        val f = File(File(cacheDir, "exports").apply { mkdirs() }, "SSEFB_logbook_${LogEntry.today()}.json")
        f.writeText(Logbook.backup(this))
        share(f, "application/json")
    }

    companion object {
        const val EXTRA_TAB = "tab"
        const val EXTRA_NEW = "new"
    }
}
