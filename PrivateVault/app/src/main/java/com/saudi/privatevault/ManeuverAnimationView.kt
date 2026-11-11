package com.saudi.privatevault

import android.content.Context
import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.Typeface
import android.os.SystemClock
import android.view.MotionEvent
import android.view.View
import kotlin.math.abs
import kotlin.math.asin
import kotlin.math.atan
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

/** The airplane at one instant of a maneuver: where, which way, and what the instruments read. */
data class ManeuverState(
    val x: Float, val y: Float,          // plan: metres east / north; profile: feet along / feet above the ground
    val hdg: Float = 0f,                 // degrees, plan view
    val bank: Float = 0f,                // degrees, + right wing down
    val ias: Float = 0f,                 // knots
    val alt: Float = 0f,                 // feet above the ground
    val pitch: Float = 0f,               // degrees, + nose up
    val vs: Float = 0f,                  // feet per minute
    val gs: Float = 0f,                  // knots over the ground
    val flaps: Int = 0,
    val warn: String? = null,
)

/** What the scene holds besides the airplane. */
class ManeuverScene {
    /** Plan: runway from (x1,y1) to (x2,y2) in metres; profile: runway from x1 to x2 in feet. */
    var runway: FloatArray? = null
    var runwayNames: Pair<String, String>? = null
    var windFrom: Float? = null
    var windKt = 0f
    var point: FloatArray? = null        // a pivot point on the ground (plan)
    var road: FloatArray? = null         // a straight road x1,y1,x2,y2 (plan)
    var field: RectF? = null             // a field boundary (plan)
    var obstacle: FloatArray? = null     // profile: x, height (ft)
    var soft = false                     // a grass strip
    var refLine: Float? = null           // profile: a dashed reference height (ft)
    var refLabel = ""
    var glide: FloatArray? = null        // profile: a normal glide path x1,y1,x2,y2 to compare with
    var aimX: Float? = null              // profile: the aiming point
    var horizonOnly = false              // profile without a runway: level flight at altitude
}

/** A maneuver as a function of progress 0..1. */
abstract class ManeuverAnim(val seconds: Float, val profile: Boolean) {
    val scene = ManeuverScene()
    var phases: List<Pair<Float, String>> = emptyList()
    abstract fun at(p: Float): ManeuverState
    val trail: List<ManeuverState> by lazy { (0..360).map { at(it / 360f) } }
    open fun phase(p: Float) = phases.lastOrNull { p >= it.first }?.second ?: ""
}

/**
 * A ground track flown at a given airspeed in a wind: the airplane crabs into the wind, its
 * groundspeed sets the time, and its bank in a turn is the one a constant radius over the ground
 * needs at that groundspeed (tan φ = GS² / g r), so the steepest bank falls downwind, as it does.
 */
class GroundTrack(seconds: Float, private val windFrom: Float = 0f, private val windKt: Float = 0f) : ManeuverAnim(seconds, false) {
    private class Pt(val x: Float, val y: Float, val trk: Float, val r: Float, val alt: Float, val ias: Float,
                     val ramp: Float, val slip: Float, val flaps: Int, val warn: String?) { var t = 0f; var crab = 0f; var gs = 0f }
    private val pts = ArrayList<Pt>()
    private var x = 0f; private var y = 0f; private var trk = 0f; private var alt = 0f; private var ias = 0f
    private var built = false

    init { if (windKt > 0) { scene.windFrom = windFrom; scene.windKt = windKt } }

    fun start(x: Float, y: Float, trk: Float, alt: Float, ias: Float) = apply { this.x = x; this.y = y; this.trk = trk; this.alt = alt; this.ias = ias }

    private var curSlip = 0f
    private val marks = ArrayList<Pair<Int, String>>()
    private fun mark(label: String?) { if (label != null) marks += pts.size to label }

    fun straight(len: Float, toAlt: Float = alt, toIas: Float = ias, flaps: Int = 0, slip: Float = 0f, warn: String? = null, label: String? = null) = apply {
        mark(label)
        val n = max(2, (len / 6f).toInt()); val a0 = alt; val i0 = ias; val s0 = curSlip
        for (k in 1..n) {
            val f = k / n.toFloat()
            val d = len / n
            x += (sin(Math.toRadians(trk.toDouble())) * d).toFloat(); y += (cos(Math.toRadians(trk.toDouble())) * d).toFloat()
            val s = s0 + (slip - s0) * min(1f, f * len / 120f)
            pts += Pt(x, y, trk, 0f, a0 + (toAlt - a0) * f, i0 + (toIas - i0) * f, 0f, s, flaps, warn)
        }
        alt = toAlt; ias = toIas; curSlip = slip
    }

