package com.saudi.privatevault

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.Canvas
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.Shader
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.core.content.ContextCompat
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.tan

/**
 * Synthetic vision: the terrain ahead drawn in 3D from the aircraft's GPS
 * position, altitude and track, ground that rises near the aircraft's
 * altitude tinted yellow and red, airports marked, under a primary flight
 * display (ground speed, altitude, vertical speed, heading). Pitch and bank
 * can come from the phone's own sensors once it is mounted and levelled.
 * For awareness only: not an approved attitude reference.
 */
class SvtActivity : BaseActivity(), SensorEventListener {
    override val alwaysDark = true

    private lateinit var view: SvtView
    private var airports: List<AviationData.Airport> = emptyList()
    private var sensors: SensorManager? = null
    private var ahrs = false
    private var pitch0 = 0f
    private var roll0 = 0f
    private var rawPitch = 0f
    private var rawRoll = 0f

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        window.statusBarColor = 0xFF000000.toInt()
        Terrain.init(this)
        val root = FrameLayout(this)
        view = SvtView(this)
        root.addView(view, FrameLayout.LayoutParams(-1, -1))
        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END
            setPadding(EfbUi.dp(this@SvtActivity, 10), EfbUi.dp(this@SvtActivity, 36), EfbUi.dp(this@SvtActivity, 10), 0)
        }
        fun chip(t: String, onClick: () -> Unit) = EfbUi.text(this, t, 13f, EfbUi.TEXT, bold = true).apply {
            background = EfbUi.cardBg(this@SvtActivity, 0xCC16213A.toInt(), 18)
            setPadding(EfbUi.dp(this@SvtActivity, 12), EfbUi.dp(this@SvtActivity, 7), EfbUi.dp(this@SvtActivity, 12), EfbUi.dp(this@SvtActivity, 7))
            EfbUi.pressable(this, onClick)
            bar.addView(this, LinearLayout.LayoutParams(-2, -2).apply { marginStart = EfbUi.dp(this@SvtActivity, 8) })
        }
        lateinit var att: TextView
        att = chip(getString(R.string.svt_ahrs_off)) {
            ahrs = !ahrs
            if (ahrs) { pitch0 = rawPitch; roll0 = rawRoll; Toast.makeText(this, R.string.svt_ahrs_hint, Toast.LENGTH_LONG).show() }
            att.text = getString(if (ahrs) R.string.svt_ahrs_on else R.string.svt_ahrs_off)
            if (!ahrs) { view.pitch = 0f; view.roll = 0f }
        }
        chip(getString(R.string.svt_level)) { pitch0 = rawPitch; roll0 = rawRoll }
        chip("✕") { finish() }
        root.addView(bar, FrameLayout.LayoutParams(-1, -2, Gravity.TOP))
        setContentView(root)
        Terrain.onTile = { view.postInvalidate() }
        Thread { airports = AviationData.airports(this); view.airports = airports }.start()
        sensors = getSystemService(Context.SENSOR_SERVICE) as? SensorManager
        startGps()
    }

    override fun onResume() {
        super.onResume()
        sensors?.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)?.let { sensors?.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME) }
    }

    override fun onPause() {
        super.onPause()
        sensors?.unregisterListener(this)
    }

    override fun onDestroy() {
        super.onDestroy()
        Terrain.onTile = null
        try { getSystemService(LocationManager::class.java)?.removeUpdates(gps) } catch (e: Exception) {}
    }

    private val rot = FloatArray(9)
    private val ori = FloatArray(3)

    override fun onSensorChanged(e: SensorEvent) {
        SensorManager.getRotationMatrixFromVector(rot, e.values)
        SensorManager.getOrientation(rot, ori)
        rawPitch = Math.toDegrees(ori[1].toDouble()).toFloat()
        rawRoll = Math.toDegrees(ori[2].toDouble()).toFloat()
        if (ahrs) {
            // Smoothed, and measured from the attitude the phone had when levelled in its mount.
            view.pitch += ((-(rawPitch - pitch0)) - view.pitch) * 0.2f
            view.roll += ((rawRoll - roll0) - view.roll) * 0.2f
            view.invalidate()
        }
    }

    override fun onAccuracyChanged(s: Sensor?, a: Int) {}

    private val gps = LocationListener { l -> view.update(l) }

    @SuppressLint("MissingPermission")
    private fun startGps() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) return
        val m = getSystemService(LocationManager::class.java) ?: return
        try {
            m.getLastKnownLocation(LocationManager.GPS_PROVIDER)?.let { view.update(it) }
            m.requestLocationUpdates(LocationManager.GPS_PROVIDER, 0L, 0f, gps, mainLooper)
        } catch (e: Exception) {
        }
    }
}

