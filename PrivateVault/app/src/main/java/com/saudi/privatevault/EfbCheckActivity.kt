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

        // ---- what stays with the pilot ----
        section(getString(R.string.efbc_pilot))
        val pc = EfbUi.card(this)
        pc.addView(EfbUi.text(this, getString(R.string.efbc_pilot_text), 14f, EfbUi.TEXT).apply { setLineSpacing(0f, 1.3f) })
        col.addView(pc)

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

    private fun refsFolder(): String =
        (VaultStore.childFolders(null).firstOrNull { it.name == REFERENCES } ?: VaultStore.addFolder(REFERENCES, null)).id

    /** The AC from the FAA, kept in the vault's References folder to read offline (with the pens and Gemini). */
    private fun openAc() {
        val folder = refsFolder()
        VaultStore.itemsIn(folder).firstOrNull { it.name == AC_NAME }?.let { item ->
            startActivity(Intent(this, PdfViewerActivity::class.java).putExtra(Viewers.EXTRA_ID, item.id))
            return
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
