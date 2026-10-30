package com.saudi.privatevault

import android.content.Context
import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Point
import android.view.MotionEvent
import org.json.JSONArray
import org.json.JSONObject
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay
import java.io.File
import java.net.URLEncoder

/**
 * Controlled and special use airspace from the FAA's own data (the same
 * source the charts are made from): Class B, C and D with their floors and
 * ceilings, restricted, prohibited, warning and alert areas and MOAs. Kept
 * on the phone, drawn over the chart, and checked against the aircraft's
 * position and altitude.
 */
object Airspace {
    class Area(
        val kind: String, val name: String, val lowFt: Int?, val highFt: Int?, val low: String, val high: String,
        val rings: List<DoubleArray>, val note: String,
    ) {
        var minLat = 90.0; var maxLat = -90.0; var minLon = 180.0; var maxLon = -180.0
        init {
            for (r in rings) for (i in r.indices step 2) {
                minLat = minOf(minLat, r[i]); maxLat = maxOf(maxLat, r[i]); minLon = minOf(minLon, r[i + 1]); maxLon = maxOf(maxLon, r[i + 1])
            }
        }

        fun contains(lat: Double, lon: Double): Boolean {
            if (lat < minLat || lat > maxLat || lon < minLon || lon > maxLon) return false
            var inside = false
            for (r in rings) {
                var j = r.size - 2
                for (i in r.indices step 2) {
                    if ((r[i] > lat) != (r[j] > lat) && lon < (r[j + 1] - r[i + 1]) * (lat - r[i]) / (r[j] - r[i]) + r[i + 1]) inside = !inside
                    j = i
                }
            }
            return inside
        }

        /** Whether an altitude in feet MSL is within its floor and ceiling (unknown limits count as in). */
        fun spans(ft: Double) = (lowFt == null || ft >= lowFt - 100) && (highFt == null || ft <= highFt + 100)

        fun limits() = "${high.ifEmpty { "?" }} / ${low.ifEmpty { "?" }}"
    }

    private const val BASE = "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services"

    // The West, from the Pacific to the Rockies.
    private const val BOX = "-125.5,31.0,-102.0,49.5"

    private fun s(o: JSONObject, vararg keys: String): String {
        for (k in keys) { val v = o.optString(k); if (v.isNotEmpty() && v != "null") return v }
        return ""
    }

    private fun feet(value: String, uom: String, code: String): Int? {
        val v = value.trim().uppercase()
        if (v.isEmpty()) return null
        if (v == "SFC" || v == "GND" || code.uppercase() == "SFC") return 0
        val n = v.replace(Regex("[^0-9.]"), "").toDoubleOrNull() ?: return null
        return if (uom.uppercase().contains("FL") || v.startsWith("FL")) (n * 100).toInt() else n.toInt()
    }

    /** Page by page, each page turned into areas at once, so only one page of the FAA's answer is held. */
    private fun query(layer: String, where: String, sua: Boolean): List<Area> {
        val all = ArrayList<Area>()
        var offset = 0
        while (true) {
            val url = "$BASE/$layer/FeatureServer/0/query?where=" + URLEncoder.encode(where, "UTF-8") +
                "&geometry=$BOX&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects" +
                "&outFields=*&returnGeometry=true&outSR=4326&geometryPrecision=4&maxAllowableOffset=0.0015&f=json&resultOffset=$offset&resultRecordCount=500"
            val j = JSONObject(AviationData.get(url, 60000))
            if (j.has("error")) throw java.io.IOException(j.optJSONObject("error")?.optString("message"))
            val f = j.optJSONArray("features") ?: break
            all.addAll(parse(f, sua))
            if (!j.optBoolean("exceededTransferLimit") || f.length() == 0) break
            offset += f.length()
        }
        return all
    }

