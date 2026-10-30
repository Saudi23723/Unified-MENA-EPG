package com.saudi.privatevault

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.provider.CalendarContract
import android.widget.Toast
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import org.json.JSONArray
import org.json.JSONObject
import org.osmdroid.config.Configuration
import org.osmdroid.tileprovider.cachemanager.CacheManager
import org.osmdroid.tileprovider.modules.SqlTileWriter
import org.osmdroid.util.BoundingBox
import java.io.File
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * Chart currency. Shown online, the charts are the FAA's own and always the
 * edition in force; what goes out of date is what was saved for flying
 * without signal. Every chart area and airport saved is remembered with its
 * edition, and when the FAA's cycle turns (56 days for VFR and IFR enroute
 * charts and the Chart Supplement, 28 days for procedures) they are fetched
 * again from the FAA by themselves on Wi-Fi, or with one tap. The cycle
 * dates can also go into the phone's calendar.
 */
object ChartUpdates {
    // An AIRAC date that is also a VFR chart date (the 56-day editions: 20 Feb 2025 … 29 Oct 2026).
    private val BASE = LocalDate.of(2025, 2, 20)
    private val CYCLE_LAYERS = setOf("sectional", "tac", "ifrlow")
    private var running = false

    /** The start of the cycle in force on a day, for a cycle of so many days. */
    fun cycleStart(days: Long, day: LocalDate = LocalDate.now()): LocalDate {
        var s = BASE
        while (!s.plusDays(days).isAfter(day)) s = s.plusDays(days)
        while (s.isAfter(day)) s = s.minusDays(days)
        return s
    }

    fun vfrEdition() = cycleStart(56).toString()
    fun airac() = cycleStart(28).toString()

    private fun file(ctx: Context) = File(ctx.filesDir, "aviation/offline_areas.json")

    private fun load(ctx: Context): JSONObject = try { JSONObject(file(ctx).readText()) } catch (e: Exception) { JSONObject() }

    private fun save(ctx: Context, o: JSONObject) {
        file(ctx).parentFile?.mkdirs()
        file(ctx).writeText(o.toString())
    }

    /** A chart area saved for offline use; the same area of the same chart replaces the older one. */
    fun rememberArea(ctx: Context, layer: String, box: BoundingBox, zMin: Int, zMax: Int) {
        if (layer !in CYCLE_LAYERS) return
        val o = load(ctx)
        val areas = o.optJSONArray("areas") ?: JSONArray()
        val key = "%s %.2f %.2f %.2f %.2f".format(Locale.US, layer, box.latNorth, box.lonEast, box.latSouth, box.lonWest)
        val keep = JSONArray()
        for (i in 0 until areas.length()) areas.optJSONObject(i)?.takeIf { it.optString("key") != key }?.let { keep.put(it) }
        keep.put(JSONObject().put("key", key).put("layer", layer).put("n", box.latNorth).put("e", box.lonEast)
            .put("s", box.latSouth).put("w", box.lonWest).put("z0", zMin).put("z1", zMax).put("ed", vfrEdition()))
        save(ctx, o.put("areas", keep))
    }

    /** Airports packed for offline use (plates, Chart Supplement, info), with the cycle they were packed in. */
    fun rememberAirports(ctx: Context, idents: List<String>, parts: OfflinePack.Parts) {
        val o = load(ctx)
        val apts = o.optJSONObject("airports") ?: JSONObject()
        for (id in idents) apts.put(id, JSONObject().put("airac", airac()).put("ed", vfrEdition())
            .put("plates", parts.plates).put("cs", parts.supplement).put("info", parts.info))
        save(ctx, o.put("airports", apts))
    }

    private fun areas(ctx: Context): List<JSONObject> = load(ctx).optJSONArray("areas")?.let { a -> (0 until a.length()).mapNotNull { a.optJSONObject(it) } } ?: emptyList()

    private fun airports(ctx: Context): List<Pair<String, JSONObject>> =
        load(ctx).optJSONObject("airports")?.let { o -> o.keys().asSequence().map { it to o.getJSONObject(it) }.toList() } ?: emptyList()

    private fun staleAreas(ctx: Context) = areas(ctx).filter { it.optString("ed") != vfrEdition() }
    private fun staleAirports(ctx: Context) = airports(ctx).filter { (_, a) ->
        (a.optBoolean("plates") && a.optString("airac") != airac()) || ((a.optBoolean("cs") || a.optBoolean("info")) && a.optString("ed") != vfrEdition())
    }

    fun outOfDate(ctx: Context) = staleAreas(ctx).size + staleAirports(ctx).size

