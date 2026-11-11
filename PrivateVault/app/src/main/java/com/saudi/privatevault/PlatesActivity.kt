package com.saudi.privatevault

import android.content.Intent
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.Toast
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Plates, as ForeFlight's tab: the airport's official FAA procedures of the current cycle, grouped
 * (airport diagram, approaches, departures, arrivals, minimums), each opened in the reader, where
 * the aircraft is drawn on any georeferenced one (the airport diagram).
 */
class PlatesActivity : BaseActivity() {
    private lateinit var col: LinearLayout
    private var ident = "KBVU"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        ident = intent.getStringExtra("ident") ?: VaultLock.prefs(this).getString("plates_ident", null)
            ?: VaultLock.prefs(this).getString("efb_home", "KBVU") ?: "KBVU"
        col = EfbUi.screen(this, getString(R.string.ff_plates)) { bar ->
            bar.menu.add(0, 1, 0, R.string.map_find).setIcon(R.drawable.ic_search).apply {
                icon?.setTint(EfbUi.TEXT); setShowAsAction(android.view.MenuItem.SHOW_AS_ACTION_ALWAYS)
            }
            bar.setOnMenuItemClickListener {
                lifecycleScope.launch {
                    val list = withContext(Dispatchers.IO) { AviationData.airports(this@PlatesActivity) }
                    AirportSearch.show(this@PlatesActivity, list, null) { a -> ident = a.icao.ifEmpty { a.ident }; VaultLock.prefs(this@PlatesActivity).edit().putString("plates_ident", ident).apply(); load() }
                }
                true
            }
        }
        load()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        intent.getStringExtra("ident")?.let { ident = it; load() }
    }

    private fun dp(v: Int) = EfbUi.dp(this, v)

    private val GROUPS = listOf(
        "APD" to "Airport diagram", "IAP" to "Approaches", "DP" to "Departures", "ODP" to "Obstacle departures",
        "STAR" to "Arrivals", "MIN" to "Minimums", "HOT" to "Hot spots", "LAH" to "LAHSO",
    )

    private fun load() {
        col.removeAllViews()
        col.addView(EfbUi.text(this, ident, 26f, EfbUi.TEXT, bold = true).apply { setPadding(dp(6), dp(12), 0, 0) })
        val wait = EfbUi.text(this, getString(R.string.apt_plates_loading), 13f, EfbUi.DIM).apply { setPadding(dp(6), dp(4), 0, 0) }
        col.addView(wait)
        lifecycleScope.launch {
            val res = withContext(Dispatchers.IO) { try { AviationData.plates(this@PlatesActivity, ident) } catch (e: Exception) { null } }
            if (res == null || res.second.isEmpty()) { wait.text = getString(if (res == null) R.string.apt_plates_fail else R.string.apt_no_plates); return@launch }
            val (cycle, list) = res
            wait.text = "FAA d-TPP · cycle $cycle"
            val known = GROUPS.map { it.first }
            for ((code, title) in GROUPS + listOf("" to "Other")) {
                val items = list.filter { if (code.isEmpty()) it.code !in known else it.code == code }
                if (items.isEmpty()) continue
                col.addView(EfbUi.section(this@PlatesActivity, "$title · ${items.size}"))
                val card = LinearLayout(this@PlatesActivity).apply { orientation = LinearLayout.VERTICAL; background = EfbUi.cardBg(this@PlatesActivity, EfbUi.CARD, 12) }
                for ((i, p) in items.withIndex()) {
                    if (i > 0) card.addView(View(this@PlatesActivity).apply { setBackgroundColor(EfbUi.CARD_LINE) }, LinearLayout.LayoutParams(-1, 1).apply { marginStart = dp(16) })
                    val row = LinearLayout(this@PlatesActivity).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(16), dp(13), dp(12), dp(13)) }
                    row.addView(EfbUi.text(this@PlatesActivity, p.name, 15.5f, EfbUi.TEXT), LinearLayout.LayoutParams(0, -2, 1f))
                    if (p.code == "APD") row.addView(EfbUi.text(this@PlatesActivity, "📍", 15f).apply { setPadding(dp(6), 0, dp(6), 0) })
                    row.addView(EfbUi.text(this@PlatesActivity, "›", 22f, EfbUi.DIM))
                    row.setOnClickListener { open(cycle, p) }
                    card.addView(row)
                }
                col.addView(card)
            }
            col.addView(EfbUi.text(this@PlatesActivity, getString(R.string.plates_note), 11.5f, EfbUi.DIM).apply { setPadding(dp(6), dp(16), dp(6), 0) })
        }
    }

    private fun open(cycle: String, p: AviationData.Plate) {
        Toast.makeText(this, R.string.apt_plates_loading, Toast.LENGTH_SHORT).show()
        lifecycleScope.launch {
            val f = withContext(Dispatchers.IO) { AviationData.platePdf(this@PlatesActivity, cycle, p.pdf) }
            if (f == null) { Toast.makeText(this@PlatesActivity, R.string.apt_plates_fail, Toast.LENGTH_LONG).show(); return@launch }
            val item = VaultItem("plate:" + p.pdf, "$ident ${p.name}", f.absolutePath, "application/pdf", f.length(), f.lastModified(), null)
            VaultStore.viewOnly(item)
            startActivity(Intent(this@PlatesActivity, PdfViewerActivity::class.java).putExtra(Viewers.EXTRA_ID, item.id))
        }
    }
}
