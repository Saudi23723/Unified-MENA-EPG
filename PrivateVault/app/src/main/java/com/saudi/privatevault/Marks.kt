package com.saudi.privatevault

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Point
import android.graphics.Typeface
import org.json.JSONArray
import org.json.JSONObject
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/**
 * Marked positions, as an EFB keeps them: one tap stores where the aeroplane is (or the middle of the
 * chart when there is no GPS) with the time and the height, numbered in order, drawn on the chart as
 * a magenta diamond, and listed to fly to, to put in the route or to send.
 */
object Marks {
    class Mark(val n: Int, val lat: Double, val lon: Double, val altFt: Int?, val time: Long) {
        val label get() = "M$n"
    }

    private fun prefs(ctx: Context) = VaultLock.prefs(ctx)

    fun all(ctx: Context): List<Mark> = try {
        val a = JSONArray(prefs(ctx).getString("marks", "[]"))
        (0 until a.length()).mapNotNull { a.optJSONObject(it) }.map {
            Mark(it.optInt("n"), it.optDouble("la"), it.optDouble("lo"), if (it.has("alt")) it.optInt("alt") else null, it.optLong("t"))
        }
    } catch (e: Exception) { emptyList() }

    private fun save(ctx: Context, list: List<Mark>) {
        val a = JSONArray()
        for (m in list) a.put(JSONObject().put("n", m.n).put("la", m.lat).put("lo", m.lon).put("t", m.time).apply { m.altFt?.let { put("alt", it) } })
        prefs(ctx).edit().putString("marks", a.toString()).apply()
    }

    fun add(ctx: Context, lat: Double, lon: Double, altFt: Int?): Mark {
        val list = all(ctx)
        val m = Mark((list.maxOfOrNull { it.n } ?: 0) + 1, lat, lon, altFt, System.currentTimeMillis())
        save(ctx, list + m)
        return m
    }

    fun remove(ctx: Context, n: Int) = save(ctx, all(ctx).filter { it.n != n })
    fun clear(ctx: Context) = save(ctx, emptyList())

    private val utc = SimpleDateFormat("HH:mm'Z'", Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") }
    fun timeOf(m: Mark): String = utc.format(Date(m.time))

    /** As a pilot reads a position out: degrees and decimal minutes. */
    fun dm(lat: Double, lon: Double): String {
        fun f(v: Double, pos: String, neg: String, w: Int): String {
            val a = Math.abs(v); val d = a.toInt(); val m = (a - d) * 60
            return "%0${w}d°%05.2f'%s".format(d, m, if (v >= 0) pos else neg)
        }
        return f(lat, "N", "S", 2) + " " + f(lon, "E", "W", 3)
    }
}

/** The marked positions on the chart. */
class MarksOverlay(private val map: MapView) : Overlay() {
    var marks: List<Marks.Mark> = emptyList()
    private val d = map.resources.displayMetrics.density
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFD81B60.toInt() }
    private val edge = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFFFFFF.toInt(); style = Paint.Style.STROKE; strokeWidth = 2f * d }
    private val tx = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFD81B60.toInt(); textSize = 12f * d; typeface = Typeface.DEFAULT_BOLD }
    private val halo = Paint(tx).apply { color = 0xFFFFFFFF.toInt(); style = Paint.Style.STROKE; strokeWidth = 3f * d }
    private val pt = Point()

    override fun draw(c: Canvas, mv: MapView, shadow: Boolean) {
        if (shadow || marks.isEmpty()) return
        val pr = mv.projection
        val r = 7f * d
        for (m in marks) {
            pr.toPixels(GeoPoint(m.lat, m.lon), pt)
            val x = pt.x.toFloat(); val y = pt.y.toFloat()
            val p = Path().apply { moveTo(x, y - r); lineTo(x + r, y); lineTo(x, y + r); lineTo(x - r, y); close() }
            c.drawPath(p, fill); c.drawPath(p, edge)
            val s = "${m.label} ${Marks.timeOf(m)}"
            c.save(); c.rotate(-mv.mapOrientation, x, y)
            c.drawText(s, x + r + 3 * d, y + 4 * d, halo); c.drawText(s, x + r + 3 * d, y + 4 * d, tx)
            c.restore()
        }
    }
}
