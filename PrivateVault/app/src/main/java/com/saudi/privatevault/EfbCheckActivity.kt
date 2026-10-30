package com.saudi.privatevault

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.BatteryManager
import android.os.Bundle
import android.os.StatFs
import android.widget.CheckBox
import android.widget.LinearLayout
import android.widget.Toast
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * Using SSEFB in place of paper (Part 91, AC 91-78A): what the app checks
 * by itself (power, chart currency, what is saved for flying offline, room
 * on the phone), the pilot's own check before each flight, and the AC
 * itself to read. The pilot in command stays responsible for the EFB and
 * its data; this page helps, the AC is the reference.
 */
class EfbCheckActivity : BaseActivity() {
    companion object {
        private const val AC_URL = "https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC_91-78A.pdf"
        private const val AC_NAME = "AC 91-78A · Use of Electronic Flight Bags.pdf"
        const val REFERENCES = "📚 References"

        /** When the pilot last completed the check, for the front page. */
        fun lastDone(ctx: Context) = VaultLock.prefs(ctx).getLong("efb_check_at", 0L)
    }

    private lateinit var col: LinearLayout
    private val prefs by lazy { VaultLock.prefs(this) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        col = EfbUi.screen(this, getString(R.string.efbc_title))
        build()
    }

    private fun dp(v: Int) = EfbUi.dp(this, v)

    private fun section(t: String) = col.addView(EfbUi.text(this, t, 17f, EfbUi.ACCENT, bold = true).apply { setPadding(dp(2), dp(18), 0, dp(2)) })

    private fun line(card: LinearLayout, ok: Boolean?, title: String, detail: String) {
        val mark = when (ok) { true -> "✅"; false -> "⚠️"; null -> "•" }
        card.addView(EfbUi.text(this, "$mark  $title", 15f, if (ok == false) EfbUi.WARN else EfbUi.TEXT, bold = true).apply { setPadding(0, dp(8), 0, 0) })
        if (detail.isNotEmpty()) card.addView(EfbUi.text(this, detail, 13f, EfbUi.DIM).apply { setPadding(dp(28), 0, 0, dp(2)) })
    }