    private fun parse(features: JSONArray, sua: Boolean): List<Area> {
        val out = ArrayList<Area>()
        for (i in 0 until features.length()) {
            val o = features.getJSONObject(i)
            val a = o.optJSONObject("attributes") ?: continue
            val g = o.optJSONObject("geometry")?.optJSONArray("rings") ?: continue
            val kind = if (sua) s(a, "TYPE_CODE", "TYPE", "LOCAL_TYPE").uppercase()
                else s(a, "CLASS", "LOCAL_TYPE", "TYPE_CODE").uppercase().removePrefix("CLASS_").removePrefix("CLASS ")
            if (!sua && kind !in setOf("B", "C", "D")) continue
            val rings = (0 until g.length()).map { r ->
                val ring = g.getJSONArray(r)
                DoubleArray(ring.length() * 2).also { d -> for (k in 0 until ring.length()) { val p = ring.getJSONArray(k); d[2 * k] = p.getDouble(1); d[2 * k + 1] = p.getDouble(0) } }
            }
            val low = s(a, "LOWER_VAL", "LOWER_DESC", "LOWALT")
            val high = s(a, "UPPER_VAL", "UPPER_DESC", "HIGHALT")
            val lowUom = s(a, "LOWER_UOM"); val highUom = s(a, "UPPER_UOM")
            out.add(Area(
                kind, s(a, "NAME", "IDENT"),
                feet(low, lowUom, s(a, "LOWER_CODE")), feet(high, highUom, s(a, "UPPER_CODE")),
                (low + if (lowUom.isNotEmpty() && lowUom != "FT") " $lowUom" else "").trim(),
                (high + if (highUom.isNotEmpty() && highUom != "FT") " $highUom" else "").trim(),
                rings,
                listOf(s(a, "TIMESOFUSE", "TIMES_OF_USE"), s(a, "CONT_AGENT", "CONTROLLING_AGENCY", "CITY")).filter { it.isNotEmpty() }.joinToString(" · "),
            ))
        }
        return out
    }

    @Volatile var areas: List<Area> = emptyList()

    /**
     * Loads the West's airspace: from the phone, refreshed from the FAA every 28 days.
     * Kept in a compact form of its own (written piece by piece), never as the FAA's
     * whole answer in one string, which does not fit in a phone's memory.
     */
    fun load(ctx: Context): List<Area> {
        val file = File(ctx.filesDir, "aviation/airspace2.json")
        File(ctx.filesDir, "aviation/airspace.json").delete()
        val fresh = file.exists() && System.currentTimeMillis() - file.lastModified() < 28L * 86400000
        if (!fresh) try {
            val cls = try { query("Class_Airspace", "CLASS IN ('B','C','D')", false) } catch (e: Exception) {
                try { query("Class_Airspace", "1=1", false) } catch (e2: Exception) { null }
            }
            val sua = try { query("Special_Use_Airspace", "1=1", true) } catch (e: Exception) { null }
            if (cls != null || sua != null) {
                val list = (cls ?: emptyList()) + (sua ?: emptyList())
                write(file, list)
                areas = list
                return list
            }
        } catch (e: Throwable) {
            // Out of memory or the FAA away: the copy on the phone stays.
        }
        if (file.exists()) try { areas = read(file) } catch (e: Throwable) { }
        return areas
    }

    private fun write(file: File, list: List<Area>) {
        file.parentFile?.mkdirs()
        val tmp = File(file.path + ".tmp")
        android.util.JsonWriter(tmp.bufferedWriter()).use { w ->
            w.beginArray()
            for (a in list) {
                w.beginObject()
                w.name("k").value(a.kind).name("n").value(a.name)
                a.lowFt?.let { w.name("lf").value(it.toLong()) }
                a.highFt?.let { w.name("hf").value(it.toLong()) }
                w.name("l").value(a.low).name("h").value(a.high).name("no").value(a.note)
                w.name("r").beginArray()
                for (r in a.rings) { w.beginArray(); for (v in r) w.value(Math.round(v * 10000) / 10000.0); w.endArray() }
                w.endArray()
                w.endObject()
            }
            w.endArray()
        }
        tmp.renameTo(file)
    }

    private fun read(file: File): List<Area> {
        val out = ArrayList<Area>()
        android.util.JsonReader(file.bufferedReader()).use { r ->
            r.beginArray()
            while (r.hasNext()) {
                var k = ""; var n = ""; var lf: Int? = null; var hf: Int? = null; var l = ""; var h = ""; var no = ""
                val rings = ArrayList<DoubleArray>()
                r.beginObject()
                while (r.hasNext()) when (r.nextName()) {
                    "k" -> k = r.nextString(); "n" -> n = r.nextString(); "lf" -> lf = r.nextInt(); "hf" -> hf = r.nextInt()
                    "l" -> l = r.nextString(); "h" -> h = r.nextString(); "no" -> no = r.nextString()
                    "r" -> {
                        r.beginArray()
                        while (r.hasNext()) {
                            val pts = ArrayList<Double>()
                            r.beginArray(); while (r.hasNext()) pts.add(r.nextDouble()); r.endArray()
                            rings.add(pts.toDoubleArray())
                        }
                        r.endArray()
                    }
                    else -> r.skipValue()
                }
                r.endObject()
                out.add(Area(k, n, lf, hf, l, h, rings, no))
            }
            r.endArray()
        }
        return out
    }

