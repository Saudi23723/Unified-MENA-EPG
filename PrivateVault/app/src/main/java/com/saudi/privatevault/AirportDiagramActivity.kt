package com.saudi.privatevault

import android.Manifest
import android.animation.ValueAnimator
import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Canvas
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import android.os.SystemClock
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.view.animation.DecelerateInterpolator
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin

/**
 * An airport on its own, full screen and in 3D: runways with their
 * markings and numbers, taxiways with their names, aprons, and the
 * buildings standing up from the ground, drawn from OpenStreetMap's survey
 * of the field. The aircraft moves on it from the GPS, and the screen warns
 * when it rolls onto a runway. The FAA's own diagram is a tap away.
 */
class AirportDiagramActivity : BaseActivity() {

    private lateinit var view: AirportView
    private lateinit var status: TextView
    private lateinit var surface: TextView
    private var ident = ""
    private var lat0 = 0.0
    private var lon0 = 0.0
    private fun dp(v: Int) = EfbUi.dp(this, v)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        window.statusBarColor = EfbUi.BG
        window.navigationBarColor = EfbUi.BG
        ident = intent.getStringExtra("ident") ?: ""
        lat0 = intent.getDoubleExtra("lat", 0.0)
        lon0 = intent.getDoubleExtra("lon", 0.0)
        val name = intent.getStringExtra("name") ?: ""
        val root = FrameLayout(this).apply { setBackgroundColor(EfbUi.BG) }
        view = AirportView(this, lat0, lon0)
        root.addView(view, FrameLayout.LayoutParams(-1, -1))

