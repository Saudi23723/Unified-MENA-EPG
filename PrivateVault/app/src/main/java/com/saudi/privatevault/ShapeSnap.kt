package com.saudi.privatevault

import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * A stroke held still at its end becomes the shape it was meant to be: a
 * straight line, an arrow, a rectangle, a triangle, a circle or a heart.
 * Points come and go as page fractions; the work is done in page pixels so
 * a circle stays round on a tall page.
 */
object ShapeSnap {

    /** The shape for [pts] (x, y fractions), or null when it is just writing. */
    fun recognize(pts: FloatArray, w: Float, h: Float, base: Mark, highlight: Boolean): Mark? {
        if (pts.size < 8 || w <= 0f || h <= 0f) return null
        val n = pts.size / 2
        val xs = FloatArray(n) { pts[it * 2] * w }
        val ys = FloatArray(n) { pts[it * 2 + 1] * h }
        var len = 0f
        for (i in 1 until n) len += hypot(xs[i] - xs[i - 1], ys[i] - ys[i - 1])
        if (len < w * 0.02f) return null
        val chord = hypot(xs[n - 1] - xs[0], ys[n - 1] - ys[0])

        fun frac(x: Float, y: Float) = floatArrayOf(x / w, y / h)
        fun two(tool: Tool, ax: Float, ay: Float, bx: Float, by: Float) =
            Mark(tool, base.color, base.width, frac(ax, ay) + frac(bx, by), round = base.round)

        // Straight enough: a line (a highlight lies along it).
        if (straight(xs, ys, 0, n - 1, len)) {
            return if (highlight) two(Tool.HIGHLIGHT, xs[0], ys[0], xs[n - 1], ys[n - 1]) else two(Tool.LINE, xs[0], ys[0], xs[n - 1], ys[n - 1])
        }
        if (highlight) return null

        // A shaft, then a head drawn back from its tip: an arrow.
        var tip = 0
        var far = 0f
        for (i in 0 until n) { val d = hypot(xs[i] - xs[0], ys[i] - ys[0]); if (d > far) { far = d; tip = i } }
        if (tip in n / 3 until n - 2) {
            var shaft = 0f
            for (i in 1..tip) shaft += hypot(xs[i] - xs[i - 1], ys[i] - ys[i - 1])
            val head = len - shaft
            if (straight(xs, ys, 0, tip, shaft) && head > shaft * 0.12f && head < shaft * 0.9f) {
                return two(Tool.ARROW, xs[0], ys[0], xs[tip], ys[tip])
            }
        }

        // The rest must come back to where it started.
        if (chord > len * 0.22f) return null
        var l = Float.MAX_VALUE; var t = Float.MAX_VALUE; var r = -Float.MAX_VALUE; var b = -Float.MAX_VALUE
        for (i in 0 until n) { l = min(l, xs[i]); r = max(r, xs[i]); t = min(t, ys[i]); b = max(b, ys[i]) }
        val bw = r - l
        val bh = b - t
        if (bw < w * 0.015f || bh < w * 0.015f) return null
        val cx = (l + r) / 2
        val cy = (t + b) / 2

        val corners = corners(xs, ys, len)
        if (heart(xs, ys, l, t, r, b)) return poly(base, heartPoints(l, t, bw, bh), w, h)
        // Round: every point about as far from the middle (as an ellipse).
        var dev = 0f
        for (i in 0 until n) {
            val ex = (xs[i] - cx) / (bw / 2)
            val ey = (ys[i] - cy) / (bh / 2)
            dev += abs(sqrt(ex * ex + ey * ey) - 1f)
        }
        dev /= n
        if (corners.size <= 2 && dev < 0.17f) return two(Tool.OVAL, l, t, r, b)
        if (corners.size == 3) {
            val c = corners.map { it }
            return poly(base, closed(c.map { xs[it] to ys[it] }), w, h)
        }
        if (corners.size == 4) {
            // Square to the page: a rectangle that can be resized; tilted: as drawn.
            val q = corners.map { xs[it] to ys[it] }
            val level = (0 until 4).all { i ->
                val (ax, ay) = q[i]; val (bx, by) = q[(i + 1) % 4]
                val a = Math.toDegrees(atan2((by - ay).toDouble(), (bx - ax).toDouble())).let { abs(((it % 90) + 90) % 90) }
                a < 14 || a > 76
            }
            return if (level) two(Tool.RECT, l, t, r, b) else poly(base, closed(q), w, h)
        }
        if (dev < 0.24f) return two(Tool.OVAL, l, t, r, b)
        return null
    }

    private fun straight(xs: FloatArray, ys: FloatArray, a: Int, z: Int, len: Float): Boolean {
        val dx = xs[z] - xs[a]
        val dy = ys[z] - ys[a]
        val chord = hypot(dx, dy)
        if (chord < len * 0.86f || chord <= 0f) return false
        var worst = 0f
        for (i in a..z) worst = max(worst, abs((xs[i] - xs[a]) * dy - (ys[i] - ys[a]) * dx) / chord)
        return worst < chord * 0.075f
    }