    fun color(kind: String): Int = when (kind) {
        "B" -> 0xFF1565C0.toInt()
        "C" -> 0xFFAD1457.toInt()
        "D" -> 0xFF1E88E5.toInt()
        "R", "P" -> 0xFFD50000.toInt()
        "MOA" -> 0xFF8E24AA.toInt()
        "W", "A" -> 0xFF6D4C41.toInt()
        else -> 0xFF546E7A.toInt()
    }

    fun spoken(kind: String) = when (kind) {
        "B" -> "Class Bravo"
        "C" -> "Class Charlie"
        "D" -> "Class Delta"
        "R" -> "Restricted area"
        "P" -> "Prohibited area"
        "MOA" -> "M O A"
        "W" -> "Warning area"
        "A" -> "Alert area"
        else -> "Airspace"
    }
}

/** The airspace drawn as charts draw it, with floors and ceilings; a tap names what is underneath. */
class AirspaceOverlay(map: MapView) : Overlay() {
    var onPick: ((List<String>) -> Unit)? = null
    private val d = map.resources.displayMetrics.density
    private val edge = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 11 * d; isFakeBoldText = true; textAlign = Paint.Align.CENTER }
    private val halo = Paint(label).apply { style = Paint.Style.STROKE; strokeWidth = 3 * d; color = 0xEEFFFFFF.toInt() }
    private val dashed = DashPathEffect(floatArrayOf(10 * d, 6 * d), 0f)
    private val pt = Point()

    override fun draw(c: Canvas, mapView: MapView, shadow: Boolean) {
        if (shadow || mapView.zoomLevelDouble < 7) return
        val box = mapView.boundingBox
        val pr = mapView.projection
        for (a in Airspace.areas) {
            if (a.maxLat < box.latSouth || a.minLat > box.latNorth || a.maxLon < box.lonWest || a.minLon > box.lonEast) continue
            val color = Airspace.color(a.kind)
            val path = Path()
            var sx = 0f; var sy = 0f; var n = 0
            for (r in a.rings) {
                for (i in r.indices step 2) {
                    pr.toPixels(GeoPoint(r[i], r[i + 1]), pt)
                    if (i == 0) path.moveTo(pt.x.toFloat(), pt.y.toFloat()) else path.lineTo(pt.x.toFloat(), pt.y.toFloat())
                    sx += pt.x; sy += pt.y; n++
                }
                path.close()
            }
            val restricted = a.kind == "R" || a.kind == "P"
            if (restricted || a.kind == "B") {
                fill.color = (color and 0x00FFFFFF) or 0x14000000
                c.drawPath(path, fill)
            }
            edge.color = color
            edge.strokeWidth = (if (a.kind == "B") 3f else 2f) * d
            edge.pathEffect = if (a.kind == "D" || a.kind == "MOA") dashed else null
            c.drawPath(path, edge)
            if (mapView.zoomLevelDouble >= 9 && n > 0) {
                val text = if (a.kind in setOf("B", "C", "D")) a.limits() else "${a.kind} ${a.name}".take(22)
                label.color = color
                c.save()
                c.rotate(-mapView.mapOrientation, sx / n, sy / n)
                c.drawText(text, sx / n, sy / n, halo)
                c.drawText(text, sx / n, sy / n, label)
                c.restore()
            }
        }
    }

    override fun onSingleTapConfirmed(e: MotionEvent, mapView: MapView): Boolean {
        val g = mapView.projection.fromPixels(e.x.toInt(), e.y.toInt())
        val hits = Airspace.areas.filter { it.contains(g.latitude, g.longitude) }
        if (hits.isEmpty()) return false
        onPick?.invoke(hits.map { a ->
            val kind = if (a.kind.length == 1 && a.kind[0] in "BCD") "Class ${a.kind}" else Airspace.spoken(a.kind)
            "$kind · ${a.name}\nCeiling ${a.high.ifEmpty { "?" }} · Floor ${a.low.ifEmpty { "?" }}" + (if (a.note.isNotEmpty()) "\n${a.note}" else "")
        })
        return true
    }
}