    private fun unmetered(ctx: Context): Boolean {
        val cm = ctx.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED)
    }

    /** On opening the app: if anything saved is from an old cycle and the phone is on Wi-Fi, update it now. */
    fun autoUpdate(act: Activity) {
        val prefs = VaultLock.prefs(act)
        if (!prefs.getBoolean("charts_auto", true) || (outOfDate(act) == 0 && OfficialCharts.current(act))) return
        if (!unmetered(act)) {
            if (outOfDate(act) == 0) return
            // Not on Wi-Fi: say so once a day, and wait for Wi-Fi.
            val day = LocalDate.now().toString()
            if (prefs.getString("charts_told", "") != day) {
                prefs.edit().putString("charts_told", day).apply()
                Toast.makeText(act, act.getString(R.string.charts_wait_wifi, outOfDate(act)), Toast.LENGTH_LONG).show()
            }
            return
        }
        update(act, quiet = true)
    }

    /** Fetches again, from the FAA, every saved chart area and airport that is out of date. */
    fun update(act: Activity, quiet: Boolean) {
        if (running) return
        val ctx = act.applicationContext
        val areas = staleAreas(ctx)
        val apts = staleAirports(ctx)
        // The FAA's own charts for the edition in force.
        if (!OfficialCharts.current(ctx)) {
            if (!quiet) Toast.makeText(act, R.string.charts_official_loading, Toast.LENGTH_LONG).show()
            Thread {
                val ed = try { OfficialCharts.update(ctx) } catch (e: Throwable) { null }
                android.os.Handler(android.os.Looper.getMainLooper()).post {
                    val now = OfficialCharts.current(ctx)
                    if (now && ed != null) Toast.makeText(ctx, ctx.getString(R.string.charts_official_done, ed), Toast.LENGTH_LONG).show()
                    else if (!quiet) Toast.makeText(ctx, R.string.charts_official_none, Toast.LENGTH_LONG).show()
                }
            }.start()
        }
        if (areas.isEmpty() && apts.isEmpty()) {
            if (!quiet && OfficialCharts.current(ctx)) Toast.makeText(act, R.string.charts_current, Toast.LENGTH_LONG).show()
            return
        }
        running = true
        Toast.makeText(act, act.getString(R.string.charts_updating, areas.size + apts.size), Toast.LENGTH_LONG).show()
        Thread {
            try {
                // The airports' plates, Chart Supplement and info for the new cycle.
                val all = AviationData.airports(ctx)
                val done = ArrayList<String>()
                for ((id, p) in apts) {
                    val a = all.firstOrNull { it.icao == id || it.ident == id } ?: continue
                    val parts = OfflinePack.Parts(info = p.optBoolean("info"), diagram = false, supplement = p.optBoolean("cs"), plates = p.optBoolean("plates"))
                    try { OfflinePack.airport(ctx, a, parts) {}; done.add(id) } catch (e: Exception) {}
                }
                if (done.isNotEmpty()) {
                    val o = load(ctx)
                    val obj = o.optJSONObject("airports") ?: JSONObject()
                    for (id in done) obj.optJSONObject(id)?.put("airac", airac())?.put("ed", vfrEdition())
                    save(ctx, o.put("airports", obj))
                }
                tiles(ctx, areas)
            } catch (e: Throwable) {
            } finally {
                finish(ctx)
            }
        }.start()
    }

    /** The chart tiles of each out-of-date area, fetched again over the old edition (kept where a fetch fails). */
    private fun tiles(ctx: Context, areas: List<JSONObject>) {
        if (areas.isEmpty()) return
        Configuration.getInstance().apply {
            userAgentValue = ctx.packageName
            osmdroidBasePath = File(ctx.filesDir, "osmdroid")
            osmdroidTileCache = File(ctx.filesDir, "osmdroid/tiles")
        }
        val writer = SqlTileWriter()
        try {
            for (area in areas) {
                val layer = AviationData.LAYERS.firstOrNull { it.key == area.optString("layer") } ?: continue
                val box = BoundingBox(area.getDouble("n"), area.getDouble("e"), area.getDouble("s"), area.getDouble("w"))
                val z0 = area.getInt("z0")
                val z1 = area.getInt("z1")
                val source = layer.source()
                val cm = try { CacheManager(source, writer, z0, z1) } catch (e: Exception) { continue }
                var failed = 0
                for (tile in CacheManager.getTilesCoverage(box, z0, z1)) {
                    if (!cm.forceLoadTile(source, tile)) failed++
                    if (failed > 30) break
                }
                if (failed <= 30) mark(ctx, area)
            }
        } catch (e: Throwable) {
        }
        // The tile store is shared with the map: left open.
    }

    private fun mark(ctx: Context, area: JSONObject) {
        val o = load(ctx)
        val arr = o.optJSONArray("areas") ?: return
        for (i in 0 until arr.length()) arr.optJSONObject(i)?.takeIf { it.optString("key") == area.optString("key") }?.put("ed", vfrEdition())
        save(ctx, o)
    }

    private fun finish(ctx: Context) {
        running = false
        android.os.Handler(android.os.Looper.getMainLooper()).post {
            Toast.makeText(ctx, if (outOfDate(ctx) == 0) R.string.charts_updated else R.string.charts_partly, Toast.LENGTH_LONG).show()
        }
    }

    private val SHOW = DateTimeFormatter.ofPattern("d MMM yyyy", Locale.US)

    /** The status lines: each cycle, how long it has left, and what is saved. */
    fun status(ctx: Context): String {
        val today = LocalDate.now()
        val v = cycleStart(56); val vn = v.plusDays(56)
        val p = cycleStart(28); val pn = p.plusDays(28)
        val left = { d: LocalDate -> java.time.temporal.ChronoUnit.DAYS.between(today, d) }
        val stale = outOfDate(ctx)
        return "VFR / IFR charts + Chart Supplement\n  ${SHOW.format(v)} → ${SHOW.format(vn)}  (${left(vn)} d left)\n" +
            "Procedures (AIRAC ${AviationData.airacCycle()})\n  ${SHOW.format(p)} → ${SHOW.format(pn)}  (${left(pn)} d left)\n\n" +
            "Official FAA GeoTIFF: " + OfficialCharts.describe(ctx) + "\n" +
            ctx.getString(R.string.charts_saved, areas(ctx).size, airports(ctx).size) +
            if (stale > 0) "\n⚠ " + ctx.getString(R.string.charts_stale, stale) else "\n✅ " + ctx.getString(R.string.charts_ok)
    }

    /** The chart-currency page: status, update now, update by itself on Wi-Fi, and the calendar. */
    fun show(act: Activity) {
        val prefs = VaultLock.prefs(act)
        val auto = prefs.getBoolean("charts_auto", true)
        MaterialAlertDialogBuilder(act)
            .setTitle(R.string.charts_title)
            .setMessage(status(act))
            .setPositiveButton(R.string.charts_update_now) { _, _ -> update(act, quiet = false) }
            .setNeutralButton(R.string.charts_calendar) { _, _ -> calendar(act) }
            .setNegativeButton(if (auto) R.string.charts_auto_off else R.string.charts_auto_on) { _, _ ->
                prefs.edit().putBoolean("charts_auto", !auto).apply()
                Toast.makeText(act, if (!auto) R.string.charts_auto_on_done else R.string.charts_auto_off_done, Toast.LENGTH_SHORT).show()
            }
            .show()
    }

    /** A repeating all-day event in the phone's calendar on each new cycle date. */
    private fun calendar(act: Activity) {
        val items = arrayOf(act.getString(R.string.charts_cal_vfr), act.getString(R.string.charts_cal_airac))
        MaterialAlertDialogBuilder(act).setTitle(R.string.charts_calendar).setItems(items) { _, i ->
            val days = if (i == 0) 56L else 28L
            val next = cycleStart(days).plusDays(days)
            val start = next.atStartOfDay(java.time.ZoneOffset.UTC).toInstant().toEpochMilli()
            val intent = Intent(Intent.ACTION_INSERT).setData(CalendarContract.Events.CONTENT_URI)
                .putExtra(CalendarContract.Events.TITLE, if (i == 0) "✈️ New FAA charts (VFR/IFR + Chart Supplement) — update SSEFB" else "✈️ New AIRAC cycle (procedures) — update SSEFB")
                .putExtra(CalendarContract.Events.DESCRIPTION, "Open SSEFB on Wi-Fi: saved charts and airports update from the FAA. Every $days days.")
                .putExtra(CalendarContract.EXTRA_EVENT_ALL_DAY, true)
                .putExtra(CalendarContract.EXTRA_EVENT_BEGIN_TIME, start)
                .putExtra(CalendarContract.EXTRA_EVENT_END_TIME, start + 86400000L)
                .putExtra(CalendarContract.Events.RRULE, "FREQ=DAILY;INTERVAL=$days")
                .putExtra(CalendarContract.Events.HAS_ALARM, 1)
            try {
                VaultLock.keepUnlockedOnce = true
                act.startActivity(intent)
            } catch (e: Exception) {
                VaultLock.keepUnlockedOnce = false
                Toast.makeText(act, R.string.charts_no_calendar, Toast.LENGTH_LONG).show()
            }
        }.show()
    }
}
