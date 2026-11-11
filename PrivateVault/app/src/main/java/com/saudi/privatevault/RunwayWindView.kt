package com.saudi.privatevault

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.view.View
import kotlin.math.cos
import kotlin.math.min
import kotlin.math.sin

/**
 * The field's runways laid out by heading inside a compass rose, the wind as an arrow blowing
 * across them, and the runway end the wind favours in green — the picture an EFB shows at the
 * top of an airport's runway page.
 */
class RunwayWindView(ctx: Context) : View(ctx) {
    /** A runway: its ends ("09", "27L"), its magnetic heading (of the first end), its length. */
    class Rwy(val ends: List<String>, val hdg: Double, val lengthFt: Int)

    var rwys: List<Rwy> = emptyList()
    var windFromMag: Double? = null
    var windKt = 0.0
    var gustKt: Double? = null
    var best: String? = null

    private val d = resources.displayMetrics.density
    private val p = Paint(Paint.ANTI_ALIAS_FLAG)
    private val t = Paint(Paint.ANTI_ALIAS_FLAG).apply { textAlign = Paint.Align.CENTER; typeface = EfbUi.MEDIUM }

    override fun onMeasure(w: Int, h: Int) {
        val width = MeasureSpec.getSize(w)
        setMeasuredDimension(width, min(width, (260 * d).toInt()))
    }

    override fun onDraw(c: Canvas) {
        val cx = width / 2f; val cy = height / 2f
        val rad = min(width, height) / 2f - 18 * d
        // The rose.
        p.style = Paint.Style.FILL; p.color = EfbUi.CARD; c.drawCircle(cx, cy, rad + 14 * d, p)
        p.style = Paint.Style.STROKE; p.strokeWidth = 1 * d; p.color = EfbUi.CARD_LINE; c.drawCircle(cx, cy, rad, p)
        for (k in 0 until 72) {
            val a = Math.toRadians(k * 5.0)
            val long = k % 6 == 0
            val r0 = rad - (if (long) 9 else 4) * d
            p.color = if (long) EfbUi.DIM else EfbUi.CARD_LINE
            c.drawLine(cx + (r0 * sin(a)).toFloat(), cy - (r0 * cos(a)).toFloat(), cx + (rad * sin(a)).toFloat(), cy - (rad * cos(a)).toFloat(), p)
        }
        t.textSize = 11 * d; t.color = EfbUi.DIM
        for ((k, s) in listOf("N", "3", "6", "E", "12", "15", "S", "21", "24", "W", "30", "33").withIndex()) {
            val a = Math.toRadians(k * 30.0); val r1 = rad - 20 * d
            t.color = if (k % 3 == 0) EfbUi.TEXT else EfbUi.DIM
            c.drawText(s, cx + (r1 * sin(a)).toFloat(), cy - (r1 * cos(a)).toFloat() + 4 * d, t)
        }

        // Runways, the longest the longest.
        val maxLen = (rwys.maxOfOrNull { it.lengthFt } ?: 1).coerceAtLeast(1)
        for (r in rwys) {
            val half = (rad - 34 * d) * (0.55f + 0.45f * r.lengthFt / maxLen)
            val wid = 11 * d
            c.save(); c.translate(cx, cy); c.rotate(r.hdg.toFloat())
            p.style = Paint.Style.FILL; p.color = 0xFF3A3D42.toInt()
            c.drawRoundRect(RectF(-wid / 2, -half, wid / 2, half), 2 * d, 2 * d, p)
            p.color = 0xCCFFFFFF.toInt(); p.strokeWidth = 1 * d; p.style = Paint.Style.STROKE
            p.pathEffect = android.graphics.DashPathEffect(floatArrayOf(5 * d, 4 * d), 0f)
            c.drawLine(0f, -half + 14 * d, 0f, half - 14 * d, p); p.pathEffect = null
            // Highlight the favoured end: it is landed toward its heading, from the far side.
            r.ends.forEachIndexed { i, e ->
                val y = if (i == 0) half else -half       // the "09" end sits at the south-west (you land heading 090)
                val good = e == best
                if (good) {
                    p.style = Paint.Style.FILL; p.color = 0xFF34C759.toInt()
                    c.drawRoundRect(RectF(-wid / 2 - 2 * d, if (i == 0) half - 22 * d else -half, wid / 2 + 2 * d, if (i == 0) half else -half + 22 * d), 3 * d, 3 * d, p)
                }
                c.save(); c.translate(0f, y + (if (i == 0) 12 else -6) * d); c.rotate(if (i == 0) 0f else 180f)
                t.textSize = 10 * d; t.color = if (good) 0xFFFFFFFF.toInt() else EfbUi.TEXT
                c.drawText(e, 0f, if (i == 0) 0f else 6 * d, t)
                c.restore()
            }
            c.restore()
        }

        // The wind: an arrow from where it blows, through the field.
        val wd = windFromMag
        if (wd != null && windKt > 0) {
            c.save(); c.translate(cx, cy); c.rotate(wd.toFloat())
            p.style = Paint.Style.STROKE; p.color = 0xFF7FD3FF.toInt(); p.strokeWidth = 4 * d; p.strokeCap = Paint.Cap.ROUND
            c.drawLine(0f, -rad + 4 * d, 0f, -rad * 0.28f, p)
            p.style = Paint.Style.FILL
            val head = Path().apply { moveTo(0f, -rad * 0.18f); lineTo(9 * d, -rad * 0.34f); lineTo(-9 * d, -rad * 0.34f); close() }
            c.drawPath(head, p)
            c.restore()
            val s = "%03.0f° %.0f KT".format(wd, windKt) + (gustKt?.let { " G%.0f".format(it) } ?: "")
            t.textSize = 12.5f * d; t.color = 0xFF7FD3FF.toInt()
            c.drawText(s, cx, height - 4 * d, t)
        } else {
            t.textSize = 12.5f * d; t.color = EfbUi.DIM
            c.drawText(if (wd == null && windKt == 0.0) "CALM / NO WIND REPORT" else "CALM", cx, height - 4 * d, t)
        }
    }
}
