package com.saudi.privatevault

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.drawable.GradientDrawable
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.SystemClock
import android.text.InputType
import android.view.Gravity
import android.view.MotionEvent
import android.view.Surface
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import com.google.android.material.dialog.MaterialAlertDialogBuilder

/**
 * A backup panel for situational awareness, as the six instruments are laid out: speed, attitude,
 * altitude, turn, heading, vertical speed. Speed, altitude, heading, turn and climb come from the
 * GPS (ground speed, GPS altitude, track); the attitude from the tablet's own motion sensors, levelled
 * by the pilot. Under them COM1 / COM2 (active ⇄ standby) and the transponder.
 * Not certified and not a primary reference: the aircraft's own instruments always come first.
 */
@SuppressLint("ViewConstructor")
class SixPack(ctx: Context) : View(ctx) {
    var gs = Double.NaN
    var alt = Double.NaN
    var vs = Double.NaN
    var trk = Double.NaN
    var turn = 0.0
    var pitch = 0f
    var roll = 0f
    var attitudeOk = false

    private val d = ctx.resources.displayMetrics.density
    private val face = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF111417.toInt() }
    private val rim = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF3A424C.toInt(); style = Paint.Style.STROKE; strokeWidth = 2.5f * d }
    private val tick = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; strokeWidth = 1.6f * d; strokeCap = Paint.Cap.ROUND }
    private val needle = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; strokeWidth = 3f * d; strokeCap = Paint.Cap.ROUND }
    private val txt = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; textAlign = Paint.Align.CENTER; textSize = 9 * d }
    private val big = Paint(txt).apply { textSize = 13 * d; isFakeBoldText = true; typeface = android.graphics.Typeface.MONOSPACE }
    private val lab = Paint(txt).apply { color = 0xFF9FB0C0.toInt(); textSize = 8 * d }
    private val sky = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF2F7FD6.toInt() }
    private val ground = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF8A5A2B.toInt() }
    private val yellow = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFFC107.toInt(); strokeWidth = 3.5f * d; style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND }

    override fun onMeasure(w: Int, h: Int) {
        val width = MeasureSpec.getSize(w)
        setMeasuredDimension(width, (width / 3f * 2f).toInt())
    }

    override fun onDraw(c: Canvas) {
        val cw = width / 3f; val ch = height / 2f
        val r = minOf(cw, ch) / 2f - 4 * d
        fun center(i: Int) = (cw * (i % 3) + cw / 2) to (ch * (i / 3) + ch / 2)
        for (i in 0 until 6) { val (x, y) = center(i); c.drawCircle(x, y, r, face); c.drawCircle(x, y, r, rim) }
        center(0).let { (x, y) -> asi(c, x, y, r) }
        center(1).let { (x, y) -> attitude(c, x, y, r) }
        center(2).let { (x, y) -> altimeter(c, x, y, r) }
        center(3).let { (x, y) -> turnCoord(c, x, y, r) }
        center(4).let { (x, y) -> heading(c, x, y, r) }
        center(5).let { (x, y) -> vsi(c, x, y, r) }
    }

    private fun dial(c: Canvas, x: Float, y: Float, r: Float, from: Float, sweep: Float, n: Int, labels: (Int) -> String?) {
        for (i in 0..n) {
            val a = Math.toRadians((from + sweep * i / n - 90).toDouble())
            val major = labels(i) != null
            val r0 = r * (if (major) 0.78f else 0.86f)
            c.drawLine(x + (r0 * Math.cos(a)).toFloat(), y + (r0 * Math.sin(a)).toFloat(), x + (r * 0.95f * Math.cos(a)).toFloat(), y + (r * 0.95f * Math.sin(a)).toFloat(), tick)
            labels(i)?.let { s -> c.drawText(s, x + (r * 0.62f * Math.cos(a)).toFloat(), y + (r * 0.62f * Math.sin(a)).toFloat() + 3 * d, txt) }
        }
    }

    private fun hand(c: Canvas, x: Float, y: Float, r: Float, deg: Float, p: Paint = needle) {
        val a = Math.toRadians((deg - 90).toDouble())
        c.drawLine(x, y, x + (r * Math.cos(a)).toFloat(), y + (r * Math.sin(a)).toFloat(), p)
        c.drawCircle(x, y, 3 * d, tick)
    }

    private fun asi(c: Canvas, x: Float, y: Float, r: Float) {
        // 0–160 kt over 320°.
        dial(c, x, y, r, 20f, 320f, 16) { i -> if (i % 2 == 0) (i * 10).toString() else null }
        c.drawText("GS kt", x, y + r * 0.35f, lab)
        if (!gs.isNaN()) { hand(c, x, y, r * 0.8f, 20f + (gs.coerceIn(0.0, 160.0) * 2).toFloat()); c.drawText("%d".format(Math.round(gs)), x, y - r * 0.25f, big) }
    }

    private fun attitude(c: Canvas, x: Float, y: Float, r: Float) {
        c.save()
        val clip = Path().apply { addCircle(x, y, r - 2 * d, Path.Direction.CW) }
        c.clipPath(clip)
        c.rotate(-roll, x, y)
        val ppd = r / 30f   // pixels per degree of pitch
        val hy = y + pitch * ppd
        c.drawRect(x - r * 2, y - r * 3, x + r * 2, hy, sky)
        c.drawRect(x - r * 2, hy, x + r * 2, y + r * 3, ground)
        c.drawLine(x - r * 2, hy, x + r * 2, hy, tick)
        for (p in intArrayOf(-20, -10, 10, 20)) {
            val py = hy - p * ppd; val w = if (Math.abs(p) == 10) r * 0.25f else r * 0.4f
            c.drawLine(x - w, py, x + w, py, tick)
        }
        c.restore()
        // Bank scale and the little aircraft, fixed.
        for (b in intArrayOf(-60, -30, -20, -10, 0, 10, 20, 30, 60)) {
            val a = Math.toRadians((b - 90).toDouble())
            val r0 = if (b % 30 == 0) r * 0.78f else r * 0.85f
            c.drawLine(x + (r0 * Math.cos(a)).toFloat(), y + (r0 * Math.sin(a)).toFloat(), x + (r * 0.95f * Math.cos(a)).toFloat(), y + (r * 0.95f * Math.sin(a)).toFloat(), tick)
        }
        c.drawLine(x - r * 0.5f, y, x - r * 0.15f, y, yellow); c.drawLine(x + r * 0.15f, y, x + r * 0.5f, y, yellow)
        c.drawCircle(x, y, 2.5f * d, yellow)
        if (!attitudeOk) c.drawText("LEVEL ↻", x, y + r * 0.6f, big)
    }

    private fun altimeter(c: Canvas, x: Float, y: Float, r: Float) {
        dial(c, x, y, r, 0f, 360f, 50) { i -> if (i % 5 == 0 && i < 50) (i / 5).toString() else null }
        c.drawText("GPS ALT", x, y + r * 0.35f, lab)
        if (!alt.isNaN()) {
            val a = alt.coerceAtLeast(0.0)
            hand(c, x, y, r * 0.5f, ((a % 10000) / 10000 * 360).toFloat(), Paint(needle).apply { strokeWidth = 4.5f * d })
            hand(c, x, y, r * 0.82f, ((a % 1000) / 1000 * 360).toFloat())
            c.drawText("%,d".format(Math.round(a)), x, y - r * 0.25f, big)
        }
    }

    private fun turnCoord(c: Canvas, x: Float, y: Float, r: Float) {
        // Standard rate (3°/s) at the marks 20° either side.
        c.drawText("TURN · 2 MIN", x, y - r * 0.5f, lab)
        for (s in intArrayOf(-1, 1)) for (m in intArrayOf(0, 20)) {
            val a = Math.toRadians((180 + s * (90 - m)).toDouble())
            c.drawLine(x + (r * 0.75f * Math.cos(a)).toFloat(), y + (r * 0.75f * Math.sin(a)).toFloat(), x + (r * 0.95f * Math.cos(a)).toFloat(), y + (r * 0.95f * Math.sin(a)).toFloat(), tick)
        }
        c.save()
        c.rotate((turn / 3.0 * 20).coerceIn(-40.0, 40.0).toFloat(), x, y)
        c.drawLine(x - r * 0.6f, y, x + r * 0.6f, y, Paint(needle).apply { strokeWidth = 4 * d })
        c.drawLine(x, y, x, y - r * 0.2f, Paint(needle).apply { strokeWidth = 4 * d })
        c.drawCircle(x, y, 5 * d, needle)
        c.restore()
        c.drawText("%.1f°/s".format(turn), x, y + r * 0.55f, txt)
    }

    private fun heading(c: Canvas, x: Float, y: Float, r: Float) {
        c.save()
        val h = if (trk.isNaN()) 0f else trk.toFloat()
        c.rotate(-h, x, y)
        dial(c, x, y, r, 0f, 360f, 36) { i -> when (i) { 0 -> "N"; 9 -> "E"; 18 -> "S"; 27 -> "W"; else -> if (i % 3 == 0 && i < 36) (i).toString() else null } }
        c.restore()
        // The lubber line and a small aircraft.
        c.drawLine(x, y - r, x, y - r * 0.8f, yellow)
        val p = Path().apply { moveTo(x, y - r * 0.3f); lineTo(x + r * 0.2f, y + r * 0.2f); lineTo(x, y + r * 0.08f); lineTo(x - r * 0.2f, y + r * 0.2f); close() }
        c.drawPath(p, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFFC107.toInt() })
        c.drawText(if (trk.isNaN()) "TRK ---" else "TRK %03d°".format(Math.round(trk).toInt() % 360), x, y + r * 0.55f, big)
    }

    private fun vsi(c: Canvas, x: Float, y: Float, r: Float) {
        // ±2000 fpm, 0 at nine o'clock.
        dial(c, x, y, r, 270f - 170f, 340f, 8) { i -> listOf("20", "15", "10", "5", "0", "5", "10", "15", "20")[i].takeIf { i % 2 == 0 } }
        c.drawText("VS ×100", x, y + r * 0.35f, lab)
        if (!vs.isNaN()) {
            val v = vs.coerceIn(-2000.0, 2000.0)
            hand(c, x, y, r * 0.82f, (270 + v / 2000 * 170).toFloat())
            c.drawText("%+d".format((Math.round(vs / 10) * 10).toInt()), x, y - r * 0.25f, big)
        }
    }
}

