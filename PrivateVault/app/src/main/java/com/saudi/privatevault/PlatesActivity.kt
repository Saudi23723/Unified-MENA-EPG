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
        binders()
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
                    row.setOnLongClickListener { addToBinder(p); true }
                    card.addView(row)
                }
                col.addView(card)
            }
            col.addView(EfbUi.text(this@PlatesActivity, getString(R.string.plates_note), 11.5f, EfbUi.DIM).apply { setPadding(dp(6), dp(16), dp(6), 0) })
        }
    }

    // ---- binders: the pilot's own sets of plates, ForeFlight's way ----

    private fun binderData(): org.json.JSONObject = try { org.json.JSONObject(VaultLock.prefs(this).getString("plate_binders", "{}")) } catch (e: Exception) { org.json.JSONObject() }
    private fun saveBinders(o: org.json.JSONObject) = VaultLock.prefs(this).edit().putString("plate_binders", o.toString()).apply()

    /** The binders at the top of the page: tap one to open its plates, which are always of the current cycle. */
    private fun binders() {
        val o = binderData()
        val names = o.keys().asSequence().toList().sorted()
        col.addView(EfbUi.section(this, if (names.isEmpty()) "Binders" else "Binders · ${names.size}"))
        if (names.isEmpty()) {
            col.addView(EfbUi.text(this, "Press and hold any plate to put it in a binder (for a trip, a checkride, the home field).", 12.5f, EfbUi.DIM).apply { setPadding(dp(6), 0, dp(6), dp(4)) })
            return
        }
        val card = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; background = EfbUi.cardBg(this@PlatesActivity, EfbUi.CARD, 12) }
        for ((i, n) in names.withIndex()) {
            if (i > 0) card.addView(View(this).apply { setBackgroundColor(EfbUi.CARD_LINE) }, LinearLayout.LayoutParams(-1, 1).apply { marginStart = dp(16) })
            val count = o.optJSONArray(n)?.length() ?: 0
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(16), dp(13), dp(12), dp(13)) }
            row.addView(EfbUi.text(this, "📒  $n", 15.5f, EfbUi.TEXT), LinearLayout.LayoutParams(0, -2, 1f))
            row.addView(EfbUi.text(this, "$count  ›", 15f, EfbUi.DIM))
            row.setOnClickListener { openBinder(n) }
            card.addView(row)
        }
        col.addView(card)
    }

    private fun openBinder(name: String) {
        val a = binderData().optJSONArray(name) ?: return
        val items = (0 until a.length()).mapNotNull { a.optJSONObject(it) }
        val labels = items.map { "${it.optString("ident")}  ${it.optString("name")}" }.toTypedArray()
        com.google.android.material.dialog.MaterialAlertDialogBuilder(this).setTitle("📒 $name")
            .setItems(labels) { _, i -> openFromBinder(items[i].optString("ident"), items[i].optString("name"), items[i].optString("pdf")) }
            .setNeutralButton("Edit") { _, _ ->
                val keep = BooleanArray(items.size) { true }
                com.google.android.material.dialog.MaterialAlertDialogBuilder(this).setTitle("Keep in “$name”")
                    .setMultiChoiceItems(labels, keep) { _, i, on -> keep[i] = on }
                    .setPositiveButton("Save") { _, _ ->
                        val o = binderData(); val na = org.json.JSONArray()
                        for ((i, it) in items.withIndex()) if (keep[i]) na.put(it)
                        if (na.length() == 0) o.remove(name) else o.put(name, na)
                        saveBinders(o); load()
                    }
                    .setNegativeButton("Cancel", null).show()
            }
            .setNegativeButton("Close", null).show()
    }

    /** A plate kept in a binder is looked up again in the cycle in force, so a binder never holds an old plate. */
    private fun openFromBinder(apt: String, name: String, pdf: String) {
        Toast.makeText(this, R.string.apt_plates_loading, Toast.LENGTH_SHORT).show()
        lifecycleScope.launch {
            val res = withContext(Dispatchers.IO) { try { AviationData.plates(this@PlatesActivity, apt) } catch (e: Exception) { null } }
            val p = res?.second?.firstOrNull { it.name == name } ?: res?.second?.firstOrNull { it.pdf == pdf }
            if (res == null || p == null) { Toast.makeText(this@PlatesActivity, "Not in the current cycle any more: $apt $name", Toast.LENGTH_LONG).show(); return@launch }
            val keep = ident; ident = apt
            open(res.first, p)
            ident = keep
        }
    }

    private fun addToBinder(p: AviationData.Plate) {
        val o = binderData()
        val names = o.keys().asSequence().toList().sorted()
        val choices = (names + "＋ New binder…").toTypedArray()
        com.google.android.material.dialog.MaterialAlertDialogBuilder(this).setTitle("Put “${p.name}” in")
            .setItems(choices) { _, i ->
                fun put(n: String) {
                    val d = binderData(); val arr = d.optJSONArray(n) ?: org.json.JSONArray()
                    for (k in 0 until arr.length()) arr.optJSONObject(k)?.let { if (it.optString("ident") == ident && it.optString("name") == p.name) { Toast.makeText(this, "Already in $n", Toast.LENGTH_SHORT).show(); return } }
                    arr.put(org.json.JSONObject().put("ident", ident).put("name", p.name).put("pdf", p.pdf).put("code", p.code))
                    d.put(n, arr); saveBinders(d)
                    Toast.makeText(this, "Added to $n", Toast.LENGTH_SHORT).show(); load()
                }
                if (i < names.size) put(names[i]) else {
                    val input = android.widget.EditText(this).apply { hint = "Binder name (e.g. KBVU–KIGM)" }
                    com.google.android.material.dialog.MaterialAlertDialogBuilder(this).setTitle("New binder").setView(input)
                        .setPositiveButton("Create") { _, _ -> input.text.toString().trim().takeIf { it.isNotEmpty() }?.let { put(it) } }
                        .setNegativeButton("Cancel", null).show()
                }
            }.show()
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