    /** A turn of [deg] degrees (+ right) on a circle of [r] metres. */
    fun turn(deg: Float, r: Float, toAlt: Float = alt, toIas: Float = ias, flaps: Int = 0, label: String? = null) = apply {
        mark(label); curSlip = 0f
        val len = abs(deg) / 360f * 2f * Math.PI.toFloat() * r
        val n = max(4, (len / 6f).toInt()); val a0 = alt; val i0 = ias; val t0 = trk
        val sgn = if (deg >= 0) 1f else -1f
        // Centre of the circle, to the right (or left) of the track.
        val cx = x + sgn * r * cos(Math.toRadians(t0.toDouble())).toFloat()
        val cy = y - sgn * r * sin(Math.toRadians(t0.toDouble())).toFloat()
        val ang0 = Math.toDegrees(Math.atan2((x - cx).toDouble(), (y - cy).toDouble())).toFloat()
        for (k in 1..n) {
            val f = k / n.toFloat()
            val a = Math.toRadians((ang0 + deg * f).toDouble())
            x = cx + r * sin(a).toFloat(); y = cy + r * cos(a).toFloat()
            trk = t0 + deg * f
            val dIn = f * len; val dOut = (1 - f) * len
            val ramp = min(1f, min(dIn, dOut) / min(70f, len / 3f))
            pts += Pt(x, y, trk, sgn * r, a0 + (toAlt - a0) * f, i0 + (toIas - i0) * f, ramp, 0f, flaps, null)
        }
        alt = toAlt; ias = toIas
    }

    private fun build() {
        if (built) return; built = true
        val w = Math.toRadians((windFrom + 180.0))
        val wx = (windKt * sin(w)).toFloat(); val wy = (windKt * cos(w)).toFloat()
        var t = 0f
        for ((i, p) in pts.withIndex()) {
            val tr = Math.toRadians(p.trk.toDouble())
            val ux = sin(tr).toFloat(); val uy = cos(tr).toFloat()
            val cross = wx * uy - wy * ux          // wind pushing the airplane to the right of the track
            val along = wx * ux + wy * uy
            val tas = max(p.ias, 20f)
            val c = Math.toDegrees(asin((cross / tas).coerceIn(-0.9f, 0.9f).toDouble())).toFloat()
            p.crab = -c
            p.gs = max(8f, tas * cos(Math.toRadians(c.toDouble())).toFloat() + along)
            if (i > 0) {
                val q = pts[i - 1]
                val d = sqrt((p.x - q.x) * (p.x - q.x) + (p.y - q.y) * (p.y - q.y))
                t += d / (p.gs * 0.5144f)
            }
            p.t = t
        }
        val total = max(1e-3f, t)
        phases = marks.filter { it.first < pts.size }.map { pts[it.first].t / total to it.second }
    }

    override fun phase(p: Float): String { build(); return super.phase(p) }

    override fun at(p: Float): ManeuverState {
        build()
        if (pts.isEmpty()) return ManeuverState(0f, 0f)
        val T = pts.last().t * p.coerceIn(0f, 1f)
        var lo = 0; var hi = pts.size - 1
        while (hi - lo > 1) { val m = (lo + hi) / 2; if (pts[m].t < T) lo = m else hi = m }
        val a = pts[lo]; val b = pts[hi]
        val f = if (b.t > a.t) ((T - a.t) / (b.t - a.t)).coerceIn(0f, 1f) else 0f
        fun l(u: Float, v: Float) = u + (v - u) * f
        val gs = l(a.gs, b.gs)
        val r = if (abs(b.r) > 0) b.r else a.r
        var bank = if (r != 0f) {
            val v = gs * 0.5144f
            Math.toDegrees(atan((v * v / (9.81f * abs(r))).toDouble())).toFloat() * (if (r > 0) 1f else -1f) * l(a.ramp, b.ramp)
        } else 0f
        // On the wheels the airplane points down the runway whatever the wind.
        val slip = if (l(a.alt, b.alt) < 3f) 1f else l(a.slip, b.slip)
        val crab = l(a.crab, b.crab)
        // Wing low into the wind in the slip, the nose straight down the runway.
        val low = (crab * 0.7f).coerceIn(-12f, 12f) * (if (l(a.alt, b.alt) > 3f) 1f else 0.2f)
        bank += slip * low
        val hdg = l(a.trk, b.trk) + crab * (1 - slip)
        val vs = if (b.t > a.t) (b.alt - a.alt) / (b.t - a.t) * 60f else 0f
        return ManeuverState(l(a.x, b.x), l(a.y, b.y), hdg, bank, l(a.ias, b.ias), l(a.alt, b.alt), 0f, vs, gs, b.flaps, b.warn)
    }
}

/** A side view built from key instants: where the airplane is, its pitch and its airspeed. */
class ProfileKeys(seconds: Float, private val keys: List<Key>) : ManeuverAnim(seconds, true) {
    class Key(val t: Float, val x: Float, val y: Float, val pitch: Float, val ias: Float, val flaps: Int = 0, val warn: String? = null, val bank: Float = 0f)

    private fun cr(p0: Float, p1: Float, p2: Float, p3: Float, u: Float): Float {
        val u2 = u * u; val u3 = u2 * u
        return 0.5f * (2 * p1 + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u2 + (-p0 + 3 * p1 - 3 * p2 + p3) * u3)
    }

    private fun pos(p: Float): Pair<Float, Float> {
        val i = (keys.indexOfLast { it.t <= p }).coerceIn(0, keys.size - 2)
        val k0 = keys[max(0, i - 1)]; val k1 = keys[i]; val k2 = keys[i + 1]; val k3 = keys[min(keys.size - 1, i + 2)]
        val u = ((p - k1.t) / max(1e-4f, k2.t - k1.t)).coerceIn(0f, 1f)
        return cr(k0.x, k1.x, k2.x, k3.x, u) to max(0f, cr(k0.y, k1.y, k2.y, k3.y, u))
    }