    /** Where the stroke turns sharply (Ramer–Douglas–Peucker over the closed loop). */
    private fun corners(xs: FloatArray, ys: FloatArray, len: Float): List<Int> {
        val n = xs.size
        val keep = BooleanArray(n)
        keep[0] = true; keep[n - 1] = true
        // Split the loop at the point farthest from the start, then simplify both halves.
        var far = 0; var d = 0f
        for (i in 0 until n) { val e = hypot(xs[i] - xs[0], ys[i] - ys[0]); if (e > d) { d = e; far = i } }
        keep[far] = true
        val eps = len * 0.035f
        fun rdp(a: Int, z: Int) {
            if (z <= a + 1) return
            val dx = xs[z] - xs[a]; val dy = ys[z] - ys[a]
            val c = max(hypot(dx, dy), 1e-3f)
            var best = -1; var bd = 0f
            for (i in a + 1 until z) {
                val e = abs((xs[i] - xs[a]) * dy - (ys[i] - ys[a]) * dx) / c
                if (e > bd) { bd = e; best = i }
            }
            if (best >= 0 && bd > eps) { keep[best] = true; rdp(a, best); rdp(best, z) }
        }
        rdp(0, far); rdp(far, n - 1)
        val idx = (0 until n).filter { keep[it] }.toMutableList()
        // The start and the end are the same corner.
        if (idx.size > 1) idx.removeAt(idx.size - 1)
        // Drop the points on a straight run (turn under 30°).
        val out = ArrayList<Int>()
        for (k in idx.indices) {
            val p = idx[(k - 1 + idx.size) % idx.size]; val c = idx[k]; val q = idx[(k + 1) % idx.size]
            val a1 = atan2(ys[c] - ys[p], xs[c] - xs[p])
            val a2 = atan2(ys[q] - ys[c], xs[q] - xs[c])
            var turn = abs(Math.toDegrees((a2 - a1).toDouble()))
            if (turn > 180) turn = 360 - turn
            if (turn > 30) out.add(c)
        }
        return out
    }

    /** Two lobes on top, a point at the bottom: a dip in the middle of the top edge. */
    private fun heart(xs: FloatArray, ys: FloatArray, l: Float, t: Float, r: Float, b: Float): Boolean {
        val bw = r - l; val bh = b - t
        if (bw < bh * 0.55f || bw > bh * 1.8f) return false
        val cx = (l + r) / 2
        // The top of the stroke near the middle sits well below the lobes.
        var midTop = Float.MAX_VALUE
        var leftTop = Float.MAX_VALUE
        var rightTop = Float.MAX_VALUE
        var bottomX = cx
        for (i in xs.indices) {
            val x = xs[i]; val y = ys[i]
            if (abs(x - cx) < bw * 0.08f && y < t + bh * 0.6f) midTop = min(midTop, y)
            if (x < cx - bw * 0.15f) leftTop = min(leftTop, y)
            if (x > cx + bw * 0.15f) rightTop = min(rightTop, y)
            if (y > b - bh * 0.04f) bottomX = x
        }
        if (midTop == Float.MAX_VALUE) return false
        val lobes = max(leftTop, rightTop)
        return midTop - lobes > bh * 0.12f && abs(bottomX - cx) < bw * 0.2f
    }

    private fun heartPoints(l: Float, t: Float, bw: Float, bh: Float): List<Pair<Float, Float>> {
        // The classic heart curve, fitted to the box drawn.
        val raw = (0..96).map { i ->
            val a = Math.PI * 2 * i / 96
            val x = 16 * sin(a).let { it * it * it }
            val y = 13 * cos(a) - 5 * cos(2 * a) - 2 * cos(3 * a) - cos(4 * a)
            x.toFloat() to (-y).toFloat()
        }
        val minX = raw.minOf { it.first }; val maxX = raw.maxOf { it.first }
        val minY = raw.minOf { it.second }; val maxY = raw.maxOf { it.second }
        return raw.map { (x, y) -> l + (x - minX) / (maxX - minX) * bw to t + (y - minY) / (maxY - minY) * bh }
    }

    private fun closed(c: List<Pair<Float, Float>>) = c + c.first()

    /** Straight sides kept sharp: many points along each side, for the pen that draws them. */
    private fun poly(base: Mark, c: List<Pair<Float, Float>>, w: Float, h: Float): Mark {
        val out = ArrayList<Float>()
        for (i in 0 until c.size - 1) {
            val (ax, ay) = c[i]; val (bx, by) = c[i + 1]
            val steps = max(2, (hypot(bx - ax, by - ay) / (w * 0.004f)).toInt())
            for (s in 0 until steps) {
                val f = s.toFloat() / steps
                out.add((ax + (bx - ax) * f) / w); out.add((ay + (by - ay) * f) / h)
            }
        }
        val (zx, zy) = c.last()
        out.add(zx / w); out.add(zy / h)
        return Mark(Tool.PEN, base.color, base.width, out.toFloatArray(), pen = base.pen)
    }
}
