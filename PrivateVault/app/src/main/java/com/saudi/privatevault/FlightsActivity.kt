package com.saudi.privatevault

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.Gravity
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.core.content.FileProvider
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Flights, as ForeFlight's tab: the flight being planned with everything that belongs to it one tap
 * away (nav log, briefing, winds, the flight plan page, weight and balance, performance), the flights
 * kept for later to load again, and the track logs the app recorded, each drawn and ready to send as
 * GPX or KML.
 */
class FlightsActivity : BaseActivity() {
    override val alwaysDark = true
    private lateinit var body: LinearLayout
    private fun dp(v: Int) = EfbUi.dp(this, v)

    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        window.statusBarColor = EfbUi.BG
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(EfbUi.BG) }
        root.addView(EfbUi.text(this, "FLIGHTS", 13f, EfbUi.TEXT, bold = true).apply {
            letterSpacing = 0.12f; setPadding(dp(16), dp(14), dp(16), dp(10)); setBackgroundColor(0xFF121820.toInt())
        })
        body = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(12), dp(6), dp(12), dp(90)) }
        root.addView(ScrollView(this).apply { addView(body) }, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(root)
        androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(root) { _, ins ->
            val bars = ins.getInsets(androidx.core.view.WindowInsetsCompat.Type.systemBars())
            root.setPadding(0, bars.top, 0, 0); ins
        }
    }

    override fun onResume() { super.onResume(); fill() }

    private fun head(t: String) = body.addView(EfbUi.text(this, t.uppercase(), 12f, EfbUi.DIM, bold = true)
        .apply { setPadding(dp(4), dp(18), dp(4), dp(6)) })

    private fun button(parent: LinearLayout, t: String, color: Int, go: () -> Unit) = parent.addView(TextView(this).apply {
        text = t; textSize = 13.5f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
        background = EfbUi.cardBg(this@FlightsActivity, color, 10); setPadding(dp(6), dp(12), dp(6), dp(12))
        setOnClickListener { go() }
    }, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(6); topMargin = dp(6) })

    private fun row(): LinearLayout = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }.also { body.addView(it) }

    private fun fill() {
        body.removeAllViews()
        val plan = FlightPlan.load(this)

        head("Current flight")
        val c = EfbUi.card(this).also { body.addView(it) }
        if (plan.points.size < 2) {
            c.addView(EfbUi.text(this, "No route yet. Plan one on the map (FPL), then come back.", 14f, EfbUi.DIM))
        } else {
            c.addView(EfbUi.text(this, plan.points.joinToString(" → ") { it.id }, 17f, EfbUi.TEXT, bold = true))
            c.addView(EfbUi.text(this, "%,d ft · %.0f nm · TAS %d kt · %.1f gal on board".format(
                plan.altitude, plan.summary().dist, plan.tas, plan.fuelOnBoard), 13f, EfbUi.DIM))
        }
        var r = row()
        button(r, "📋 Nav log", 0xFF0A84FF.toInt()) {
            startActivity(Intent(this, MapActivity::class.java).putExtra(MapActivity.EXTRA_NAVLOG, true))
        }
        button(r, "☁ Briefing", 0xFF5E5CE6.toInt()) { BriefingActivity.open(this) }
        button(r, "🌬 Winds", 0xFF48484A.toInt()) { WindSectionActivity.open(this) }
        r = row()
        button(r, "⚖ Weight & balance", 0xFF48484A.toInt()) { startActivity(Intent(this, WeightBalanceActivity::class.java)) }
        button(r, "📈 Performance", 0xFF48484A.toInt()) { startActivity(Intent(this, PerformanceActivity::class.java)) }
        r = row()
        button(r, "💾 Keep this flight", 0xFF2E7D32.toInt()) { keep(plan) }
        button(r, "🗺 Map", 0xFF48484A.toInt()) { startActivity(Intent(this, MapActivity::class.java)) }

        head("Kept flights")
        val kept = saved()
        if (kept.length() == 0) body.addView(EfbUi.text(this, "None yet: “Keep this flight” saves the route, height and fuel to load again.", 13f, EfbUi.DIM)
            .apply { setPadding(dp(4), 0, dp(4), 0) })
        for (i in kept.length() - 1 downTo 0) {
            val o = kept.optJSONObject(i) ?: continue
            val card = EfbUi.card(this).also { body.addView(it, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(6) }) }
            card.addView(EfbUi.text(this, o.optString("name"), 15.5f, EfbUi.TEXT, bold = true))
            card.addView(EfbUi.text(this, o.optString("when"), 12f, EfbUi.DIM))
            card.setOnClickListener {
                MaterialAlertDialogBuilder(this).setTitle(o.optString("name"))
                    .setMessage("Load this flight in place of the current one?")
                    .setPositiveButton("Load") { _, _ ->
                        VaultLock.prefs(this).edit().putString("flight_plan", o.optString("plan")).apply()
                        Toast.makeText(this, "Loaded", Toast.LENGTH_SHORT).show(); fill()
                    }
                    .setNeutralButton("Delete") { _, _ -> val a = saved(); a.remove(i); store(a); fill() }
                    .setNegativeButton("Cancel", null).show()
            }
        }

        head("Track logs")
        val dir = File(filesDir, "tracks")
        val files = dir.listFiles()?.filter { it.name.endsWith(".csv") }?.sortedByDescending { it.name }.orEmpty()
        if (files.isEmpty()) body.addView(EfbUi.text(this, "No tracks yet: the app records one each time it flies with the GPS on.", 13f, EfbUi.DIM)
            .apply { setPadding(dp(4), 0, dp(4), 0) })
        val fmt = SimpleDateFormat("EEE d MMM yyyy · HH:mm", Locale.US)
        for (f in files.take(60)) {
            val pts = Tracks.read(this, "tracks/${f.name}")
            if (pts.size < 2) continue
            var nm = 0.0
            for (k in 1 until pts.size) nm += Nav.distanceNm(pts[k - 1].lat, pts[k - 1].lon, pts[k].lat, pts[k].lon)
            val mins = (pts.last().time - pts.first().time) / 60000.0
            val top = pts.maxOf { it.altFt }
            val card = EfbUi.card(this).also { body.addView(it, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(6) }) }
            card.addView(EfbUi.text(this, fmt.format(Date(pts.first().time)), 15f, EfbUi.TEXT, bold = true))
            card.addView(EfbUi.text(this, "%s · %.0f nm · highest %,d ft".format(FlightPlan.hm(mins), nm, Math.round(top).toInt()), 12.5f, EfbUi.DIM))
            card.setOnClickListener { showTrack(f, pts) }
        }
    }

    private fun showTrack(f: File, pts: List<Tracks.Point>) {
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(12), dp(8), dp(12), 0) }
        box.addView(TrackView(this, pts), LinearLayout.LayoutParams(-1, dp(420)))
        val name = f.name.removeSuffix(".csv")
        MaterialAlertDialogBuilder(this).setTitle("Track log").setView(box)
            .setPositiveButton("GPX") { _, _ -> send("track_$name.gpx", Tracks.gpx(name, pts), "application/gpx+xml") }
            .setNeutralButton("KML (Google Earth)") { _, _ -> send("track_$name.kml", Tracks.kml(name, pts), "application/vnd.google-earth.kml+xml") }
            .setNegativeButton("Close", null).show()
    }

    private fun send(file: String, text: String, type: String) {
        val dir = File(cacheDir, "exports").apply { mkdirs() }
        val f = File(dir, file).apply { writeText(text) }
        val uri = FileProvider.getUriForFile(this, "$packageName.files", f)
        startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply {
            this.type = type; putExtra(Intent.EXTRA_STREAM, uri); addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }, file))
    }

    private fun saved(): JSONArray = try { JSONArray(VaultLock.prefs(this).getString("flights_kept", "[]")) } catch (e: Exception) { JSONArray() }
    private fun store(a: JSONArray) = VaultLock.prefs(this).edit().putString("flights_kept", a.toString()).apply()

    private fun keep(plan: FlightPlan) {
        if (plan.points.size < 2) { Toast.makeText(this, "No route to keep", Toast.LENGTH_SHORT).show(); return }
        val a = saved()
        a.put(JSONObject().put("name", plan.points.joinToString(" → ") { it.id })
            .put("when", SimpleDateFormat("d MMM yyyy HH:mm", Locale.US).format(Date()) + " · %,d ft".format(plan.altitude))
            .put("plan", plan.toJson().toString()))
        store(a)
        Toast.makeText(this, "Kept", Toast.LENGTH_SHORT).show()
        fill()
    }

    companion object {
        fun open(ctx: Context) = ctx.startActivity(Intent(ctx, FlightsActivity::class.java))
    }
}