    override fun at(p: Float): ManeuverState {
        val q = p.coerceIn(0f, 1f)
        val i = (keys.indexOfLast { it.t <= q }).coerceIn(0, keys.size - 2)
        val a = keys[i]; val b = keys[i + 1]
        val u0 = ((q - a.t) / max(1e-4f, b.t - a.t)).coerceIn(0f, 1f)
        val u = u0 * u0 * (3 - 2 * u0)
        val (x, y) = pos(q)
        val (x2, y2) = pos(min(1f, q + 0.004f)); val (x1, y1) = pos(max(0f, q - 0.004f))
        val ias = a.ias + (b.ias - a.ias) * u
        val dx = x2 - x1
        val vs = if (abs(dx) > 0.01f) (y2 - y1) / dx * max(ias, 1f) * 101.27f else 0f
        val warn = if (u0 < 0.5f) a.warn else b.warn
        return ManeuverState(x, y, 0f, a.bank + (b.bank - a.bank) * u, ias, y, a.pitch + (b.pitch - a.pitch) * u, vs, ias, if (u0 < 0.5f) a.flaps else b.flaps, warn)
    }
}

/**
 * Draws a maneuver as a short looping clip: the ground and the runway, the path ahead dashed,
 * the path flown glowing, the airplane with its shadow, and a small panel of what the
 * instruments read (airspeed, altitude, bank, a little attitude ball). Tap to pause, drag to scrub.
 */
class ManeuverAnimationView(ctx: Context) : View(ctx) {
    var anim: ManeuverAnim? = null
        set(v) { field = v; elapsed = 0L; invalidate() }
    var playing = true
        set(v) { field = v; last = 0L; onPlayChanged?.invoke(v); invalidate() }
    var speed = 1f
    /** A still of the whole path, for a list. */
    var thumb = false
    var onPlayChanged: ((Boolean) -> Unit)? = null

