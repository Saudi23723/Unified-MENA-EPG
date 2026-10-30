package com.saudi.privatevault

import android.content.Context
import org.json.JSONObject
import java.io.File
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * Where each kind of data comes from, which edition is in force, and until
 * when: the dates shown on the chart and the page a pilot shows an
 * instructor or examiner. The FAA's chart service is also asked what it
 * says about its own edition, so what is shown is the service's word.
 */
object DataCurrency {
    private val SHOW = DateTimeFormatter.ofPattern("d MMM yyyy", Locale.US)
    private val SHORT = DateTimeFormatter.ofPattern("d MMM", Locale.US)
    private const val FAA_TILES = "https://tiles.arcgis.com/tiles/ssFJjBXIUyZDrSYZ/arcgis/rest/services"

    class Row(val what: String, val source: String, val edition: String, val ok: Boolean?, val note: String = "")

    fun vfr(): Pair<LocalDate, LocalDate> = ChartUpdates.cycleStart(56).let { it to it.plusDays(56) }
    fun airac(): Pair<LocalDate, LocalDate> = ChartUpdates.cycleStart(28).let { it to it.plusDays(28) }

    /** The line on the chart: the VFR edition in force and the procedures' cycle. */
    fun mapLine(ctx: Context): Pair<String, Boolean> {
        val (a, b) = vfr()
        val stale = ChartUpdates.outOfDate(ctx)
        val text = "VFR ${SHORT.format(a)} – ${SHORT.format(b.minusDays(1))} · AIRAC ${AviationData.airacCycle()}" +
            (if (OfficialCharts.current(ctx)) " · FAA GeoTIFF" else "") +
            if (stale > 0) " · ⚠ $stale" else " ✓"
        return text to (stale == 0)
    }

    /**
     * What the FAA's tile service writes about its edition (description or credits), kept a day.
     * Called off the main thread.
     */
    fun serviceEdition(ctx: Context, service: String): String {
        val prefs = VaultLock.prefs(ctx)
        val key = "svc_ed_$service"
        val at = prefs.getLong("${key}_at", 0)
        if (System.currentTimeMillis() - at < 86400000L) return prefs.getString(key, "") ?: ""
        val text = try {
            val j = JSONObject(AviationData.get("$FAA_TILES/$service/MapServer?f=json", 15000))
            listOf("description", "serviceDescription", "copyrightText")
                .map { j.optString(it).replace(Regex("<[^>]+>"), " ").replace(Regex("\\s+"), " ").trim() }
                .filter { it.isNotEmpty() }.distinct().joinToString(" · ").take(220)
        } catch (e: Exception) {
            return prefs.getString(key, "") ?: ""
        }
        prefs.edit().putString(key, text).putLong("${key}_at", System.currentTimeMillis()).apply()
        return text
    }

    private fun age(f: File): String {
        if (!f.exists()) return "—"
        val h = (System.currentTimeMillis() - f.lastModified()) / 3600000
        return if (h < 48) "${h} h" else "${h / 24} d"
    }

    /** Every source, with its edition and validity. Called off the main thread. */
    fun rows(ctx: Context): List<Row> {
        val (va, vb) = vfr()
        val (pa, pb) = airac()
        val today = LocalDate.now()
        val vfrDates = "${SHOW.format(va)} → ${SHOW.format(vb.minusDays(1))}"
        val stale = ChartUpdates.outOfDate(ctx)
        val av = File(ctx.filesDir, "aviation")
        return listOf(
            Row("VFR Sectional / TAC", "FAA Aeronautical Information Services (tiles.arcgis.com · FAA AIS)",
                "56-day cycle: $vfrDates", stale == 0,
                serviceEdition(ctx, "VFR_Sectional").ifEmpty { "Online: the FAA service. Offline: saved tiles" + if (stale > 0) " ($stale saved areas from an old edition)" else ", current edition" }),
            Row("VFR charts, official GeoTIFF (offline)", "FAA AIS GeoTIFF (aeronav.faa.gov), as WebP tiles",
                OfficialCharts.describe(ctx), if (OfficialCharts.edition(ctx) == null) null else OfficialCharts.current(ctx),
                if (OfficialCharts.edition(ctx) == null) "Not on this phone yet: Chart updates → download" else "Drawn over the chart where it covers"),
            Row("IFR Enroute Low", "FAA AIS (tiles.arcgis.com · FAA AIS)", "56-day cycle: $vfrDates", stale == 0),
            Row("Terminal procedures (plates, airport diagrams)", "FAA d-TPP (aeronav.faa.gov)",
                "AIRAC ${AviationData.airacCycle()}: ${SHOW.format(pa)} → ${SHOW.format(pb.minusDays(1))}", pb.isAfter(today)),
            Row("Chart Supplement", "FAA (aeronav.faa.gov)", "Edition ${OfflinePack.csEdition()} · 56-day: $vfrDates", true),
            Row("Airports", "FAA AIS (US_Airport)", "Refreshed every 28 days · last ${age(File(av, "airports_us.json"))} ago",
                File(av, "airports_us.json").let { it.exists() && System.currentTimeMillis() - it.lastModified() < 28L * 86400000 }),
            Row("Airspace (B/C/D, special use)", "FAA AIS (Class_Airspace, Special_Use_Airspace)",
                "Refreshed every 28 days · last ${age(File(av, "airspace2.json"))} ago",
                File(av, "airspace2.json").let { it.exists() && System.currentTimeMillis() - it.lastModified() < 28L * 86400000 },
                "Boundaries simplified to about 150 m for the drawing and alerts; the chart is the reference"),
            Row("NOTAMs", "FAA NOTAM Search / FAA NOTAM API", "Live when online; saved copy shows its time", null),
            Row("TFRs", "FAA (tfr.faa.gov)", "Live when online", null),
            Row("METAR / TAF / winds / AIRMET / SIGMET / PIREP", "NWS Aviation Weather Center (aviationweather.gov)", "Live when online", null),
            Row("Radar", "NEXRAD composite (Iowa Environmental Mesonet)", "Every 5 minutes", null, "Advisory only, a few minutes old"),
            Row("Terrain", "AWS Terrain Tiles (not FAA)", "—", null, "Awareness only: not certified terrain data"),
            Row("Traffic", "ADS-B receiver (GDL 90) or airplanes.live", "Live", null, "Awareness only: not for separation; see and avoid"),
            Row("GPS position", "The phone's GPS", "—", null, "Not a certified navigator: VFR situational awareness"),
        )
    }
}