@SuppressLint("ViewConstructor")
class SvtView(ctx: Context) : View(ctx) {
    var pitch = 0f
    var roll = 0f
    var airports: List<AviationData.Airport> = emptyList()

    private var fix: Location? = null
    private var heading = 0.0
    private var lastAlt = Double.NaN
    private var lastAt = 0L
    private var vs = 0.0
    private val d = ctx.resources.displayMetrics.density

    fun update(l: Location) {
        fix = l
        if (l.hasBearing() && l.hasSpeed() && l.speed > 2) heading = l.bearing.toDouble()
        if (l.hasAltitude()) {
            val ft = l.altitude * 3.28084
            val now = System.currentTimeMillis()
            if (!lastAlt.isNaN() && now > lastAt) vs = vs * 0.7 + ((ft - lastAlt) / ((now - lastAt) / 60000.0)).coerceIn(-5000.0, 5000.0) * 0.3
            lastAlt = ft
            lastAt = now
        }
        invalidate()
    }

    private val sky = Paint()
    private val earth = Paint().apply { color = 0xFF5D4037.toInt() }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFFFFFF.toInt(); strokeWidth = 2 * d; style = Paint.Style.STROKE }
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFFFFFF.toInt(); textSize = 15 * d; isFakeBoldText = true; textAlign = Paint.Align.CENTER }
    private val box = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xCC000000.toInt() }
    private val path = Path()

    // The ground ahead: rows from near to far, columns across a 90° view.
    private val rows = 46
    private val cols = 33
    private val sx = FloatArray(rows * cols)
    private val sy = FloatArray(rows * cols)
    private val ok = BooleanArray(rows * cols)
    private val elev = FloatArray(rows * cols)

    override fun onDraw(c: Canvas) {
        val l = fix
        val w = width.toFloat(); val h = height.toFloat()
        val cx = w / 2; val cy = h * 0.45f
        val f = (w / 2) / tan(Math.toRadians(45.0)).toFloat()
        val altFt = l?.takeIf { it.hasAltitude() }?.altitude?.times(3.28084) ?: 0.0
        val pr = Math.toRadians(pitch.toDouble())
        val horizon = cy + (tan(pr) * f).toFloat()
        c.save()
        c.rotate(-roll, cx, cy)
        sky.shader = LinearGradient(0f, horizon - h, 0f, horizon, 0xFF0D47A1.toInt(), 0xFF64B5F6.toInt(), Shader.TileMode.CLAMP)
        c.drawRect(-w, horizon - 2 * h, 2 * w, horizon, sky)
        c.drawRect(-w, horizon, 2 * w, horizon + 2 * h, earth)
        if (l != null) drawTerrain(c, l, altFt, cx, cy, f, pr)
        c.drawLine(-w, horizon, 2 * w, horizon, line)
        // Pitch ladder every 5°.
        text.textSize = 11 * d
        for (deg in listOf(-10, -5, 5, 10)) {
            val y = cy + (tan(pr - Math.toRadians(deg.toDouble())) * f).toFloat()
            val half = if (deg % 10 == 0) 60 * d else 30 * d
            c.drawLine(cx - half, y, cx + half, y, line)
            c.drawText("$deg", cx - half - 14 * d, y + 4 * d, text)
        }
        c.restore()
        // Aircraft symbol.
        line.color = 0xFFFFD600.toInt(); line.strokeWidth = 4 * d
        c.drawLine(cx - 70 * d, cy, cx - 25 * d, cy, line)
        c.drawLine(cx + 25 * d, cy, cx + 70 * d, cy, line)
        c.drawCircle(cx, cy, 4 * d, line)
        line.color = 0xFFFFFFFF.toInt(); line.strokeWidth = 2 * d
        drawTapes(c, l, altFt, w, h)
    }

    private fun drawTerrain(c: Canvas, l: Location, altFt: Double, cx: Float, cy: Float, f: Float, pr: Double) {
        val hd = Math.toRadians(heading)
        val sinH = sin(hd); val cosH = cos(hd)
        val cosP = cos(pr); val sinP = sin(pr)
        val mLat = 111320.0; val mLon = 111320.0 * cos(Math.toRadians(l.latitude))
        val camM = altFt / 3.28084
        for (r in 0 until rows) {
            val fwd = 150.0 * Math.pow(1.11, r.toDouble())     // 150 m out to about 18 nm
            for (k in 0 until cols) {
                val i = r * cols + k
                val side = fwd * ((k - (cols - 1) / 2.0) / ((cols - 1) / 2.0)) * 1.15
                val east = fwd * sinH + side * cosH
                val north = fwd * cosH - side * sinH
                val e = Terrain.elevationFt(l.latitude + north / mLat, l.longitude + east / mLon)
                elev[i] = e ?: Float.NaN
                if (e == null) { ok[i] = false; continue }
                val up = e / 3.28084 - camM
                val fz = fwd * cosP + up * sinP
                val uz = up * cosP - fwd * sinP
                if (fz < 20) { ok[i] = false; continue }
                ok[i] = true
                sx[i] = (cx + side / fz * f).toFloat()
                sy[i] = (cy - uz / fz * f).toFloat()
            }
        }
        // Far rows first, so nearer ground covers what it hides.
        for (r in rows - 2 downTo 0) for (k in 0 until cols - 1) {
            val a = r * cols + k; val b = a + 1; val cc = a + cols + 1; val dd = a + cols
            if (!ok[a] || !ok[b] || !ok[cc] || !ok[dd]) continue
            val e = maxOf(elev[a], elev[b], elev[cc], elev[dd])
            val slope = (elev[dd] - elev[a]).coerceIn(-300f, 300f) / 300f
            fill.color = when {
                e >= altFt - 100 -> 0xFFD32F2F.toInt()
                e >= altFt - 1000 -> 0xFFF9A825.toInt()
                else -> shade(e, slope)
            }
            path.reset()
            path.moveTo(sx[a], sy[a]); path.lineTo(sx[b], sy[b]); path.lineTo(sx[cc], sy[cc]); path.lineTo(sx[dd], sy[dd]); path.close()
            c.drawPath(path, fill)
        }
        // Airports ahead, with their identifiers.
        text.textSize = 13 * d
        for (a in airports) {
            val dn = (a.lat - l.latitude) * mLat; val de = (a.lon - l.longitude) * mLon
            val fwd = de * sinH + dn * cosH
            val side = de * cosH - dn * sinH
            if (fwd < 300 || fwd > 30000 || Math.abs(side) > fwd * 1.2) continue
            val up = a.elevation / 3.28084 - camM
            val fz = fwd * cosP + up * sinP
            val uz = up * cosP - fwd * sinP
            val x = (cx + side / fz * f).toFloat(); val y = (cy - uz / fz * f).toFloat()
            fill.color = 0xFF00E5FF.toInt()
            c.drawCircle(x, y, 5 * d, fill)
            c.drawText(a.icao.ifEmpty { a.ident } + " %.1f".format(Math.hypot(dn, de) / 1852), x, y - 10 * d, text)
        }
    }

    /** Lower ground greener, higher ground browner and paler, lit from the north-west. */
    private fun shade(ft: Float, slope: Float): Int {
        val t = (ft / 9000f).coerceIn(0f, 1f)
        val r = 70 + t * 120; val g = 110 + t * 60 - t * t * 40; val b = 50 + t * 70
        val k = 0.75f + slope * 0.25f
        return android.graphics.Color.rgb((r * k).toInt().coerceIn(0, 255), (g * k).toInt().coerceIn(0, 255), (b * k).toInt().coerceIn(0, 255))
    }

    private fun drawTapes(c: Canvas, l: Location?, altFt: Double, w: Float, h: Float) {
        val kt = l?.takeIf { it.hasSpeed() }?.speed?.times(1.943844) ?: 0.0
        val rect = RectF()
        fun readout(x: Float, y: Float, wide: Float, big: String, small: String) {
            rect.set(x - wide / 2, y - 26 * d, x + wide / 2, y + 20 * d)
            c.drawRoundRect(rect, 8 * d, 8 * d, box)
            text.textSize = 20 * d
            c.drawText(big, x, y + 2 * d, text)
            text.textSize = 10 * d
            c.drawText(small, x, y + 15 * d, text)
        }
        val cy = h * 0.45f
        readout(52 * d, cy, 84 * d, "%d".format(Math.round(kt)), "GS KT")
        readout(w - 60 * d, cy, 100 * d, "%,d".format(Math.round(altFt)), "ALT FT (GPS)")
        readout(w - 60 * d, cy + 60 * d, 100 * d, "%+d".format((Math.round(vs / 50) * 50).toInt()), "FPM")
        val mag = l?.let { Nav.magnetic(heading, it.latitude, it.longitude) } ?: heading
        readout(w / 2, 70 * d, 90 * d, Nav.deg(mag), "TRK M")
        if (l == null) {
            text.textSize = 16 * d
            c.drawText(context.getString(R.string.map_no_gps), w / 2, h * 0.8f, text)
        }
        text.textSize = 10 * d
        c.drawText(context.getString(R.string.svt_note), w / 2, h - 14 * d, text)
    }
}