        val top = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(12), dp(10), dp(12), 0)
        }
        val head = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        head.addView(chip("✕") { finish() })
        head.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(12), 0, 0, 0)
            addView(EfbUi.text(this@AirportDiagramActivity, intent.getStringExtra("icao")?.ifEmpty { ident } ?: ident, 22f, EfbUi.ACCENT, bold = true))
            addView(EfbUi.text(this@AirportDiagramActivity, name, 12f, EfbUi.DIM))
        }, LinearLayout.LayoutParams(0, -2, 1f))
        top.addView(head)
        val chips = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(8), 0, 0) }
        lateinit var c3d: TextView
        lateinit var cFollow: TextView
        lateinit var cTrack: TextView
        c3d = chip("3D") { view.set3d(!view.is3d); mark(c3d, view.is3d) }
        cTrack = chip("🧭 Track up") { view.trackUp = !view.trackUp; if (!view.trackUp) view.northUp(); mark(cTrack, view.trackUp) }
        cFollow = chip("📍 Follow") { view.following = !view.following; mark(cFollow, view.following); if (view.following) view.goToOwnship() }
        chips.addView(c3d)
        chips.addView(cTrack)
        chips.addView(cFollow)
        chips.addView(chip("📄 FAA diagram") { faaDiagram() })
        chips.addView(chip("⟳") { load(refresh = true) })
        top.addView(HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; addView(chips) })
        root.addView(top, FrameLayout.LayoutParams(-1, -2, Gravity.TOP))
        view.onUserMove = { if (view.following) { view.following = false; mark(cFollow, false) } }

        val bottom = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(12), 0, dp(12), dp(14))
        }
        surface = EfbUi.text(this, "", 20f, 0xFFFFFFFF.toInt(), bold = true).apply {
            gravity = Gravity.CENTER
            setPadding(dp(14), dp(10), dp(14), dp(10))
            visibility = View.GONE
        }
        bottom.addView(surface, LinearLayout.LayoutParams(-1, -2))
        status = EfbUi.ltr(EfbUi.text(this, getString(R.string.dia_loading), 14f, EfbUi.TEXT, mono = true)).apply {
            gravity = Gravity.CENTER
            background = EfbUi.cardBg(this@AirportDiagramActivity, 0xE616213A.toInt(), 14)
            setPadding(dp(14), dp(8), dp(14), dp(8))
        }
        bottom.addView(status, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8) })
        root.addView(bottom, FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM))
        setContentView(root)
        androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(root) { _, insets ->
            val bars = insets.getInsets(androidx.core.view.WindowInsetsCompat.Type.systemBars())
            top.setPadding(dp(12), dp(10) + bars.top, dp(12), 0)
            bottom.setPadding(dp(12), 0, dp(12), dp(14) + bars.bottom)
            insets
        }
        mark(c3d, true)
        load(refresh = false)
        startGps()
    }

    override fun onDestroy() {
        super.onDestroy()
        try { getSystemService(LocationManager::class.java)?.removeUpdates(gps) } catch (e: Exception) {}
    }

    private fun chip(label: String, onClick: () -> Unit): TextView = EfbUi.text(this, label, 14f, EfbUi.TEXT, bold = true).apply {
        background = EfbUi.cardBg(this@AirportDiagramActivity, 0xE616213A.toInt(), 20)
        setPadding(dp(14), dp(8), dp(14), dp(8))
        layoutParams = LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(8) }
        EfbUi.pressable(this, onClick)
    }

    private fun mark(chip: TextView, on: Boolean) {
        chip.background = EfbUi.cardBg(this, if (on) 0xFF00838F.toInt() else 0xE616213A.toInt(), 20)
    }

    private fun load(refresh: Boolean) {
        status.text = getString(R.string.dia_loading)
        lifecycleScope.launch {
            val json = withContext(Dispatchers.IO) { fetch(this@AirportDiagramActivity, ident, lat0, lon0, refresh) }
            if (json == null) {
                status.text = getString(R.string.dia_fail)
                return@launch
            }
            val n = view.load(json)
            status.text = if (n == 0) getString(R.string.dia_empty) else getString(R.string.dia_hint)
            view.flyIn()
        }
    }

    private fun faaDiagram() {
        Toast.makeText(this, R.string.apt_plates_loading, Toast.LENGTH_SHORT).show()
        lifecycleScope.launch {
            val res = withContext(Dispatchers.IO) { AviationData.plates(this@AirportDiagramActivity, ident) }
            val apd = res?.second?.firstOrNull { it.code == "APD" }
            val f = if (res != null && apd != null) withContext(Dispatchers.IO) { AviationData.platePdf(this@AirportDiagramActivity, res.first, apd.pdf) } else null
            if (f == null || apd == null) {
                Toast.makeText(this@AirportDiagramActivity, R.string.apt_no_plates, Toast.LENGTH_LONG).show()
                return@launch
            }
            val item = VaultItem("plate:" + apd.pdf, "$ident ${apd.name}", f.absolutePath, "application/pdf", f.length(), f.lastModified(), null)
            VaultStore.viewOnly(item)
            startActivity(Intent(this@AirportDiagramActivity, PdfViewerActivity::class.java).putExtra(Viewers.EXTRA_ID, item.id))
        }
    }

    // ---- the aircraft ----

    private val gps = LocationListener { l -> onFix(l) }

    @SuppressLint("MissingPermission")
    private fun startGps() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) return
        val m = getSystemService(LocationManager::class.java) ?: return
        try {
            m.getLastKnownLocation(LocationManager.GPS_PROVIDER)?.takeIf { System.currentTimeMillis() - it.time < 120000 }?.let { onFix(it) }
            m.requestLocationUpdates(LocationManager.GPS_PROVIDER, 0L, 0f, gps, mainLooper)
        } catch (e: Exception) {
        }
    }

    private var lastSurface = ""

    private fun onFix(l: Location) {
        view.ownship(l)
        val kt = if (l.hasSpeed()) l.speed * 1.943844 else 0.0
        val near = Nav.distanceNm(l.latitude, l.longitude, lat0, lon0)
        if (near > 5) {
            status.text = "GS %d kt · %.1f nm %s".format(Math.round(kt), near, getString(R.string.dia_away))
            surface.visibility = View.GONE
            return
        }
        val on = view.surfaceAt(l.latitude, l.longitude)
        status.text = "GS %d kt%s".format(Math.round(kt), if (l.hasBearing() && kt > 2) "  ·  TRK " + Nav.deg(Nav.magnetic(l.bearing.toDouble(), l.latitude, l.longitude)) + "M" else "")
        if (on == null) {
            surface.visibility = View.GONE
            lastSurface = ""
            return
        }
        surface.text = on.second
        surface.background = EfbUi.cardBg(this, if (on.first) 0xFFC62828.toInt() else 0xFF111111.toInt(), 12)
        surface.setTextColor(if (on.first) 0xFFFFFFFF.toInt() else 0xFFF2C744.toInt())
        if (surface.visibility != View.VISIBLE || on.second != lastSurface) {
            surface.visibility = View.VISIBLE
            surface.scaleX = 0.8f; surface.scaleY = 0.8f; surface.alpha = 0f
            surface.animate().scaleX(1f).scaleY(1f).alpha(1f).setDuration(260).start()
            // Rolling onto a runway: a pulse and a buzz, the moment it happens.
            if (on.first && kt < 40) {
                (getSystemService(Context.VIBRATOR_SERVICE) as? android.os.Vibrator)?.let {
                    try { it.vibrate(android.os.VibrationEffect.createWaveform(longArrayOf(0, 180, 120, 180), -1)) } catch (e: Exception) {}
                }
            }
        }
        lastSurface = on.second
    }

    companion object {
        fun open(act: Activity, a: AviationData.Airport) {
            act.startActivity(Intent(act, AirportDiagramActivity::class.java)
                .putExtra("ident", a.ident).putExtra("icao", a.icao).putExtra("name", a.name)
                .putExtra("lat", a.lat).putExtra("lon", a.lon))
        }

        private val SERVERS = listOf(
            "https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter",
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
        )

        /** The airport's surveyed shapes, kept on the phone so the diagram works on the ground without signal. */
        fun fetch(ctx: Context, ident: String, lat: Double, lon: Double, refresh: Boolean): JSONObject? {
            val file = File(ctx.filesDir, "aviation/apt/${ident.replace(Regex("[^A-Z0-9]"), "")}.json")
            if (!refresh && file.length() > 0) try { return JSONObject(file.readText()) } catch (e: Exception) {}
            val q = "[out:json][timeout:40];(" +
                "way[\"aeroway\"](around:4500,$lat,$lon);" +
                "way[\"building\"](around:2500,$lat,$lon);" +
                ");out geom;"
            for (server in SERVERS) {
                try {
                    val c = URL("$server?data=" + URLEncoder.encode(q, "UTF-8")).openConnection() as HttpURLConnection
                    c.connectTimeout = 20000
                    c.readTimeout = 60000
                    c.setRequestProperty("User-Agent", "Khazanti-EFB/1.0")
                    try {
                        if (c.responseCode != 200) continue
                        val text = c.inputStream.bufferedReader().readText()
                        val json = JSONObject(text)
                        if ((json.optJSONArray("elements")?.length() ?: 0) == 0) continue
                        file.parentFile?.mkdirs()
                        file.writeText(text)
                        return json
                    } finally {
                        c.disconnect()
                    }
                } catch (e: Exception) {
                }
            }
            return if (file.length() > 0) try { JSONObject(file.readText()) } catch (e: Exception) { null } else null
        }
    }
}

