package com.saudi.privatevault

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.view.View

/**
 * Hours split into their parts, as a ring with the total in the middle and a key beside it: by the
 * aeroplane flown, by the seat flown in, by the field flown from. Small parts are gathered into one
 * "other", so the ring stays readable however long the logbook grows.
 */
class PieChart(ctx: Context, parts: List<Pair<String, Double>>, private val centreLabel: String = "") : View(ctx) {

    private val d = ctx.resources.displayMetrics.density
    private val slice = Paint(Paint.ANTI_ALIAS_FLAG)
    private val hole = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = EfbUi.CARD }
    private val big = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = EfbUi.TEXT; textSize = 17 * d; isFakeBoldText = true; textAlign = Paint.Align.CENTER }
    private val small = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = EfbUi.DIM; textSize = 10 * d; textAlign = Paint.Align.CENTER }
    private val key = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = EfbUi.TEXT; textSize = 12.5f * d }
    private val keyDim = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = EfbUi.DIM; textSize = 11.5f * d }

    private val colours = intArrayOf(
        0xFF1F6FEB.toInt(), 0xFF3FB950.toInt(), 0xFFD29922.toInt(), 0xFFA371F7.toInt(),
        0xFF39C5CF.toInt(), 0xFFF78166.toInt(), 0xFF8B949E.toInt(), 0xFFDB61A2.toInt(),
    )

    private val data: List<Pair<String, Double>>
    private val total: Double

    init {
        val clean = parts.filter { it.second > 0.001 }.sortedByDescending { it.second }
        total = clean.sumOf { it.second }
        // Seven named parts at most; the rest together, so the key never runs off the card.
        data = if (clean.size <= 8) clean else clean.take(7) + ("Other" to clean.drop(7).sumOf { it.second })
    }

    override fun onMeasure(w: Int, h: Int) {
        val width = MeasureSpec.getSize(w)
        val rows = data.size
        setMeasuredDimension(width, maxOf((150 * d).toInt(), (rows * 22 * d).toInt() + (24 * d).toInt()))
    }

    override fun onDraw(c: Canvas) {
        if (data.isEmpty() || total <= 0) return
        val h = height.toFloat()
        val r = minOf(h * 0.44f, width * 0.22f)
        val cx = r + 12 * d
        val cy = h / 2
        val box = RectF(cx - r, cy - r, cx + r, cy + r)
        var start = -90f
        for ((i, p) in data.withIndex()) {
            val sweep = (p.second / total * 360).toFloat()
            slice.color = colours[i % colours.size]
            c.drawArc(box, start, sweep - 0.6f, true, slice)
            start += sweep
        }
        c.drawCircle(cx, cy, r * 0.58f, hole)
        c.drawText(EfbUi.num(total), cx, cy + 2 * d, big)
        c.drawText(centreLabel.ifEmpty { "hours" }, cx, cy + 15 * d, small)
        // The key: a dot, the name, then its hours and its share.
        val left = cx + r + 16 * d
        val step = (h - 12 * d) / data.size
        var y = 6 * d + step / 2
        for ((i, p) in data.withIndex()) {
            slice.color = colours[i % colours.size]
            c.drawCircle(left + 5 * d, y - 4 * d, 5 * d, slice)
            val pct = p.second / total * 100
            val name = p.first.take(18)
            c.drawText(name, left + 16 * d, y, key)
            val tail = "%s h · %.0f%%".format(EfbUi.num(p.second), pct)
            c.drawText(tail, width - keyDim.measureText(tail) - 8 * d, y, keyDim)
            y += step
        }
    }
}