object AvionicsPanel : SensorEventListener {
    private const val TAG = "avionics_panel"
    private var six: SixPack? = null
    private var sm: SensorManager? = null
    private var act: Activity? = null
    private var lastTrk = Double.NaN
    private var lastTrkAt = 0L
    private val rot = FloatArray(9)
    private val out = FloatArray(9)
    private val o = FloatArray(3)
    private var pitch0 = 0f
    private var roll0 = 0f
    private var rawP = 0f
    private var rawR = 0f

    fun isOpen(act: Activity) = act.findViewById<FrameLayout>(android.R.id.content)?.findViewWithTag<View>(TAG) != null

    fun toggle(act: Activity) {
        val content = act.findViewById<FrameLayout>(android.R.id.content) ?: return
        content.findViewWithTag<View>(TAG)?.let { close(act); return }
        AvionicsPanel.act = act
        val dd = act.resources.displayMetrics.density
        fun dp(v: Int) = (v * dd).toInt()
        val p = VaultLock.prefs(act)
        pitch0 = p.getFloat("ahrs_p0", 0f); roll0 = p.getFloat("ahrs_r0", 0f)
        val card = LinearLayout(act).apply {
            tag = TAG; orientation = LinearLayout.VERTICAL; elevation = dp(24).toFloat()
            setPadding(dp(8), dp(4), dp(8), dp(8)); layoutDirection = View.LAYOUT_DIRECTION_LTR
            background = GradientDrawable().apply { setColor(0xF2090B0D.toInt()); cornerRadius = dp(18).toFloat(); setStroke(dp(1), 0xFF2A323C.toInt()) }
        }
        // Handle: drag to move, ✕ to close, ⟲ to level the attitude.
        val head = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        head.addView(TextView(act).apply { text = act.getString(R.string.av_title); textSize = 12f; setTextColor(0xFF9FB0C0.toInt()); typeface = EfbUi.MEDIUM }, LinearLayout.LayoutParams(0, -2, 1f))
        fun chip(t: String, f: () -> Unit) = TextView(act).apply { text = t; textSize = 13f; setTextColor(Color.WHITE); setPadding(dp(10), dp(6), dp(10), dp(6)); setOnClickListener { f() } }
        head.addView(chip("⟲ " + act.getString(R.string.av_level)) {
            pitch0 = rawP; roll0 = rawR
            p.edit().putFloat("ahrs_p0", pitch0).putFloat("ahrs_r0", roll0).apply()
            six?.attitudeOk = true
        })
        head.addView(chip("✕") { close(act) })
        card.addView(head)
        val s = SixPack(act)
        six = s
        s.attitudeOk = p.contains("ahrs_p0")
        card.addView(s, LinearLayout.LayoutParams(-1, -2))
        card.addView(radios(act, ::dp))
        card.addView(TextView(act).apply { text = act.getString(R.string.av_note); textSize = 10f; setTextColor(0xFF7E8B98.toInt()); setPadding(dp(4), dp(4), dp(4), 0) })
        val w = minOf(act.resources.displayMetrics.widthPixels - dp(16), dp(420))
        content.addView(card, FrameLayout.LayoutParams(w, -2, Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL).apply { bottomMargin = dp(70) })
        var sy = 0f; var ty = 0f
        head.setOnTouchListener { _, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> { sy = e.rawY; ty = card.translationY }
                MotionEvent.ACTION_MOVE -> card.translationY = ty + e.rawY - sy
            }
            true
        }
        sm = act.getSystemService(SensorManager::class.java)
        (sm?.getDefaultSensor(Sensor.TYPE_GAME_ROTATION_VECTOR) ?: sm?.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR))?.let {
            sm?.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME)
        }
    }

    fun close(act: Activity) {
        try { sm?.unregisterListener(this) } catch (e: Exception) {}
        sm = null; six = null; AvionicsPanel.act = null
        val content = act.findViewById<FrameLayout>(android.R.id.content) ?: return
        content.findViewWithTag<View>(TAG)?.let { v -> content.post { (v.parent as? ViewGroup)?.removeView(v) } }
    }

    /** One GPS fix: ground speed (kt), GPS altitude (ft), vertical speed (fpm), track (°M). */
    fun feed(gs: Double, alt: Double, vs: Double, trk: Double) {
        val s = six ?: return
        val now = SystemClock.elapsedRealtime()
        if (!trk.isNaN() && !lastTrk.isNaN() && now > lastTrkAt) {
            val dt = (now - lastTrkAt) / 1000.0
            val dTrk = ((trk - lastTrk + 540) % 360) - 180
            if (dt in 0.2..5.0) s.turn = s.turn * 0.6 + (dTrk / dt) * 0.4
        }
        if (!trk.isNaN()) { lastTrk = trk; lastTrkAt = now }
        s.gs = gs; s.alt = alt; s.vs = vs; s.trk = trk
        s.invalidate()
    }

    override fun onSensorChanged(e: SensorEvent) {
        val s = six ?: return
        val a = act ?: return
        SensorManager.getRotationMatrixFromVector(rot, e.values)
        // The tablet upright on the panel or the knee, whichever way the screen is turned.
        val rotation = try { a.display?.rotation ?: Surface.ROTATION_0 } catch (x: Exception) { Surface.ROTATION_0 }
        when (rotation) {
            Surface.ROTATION_90 -> SensorManager.remapCoordinateSystem(rot, SensorManager.AXIS_Z, SensorManager.AXIS_MINUS_X, out)
            Surface.ROTATION_270 -> SensorManager.remapCoordinateSystem(rot, SensorManager.AXIS_MINUS_Z, SensorManager.AXIS_X, out)
            else -> SensorManager.remapCoordinateSystem(rot, SensorManager.AXIS_X, SensorManager.AXIS_Z, out)
        }
        SensorManager.getOrientation(out, o)
        rawP = Math.toDegrees(-o[1].toDouble()).toFloat()
        rawR = Math.toDegrees(o[2].toDouble()).toFloat()
        // Smoothed, so a bump does not swing the horizon.
        s.pitch = s.pitch * 0.8f + (rawP - pitch0) * 0.2f
        s.roll = s.roll * 0.8f + (rawR - roll0) * 0.2f
        s.invalidate()
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    /** COM1 and COM2, active ⇄ standby, and the transponder: what is set, kept, a tap away. */
    private fun radios(act: Activity, dp: (Int) -> Int): View {
        val p = VaultLock.prefs(act)
        val box = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; setPadding(0, dp(6), 0, 0) }
        fun field(label: String, keyA: String, keyS: String, defA: String, defS: String) {
            val row = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(4), dp(3), dp(4), dp(3)) }
            row.addView(TextView(act).apply { text = label; textSize = 12f; setTextColor(0xFF9FB0C0.toInt()); typeface = EfbUi.MEDIUM }, LinearLayout.LayoutParams(dp(52), -2))
            val a = TextView(act).apply { textSize = 20f; setTextColor(0xFF39FF14.toInt()); typeface = android.graphics.Typeface.MONOSPACE; setTypeface(typeface, android.graphics.Typeface.BOLD) }
            val sb = TextView(act).apply { textSize = 17f; setTextColor(0xFFB8C4CE.toInt()); typeface = android.graphics.Typeface.MONOSPACE }
            fun paint() { a.text = p.getString(keyA, defA); sb.text = p.getString(keyS, defS) }
            paint()
            val swap = TextView(act).apply {
                text = "⇄"; textSize = 20f; setTextColor(Color.WHITE); setPadding(dp(14), dp(2), dp(14), dp(2))
                background = GradientDrawable().apply { setColor(0xFF1A2029.toInt()); cornerRadius = dp(10).toFloat() }
                setOnClickListener { val x = p.getString(keyA, defA); p.edit().putString(keyA, p.getString(keyS, defS)).putString(keyS, x).apply(); paint() }
            }
            sb.setOnClickListener { ask(act, label + " STBY", sb.text.toString(), freq = true) { v -> p.edit().putString(keyS, v).apply(); paint() } }
            a.setOnClickListener { ask(act, label, a.text.toString(), freq = true) { v -> p.edit().putString(keyA, v).apply(); paint() } }
            row.addView(a, LinearLayout.LayoutParams(0, -2, 1f))
            row.addView(swap)
            row.addView(sb, LinearLayout.LayoutParams(0, -2, 1f).apply { marginStart = dp(12) })
            box.addView(row)
        }
        field("COM1", "com1_a", "com1_s", "122.800", "121.500")
        field("COM2", "com2_a", "com2_s", "121.500", "122.800")
        // Transponder: the code, the mode, VFR 1200 at a tap, IDENT for 18 seconds.
        val x = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(4), dp(3), dp(4), dp(3)) }
        x.addView(TextView(act).apply { text = "XPDR"; textSize = 12f; setTextColor(0xFF9FB0C0.toInt()); typeface = EfbUi.MEDIUM }, LinearLayout.LayoutParams(dp(52), -2))
        val code = TextView(act).apply { textSize = 20f; setTextColor(0xFF39FF14.toInt()); typeface = android.graphics.Typeface.MONOSPACE; setTypeface(typeface, android.graphics.Typeface.BOLD) }
        val mode = TextView(act).apply { textSize = 13f; setTextColor(Color.WHITE); setPadding(dp(10), dp(4), dp(10), dp(4)); background = GradientDrawable().apply { setColor(0xFF1A2029.toInt()); cornerRadius = dp(10).toFloat() } }
        fun paintX() {
            val c = p.getString("xpdr", "1200")!!
            code.text = c
            code.setTextColor(when (c) { "7500", "7600", "7700" -> 0xFFFF5252.toInt(); else -> 0xFF39FF14.toInt() })
            mode.text = p.getString("xpdr_mode", "ALT")
        }
        paintX()
        code.setOnClickListener { ask(act, "Squawk", code.text.toString(), freq = false) { v -> p.edit().putString("xpdr", v).apply(); paintX() } }
        mode.setOnClickListener { val m = listOf("SBY", "ON", "ALT"); val n = m[(m.indexOf(p.getString("xpdr_mode", "ALT")) + 1) % 3]; p.edit().putString("xpdr_mode", n).apply(); paintX() }
        val vfr = TextView(act).apply { text = "VFR"; textSize = 13f; setTextColor(Color.WHITE); setPadding(dp(10), dp(4), dp(10), dp(4)); setOnClickListener { p.edit().putString("xpdr", "1200").apply(); paintX() } }
        val ident = TextView(act).apply {
            text = "IDENT"; textSize = 13f; setTextColor(Color.WHITE); setPadding(dp(10), dp(4), dp(10), dp(4))
            background = GradientDrawable().apply { setColor(0xFF1A2029.toInt()); cornerRadius = dp(10).toFloat() }
            setOnClickListener { v -> (v as TextView).setTextColor(0xFF39FF14.toInt()); v.postDelayed({ v.setTextColor(Color.WHITE) }, 18000) }
        }
        x.addView(code, LinearLayout.LayoutParams(0, -2, 1f))
        x.addView(mode); x.addView(vfr); x.addView(ident)
        box.addView(x)
        return box
    }

    /** A frequency (118.000–136.990) or a squawk (four digits 0–7), checked before it is kept. */
    private fun ask(act: Activity, title: String, now: String, freq: Boolean, done: (String) -> Unit) {
        val e = EditText(act).apply {
            setText(now); setSelectAllOnFocus(true)
            inputType = if (freq) InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL else InputType.TYPE_CLASS_NUMBER
        }
        MaterialAlertDialogBuilder(act).setTitle(title).setView(e)
            .setPositiveButton(android.R.string.ok) { _, _ ->
                val t = e.text.toString().trim()
                if (freq) {
                    val f = t.replace(',', '.').toDoubleOrNull()
                    val v = f?.let { if (it < 1000 && it >= 118.0 && it < 137.0) it else if (it in 118000.0..136999.0) it / 1000 else null }
                    if (v != null) done("%.3f".format(java.util.Locale.US, v))
                    else android.widget.Toast.makeText(act, "118.000 – 136.990", android.widget.Toast.LENGTH_SHORT).show()
                } else {
                    if (t.length == 4 && t.all { it in '0'..'7' }) done(t)
                    else android.widget.Toast.makeText(act, "0000 – 7777", android.widget.Toast.LENGTH_SHORT).show()
                }
            }.setNegativeButton(R.string.cancel, null).show()
    }
}