/**
 * The airport drawn in perspective. Points are metres east and north of the
 * airport's reference point; the camera looks at a focus point from a
 * distance set by the zoom, turned by a heading and tilted towards the
 * horizon, so buildings stand up and the far end of a runway narrows.
 */
@SuppressLint("ViewConstructor")
class AirportView(ctx: Context, private val lat0: Double, private val lon0: Double) : View(ctx) {

    class Feature(val kind: String, val ref: String, val pts: FloatArray, val width: Float, val height: Float)

    private val features = ArrayList<Feature>()
    private val d = ctx.resources.displayMetrics.density
    private val mx = (111320.0 * cos(Math.toRadians(lat0))).toFloat()
    private val my = 110540f

    // The camera.
    private var cx = 0f
    private var cy = 0f
    private var heading = 0f
    private var scale = 0.25f        // pixels per metre at the focus
    private var tilt = 52f
    var is3d = true
        private set
    var trackUp = false
    var following = false
    var onUserMove: (() -> Unit)? = null
    private var fit = 0.25f

    private var fix: Location? = null
    private var fixAt = 0L
    private val variation = Nav.variation(lat0, lon0)

    private fun x(lon: Double) = ((lon - lon0) * mx).toFloat()
    private fun y(lat: Double) = ((lat - lat0) * my).toFloat()

    fun load(json: JSONObject): Int {
        features.clear()
        val el = json.optJSONArray("elements") ?: JSONArray()
        var aerodrome: Feature? = null
        val buildings = ArrayList<Feature>()
        for (i in 0 until el.length()) {
            val o = el.optJSONObject(i) ?: continue
            val g = o.optJSONArray("geometry") ?: continue
            if (g.length() < 2) continue
            val pts = FloatArray(g.length() * 2)
            for (k in 0 until g.length()) {
                val p = g.getJSONObject(k)
                pts[2 * k] = x(p.getDouble("lon"))
                pts[2 * k + 1] = y(p.getDouble("lat"))
            }
            val t = o.optJSONObject("tags") ?: JSONObject()
            val aeroway = t.optString("aeroway")
            val ref = t.optString("ref").ifEmpty { t.optString("name") }
            val width = t.optString("width").replace(Regex("[^0-9.]"), "").toFloatOrNull()
            val f = when {
                aeroway == "runway" -> Feature("runway", t.optString("ref"), pts, width ?: 30f, 0f)
                aeroway == "taxiway" || aeroway == "taxilane" -> Feature("taxiway", t.optString("ref"), pts, width ?: if (aeroway == "taxilane") 9f else 15f, 0f)
                aeroway == "apron" -> Feature("apron", "", pts, 0f, 0f)
                aeroway == "holding_position" -> Feature("hold", ref, pts, 0f, 0f)
                aeroway == "aerodrome" -> Feature("aerodrome", "", pts, 0f, 0f).also { if (aerodrome == null || area(pts) > area(aerodrome!!.pts)) aerodrome = it }
                aeroway == "terminal" || aeroway == "hangar" || t.has("building") -> {
                    val h = t.optString("height").replace(Regex("[^0-9.]"), "").toFloatOrNull()
                        ?: t.optString("building:levels").toFloatOrNull()?.times(3.4f)
                        ?: when {
                            aeroway == "terminal" || t.optString("building") == "terminal" -> 13f
                            aeroway == "hangar" || t.optString("building") == "hangar" -> 9f
                            else -> 6f
                        }
                    Feature("building", "", pts, 0f, h).also { buildings.add(it); null }
                }
                else -> null
            }
            if (f != null && f.kind != "building" && f.kind != "aerodrome") features.add(f)
        }
        // Buildings only within the field, so the town around it stays out.
        val field = aerodrome
        val kept = if (field != null) buildings.filter { b -> inside(field.pts, b.pts[0], b.pts[1]) } else buildings.filter { hypot(it.pts[0], it.pts[1]) < 1500 }
        field?.let { features.add(0, it) }
        features.addAll(kept)
        // Draw order: ground first, then pavement, runways, marks, and buildings last.
        val order = listOf("aerodrome", "apron", "taxiway", "runway", "hold", "building")
        features.sortBy { order.indexOf(it.kind) }
        var maxR = 600f
        for (f in features) if (f.kind == "runway") for (k in f.pts.indices step 2) maxR = maxOf(maxR, hypot(f.pts[k], f.pts[k + 1]))
        fit = (minOf(width, height).coerceAtLeast(1) / (2.3f * maxR))
        invalidate()
        return features.count { it.kind == "runway" || it.kind == "taxiway" }
    }

