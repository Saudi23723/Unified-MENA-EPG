package com.saudi.privatevault

import android.content.Context
import android.graphics.Canvas
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Shader
import android.view.View

/**
 * A flight's recorded track, drawn: the ground track from above (coloured by altitude, green at
 * the start, a square where it ended), and under it the altitude profile against time.
 */
class TrackView(ctx: Context, private val pts: List<Tracks.Point>) : View(ctx) {
    private val d = ctx.resources.displayMetrics.density
    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 3 * d; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val txt = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFB8C4CE.toInt(); textSize = 11 * d }
    private val grid = Paint().apply { color = 0x22FFFFFF; strokeWidth = 1f }

    override fun onMeasure(w: Int, h: Int) {
        val width = MeasureSpec.getSize(w)
        setMeasuredDimension(width, (width * 0.95f).toInt())
    }

    private fun altColor(f: Float): Int {
        // Low → high: green, yellow, orange, magenta.
        val stops = intArrayOf(0xFF33D17A.toInt(), 0xFFF6D32D.toInt(), 0xFFFF8A3D.toInt(), 0xFFE040FB.toInt())
        val x = (f.coerceIn(0f, 1f) * (stops.size - 1))
        val i = x.toInt().coerceAtMost(stops.size - 2)
        return android.animation.ArgbEvaluator().evaluate(x - i, stops[i], stops[i + 1]) as Int
    }

    override fun onDraw(c: Canvas) {
        if (pts.size < 2) return
        c.drawColor(0xFF0B1116.toInt())
        val w = width.toFloat(); val mapH = height * 0.68f; val pad = 14 * d
        val minLat = pts.minOf { it.lat }; val maxLat = pts.maxOf { it.lat }
        val minLon = pts.minOf { it.lon }; val maxLon = pts.maxOf { it.lon }
        val k = Math.cos(Math.toRadians((minLat + maxLat) / 2))
        val spanX = ((maxLon - minLon) * k).coerceAtLeast(1e-4); val spanY = (maxLat - minLat).coerceAtLeast(1e-4)
        val sc = minOf((w - 2 * pad) / spanX, (mapH - 2 * pad) / spanY)
        val ox = (w - spanX * sc) / 2; val oy = (mapH - spanY * sc) / 2
        fun x(p: Tracks.Point) = (ox + (p.lon - minLon) * k * sc).toFloat()
        fun y(p: Tracks.Point) = (oy + (maxLat - p.lat) * sc).toFloat()
        val lo = pts.minOf { it.altFt }; val hi = pts.maxOf { it.altFt }.coerceAtLeast(lo + 1)
        for (i in 1 until pts.size) {
            line.color = altColor(((pts[i].altFt - lo) / (hi - lo)).toFloat())
            c.drawLine(x(pts[i - 1]), y(pts[i - 1]), x(pts[i]), y(pts[i]), line)
        }
        fill.color = 0xFF33D17A.toInt(); c.drawCircle(x(pts.first()), y(pts.first()), 6 * d, fill)
        fill.color = 0xFFFFFFFF.toInt(); val e = pts.last(); c.drawRect(x(e) - 5 * d, y(e) - 5 * d, x(e) + 5 * d, y(e) + 5 * d, fill)
        // Scale bar: one nautical mile.
        val nm = (sc / 60.0).toFloat()
        if (nm in 8 * d..w / 2) {
            line.color = 0xFFB8C4CE.toInt(); line.strokeWidth = 2 * d
            c.drawLine(pad, mapH - pad, pad + nm, mapH - pad, line); c.drawText("1 NM", pad, mapH - pad - 5 * d, txt)
            line.strokeWidth = 3 * d
        }
        // Altitude profile.
        val top = mapH + 18 * d; val bot = height - 16 * d
        val t0 = pts.first().time; val t1 = pts.last().time.coerceAtLeast(t0 + 1)
        for (g in 0..3) { val gy = top + (bot - top) * g / 3; c.drawLine(pad, gy, w - pad, gy, grid) }
        val path = Path(); val area = Path()
        pts.forEachIndexed { i, p ->
            val px = pad + (w - 2 * pad) * (p.time - t0).toFloat() / (t1 - t0)
            val py = (bot - (bot - top) * ((p.altFt - lo) / (hi - lo))).toFloat()
            if (i == 0) { path.moveTo(px, py); area.moveTo(px, bot); area.lineTo(px, py) } else { path.lineTo(px, py); area.lineTo(px, py) }
        }
        area.lineTo(w - pad, bot); area.close()
        fill.shader = LinearGradient(0f, top, 0f, bot, 0x6633A1FF, 0x0533A1FF, Shader.TileMode.CLAMP)
        c.drawPath(area, fill); fill.shader = null
        line.color = 0xFF33A1FF.toInt(); line.strokeWidth = 2 * d
        c.drawPath(path, line); line.strokeWidth = 3 * d
        c.drawText("%,.0f ft".format(hi), pad, top - 4 * d, txt)
        c.drawText("%,.0f ft".format(lo), pad, bot + 12 * d, txt)
        val mins = (t1 - t0) / 60000
        val s = "%d:%02d".format(mins / 60, mins % 60)
        c.drawText(s, w - pad - txt.measureText(s), bot + 12 * d, txt)
    }
}