    private fun build() {
        col.removeAllViews()

        // ---- what the app checks by itself ----
        section(getString(R.string.efbc_status))
        val st = EfbUi.card(this)
        val bm = getSystemService(Context.BATTERY_SERVICE) as BatteryManager
        val pct = bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
        val charging = bm.isCharging
        line(st, pct >= 80 || charging, getString(R.string.efbc_battery, pct), getString(if (charging) R.string.efbc_charging else R.string.efbc_battery_tip))
        val stale = ChartUpdates.outOfDate(this)
        line(st, stale == 0, getString(R.string.efbc_charts), ChartUpdates.status(this))
        val free = try { StatFs(filesDir.path).availableBytes / (1024 * 1024) } catch (e: Exception) { -1L }
        line(st, free < 0 || free > 500, getString(R.string.efbc_space, free), "")
        val myVersion = try { packageManager.getPackageInfo(packageName, 0).versionName } catch (e: Exception) { "" }
        line(st, null, getString(R.string.efbc_version, myVersion), getString(R.string.efbc_version_tip))
        val last = lastDone(this)
        line(st, last > 0 && System.currentTimeMillis() - last < 24 * 3600 * 1000L,
            getString(R.string.efbc_last), if (last == 0L) "—" else java.text.DateFormat.getDateTimeInstance().format(java.util.Date(last)))
        col.addView(st)

        // ---- the pilot's own check before each flight ----
        section(getString(R.string.efbc_preflight))
        val pf = EfbUi.card(this)
        val items = resources.getStringArray(R.array.efbc_items)
        val boxes = items.map { t ->
            CheckBox(this).apply {
                text = t; setTextColor(EfbUi.TEXT); textSize = 15f
                buttonTintList = android.content.res.ColorStateList.valueOf(EfbUi.ACCENT)
                setPadding(dp(4), dp(6), 0, dp(6))
            }.also { pf.addView(it) }
        }
        // What the app already knows ticks itself.
        boxes.getOrNull(0)?.isChecked = pct >= 80 || charging
        boxes.getOrNull(1)?.isChecked = stale == 0
        val done = EfbUi.text(this, getString(R.string.efbc_done), 16f, EfbUi.BG, bold = true).apply {
            gravity = android.view.Gravity.CENTER
            background = EfbUi.cardBg(this@EfbCheckActivity, EfbUi.ACCENT, 14)
            setPadding(dp(12), dp(12), dp(12), dp(12))
        }
        EfbUi.pressable(done) {
            val missing = boxes.count { !it.isChecked }
            if (missing > 0) {
                Toast.makeText(this, getString(R.string.efbc_missing, missing), Toast.LENGTH_LONG).show()
            } else {
                prefs.edit().putLong("efb_check_at", System.currentTimeMillis()).apply()
                Toast.makeText(this, R.string.efbc_saved, Toast.LENGTH_SHORT).show()
                build()
            }
        }
        pf.addView(done, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) })
        col.addView(pf)

        // ---- every source, its edition and validity: the page to show an instructor or examiner ----
        section(getString(R.string.efbc_sources))
        val src = EfbUi.card(this)
        src.addView(EfbUi.text(this, getString(R.string.map_loading_wx), 13f, EfbUi.DIM))
        col.addView(src)
        lifecycleScope.launch {
            val rows = withContext(Dispatchers.IO) { DataCurrency.rows(this@EfbCheckActivity) }
            src.removeAllViews()
            for (r in rows) {
                line(src, r.ok, r.what, "${r.source}\n${r.edition}" + if (r.note.isNotEmpty()) "\n${r.note}" else "")
            }
            val verify = EfbUi.text(this@EfbCheckActivity, "🔗 " + getString(R.string.efbc_verify), 14f, EfbUi.ACCENT, bold = true).apply { setPadding(0, dp(12), 0, 0) }
            EfbUi.pressable(verify) {
                try { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://www.faa.gov/air_traffic/flight_info/aeronav/productcatalog/doles/"))) } catch (e: Exception) {}
            }
            src.addView(verify)
        }

        // ---- self-test: the app checks that it works, now ----
        section(getString(R.string.efbc_selftest))
        val tc = EfbUi.card(this)
        val lastTest = prefs.getString("efb_selftest", "") ?: ""
        if (lastTest.isNotEmpty()) tc.addView(EfbUi.text(this, lastTest, 13f, EfbUi.DIM).apply { setPadding(0, 0, 0, dp(6)) })
        val run = EfbUi.text(this, "🧪 " + getString(R.string.efbc_selftest_run), 16f, EfbUi.BG, bold = true).apply {
            gravity = android.view.Gravity.CENTER
            background = EfbUi.cardBg(this@EfbCheckActivity, EfbUi.ACCENT, 14)
            setPadding(dp(12), dp(12), dp(12), dp(12))
        }
        EfbUi.pressable(run) { selfTest(tc, run) }
        tc.addView(run)
        col.addView(tc)

        // ---- what an examiner may ask ----
        section(getString(R.string.efbc_dpe))
        val dc = EfbUi.card(this)
        dc.addView(EfbUi.text(this, getString(R.string.efbc_dpe_text), 14f, EfbUi.TEXT).apply { setLineSpacing(0f, 1.3f) })
        col.addView(dc)

        // ---- what stays with the pilot ----
        section(getString(R.string.efbc_pilot))
        val pc = EfbUi.card(this)
        pc.addView(EfbUi.text(this, getString(R.string.efbc_pilot_text), 14f, EfbUi.TEXT).apply { setLineSpacing(0f, 1.3f) })
        col.addView(pc)

        // ---- NASA ASRS (AC 00-46F) ----
        section(getString(R.string.asrs_title))
        val asrs = EfbUi.card(this)
        asrs.addView(EfbUi.text(this, getString(R.string.asrs_text), 14f, EfbUi.TEXT).apply { setLineSpacing(0f, 1.3f) })
        val file = EfbUi.text(this, "📨 " + getString(R.string.asrs_open), 16f, EfbUi.ACCENT, bold = true).apply { setPadding(0, dp(12), 0, dp(4)) }
        EfbUi.pressable(file) { try { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://asrs.arc.nasa.gov/"))) } catch (e: Exception) {} }
        asrs.addView(file)
        col.addView(asrs)

        // ---- the AC itself ----
        section(getString(R.string.efbc_ac))
        val ac = EfbUi.card(this)
        ac.addView(EfbUi.text(this, getString(R.string.efbc_ac_text), 14f, EfbUi.DIM))
        val open = EfbUi.text(this, "📄 " + getString(R.string.efbc_ac_open), 16f, EfbUi.ACCENT, bold = true).apply { setPadding(0, dp(12), 0, dp(4)) }
        EfbUi.pressable(open) { openAc() }
        ac.addView(open)
        col.addView(ac)
        EfbUi.stagger(col)
    }

    /** Each part checked for real: position, clock, the FAA sources, and what is saved for offline. */
    private fun selfTest(card: LinearLayout, button: android.view.View) {
        button.isEnabled = false
        val out = EfbUi.text(this, "…", 14f, EfbUi.TEXT).apply { setLineSpacing(0f, 1.3f); setPadding(0, dp(10), 0, 0) }
        card.addView(out)
        val home = prefs.getString("efb_home", "KBVU")!!
        lifecycleScope.launch {
            val lines = ArrayList<String>()
            fun add(ok: Boolean?, t: String) {
                lines.add((when (ok) { true -> "✅"; false -> "❌"; null -> "⚠️" }) + " " + t)
                out.text = lines.joinToString("\n")
            }
            // Position: a fresh fix from the GPS itself (up to 30 s), its accuracy.
            add(null, getString(R.string.st_gps_wait))
            val fix = freshFix()
            lines.removeAt(lines.size - 1)
            if (fix == null) add(null, getString(R.string.st_gps_none))
            else {
                val ageMin = (System.currentTimeMillis() - fix.time) / 60000
                add(if (fix.accuracy < 30) true else null, getString(R.string.st_gps, Math.round(fix.accuracy), ageMin))
                // The phone's clock against the satellites' time (GPS fixes carry it).
                if (fix.provider == android.location.LocationManager.GPS_PROVIDER && ageMin < 5) {
                    val skew = Math.abs(System.currentTimeMillis() - fix.time - (android.os.SystemClock.elapsedRealtimeNanos() - fix.elapsedRealtimeNanos) / 1000000) / 1000
                    add(skew < 60, getString(R.string.st_clock, skew))
                }
            }
            suspend fun probe(label: String, url: String) {
                val ok = withContext(Dispatchers.IO) {
                    try {
                        val c = java.net.URL(url).openConnection() as java.net.HttpURLConnection
                        c.connectTimeout = 10000; c.readTimeout = 15000
                        c.setRequestProperty("User-Agent", "SSEFB")
                        try { c.responseCode in 200..399 } finally { c.disconnect() }
                    } catch (e: Exception) { false }
                }
                add(if (ok) true else null, label + if (ok) "" else " — " + getString(R.string.st_offline))
            }
            probe("FAA VFR charts", "https://tiles.arcgis.com/tiles/ssFJjBXIUyZDrSYZ/arcgis/rest/services/VFR_Sectional/MapServer/tile/8/101/45")
            probe("FAA d-TPP (plates)", "https://aeronav.faa.gov/d-tpp/${AviationData.airacCycle()}/xml_data/d-tpp_Metafile.xml")
            probe("Aviation Weather Center", "https://aviationweather.gov/api/data/metar?ids=$home&format=raw")
            probe("FAA TFRs", "https://tfr.faa.gov/")
            // Offline readiness for the home airport.
            val (info, plates, notams) = withContext(Dispatchers.IO) {
                val st = if (home.length == 3) "K$home" else home
                Triple(
                    File(filesDir, "aviation/info/${st.replace(Regex("[^A-Z0-9]"), "")}.json").exists(),
                    File(filesDir, "aviation/tpp.json").exists(),
                    AviationData.notamsSaved(this@EfbCheckActivity, st),
                )
            }
            add(info, getString(R.string.st_home_info, home))
            add(plates, getString(R.string.st_plates))
            add(if (notams != null) true else null, getString(R.string.st_notams, home) +
                (notams?.second?.let { " · " + java.text.DateFormat.getDateTimeInstance(java.text.DateFormat.SHORT, java.text.DateFormat.SHORT).format(java.util.Date(it)) } ?: ""))
            val stale = ChartUpdates.outOfDate(this@EfbCheckActivity)
            add(stale == 0, getString(R.string.st_saved_charts, stale))
            val crash = File(filesDir, "last_crash.txt").exists()
            add(!crash, getString(if (crash) R.string.st_crash else R.string.st_nocrash))
            val stamp = java.text.DateFormat.getDateTimeInstance(java.text.DateFormat.SHORT, java.text.DateFormat.SHORT).format(java.util.Date())
            val fails = lines.count { it.startsWith("❌") }
            val warns = lines.count { it.startsWith("⚠️") }
            val summary = getString(R.string.st_summary, stamp, lines.size - fails - warns, warns, fails)
            add(if (fails == 0 && warns == 0) true else if (fails == 0) null else false, summary)
            prefs.edit().putString("efb_selftest", summary).apply()
            button.isEnabled = true
        }
    }

    /** One new GPS position, or null after 30 s (indoors, or no permission). */
    private suspend fun freshFix(): android.location.Location? = kotlinx.coroutines.withTimeoutOrNull(30000) {
        kotlinx.coroutines.suspendCancellableCoroutine { cont ->
            val lm = getSystemService(android.location.LocationManager::class.java)
            val listener = object : android.location.LocationListener {
                override fun onLocationChanged(l: android.location.Location) {
                    lm.removeUpdates(this)
                    if (cont.isActive) cont.resumeWith(Result.success(l))
                }
                override fun onProviderDisabled(provider: String) {}
                override fun onProviderEnabled(provider: String) {}
                @Deprecated("old API") override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) {}
            }
            try {
                lm.requestLocationUpdates(android.location.LocationManager.GPS_PROVIDER, 0L, 0f, listener, android.os.Looper.getMainLooper())
            } catch (e: Exception) {
                if (cont.isActive) cont.resumeWith(Result.success(null))
            }
            cont.invokeOnCancellation { lm.removeUpdates(listener) }
        }
    }

    private fun refsFolder(): String =
        (VaultStore.childFolders(null).firstOrNull { it.name == REFERENCES } ?: VaultStore.addFolder(REFERENCES, null)).id

    /** The AC from the FAA, kept in the vault's References folder to read offline (with the pens and Gemini). */
    private fun openAc() {
        val folder = refsFolder()
        VaultStore.itemsIn(folder).firstOrNull { it.name == AC_NAME }?.let { item ->
            startActivity(Intent(this, PdfViewerActivity::class.java).putExtra(Viewers.EXTRA_ID, item.id))
            return
        }
        // The AC ships with the app: no download needed.
        try {
            val target = VaultStore.downloadTarget(AC_NAME)
            assets.open("library/AC_91-78A_EFB.pdf").use { inp -> target.outputStream().use { inp.copyTo(it) } }
            val item = VaultStore.adopt(target, AC_NAME, "application/pdf", folder)
            startActivity(Intent(this, PdfViewerActivity::class.java).putExtra(Viewers.EXTRA_ID, item.id))
            return
        } catch (e: Exception) {
        }
        Toast.makeText(this, R.string.efbc_ac_loading, Toast.LENGTH_SHORT).show()
        lifecycleScope.launch {
            val item = withContext(Dispatchers.IO) {
                try {
                    val target = VaultStore.downloadTarget(AC_NAME)
                    val c = URL(AC_URL).openConnection() as HttpURLConnection
                    c.connectTimeout = 20000; c.readTimeout = 60000
                    c.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android) SSEFB")
                    try {
                        if (c.responseCode != 200 || c.contentType?.contains("pdf", true) == false) null
                        else {
                            c.inputStream.use { inp -> target.outputStream().use { inp.copyTo(it) } }
                            if (target.length() < 10000) { target.delete(); null }
                            else VaultStore.adopt(target, AC_NAME, "application/pdf", folder)
                        }
                    } finally {
                        c.disconnect()
                    }
                } catch (e: Exception) {
                    null
                }
            }
            if (item != null) {
                startActivity(Intent(this@EfbCheckActivity, PdfViewerActivity::class.java).putExtra(Viewers.EXTRA_ID, item.id))
            } else {
                // The FAA moved it: its page, where a tap on the PDF saves it.
                Toast.makeText(this@EfbCheckActivity, R.string.efbc_ac_web, Toast.LENGTH_LONG).show()
                try {
                    startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://www.faa.gov/regulations_policies/advisory_circulars/index.cfm/go/document.list?q=91-78")))
                } catch (e: Exception) {
                }
            }
        }
    }
}