    private fun area(p: FloatArray): Float {
        var a = 0f
        var j = p.size - 2
        for (i in p.indices step 2) {
            a += (p[j] + p[i]) * (p[j + 1] - p[i + 1])
            j = i
        }
        return Math.abs(a / 2)
    }

    private fun inside(p: FloatArray, px: Float, py: Float): Boolean {
        var c = false
        var j = p.size - 2
        for (i in p.indices step 2) {
            if ((p[i + 1] > py) != (p[j + 1] > py) && px < (p[j] - p[i]) * (py - p[i + 1]) / (p[j + 1] - p[i + 1]) + p[i]) c = !c
            j = i
        }
        return c
    }

    // ---- camera motion ----

    private var anim: ValueAnimator? = null

    private fun animateTo(s: Float, h: Float, t: Float, x: Float = cx, y: Float = cy, ms: Long = 900) {
        anim?.cancel()
        val s0 = scale; val h0 = heading; val t0 = tilt; val x0 = cx; val y0 = cy
        val dh = ((h - h0 + 540) % 360) - 180
        anim = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = ms
            interpolator = DecelerateInterpolator(1.6f)
            addUpdateListener {
                val f = it.animatedValue as Float
                scale = (s0 * Math.pow((s / s0).toDouble(), f.toDouble())).toFloat()
                heading = h0 + dh * f
                tilt = t0 + (t - t0) * f
                cx = x0 + (x - x0) * f
                cy = y0 + (y - y0) * f
                invalidate()
            }
            start()
        }
    }

    /** The opening shot: from high and turned, sweeping down onto the field. */
    fun flyIn() {
        post {
            if (fit <= 0f || width == 0) return@post
            fit = minOf(width, height) / (2.3f * maxRadius())
            scale = fit * 0.25f
            heading = -60f
            tilt = 70f
            cx = 0f; cy = 0f
            animateTo(fit, 0f, if (is3d) 52f else 0f, 0f, 0f, 2200)
        }
    }

    private fun maxRadius(): Float {
        var r = 600f
        for (f in features) if (f.kind == "runway") for (k in f.pts.indices step 2) r = maxOf(r, hypot(f.pts[k], f.pts[k + 1]))
        return r
    }

    fun set3d(on: Boolean) {
        is3d = on
        animateTo(scale, heading, if (on) 52f else 0f, ms = 700)
    }

    fun northUp() = animateTo(scale, 0f, tilt, ms = 600)

    fun goToOwnship() {
        val l = fix ?: return
        animateTo(maxOf(scale, fit * 2.5f), if (trackUp && l.hasBearing()) l.bearing else heading, tilt, x(l.longitude), y(l.latitude), 800)
    }

    fun ownship(l: Location) {
        fix = l
        fixAt = SystemClock.elapsedRealtime()
        invalidate()
    }

    /** Whether a point is on a runway (true) or a taxiway (false), and its name. */
    fun surfaceAt(lat: Double, lon: Double): Pair<Boolean, String>? {
        val px = x(lon); val py = y(lat)
        for (f in features) if (f.kind == "runway" && near(f, px, py, f.width / 2 + 3)) return true to "⚠️ RWY ${f.ref}"
        for (f in features) if (f.kind == "taxiway" && f.ref.isNotEmpty() && near(f, px, py, f.width / 2 + 4)) return false to "TWY ${f.ref}"
        return null
    }

    private fun near(f: Feature, px: Float, py: Float, r: Float): Boolean {
        val p = f.pts
        for (i in 0 until p.size - 2 step 2) {
            val ax = p[i]; val ay = p[i + 1]; val bx = p[i + 2]; val by = p[i + 3]
            val l2 = (bx - ax) * (bx - ax) + (by - ay) * (by - ay)
            val t = if (l2 == 0f) 0f else (((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / l2).coerceIn(0f, 1f)
            if (hypot(px - (ax + t * (bx - ax)), py - (ay + t * (by - ay))) < r) return true
        }
        return false
    }

    private fun predicted(): Triple<Float, Float, Float>? {
        val l = fix ?: return null
        val kt = if (l.hasSpeed()) l.speed * 1.943844 else 0.0
        var lat = l.latitude; var lon = l.longitude
        if (kt > 2 && l.hasBearing()) {
            val age = ((SystemClock.elapsedRealtime() - fixAt) / 1000.0).coerceAtMost(2.5)
            val g = Nav.destination(lat, lon, l.bearing.toDouble(), kt * age / 3600)
            lat = g.latitude; lon = g.longitude
        }
        return Triple(x(lon), y(lat), if (l.hasBearing()) l.bearing else 0f)
    }

    // ---- projection ----

    private var cosH = 1f; private var sinH = 0f; private var cosT = 1f; private var sinT = 0f
    private var dist = 1000f
    private var anchor = 0.5f

    private fun setup() {
        val h = Math.toRadians(heading.toDouble())
        cosH = cos(h).toFloat(); sinH = sin(h).toFloat()
        val t = Math.toRadians(tilt.toDouble())
        cosT = cos(t).toFloat(); sinT = sin(t).toFloat()
        dist = height / scale * 1.1f
        anchor = 0.5f + 0.12f * (tilt / 60f)
    }

    /** World (metres, metres, metres up) to screen; false when behind the camera. */
    private fun project(x: Float, y: Float, z: Float, out: FloatArray, i: Int = 0): Boolean {
        val dx = x - cx; val dy = y - cy
        val rx = dx * cosH - dy * sinH
        val ry = dx * sinH + dy * cosH
        val depth = dist + ry * sinT - z * cosT
        if (depth < dist * 0.12f) return false
        val k = scale * dist / depth
        out[i] = width / 2f + rx * k
        out[i + 1] = height * anchor - (ry * cosT + z * sinT) * k
        return true
    }

    private fun depthOf(x: Float, y: Float): Float {
        val dx = x - cx; val dy = y - cy
        return dist + (dx * sinH + dy * cosH) * sinT
    }

    private fun pxPerM(x: Float, y: Float) = scale * dist / depthOf(x, y).coerceAtLeast(dist * 0.12f)

    // ---- drawing ----

    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND }
    private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply { isFakeBoldText = true; textAlign = Paint.Align.CENTER; typeface = android.graphics.Typeface.MONOSPACE }
    private val sky = Paint()
    private val a = FloatArray(2)
    private val b = FloatArray(2)
    private val path = Path()

    private fun polyPath(p: FloatArray, z: Float, close: Boolean): Boolean {
        path.reset()
        for (i in p.indices step 2) {
            if (!project(p[i], p[i + 1], z, a)) return false
            if (i == 0) path.moveTo(a[0], a[1]) else path.lineTo(a[0], a[1])
        }
        if (close) path.close()
        return true
    }

    override fun onDraw(c: Canvas) {
        c.drawColor(EfbUi.BG)
        if (following) predicted()?.let { (px, py, brg) ->
            cx = px; cy = py
            if (trackUp && (fix?.speed ?: 0f) > 1f) heading += ((((brg - heading) + 540) % 360) - 180) * 0.12f
        }
        setup()
        if (tilt > 5) {
            // A horizon glow beyond the field.
            sky.shader = android.graphics.LinearGradient(0f, 0f, 0f, height * 0.45f, 0xFF1C3A5E.toInt(), EfbUi.BG, android.graphics.Shader.TileMode.CLAMP)
            sky.alpha = (255 * (tilt / 60f)).toInt().coerceIn(0, 255)
            c.drawRect(0f, 0f, width.toFloat(), height * 0.45f, sky)
        }
        // Buildings drawn far to near, so the near ones stand in front.
        val buildings = ArrayList<Feature>()
        for (f in features) {
            when (f.kind) {
                "aerodrome" -> if (polyPath(f.pts, 0f, true)) { fill.color = 0xFF10261C.toInt(); c.drawPath(path, fill) }
                "apron" -> if (polyPath(f.pts, 0f, true)) { fill.color = 0xFF2B3546.toInt(); c.drawPath(path, fill) }
                "taxiway" -> drawTaxiway(c, f)
                "runway" -> drawRunway(c, f)
                "hold" -> if (polyPath(f.pts, 0f, false)) {
                    stroke.pathEffect = null
                    stroke.color = 0xFFF2C744.toInt(); stroke.strokeWidth = maxOf(2f * d, 1.2f * pxPerM(f.pts[0], f.pts[1]))
                    c.drawPath(path, stroke)
                }
                "building" -> buildings.add(f)
            }
        }
        buildings.sortByDescending { depthOf(it.pts[0], it.pts[1]) }
        for (f in buildings) drawBuilding(c, f)
        drawLabels(c)
        drawOwnship(c)
        drawCompass(c)
        if (following || (anim?.isRunning == true)) postInvalidateOnAnimation()
    }

    private fun drawTaxiway(c: Canvas, f: Feature) {
        stroke.pathEffect = null
        val p = f.pts
        for (i in 0 until p.size - 2 step 2) {
            if (!project(p[i], p[i + 1], 0f, a) || !project(p[i + 2], p[i + 3], 0f, b)) continue
            val k = pxPerM((p[i] + p[i + 2]) / 2, (p[i + 1] + p[i + 3]) / 2)
            stroke.color = 0xFF3A4457.toInt()
            stroke.strokeWidth = maxOf(1.5f * d, f.width * k)
            c.drawLine(a[0], a[1], b[0], b[1], stroke)
        }
        stroke.color = 0xFFF2C744.toInt()
        for (i in 0 until p.size - 2 step 2) {
            if (!project(p[i], p[i + 1], 0f, a) || !project(p[i + 2], p[i + 3], 0f, b)) continue
            stroke.strokeWidth = maxOf(1f * d, 0.5f * pxPerM(p[i], p[i + 1]))
            c.drawLine(a[0], a[1], b[0], b[1], stroke)
        }
    }

    private val dash = FloatArray(2)

    private fun drawRunway(c: Canvas, f: Feature) {
        val p = f.pts
        val x1 = p[0]; val y1 = p[1]; val x2 = p[p.size - 2]; val y2 = p[p.size - 1]
        val len = hypot(x2 - x1, y2 - y1)
        if (len < 50) return
        val ux = (x2 - x1) / len; val uy = (y2 - y1) / len
        val nx = -uy; val ny = ux
        val w = f.width / 2
        fun quad(s0: Float, s1: Float, o0: Float, o1: Float, color: Int) {
            path.reset()
            val corners = floatArrayOf(
                x1 + ux * s0 + nx * o0, y1 + uy * s0 + ny * o0, x1 + ux * s1 + nx * o0, y1 + uy * s1 + ny * o0,
                x1 + ux * s1 + nx * o1, y1 + uy * s1 + ny * o1, x1 + ux * s0 + nx * o1, y1 + uy * s0 + ny * o1,
            )
            for (i in 0 until 8 step 2) {
                if (!project(corners[i], corners[i + 1], 0f, a)) return
                if (i == 0) path.moveTo(a[0], a[1]) else path.lineTo(a[0], a[1])
            }
            path.close()
            fill.color = color
            c.drawPath(path, fill)
        }
        quad(-8f, len + 8f, -w - 2, w + 2, 0xFF0D0F12.toInt())
        quad(0f, len, -w, w, 0xFF23272E.toInt())
        // Edge lines, threshold bars, the dashed centre line, and touchdown aiming marks.
        quad(0f, len, w - 1f, w - 0.1f, 0xFFE0E0E0.toInt())
        quad(0f, len, -w + 0.1f, -w + 1f, 0xFFE0E0E0.toInt())
        val bars = 8
        for (end in 0..1) {
            for (i in 0 until bars) {
                val o = -w * 0.85f + (w * 1.7f) * (i + 0.5f) / bars
                val s0 = if (end == 0) 6f else len - 36f
                quad(s0, s0 + 30f, o - w * 0.06f, o + w * 0.06f, 0xFFF5F5F5.toInt())
            }
            val aim = if (end == 0) 300f else len - 345f
            if (len > 900) {
                quad(aim, aim + 45f, w * 0.25f, w * 0.45f, 0xFFF5F5F5.toInt())
                quad(aim, aim + 45f, -w * 0.45f, -w * 0.25f, 0xFFF5F5F5.toInt())
            }
        }
        var s = 120f
        while (s < len - 120f) {
            quad(s, minOf(s + 36f, len - 120f), -0.5f, 0.5f, 0xFFF5F5F5.toInt())
            s += 60f
        }
        // The numbers, each at the end it is read from when landing.
        val parts = f.ref.split('/').map { it.trim() }.filter { it.isNotEmpty() }
        if (parts.isEmpty()) return
        val brgTrue = (Math.toDegrees(atan2(ux.toDouble(), uy.toDouble())) + 360) % 360
        val brgMag = (brgTrue - variation + 360) % 360
        fun closeness(part: String, b: Double): Double {
            val n = part.takeWhile { it.isDigit() }.toIntOrNull() ?: return 999.0
            return Math.abs(((n * 10 - b + 540) % 360) - 180)
        }
        val atStart = parts.minByOrNull { closeness(it, brgMag) } ?: return
        val atEnd = parts.firstOrNull { it != atStart } ?: atStart
        number(c, atStart, x1 + ux * 70, y1 + uy * 70)
        if (parts.size > 1) number(c, atEnd, x2 - ux * 70, y2 - uy * 70)
    }

    private fun number(c: Canvas, text: String, x: Float, y: Float) {
        if (!project(x, y, 0f, a)) return
        val k = pxPerM(x, y)
        label.textSize = (18f * k).coerceIn(11f * d, 30f * d)
        label.color = 0xFF000000.toInt()
        label.style = Paint.Style.STROKE
        label.strokeWidth = 4 * d
        c.drawText(text, a[0], a[1], label)
        label.style = Paint.Style.FILL
        label.color = 0xFFFFFFFF.toInt()
        c.drawText(text, a[0], a[1], label)
    }

    private fun drawBuilding(c: Canvas, f: Feature) {
        val p = f.pts
        val n = p.size / 2
        val h = f.height
        if (tilt > 3) {
            // Walls, far first, shaded by which way they face.
            val idx = (0 until n - 1).sortedByDescending { i -> depthOf((p[2 * i] + p[2 * i + 2]) / 2, (p[2 * i + 1] + p[2 * i + 3]) / 2) }
            for (i in idx) {
                val ax = p[2 * i]; val ay = p[2 * i + 1]; val bx = p[2 * i + 2]; val by = p[2 * i + 3]
                path.reset()
                if (!project(ax, ay, 0f, a)) continue
                path.moveTo(a[0], a[1])
                if (!project(bx, by, 0f, a)) continue
                path.lineTo(a[0], a[1])
                if (!project(bx, by, h, a)) continue
                path.lineTo(a[0], a[1])
                if (!project(ax, ay, h, a)) continue
                path.lineTo(a[0], a[1])
                path.close()
                val ex = bx - ax; val ey = by - ay
                val el = hypot(ex, ey).coerceAtLeast(0.01f)
                val light = 0.55f + 0.4f * ((-ey / el) * 0.6f + (ex / el) * 0.8f).coerceIn(-1f, 1f) * 0.5f
                val v = (0x8A * light).toInt().coerceIn(0, 255)
                fill.color = android.graphics.Color.rgb((v * 0.85f).toInt(), (v * 0.92f).toInt(), v)
                c.drawPath(path, fill)
            }
        }
        if (polyPath(p, h, true)) {
            fill.color = 0xFF8C9BB5.toInt()
            c.drawPath(path, fill)
            stroke.pathEffect = null
            stroke.color = 0xFFB8C4D9.toInt()
            stroke.strokeWidth = 1f * d
            c.drawPath(path, stroke)
        }
    }

    private val pill = RectF()

    private fun drawLabels(c: Canvas) {
        // One sign per taxiway name every few hundred metres, standing upright like a real sign.
        val placed = ArrayList<Triple<String, Float, Float>>()
        label.textSize = 12f * d
        for (f in features) {
            if (f.kind != "taxiway" || f.ref.isEmpty()) continue
            val p = f.pts
            val mid = (p.size / 4) * 2
            val x = p[mid]; val y = p[mid + 1]
            if (placed.any { it.first == f.ref && hypot(it.second - x, it.third - y) < 350 }) continue
            if (!project(x, y, 0f, a)) continue
            if (a[0] < 0 || a[1] < 0 || a[0] > width || a[1] > height) continue
            placed.add(Triple(f.ref, x, y))
            val w = label.measureText(f.ref) / 2 + 6 * d
            pill.set(a[0] - w, a[1] - 11 * d, a[0] + w, a[1] + 6 * d)
            fill.color = 0xFF111111.toInt()
            c.drawRoundRect(pill, 4 * d, 4 * d, fill)
            stroke.pathEffect = null
            stroke.color = 0xFFF2C744.toInt()
            stroke.strokeWidth = 1.2f * d
            c.drawRoundRect(pill, 4 * d, 4 * d, stroke)
            label.style = Paint.Style.FILL
            label.color = 0xFFF2C744.toInt()
            c.drawText(f.ref, a[0], a[1], label)
        }
    }

    private val plane = Path()

    private fun drawOwnship(c: Canvas) {
        val (px, py, brg) = predicted() ?: return
        if (!project(px, py, 0f, a)) return
        val ahead = Nav.destination(0.0, 0.0, brg.toDouble(), 0.01)
        val hx = px + (ahead.longitude * 111320).toFloat()
        val hy = py + (ahead.latitude * 110540).toFloat()
        if (!project(hx, hy, 0f, b)) return
        val ang = Math.toDegrees(atan2((b[0] - a[0]).toDouble(), -(b[1] - a[1]).toDouble())).toFloat()
        val size = maxOf(30f * d, 11f * pxPerM(px, py))
        val f = size / 24f
        plane.reset()
        plane.moveTo(0f, -11 * f); plane.lineTo(1.5f * f, -4 * f); plane.lineTo(10 * f, 1 * f); plane.lineTo(10 * f, 3 * f)
        plane.lineTo(1.5f * f, 0.5f * f); plane.lineTo(1 * f, 7 * f); plane.lineTo(4 * f, 9 * f); plane.lineTo(4 * f, 10.5f * f)
        plane.lineTo(0f, 9.5f * f); plane.lineTo(-4 * f, 10.5f * f); plane.lineTo(-4 * f, 9 * f); plane.lineTo(-1 * f, 7 * f)
        plane.lineTo(-1.5f * f, 0.5f * f); plane.lineTo(-10 * f, 3 * f); plane.lineTo(-10 * f, 1 * f); plane.lineTo(-1.5f * f, -4 * f); plane.close()
        // A soft pulse under the aircraft.
        val pulse = (SystemClock.uptimeMillis() % 1600) / 1600f
        fill.color = 0x00E5FF or (((1 - pulse) * 90).toInt() shl 24)
        c.drawCircle(a[0], a[1], size * (0.6f + pulse), fill)
        c.save()
        c.translate(a[0], a[1])
        c.rotate(ang)
        stroke.pathEffect = null
        stroke.color = 0xFF000000.toInt(); stroke.strokeWidth = 3 * d
        c.drawPath(plane, stroke)
        fill.color = 0xFF00E5FF.toInt()
        c.drawPath(plane, fill)
        c.restore()
        postInvalidateDelayed(40)
    }

    private fun drawCompass(c: Canvas) {
        val r = 18 * d
        val x = width - r - 16 * d
        val y = height - r - 96 * d
        fill.color = 0xCC16213A.toInt()
        c.drawCircle(x, y, r, fill)
        c.save()
        c.rotate(-heading, x, y)
        fill.color = 0xFFEF5350.toInt()
        path.reset(); path.moveTo(x, y - r * 0.8f); path.lineTo(x + r * 0.28f, y); path.lineTo(x - r * 0.28f, y); path.close()
        c.drawPath(path, fill)
        fill.color = 0xFFECEFF4.toInt()
        path.reset(); path.moveTo(x, y + r * 0.8f); path.lineTo(x + r * 0.28f, y); path.lineTo(x - r * 0.28f, y); path.close()
        c.drawPath(path, fill)
        c.restore()
    }

    // ---- touch: one finger moves, two fingers zoom, turn and tilt ----

    private var lastX = 0f; private var lastY = 0f
    private var lastSpan = 0f; private var lastAngle = 0f; private var lastMidY = 0f
    private var downAt = 0L; private var lastTap = 0L

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(e: MotionEvent): Boolean {
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                anim?.cancel()
                lastX = e.x; lastY = e.y
                downAt = SystemClock.uptimeMillis()
            }
            MotionEvent.ACTION_POINTER_DOWN -> if (e.pointerCount == 2) twoFinger(e, reset = true)
            MotionEvent.ACTION_POINTER_UP -> {
                val keep = if (e.actionIndex == 0) 1 else 0
                lastX = e.getX(keep); lastY = e.getY(keep)
            }
            MotionEvent.ACTION_MOVE -> {
                if (e.pointerCount >= 2) twoFinger(e, reset = false)
                else {
                    val dxs = e.x - lastX; val dys = e.y - lastY
                    lastX = e.x; lastY = e.y
                    if (Math.abs(dxs) + Math.abs(dys) > 0.5f) {
                        onUserMove?.invoke()
                        val rx = -dxs / scale
                        val ry = dys / (scale * maxOf(cosT, 0.4f))
                        cx += rx * cosH + ry * sinH
                        cy += -rx * sinH + ry * cosH
                        invalidate()
                    }
                }
            }
            MotionEvent.ACTION_UP -> {
                val now = SystemClock.uptimeMillis()
                if (now - downAt < 200) {
                    if (now - lastTap < 300) animateTo(scale * 2f, heading, tilt, ms = 450)
                    lastTap = now
                }
            }
        }
        return true
    }

    private fun twoFinger(e: MotionEvent, reset: Boolean) {
        val x0 = e.getX(0); val y0 = e.getY(0); val x1 = e.getX(1); val y1 = e.getY(1)
        val span = hypot(x1 - x0, y1 - y0)
        val angle = Math.toDegrees(atan2((y1 - y0).toDouble(), (x1 - x0).toDouble())).toFloat()
        val midY = (y0 + y1) / 2
        if (!reset && lastSpan > 0) {
            onUserMove?.invoke()
            val dSpan = span - lastSpan
            scale = (scale * span / lastSpan).coerceIn(0.01f, 40f)
            var da = angle - lastAngle
            if (da > 180) da -= 360
            if (da < -180) da += 360
            heading -= da
            if (Math.abs(dSpan) < 3f) tilt = (tilt + (lastMidY - midY) * 0.25f).coerceIn(0f, 68f)
            is3d = tilt > 5
            invalidate()
        }
        lastSpan = span; lastAngle = angle; lastMidY = midY
    }
}