    private var elapsed = 0L
    private var last = 0L
    private val HOLD = 1400L
    private val d = resources.displayMetrics.density
    private fun dp(v: Float) = v * d

    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND }
    private val txt = Paint(Paint.ANTI_ALIAS_FLAG).apply { typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL) }
    private val mono = Paint(Paint.ANTI_ALIAS_FLAG).apply { typeface = Typeface.create(Typeface.MONOSPACE, Typeface.BOLD) }

    private val ACC = 0xFF2D8CFF.toInt()
    private val GREEN = 0xFF34C759.toInt()
    private val MAG = 0xFFFF2D9B.toInt()
    private val AMBER = 0xFFFFB020.toInt()
    private val RED = 0xFFFF453A.toInt()

    fun restart() { elapsed = 0L; last = 0L; playing = true }

    fun progress(): Float {
        val a = anim ?: return 0f
        return min(1f, elapsed / (a.seconds * 1000f))
    }

    override fun onTouchEvent(e: MotionEvent): Boolean {
        if (thumb) return super.onTouchEvent(e)
        val a = anim ?: return false
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> { parent?.requestDisallowInterceptTouchEvent(true); downX = e.x; scrubbed = false; return true }
            MotionEvent.ACTION_MOVE -> {
                if (abs(e.x - downX) > dp(8f) || scrubbed) {
                    scrubbed = true
                    if (playing) playing = false
                    elapsed = ((e.x / width).coerceIn(0f, 1f) * a.seconds * 1000f).toLong()
                    invalidate()
                }
            }
            MotionEvent.ACTION_UP -> { if (!scrubbed) { if (progress() >= 1f && !playing) elapsed = 0L; playing = !playing }; performClick() }
        }
        return true
    }
    private var downX = 0f
    private var scrubbed = false
    override fun performClick(): Boolean { super.performClick(); return true }

    override fun onDraw(c: Canvas) {
        val a = anim ?: return
        val now = SystemClock.uptimeMillis()
        if (playing && !thumb) {
            if (last != 0L) elapsed += ((now - last) * speed).toLong()
            last = now
            if (elapsed > a.seconds * 1000 + HOLD) elapsed = 0L
        }
        val p = if (thumb) 1f else progress()
        if (a.profile) drawProfile(c, a, p) else drawPlan(c, a, p)
        if (!thumb) {
            hud(c, a.at(p), a)
            caption(c, a, p)
            bar(c, p)
            if (!playing) playBadge(c)
        }
        if (playing && !thumb && isAttachedToWindow) postInvalidateOnAnimation()
    }

    override fun onAttachedToWindow() { super.onAttachedToWindow(); last = 0L; invalidate() }

    // ---------------------------------------------------------------- plan view

    private fun drawPlan(c: Canvas, a: ManeuverAnim, p: Float) {
        val w = width.toFloat(); val h = height.toFloat()
        // Ground: a dusk-green field pattern under a soft vignette.
        fill.shader = LinearGradient(0f, 0f, 0f, h, 0xFF16261C.toInt(), 0xFF0E1712.toInt(), Shader.TileMode.CLAMP)
        c.drawRect(0f, 0f, w, h, fill); fill.shader = null

        val s = a.scene
        var minX = Float.MAX_VALUE; var maxX = -Float.MAX_VALUE; var minY = Float.MAX_VALUE; var maxY = -Float.MAX_VALUE
        fun inc(x: Float, y: Float) { minX = min(minX, x); maxX = max(maxX, x); minY = min(minY, y); maxY = max(maxY, y) }
        a.trail.forEach { inc(it.x, it.y) }
        s.runway?.let { inc(it[0], it[1]); inc(it[2], it[3]) }
        s.point?.let { inc(it[0], it[1]) }
        s.field?.let { inc(it.left, it.top); inc(it.right, it.bottom) }
        val padT = if (thumb) dp(6f) else dp(54f); val padB = if (thumb) dp(6f) else dp(46f); val padS = if (thumb) dp(6f) else dp(20f)
        val sc = min((w - 2 * padS) / max(1f, maxX - minX), (h - padT - padB) / max(1f, maxY - minY))
        val ox = padS + ((w - 2 * padS) - (maxX - minX) * sc) / 2 - minX * sc
        val oy = padT + ((h - padT - padB) - (maxY - minY) * sc) / 2 + maxY * sc
        fun X(x: Float) = ox + x * sc
        fun Y(y: Float) = oy - y * sc

        // Field patchwork: a few tilted rectangles for depth.
        if (!thumb) {
            val tile = dp(46f)
            var i = 0
            var yy = -tile
            while (yy < h + tile) {
                var xx = -tile + (i % 2) * tile / 2
                while (xx < w + tile) {
                    val shade = ((xx.toInt() / 7 + yy.toInt() / 11 + i) and 3)
                    fill.color = when (shade) { 0 -> 0x10FFFFFF; 1 -> 0x0A9AD47A; 2 -> 0x08000000; else -> 0x06C8B060 }
                    c.drawRect(xx + 1, yy + 1, xx + tile - 1, yy + tile - 1, fill)
                    xx += tile
                }
                yy += tile; i++
            }
        }

        s.field?.let { f ->
            line.color = 0x55E5D27A; line.strokeWidth = dp(1.5f); line.pathEffect = DashPathEffect(floatArrayOf(dp(5f), dp(4f)), 0f)
            c.drawRect(X(f.left), Y(f.bottom), X(f.right), Y(f.top), line); line.pathEffect = null
            fill.color = 0x14E5D27A; c.drawRect(X(f.left), Y(f.bottom), X(f.right), Y(f.top), fill)
        }
        s.road?.let { r ->
            line.color = 0xFF5A5F66.toInt(); line.strokeWidth = dp(6f); c.drawLine(X(r[0]), Y(r[1]), X(r[2]), Y(r[3]), line)
            line.color = 0xAAE8E8E8.toInt(); line.strokeWidth = dp(1f); line.pathEffect = DashPathEffect(floatArrayOf(dp(6f), dp(6f)), 0f)
            c.drawLine(X(r[0]), Y(r[1]), X(r[2]), Y(r[3]), line); line.pathEffect = null
        }
        s.point?.let { pt ->
            val cx = X(pt[0]); val cy = Y(pt[1])
            fill.color = 0x33FFB020; c.drawCircle(cx, cy, dp(14f), fill)
            fill.color = AMBER; c.drawCircle(cx, cy, dp(5f), fill)
            line.color = 0xFF0E1712.toInt(); line.strokeWidth = dp(1.5f); c.drawCircle(cx, cy, dp(5f), line)
        }
        s.runway?.let { r -> runwayPlan(c, X(r[0]), Y(r[1]), X(r[2]), Y(r[3]), s) }

        // Path ahead, dashed; path flown, glowing.
        val ahead = Path(); val flown = Path()
        val n = a.trail.size - 1
        val cut = (p * n).toInt()
        for ((i, st) in a.trail.withIndex()) {
            if (i == 0) ahead.moveTo(X(st.x), Y(st.y)) else ahead.lineTo(X(st.x), Y(st.y))
            if (i <= cut) { if (i == 0) flown.moveTo(X(st.x), Y(st.y)) else flown.lineTo(X(st.x), Y(st.y)) }
        }
        val now = a.at(p)
        if (!thumb) flown.lineTo(X(now.x), Y(now.y))
        line.pathEffect = DashPathEffect(floatArrayOf(dp(4f), dp(5f)), 0f)
        line.color = 0x66FFFFFF; line.strokeWidth = dp(1.4f); c.drawPath(ahead, line); line.pathEffect = null
        if (thumb) {
            line.color = MAG; line.strokeWidth = dp(2f); c.drawPath(ahead, line)
            return
        }
        line.color = 0x44FF2D9B; line.strokeWidth = dp(9f); c.drawPath(flown, line)
        line.color = MAG; line.strokeWidth = dp(3f); c.drawPath(flown, line)

        // The airplane, its shadow cast aside by its height.
        val shadow = min(dp(22f), now.alt / 1000f * dp(18f))
        drawPlane(c, X(now.x) + shadow * 0.6f, Y(now.y) + shadow, now.hdg, now.bank, 0x66000000, dp(28f))
        drawPlane(c, X(now.x), Y(now.y), now.hdg, now.bank, 0xFFFFFFFF.toInt(), dp(28f))

        s.windFrom?.let { wind(c, it, s.windKt) }
    }

    private fun runwayPlan(c: Canvas, x1: Float, y1: Float, x2: Float, y2: Float, s: ManeuverScene) {
        val len = sqrt((x2 - x1) * (x2 - x1) + (y2 - y1) * (y2 - y1))
        val ang = Math.toDegrees(Math.atan2((y2 - y1).toDouble(), (x2 - x1).toDouble())).toFloat()
        val wid = max(dp(9f), min(dp(16f), len * 0.07f))
        c.save(); c.translate(x1, y1); c.rotate(ang)
        fill.color = if (s.soft) 0xFF3E6B3A.toInt() else 0xFF2E3136.toInt()
        c.drawRoundRect(RectF(0f, -wid / 2, len, wid / 2), dp(2f), dp(2f), fill)
        if (!s.soft) {
            line.color = 0xCCFFFFFF.toInt(); line.strokeWidth = dp(1f)
            line.pathEffect = DashPathEffect(floatArrayOf(dp(6f), dp(5f)), 0f)
            c.drawLine(len * 0.12f, 0f, len * 0.88f, 0f, line); line.pathEffect = null
            fill.color = 0xDDFFFFFF.toInt()
            for (k in 0..3) {
                val yy = -wid / 2 + wid * (k + 0.8f) / 5f
                c.drawRect(dp(3f), yy, dp(9f), yy + dp(1.2f), fill)
                c.drawRect(len - dp(9f), yy, len - dp(3f), yy + dp(1.2f), fill)
            }
        }
        c.restore()
        s.runwayNames?.let { (a, b) ->
            txt.textSize = dp(10f); txt.color = 0xDDFFFFFF.toInt(); txt.textAlign = Paint.Align.CENTER
            val ux = (x2 - x1) / max(1f, len); val uy = (y2 - y1) / max(1f, len)
            c.drawText(a, x1 - ux * dp(13f), y1 - uy * dp(13f) + dp(4f), txt)
            c.drawText(b, x2 + ux * dp(13f), y2 + uy * dp(13f) + dp(4f), txt)
        }
    }

    /** Top-down silhouette; the wings foreshorten with the bank. */
    private fun drawPlane(c: Canvas, x: Float, y: Float, hdg: Float, bank: Float, color: Int, size: Float) {
        c.save(); c.translate(x, y); c.rotate(hdg)
        val k = size / 28f
        val span = 13f * k * max(0.35f, cos(Math.toRadians(bank.toDouble())).toFloat())
        val path = Path().apply {
            // fuselage
            moveTo(0f, -12f * k); lineTo(1.6f * k, -9f * k); lineTo(1.6f * k, 8f * k); lineTo(0.8f * k, 12f * k)
            lineTo(-0.8f * k, 12f * k); lineTo(-1.6f * k, 8f * k); lineTo(-1.6f * k, -9f * k); close()
            // wing
            moveTo(-span, -3f * k); lineTo(span, -3f * k); lineTo(span, 0.6f * k); lineTo(-span, 0.6f * k); close()
            // tailplane
            moveTo(-5f * k, 9f * k); lineTo(5f * k, 9f * k); lineTo(5f * k, 11.2f * k); lineTo(-5f * k, 11.2f * k); close()
        }
        fill.color = color; c.drawPath(path, fill)
        if (color == 0xFFFFFFFF.toInt()) {
            // The low wing tip in colour: which way it banks reads at a glance.
            if (abs(bank) > 3f) {
                fill.color = if (bank > 0) GREEN else RED
                val sx = if (bank > 0) span else -span
                c.drawCircle(sx, -1.2f * k, 1.6f * k, fill)
            }
            fill.color = ACC; c.drawCircle(0f, -6f * k, 1.1f * k, fill)
        }
        c.restore()
    }

    private fun wind(c: Canvas, from: Float, kt: Float) {
        val cx = width - dp(34f); val cy = dp(78f)
        fill.color = 0xB0101418.toInt(); c.drawCircle(cx, cy, dp(22f), fill)
        line.color = 0x33FFFFFF; line.strokeWidth = dp(1f); c.drawCircle(cx, cy, dp(22f), line)
        c.save(); c.translate(cx, cy); c.rotate(from + 180f)
        line.color = 0xFF7FD3FF.toInt(); line.strokeWidth = dp(2.4f)
        c.drawLine(0f, dp(12f), 0f, -dp(12f), line)
        val head = Path().apply { moveTo(0f, -dp(15f)); lineTo(dp(5f), -dp(7f)); lineTo(-dp(5f), -dp(7f)); close() }
        fill.color = 0xFF7FD3FF.toInt(); c.drawPath(head, fill)
        c.restore()
        txt.textSize = dp(9.5f); txt.color = 0xFF7FD3FF.toInt(); txt.textAlign = Paint.Align.CENTER
        c.drawText("WIND %.0f KT".format(kt), cx, cy + dp(34f), txt)
    }

    // ---------------------------------------------------------------- side view

    private fun drawProfile(c: Canvas, a: ManeuverAnim, p: Float) {
        val w = width.toFloat(); val h = height.toFloat()
        val s = a.scene
        var minX = Float.MAX_VALUE; var maxX = -Float.MAX_VALUE; var maxY = 0f; var minY = Float.MAX_VALUE
        a.trail.forEach { minX = min(minX, it.x); maxX = max(maxX, it.x); maxY = max(maxY, it.y); minY = min(minY, it.y) }
        val midY = (minY + maxY) / 2; val spanY = max(120f, maxY - minY)
        s.runway?.let { minX = min(minX, it[0]); maxX = max(maxX, it[1]) }
        s.obstacle?.let { maxY = max(maxY, it[1] * 1.6f) }
        s.refLine?.let { maxY = max(maxY, it * 1.3f) }
        val padT = if (thumb) dp(4f) else dp(58f); val padB = if (thumb) dp(4f) else dp(56f); val padS = if (thumb) dp(4f) else dp(18f)
        val ground = h - padB
        val sx = (w - 2 * padS) / max(1f, maxX - minX)
        val sy = if (s.horizonOnly) (ground - padT) * 0.6f / spanY else (ground - padT) / max(20f, maxY)
        fun X(x: Float) = padS + (x - minX) * sx
        fun Y(y: Float) = if (s.horizonOnly) padT + (ground - padT) * 0.5f - (y - midY) * sy else ground - y * sy

        // Sky and ground.
        fill.shader = LinearGradient(0f, 0f, 0f, ground, 0xFF0B2545.toInt(), 0xFF2B5D8C.toInt(), Shader.TileMode.CLAMP)
        c.drawRect(0f, 0f, w, ground, fill)
        fill.shader = LinearGradient(0f, ground, 0f, h, if (s.soft) 0xFF2F5A2B.toInt() else 0xFF26402A.toInt(), 0xFF101A12.toInt(), Shader.TileMode.CLAMP)
        c.drawRect(0f, ground, w, h, fill); fill.shader = null
        if (!thumb) {
            // Far hills for depth.
            fill.color = 0x2A0E1A10
            val hills = Path().apply {
                moveTo(0f, ground)
                var xx = 0f; var k = 0
                while (xx <= w) { lineTo(xx, ground - dp(10f) - (sin(k * 0.9) * dp(7f)).toFloat() - (k % 3) * dp(3f)); xx += dp(28f); k++ }
                lineTo(w, ground); close()
            }
            c.drawPath(hills, fill)
        }

        s.runway?.let { r ->
            fill.color = if (s.soft) 0xFF4E7F45.toInt() else 0xFF3A3D42.toInt()
            c.drawRect(X(r[0]), ground - dp(1f), X(r[1]), ground + dp(5f), fill)
            if (!s.soft) {
                fill.color = 0xCCFFFFFF.toInt()
                var xx = X(r[0]) + dp(10f)
                while (xx < X(r[1]) - dp(10f)) { c.drawRect(xx, ground + dp(1.5f), xx + dp(8f), ground + dp(2.6f), fill); xx += dp(18f) }
            } else {
                line.color = 0x557FBF6A; line.strokeWidth = dp(1f)
                var xx = X(r[0]); var k = 0
                while (xx < X(r[1])) { c.drawLine(xx, ground, xx + dp(1.5f), ground - dp(2f + (k % 3)), line); xx += dp(4f); k++ }
            }
        }
        s.aimX?.let { ax ->
            fill.color = 0xFFFFFFFF.toInt(); c.drawRect(X(ax) - dp(5f), ground - dp(1f), X(ax) + dp(5f), ground + dp(4f), fill)
        }
        s.glide?.let { g ->
            line.color = 0x88FFFFFF.toInt(); line.strokeWidth = dp(1.2f); line.pathEffect = DashPathEffect(floatArrayOf(dp(3f), dp(4f)), 0f)
            c.drawLine(X(g[0]), Y(g[1]), X(g[2]), Y(g[3]), line); line.pathEffect = null
        }
        s.refLine?.let { ry ->
            line.color = 0x66FFD60A; line.strokeWidth = dp(1f); line.pathEffect = DashPathEffect(floatArrayOf(dp(6f), dp(5f)), 0f)
            c.drawLine(0f, Y(ry), w, Y(ry), line); line.pathEffect = null
            if (!thumb) { txt.textSize = dp(9.5f); txt.color = 0xCCFFD60A.toInt(); txt.textAlign = Paint.Align.LEFT; c.drawText(s.refLabel, dp(8f), Y(ry) - dp(4f), txt) }
        }
        s.obstacle?.let { o -> tree(c, X(o[0]), ground, o[1] * sy) }

        val ahead = Path(); val flown = Path()
        val n = a.trail.size - 1; val cut = (p * n).toInt()
        for ((i, st) in a.trail.withIndex()) {
            if (i == 0) ahead.moveTo(X(st.x), Y(st.y)) else ahead.lineTo(X(st.x), Y(st.y))
            if (i <= cut) { if (i == 0) flown.moveTo(X(st.x), Y(st.y)) else flown.lineTo(X(st.x), Y(st.y)) }
        }
        val now = a.at(p)
        line.pathEffect = DashPathEffect(floatArrayOf(dp(4f), dp(5f)), 0f)
        line.color = 0x66FFFFFF; line.strokeWidth = dp(1.4f); c.drawPath(ahead, line); line.pathEffect = null
        if (thumb) { line.color = MAG; line.strokeWidth = dp(2f); c.drawPath(ahead, line); return }
        flown.lineTo(X(now.x), Y(now.y))
        line.color = 0x44FF2D9B; line.strokeWidth = dp(9f); c.drawPath(flown, line)
        line.color = MAG; line.strokeWidth = dp(3f); c.drawPath(flown, line)
        sidePlane(c, X(now.x), Y(now.y), now.pitch, now.flaps)
    }

    private fun tree(c: Canvas, x: Float, ground: Float, hpx: Float) {
        fill.color = 0xFF5B3A22.toInt(); c.drawRect(x - dp(1.5f), ground - hpx * 0.35f, x + dp(1.5f), ground, fill)
        fill.color = 0xFF2E6B35.toInt()
        val p = Path().apply { moveTo(x, ground - hpx); lineTo(x + hpx * 0.28f, ground - hpx * 0.3f); lineTo(x - hpx * 0.28f, ground - hpx * 0.3f); close() }
        c.drawPath(p, fill)
        txt.textSize = dp(9f); txt.color = 0xCCFFFFFF.toInt(); txt.textAlign = Paint.Align.CENTER
        c.drawText("50 FT", x, ground - hpx - dp(4f), txt)
    }

    /** A side silhouette of a low-wing two-seater, pitched; flaps drawn when out. */
    private fun sidePlane(c: Canvas, x: Float, y: Float, pitch: Float, flaps: Int) {
        val k = dp(1f)
        c.save(); c.translate(x, y); c.rotate(-pitch)
        val body = Path().apply {
            moveTo(15f * k, 0f)                    // spinner
            cubicTo(14f * k, -3f * k, 9f * k, -3.5f * k, 5f * k, -4f * k)
            cubicTo(2f * k, -8f * k, -4f * k, -8f * k, -6f * k, -4f * k)   // canopy
            lineTo(-17f * k, -2.5f * k)
            lineTo(-21f * k, -10f * k); lineTo(-24f * k, -10f * k); lineTo(-23f * k, -1f * k)   // fin
            lineTo(-22f * k, 1f * k)
            cubicTo(-10f * k, 2.5f * k, 6f * k, 3.5f * k, 15f * k, 1.5f * k)
            close()
        }
        fill.color = 0x55000000; c.save(); c.translate(dp(1.5f), dp(2f)); c.drawPath(body, fill); c.restore()
        fill.color = 0xFFF4F6F8.toInt(); c.drawPath(body, fill)
        fill.color = 0xFF2D8CFF.toInt(); c.drawRect(-15f * k, -0.6f * k, 13f * k, 0.8f * k, fill)  // stripe
        val canopy = Path().apply { moveTo(4f * k, -4f * k); cubicTo(1.5f * k, -7.2f * k, -3.5f * k, -7.2f * k, -5.5f * k, -4f * k); close() }
        fill.color = 0xFF1A3A5C.toInt(); c.drawPath(canopy, fill)
        // Low wing, with the flap hanging from its trailing edge.
        fill.color = 0xFFD0D5DB.toInt(); c.drawRoundRect(RectF(-6f * k, 1.6f * k, 5f * k, 3.6f * k), k, k, fill)
        if (flaps > 0) {
            c.save(); c.translate(-6f * k, 2.6f * k); c.rotate(-(min(50, flaps) * 0.8f))
            fill.color = AMBER; c.drawRect(-5f * k, -0.8f * k, 0f, 0.8f * k, fill); c.restore()
        }
        // Gear and the turning propeller.
        line.color = 0xFF9AA0A6.toInt(); line.strokeWidth = 1.2f * k
        c.drawLine(-1f * k, 3f * k, -2f * k, 6f * k, line); c.drawLine(11f * k, 2f * k, 11f * k, 5.5f * k, line)
        fill.color = 0xFF202326.toInt(); c.drawCircle(-2f * k, 6.6f * k, 1.6f * k, fill); c.drawCircle(11f * k, 6f * k, 1.4f * k, fill)
        val spin = (SystemClock.uptimeMillis() / 16 % 4).toInt()
        line.color = 0x99DDE3EA.toInt(); line.strokeWidth = 1.4f * k
        val half = (if (spin % 2 == 0) 7f else 4f) * k
        c.drawLine(15.6f * k, -half, 15.6f * k, half, line)
        c.restore()
    }

    // ---------------------------------------------------------------- overlays

    private fun hud(c: Canvas, st: ManeuverState, a: ManeuverAnim) {
        val rows = ArrayList<Pair<String, String>>()
        rows += "IAS" to "%.0f".format(st.ias)
        rows += "ALT" to "%.0f".format(st.alt)
        if (a.profile) rows += "PITCH" to "%+.0f°".format(st.pitch)
        if (!a.profile || abs(st.bank) >= 1) rows += "BANK" to (if (abs(st.bank) < 1) "0°" else "%.0f° %s".format(abs(st.bank), if (st.bank > 0) "R" else "L"))
        rows += "VS" to "%+.0f".format((st.vs / 10f).toInt() * 10f)
        if (!a.profile && a.scene.windFrom != null) rows += "GS" to "%.0f".format(st.gs)
        if (st.flaps > 0 || a.profile) rows += "FLAP" to "${st.flaps}°"

        val cellW = min(dp(54f), (width - dp(16f)) / rows.size); val hgt = dp(40f)
        val total = cellW * rows.size
        val left = max(dp(8f), (width - total) / 2f)
        val r = RectF(left, dp(8f), left + total, dp(8f) + hgt)
        fill.color = 0xD90C0D10.toInt(); c.drawRoundRect(r, dp(10f), dp(10f), fill)
        line.color = 0x30FFFFFF; line.strokeWidth = dp(1f); c.drawRoundRect(r, dp(10f), dp(10f), line)
        for ((i, row) in rows.withIndex()) {
            val cx = left + cellW * i + cellW / 2
            txt.textSize = dp(8.5f); txt.color = 0xFF9A9CA3.toInt(); txt.textAlign = Paint.Align.CENTER
            c.drawText(row.first, cx, r.top + dp(14f), txt)
            mono.textSize = dp(13.5f); mono.textAlign = Paint.Align.CENTER
            mono.color = when {
                row.first == "BANK" && abs(st.bank) > 40 -> AMBER
                row.first == "IAS" && st.warn != null -> RED
                else -> 0xFFFFFFFF.toInt()
            }
            c.drawText(row.second, cx, r.top + dp(32f), mono)
            if (i > 0) { line.color = 0x22FFFFFF; c.drawLine(left + cellW * i, r.top + dp(8f), left + cellW * i, r.bottom - dp(8f), line) }
        }
        attitude(c, st, a.profile)
        st.warn?.let { msg ->
            val blink = (SystemClock.uptimeMillis() / 260) % 2 == 0L
            if (blink || !playing) {
                txt.textSize = dp(12f); txt.textAlign = Paint.Align.CENTER
                val tw = txt.measureText(msg) + dp(22f)
                val rr = RectF(width / 2f - tw / 2, r.bottom + dp(8f), width / 2f + tw / 2, r.bottom + dp(32f))
                fill.color = RED; c.drawRoundRect(rr, dp(12f), dp(12f), fill)
                txt.color = 0xFFFFFFFF.toInt(); c.drawText(msg, width / 2f, rr.bottom - dp(7.5f), txt)
            }
        }
    }

    /** A small attitude ball: sky over ground, rolled and pitched, the airplane symbol fixed. */
    private fun attitude(c: Canvas, st: ManeuverState, profile: Boolean) {
        val rad = dp(26f)
        val cx = dp(12f) + rad; val cy = height - dp(46f) - rad
        c.save()
        val clip = Path().apply { addCircle(cx, cy, rad, Path.Direction.CW) }
        c.clipPath(clip)
        c.translate(cx, cy); c.rotate(-st.bank)
        val off = st.pitch * rad / 30f
        fill.color = 0xFF2F7BD6.toInt(); c.drawRect(-rad * 2, -rad * 2, rad * 2, off, fill)
        fill.color = 0xFF8A5A2E.toInt(); c.drawRect(-rad * 2, off, rad * 2, rad * 2, fill)
        line.color = 0xFFFFFFFF.toInt(); line.strokeWidth = dp(1.2f); c.drawLine(-rad * 2, off, rad * 2, off, line)
        line.strokeWidth = dp(0.8f)
        for (k in listOf(-10, 10)) { val yy = off - k * rad / 30f; c.drawLine(-rad * 0.25f, yy, rad * 0.25f, yy, line) }
        c.restore()
        line.color = 0x80FFFFFF.toInt(); line.strokeWidth = dp(1.2f); c.drawCircle(cx, cy, rad, line)
        line.color = AMBER; line.strokeWidth = dp(2.4f)
        c.drawLine(cx - rad * 0.55f, cy, cx - rad * 0.18f, cy, line); c.drawLine(cx + rad * 0.18f, cy, cx + rad * 0.55f, cy, line)
        fill.color = AMBER; c.drawCircle(cx, cy, dp(2f), fill)
    }

    private fun caption(c: Canvas, a: ManeuverAnim, p: Float) {
        val s = a.phase(p)
        if (s.isEmpty()) return
        txt.textSize = dp(12.5f); txt.textAlign = Paint.Align.CENTER
        val tw = txt.measureText(s) + dp(26f)
        val cx = width / 2f + dp(20f)
        val r = RectF(cx - tw / 2, height - dp(40f), cx + tw / 2, height - dp(14f))
        fill.color = 0xE6101216.toInt(); c.drawRoundRect(r, dp(13f), dp(13f), fill)
        line.color = 0x552D8CFF; line.strokeWidth = dp(1f); c.drawRoundRect(r, dp(13f), dp(13f), line)
        txt.color = 0xFFFFFFFF.toInt(); c.drawText(s, cx, r.bottom - dp(8.5f), txt)
    }

    private fun bar(c: Canvas, p: Float) {
        val y = height - dp(4f)
        fill.color = 0x33FFFFFF; c.drawRect(0f, y, width.toFloat(), height.toFloat(), fill)
        fill.color = ACC; c.drawRect(0f, y, width * p, height.toFloat(), fill)
    }

    private fun playBadge(c: Canvas) {
        val cx = width / 2f; val cy = height / 2f
        fill.color = 0x99000000.toInt(); c.drawCircle(cx, cy, dp(28f), fill)
        fill.color = 0xFFFFFFFF.toInt()
        val tri = Path().apply { moveTo(cx - dp(8f), cy - dp(12f)); lineTo(cx + dp(13f), cy); lineTo(cx - dp(8f), cy + dp(12f)); close() }
        c.drawPath(tri, fill)
    }
}
