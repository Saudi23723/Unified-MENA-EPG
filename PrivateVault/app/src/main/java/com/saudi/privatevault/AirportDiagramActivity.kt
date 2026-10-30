package com.saudi.privatevault

import android.Manifest
import android.animation.ValueAnimator
import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Point
import android.graphics.RectF
import android.graphics.drawable.GradientDrawable
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
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
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import org.osmdroid.config.Configuration
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.CustomZoomButtonsController
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay
import org.osmdroid.views.overlay.gestures.RotationGestureOverlay
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import kotlin.math.hypot

/**
 * An airport on its own, full screen: the satellite photo of the field (it
 * is always there, online or saved), with runway numbers, taxiway signs and
 * hold-short lines drawn over it from OpenStreetMap's survey when available.
 * It turns with two fingers, tilts into 3D, follows the aircraft, and warns
 * when the aircraft rolls onto a runway. The FAA diagram is a tap away.
 */
class AirportDiagramActivity : BaseActivity() {

    private lateinit var map: MapView
    private lateinit var labels: LabelsOverlay
    private lateinit var pattern: PatternOverlay
    private var windLine = ""
    private lateinit var ownship: OwnshipOverlay
    private lateinit var info: TextView
    private lateinit var gpsLine: TextView
    private lateinit var surface: TextView
    private var ident = ""
    private var lat0 = 0.0
    private var lon0 = 0.0
    private var following = false
    private var trackUp = false
    private var tilted = false
    private fun dp(v: Int) = EfbUi.dp(this, v)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Configuration.getInstance().apply {
            userAgentValue = packageName
            osmdroidBasePath = File(filesDir, "osmdroid")
            osmdroidTileCache = File(filesDir, "osmdroid/tiles")
        }
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        window.statusBarColor = EfbUi.BG
        window.navigationBarColor = EfbUi.BG
        ident = intent.getStringExtra("ident") ?: ""
        lat0 = intent.getDoubleExtra("lat", 0.0)
        lon0 = intent.getDoubleExtra("lon", 0.0)
        val name = intent.getStringExtra("name") ?: ""

        val root = FrameLayout(this).apply { setBackgroundColor(EfbUi.BG) }
        val holder = FrameLayout(this)
        root.addView(holder, FrameLayout.LayoutParams(-1, -1))
        val imagery = AviationData.LAYERS.first { it.key == "imagery" }
        map = MapView(this, SmoothTileProvider(applicationContext, imagery.source()))
        holder.addView(map, FrameLayout.LayoutParams(-1, -1))
        map.setMultiTouchControls(true)
        map.zoomController.setVisibility(CustomZoomButtonsController.Visibility.NEVER)
        map.minZoomLevel = 11.0
        map.maxZoomLevel = 20.0
        map.isTilesScaledToDpi = true
        map.overlayManager.tilesOverlay.setLoadingBackgroundColor(EfbUi.BG)
        map.overlayManager.tilesOverlay.setLoadingLineColor(EfbUi.BG)
        map.controller.setZoom(12.5)
        map.controller.setCenter(GeoPoint(lat0, lon0))
        map.overlays.add(RotationGestureOverlay(map).apply { isEnabled = true })
        labels = LabelsOverlay(map)
        map.overlays.add(labels)
        pattern = PatternOverlay(map).apply {
            val elev = intent.getIntExtra("elev", -1)
            // Pattern altitude: 1,000 ft above the field (AC 90-66), to the next hundred.
            if (elev >= 0) tpaFt = ((elev + 1000 + 50) / 100) * 100
        }
        map.overlays.add(pattern)
        ownship = OwnshipOverlay(map, airplane()).apply { onUserPan = { stopFollowing() } }
        map.overlays.add(ownship)
        map.setOnTouchListener { _, e -> if (e.actionMasked == MotionEvent.ACTION_MOVE) stopFollowing(); false }

        val top = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(12), dp(10), dp(12), 0) }
        val head = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = EfbUi.cardBg(this@AirportDiagramActivity, 0xE60B1220.toInt(), 16)
            setPadding(dp(6), dp(6), dp(12), dp(6))
        }
        head.addView(chip("✕") { finish() })
        head.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(10), 0, 0, 0)
            addView(EfbUi.text(this@AirportDiagramActivity, intent.getStringExtra("icao")?.ifEmpty { ident } ?: ident, 22f, EfbUi.ACCENT, bold = true))
            addView(EfbUi.text(this@AirportDiagramActivity, name, 12f, EfbUi.DIM))
        }, LinearLayout.LayoutParams(0, -2, 1f))
        top.addView(head)
        val chips = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(8), 0, 0) }
        lateinit var c3d: TextView
        lateinit var cTrack: TextView
        lateinit var cFollow: TextView
        c3d = chip("3D") { tilt(!tilted); mark(c3d, tilted) }
        cTrack = chip("🧭 Track up") {
            trackUp = !trackUp
            mark(cTrack, trackUp)
            if (!trackUp) turnTo(0f)
        }
        cFollow = chip("📍 Follow") {
            if (ownship.fix == null) { Toast.makeText(this, R.string.map_no_gps, Toast.LENGTH_SHORT).show(); return@chip }
            following = !following
            mark(cFollow, following)
            if (following) ownship.position()?.let { map.controller.animateTo(it, maxOf(map.zoomLevelDouble, 16.5), 700L) }
        }
        followChip = cFollow
        lateinit var cPause: TextView
        cPause = chip("⏸ Pause") { if (sketch == null) pause(root, bottom = null) else play(); cPause.text = if (sketch == null) "⏸ Pause" else "▶ Play"; mark(cPause, sketch != null) }
        pauseChip = cPause
        chips.addView(cPause)
        chips.addView(chip("🛫 Pattern") { choosePattern() })
        chips.addView(c3d)
        chips.addView(cTrack)
        chips.addView(cFollow)
        chips.addView(chip("📄 FAA diagram") { faaDiagram() })
        chips.addView(chip("N↑") { turnTo(0f) })
        chips.addView(chip("⟳") { load(refresh = true) })
        top.addView(HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; addView(chips) })
        root.addView(top, FrameLayout.LayoutParams(-1, -2, Gravity.TOP))

        val bottom = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(12), 0, dp(12), dp(14)) }
        surface = EfbUi.text(this, "", 20f, 0xFFFFFFFF.toInt(), bold = true).apply {
            gravity = Gravity.CENTER
            setPadding(dp(14), dp(10), dp(14), dp(10))
            visibility = View.GONE
        }
        bottom.addView(surface, LinearLayout.LayoutParams(-1, -2))
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = EfbUi.cardBg(this@AirportDiagramActivity, 0xE60B1220.toInt(), 14)
            setPadding(dp(14), dp(8), dp(14), dp(8))
        }
        gpsLine = EfbUi.ltr(EfbUi.text(this, getString(R.string.map_no_gps), 15f, EfbUi.TEXT, bold = true, mono = true)).apply { gravity = Gravity.CENTER }
        info = EfbUi.text(this, getString(R.string.dia_loading), 12f, EfbUi.DIM).apply { gravity = Gravity.CENTER }
        panel.addView(gpsLine)
        panel.addView(info)
        bottom.addView(panel, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8) })
        root.addView(bottom, FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM))
        bottomBar = bottom
        setContentView(root)
        androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(root) { _, insets ->
            val bars = insets.getInsets(androidx.core.view.WindowInsetsCompat.Type.systemBars())
            top.setPadding(dp(12), dp(10) + bars.top, dp(12), 0)
            bottom.setPadding(dp(12), 0, dp(12), dp(14) + bars.bottom)
            insets
        }
        mark(c3d, false)
        this.holder = holder

        // The opening shot: from high and turned, sweeping down onto the field.
        map.mapOrientation = -50f
        map.post {
            map.controller.animateTo(GeoPoint(lat0, lon0), 15.6, 2200L)
            turnTo(0f, 2200)
        }
        load(refresh = false)
        startGps()
    }

    private var holder: FrameLayout? = null
    private var sketch: DiagramSketch? = null
    private var sketchTools: View? = null
    private var bottomBar: View? = null
    private var pauseChip: TextView? = null

    /** Paused: the view holds still (no follow, no turning) and can be drawn on, to explain; nothing is kept. */
    @Suppress("UNUSED_PARAMETER")
    private fun pause(root: FrameLayout, bottom: View?) {
        stopFollowing()
        turn?.cancel()
        map.animate().cancel()
        val inv = android.graphics.Matrix()
        val sk = DiagramSketch(this, airplane()) { a, b ->
            // Screen to ground, through the 3D tilt and the map's turn.
            if (!map.matrix.invert(inv)) null else {
            val pts = floatArrayOf(a.x - map.left, a.y - map.top, b.x - map.left, b.y - map.top)
            inv.mapPoints(pts)
            val g1 = map.projection.fromPixels(pts[0].toInt(), pts[1].toInt()) as GeoPoint
            val g2 = map.projection.fromPixels(pts[2].toInt(), pts[3].toInt()) as GeoPoint
            g1.distanceToAsDouble(g2)
            }
        }
        val tools = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = EfbUi.cardBg(this@AirportDiagramActivity, 0xE60B1220.toInt(), 16)
            setPadding(dp(6), dp(6), dp(6), dp(6))
        }
        val toolChips = ArrayList<Pair<DiagramSketch.Tool, TextView>>()
        for (t in DiagramSketch.Tool.values()) {
            val c = chip(t.label) {
                // The pen in hand again: pick the kind of pen.
                if (t == DiagramSketch.Tool.PEN && sk.tool == t) PenInk.choose(this, sk.pen) { i -> sk.pen = i }
                sk.tool = t; toolChips.forEach { (k, v) -> mark(v, k == t) }
            }
            if (t == DiagramSketch.Tool.PEN) c.setOnLongClickListener { PenInk.choose(this, sk.pen) { i -> sk.pen = i }; true }
            toolChips.add(t to c)
            tools.addView(c)
        }
        mark(toolChips[0].second, true)
        for (col in intArrayOf(0xFFFFEB3B.toInt(), 0xFFFF1744.toInt(), 0xFF00E5FF.toInt(), 0xFF76FF03.toInt(), 0xFFFF9100.toInt(), 0xFFFFFFFF.toInt(), 0xFF000000.toInt())) {
            tools.addView(View(this).apply {
                background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(col); setStroke(dp(2), 0xFF455A64.toInt()) }
                setOnClickListener { sk.color = col; if (sk.tool == DiagramSketch.Tool.ERASER) { sk.tool = DiagramSketch.Tool.PEN; toolChips.forEach { (k, v) -> mark(v, k == DiagramSketch.Tool.PEN) } } }
            }, LinearLayout.LayoutParams(dp(28), dp(28)).apply { marginEnd = dp(8) })
        }
        tools.addView(chip("↶") { sk.undo() })
        tools.addView(chip("🗑") { sk.clear() })
        tools.addView(chip("▶ Play") { play() })
        val scroll = HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; addView(tools) }
        // Above the map, under the top bar, so its chips stay usable.
        root.addView(sk, 1, FrameLayout.LayoutParams(-1, -1))
        root.addView(scroll, FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM).apply {
            setMargins(dp(12), 0, dp(12), dp(14) + (androidx.core.view.ViewCompat.getRootWindowInsets(root)
                ?.getInsets(androidx.core.view.WindowInsetsCompat.Type.systemBars())?.bottom ?: 0))
        })
        bottomBar?.visibility = View.GONE
        sketch = sk
        sketchTools = scroll
        Toast.makeText(this, R.string.dia_paused, Toast.LENGTH_SHORT).show()
    }

    private fun play() {
        val root = sketch?.parent as? FrameLayout ?: return
        root.removeView(sketch)
        root.removeView(sketchTools)
        sketch = null
        sketchTools = null
        bottomBar?.visibility = View.VISIBLE
        pauseChip?.let { it.text = "⏸ Pause"; mark(it, false) }
    }
    private var followChip: TextView? = null

    override fun onResume() {
        super.onResume()
        map.onResume()
        map.removeCallbacks(frame)
        map.post(frame)
    }

    override fun onPause() {
        super.onPause()
        map.onPause()
        map.removeCallbacks(frame)
    }

    override fun onDestroy() {
        super.onDestroy()
        try { getSystemService(LocationManager::class.java)?.removeUpdates(gps) } catch (e: Exception) {}
        map.onDetach()
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

    /** The runway into the wind (from the METAR), else the airport's calm-wind runway; and the line under the view. */
    private fun pickRunway() {
        val station = (intent.getStringExtra("icao")?.ifEmpty { null } ?: ident).let { if (it.length == 3) "K$it" else it }
        lifecycleScope.launch {
            val m = withContext(Dispatchers.IO) { AviationData.metar(station) }
            val j = m?.json
            val spd = j?.opt("wspd")?.toString()?.toDoubleOrNull() ?: 0.0
            val dirTrue = j?.opt("wdir")?.toString()?.toDoubleOrNull()
            var best: String? = null
            if (dirTrue != null && spd >= 3) {
                val dirMag = Nav.magnetic(dirTrue, lat0, lon0)
                best = pattern.ends.keys.maxByOrNull { r ->
                    val n = r.takeWhile { it.isDigit() }.toIntOrNull() ?: return@maxByOrNull -99.0
                    Math.cos(Math.toRadians(dirMag - n * 10.0))
                }
            }
            if (best == null) best = PatternOverlay.calmRunway(ident)?.takeIf { it in pattern.ends } ?: pattern.ends.keys.firstOrNull()
            windLine = if (j == null) "" else if (spd < 3) "Wind calm" else "Wind %03d° %d kt".format(dirTrue?.toInt() ?: 0, spd.toInt())
            if (pattern.runway == null) setPattern(best)
            else showPatternInfo()
        }
    }

    private fun setPattern(rwy: String?) {
        pattern.runway = rwy
        pattern.right = rwy != null && PatternOverlay.isRight(this, ident, rwy)
        map.invalidate()
        showPatternInfo()
    }

    private fun showPatternInfo() {
        val r = pattern.runway
        info.text = if (r == null) getString(R.string.dia_hint) else
            listOfNotNull(windLine.ifEmpty { null }, "RWY $r · ${if (pattern.right) "Right" else "Left"} traffic",
                if (pattern.tpaFt > 0) "TPA %,d ft".format(pattern.tpaFt) else null).joinToString("  ·  ") +
                "\n" + getString(R.string.tp_source)
    }

    /** Which runway's pattern, and its side (left or right traffic), kept per airport. */
    private fun choosePattern() {
        val rwys = pattern.ends.keys.toList()
        if (rwys.isEmpty()) { Toast.makeText(this, R.string.dia_photo_only, Toast.LENGTH_SHORT).show(); return }
        val labels2 = rwys.map { r -> "RWY $r  ·  ${if (PatternOverlay.isRight(this, ident, r)) "Right" else "Left"} traffic" + if (r == pattern.runway) "  ✓" else "" } +
            getString(R.string.tp_side) + getString(R.string.tp_off)
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.tp_title)
            .setItems(labels2.toTypedArray()) { _, i ->
                when {
                    i < rwys.size -> setPattern(rwys[i])
                    i == rwys.size -> pattern.runway?.let { r ->
                        PatternOverlay.setRight(this, ident, r, !pattern.right)
                        setPattern(r)
                    }
                    else -> setPattern(null)
                }
            }
            .show()
    }

    private fun stopFollowing() {
        if (!following) return
        following = false
        followChip?.let { mark(it, false) }
    }

    private var turn: ValueAnimator? = null

    private fun turnTo(deg: Float, ms: Long = 600) {
        turn?.cancel()
        val from = map.mapOrientation
        val delta = ((deg - from + 540) % 360) - 180
        turn = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = ms
            interpolator = DecelerateInterpolator()
            addUpdateListener { map.mapOrientation = from + delta * (it.animatedValue as Float) }
            start()
        }
    }

    /** The field laid down in perspective, the horizon beyond it. */
    private fun tilt(on: Boolean) {
        tilted = on
        val h = (holder?.height ?: map.height).toFloat().coerceAtLeast(1f)
        map.pivotX = map.width / 2f
        map.pivotY = h
        map.cameraDistance = 12000 * resources.displayMetrics.density
        map.animate().rotationX(if (on) 45f else 0f).scaleX(if (on) 1.7f else 1f).scaleY(if (on) 1.45f else 1f)
            .setDuration(700).setInterpolator(DecelerateInterpolator()).start()
        holder?.background = if (on) GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM,
            intArrayOf(0xFF0B1A33.toInt(), 0xFF2D5C8A.toInt(), 0xFF9EC3E0.toInt())) else null
    }

    private fun load(refresh: Boolean) {
        info.text = getString(R.string.dia_loading)
        lifecycleScope.launch {
            val json = withContext(Dispatchers.IO) { fetch(this@AirportDiagramActivity, ident, lat0, lon0, refresh) }
            val n = if (json != null) labels.load(json) else 0
            pattern.ends = labels.runwayEnds()
            pickRunway()
            info.text = getString(if (n > 0) R.string.dia_hint else R.string.dia_photo_only)
            map.invalidate()
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

    private val frame: Runnable = object : Runnable {
        private var heading = Float.NaN
        override fun run() {
            val fix = ownship.fix
            if (sketch != null) {
                // Paused: the view holds still.
            } else if (fix != null && following) {
                ownship.position()?.let { map.controller.setCenter(it) }
                if (trackUp && fix.hasBearing() && ownship.speedKt() > 2) {
                    heading = if (heading.isNaN()) fix.bearing else heading + (((fix.bearing - heading + 540) % 360) - 180) * 0.15f
                    map.mapOrientation = -heading
                }
            } else if (fix != null && ownship.speedKt() > 2) {
                map.invalidate()
            }
            map.postDelayed(this, if (following) 33L else 200L)
        }
    }

    private var lastSurface = ""

    private fun onFix(l: Location) {
        ownship.update(l)
        val kt = if (l.hasSpeed()) l.speed * 1.943844 else 0.0
        val near = Nav.distanceNm(l.latitude, l.longitude, lat0, lon0)
        val trk = if (l.hasBearing() && kt > 2) "  ·  TRK " + Nav.deg(Nav.magnetic(l.bearing.toDouble(), l.latitude, l.longitude)) + "M" else ""
        gpsLine.text = "GS %d kt%s".format(Math.round(kt), trk) + if (near > 3) "  ·  %.1f nm".format(near) else ""
        val on = if (near < 3) labels.surfaceAt(l.latitude, l.longitude) else null
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
            // Rolling onto a runway: a buzz the moment it happens.
            if (on.first && kt < 40) {
                (getSystemService(Context.VIBRATOR_SERVICE) as? android.os.Vibrator)?.let {
                    try { it.vibrate(android.os.VibrationEffect.createWaveform(longArrayOf(0, 180, 120, 180), -1)) } catch (e: Exception) {}
                }
            }
        }
        lastSurface = on.second
    }

    private fun airplane(): Bitmap {
        val s = (34 * resources.displayMetrics.density).toInt()
        val bmp = Bitmap.createBitmap(s, s, Bitmap.Config.ARGB_8888)
        val c = Canvas(bmp)
        val f = s / 24f
        val p = Path().apply {
            moveTo(12 * f, 1 * f); lineTo(13.5f * f, 8 * f); lineTo(22 * f, 13 * f); lineTo(22 * f, 15 * f)
            lineTo(13.5f * f, 12.5f * f); lineTo(13 * f, 19 * f); lineTo(16 * f, 21 * f); lineTo(16 * f, 22.5f * f)
            lineTo(12 * f, 21.5f * f); lineTo(8 * f, 22.5f * f); lineTo(8 * f, 21 * f); lineTo(11 * f, 19 * f)
            lineTo(10.5f * f, 12.5f * f); lineTo(2 * f, 15 * f); lineTo(2 * f, 13 * f); lineTo(10.5f * f, 8 * f); close()
        }
        c.drawPath(p, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF000000.toInt(); style = Paint.Style.STROKE; strokeWidth = 2.5f * f })
        c.drawPath(p, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF00E5FF.toInt() })
        return bmp
    }

    companion object {
        fun open(act: Activity, a: AviationData.Airport) {
            act.startActivity(Intent(act, AirportDiagramActivity::class.java)
                .putExtra("ident", a.ident).putExtra("icao", a.icao).putExtra("name", a.name)
                .putExtra("lat", a.lat).putExtra("lon", a.lon).putExtra("elev", a.elevation))
        }

        private val SERVERS = listOf(
            "https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.private.coffee/api/interpreter",
        )

        /** The airport's surveyed runways, taxiways and hold lines, kept on the phone for use without signal. */
        fun fetch(ctx: Context, ident: String, lat: Double, lon: Double, refresh: Boolean): JSONObject? {
            val file = File(ctx.filesDir, "aviation/apt/${ident.replace(Regex("[^A-Z0-9]"), "")}.json")
            if (!refresh && file.length() > 0) try { return JSONObject(file.readText()) } catch (e: Exception) {}
            val q = "[out:json][timeout:30];way[\"aeroway\"~\"runway|taxiway|taxilane|holding_position\"](around:4000,$lat,$lon);out geom;"
            for (server in SERVERS) {
                try {
                    val c = URL(server).openConnection() as HttpURLConnection
                    c.connectTimeout = 15000
                    c.readTimeout = 45000
                    c.requestMethod = "POST"
                    c.doOutput = true
                    c.setRequestProperty("User-Agent", "SSEFB/1.0")
                    c.setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
                    c.outputStream.use { it.write(("data=" + URLEncoder.encode(q, "UTF-8")).toByteArray()) }
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
 * Runway numbers at the ends they are read from, black-and-yellow taxiway
 * signs, and hold-short lines, over the satellite photo.
 */
class LabelsOverlay(private val map: MapView) : Overlay() {

    class Feature(val kind: String, val ref: String, val lat: DoubleArray, val lon: DoubleArray, val width: Double)

    private val features = ArrayList<Feature>()
    private val d = map.resources.displayMetrics.density
    private val pt = Point()
    private val pt2 = Point()
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND }
    private val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { isFakeBoldText = true; textAlign = Paint.Align.CENTER; typeface = android.graphics.Typeface.MONOSPACE }
    private val pill = RectF()

    fun load(json: JSONObject): Int {
        features.clear()
        endsCache = null
        val el = json.optJSONArray("elements") ?: JSONArray()
        for (i in 0 until el.length()) {
            val o = el.optJSONObject(i) ?: continue
            val g = o.optJSONArray("geometry") ?: continue
            if (g.length() < 2) continue
            val t = o.optJSONObject("tags") ?: JSONObject()
            val kind = when (t.optString("aeroway")) {
                "runway" -> "runway"
                "taxiway", "taxilane" -> "taxiway"
                "holding_position" -> "hold"
                else -> continue
            }
            val lat = DoubleArray(g.length()) { g.getJSONObject(it).getDouble("lat") }
            val lon = DoubleArray(g.length()) { g.getJSONObject(it).getDouble("lon") }
            val w = t.optString("width").replace(Regex("[^0-9.]"), "").toDoubleOrNull() ?: if (kind == "runway") 30.0 else 15.0
            features.add(Feature(kind, t.optString("ref"), lat, lon, w))
        }
        return features.size
    }

    /**
     * Each runway end: designator → (threshold, far end), from all the pieces of a runway
     * (OSM often draws one runway in several pieces), its ends the two points farthest apart.
     */
    private var endsCache: Map<String, Pair<GeoPoint, GeoPoint>>? = null

    fun runwayEnds(): Map<String, Pair<GeoPoint, GeoPoint>> {
        endsCache?.let { return it }
        val out = LinkedHashMap<String, Pair<GeoPoint, GeoPoint>>()
        for ((ref, list) in features.filter { it.kind == "runway" && it.ref.isNotEmpty() }.groupBy { it.ref }) {
            val pts = list.flatMap { f -> f.lat.indices.map { GeoPoint(f.lat[it], f.lon[it]) } }
            var a0 = pts.first(); var a1 = pts.last(); var best = -1.0
            for (i in pts.indices) for (j in i + 1 until pts.size) {
                val dd = Nav.distanceNm(pts[i].latitude, pts[i].longitude, pts[j].latitude, pts[j].longitude)
                if (dd > best) { best = dd; a0 = pts[i]; a1 = pts[j] }
            }
            val brg = Nav.magnetic(Nav.bearingTrue(a0.latitude, a0.longitude, a1.latitude, a1.longitude), a0.latitude, a0.longitude)
            val parts = ref.split('/').map { it.trim() }.filter { it.isNotEmpty() }
            fun gap(p: String) = p.takeWhile { it.isDigit() }.toIntOrNull()?.let { Math.abs(((it * 10 - brg + 540) % 360) - 180) } ?: 999.0
            val first = parts.minByOrNull { gap(it) } ?: continue
            out[first] = a0 to a1
            parts.firstOrNull { it != first }?.let { out[it] = a1 to a0 }
        }
        endsCache = out
        return out
    }

    /** Whether a point is on a runway (true) or a taxiway (false), and its name. */
    fun surfaceAt(lat: Double, lon: Double): Pair<Boolean, String>? {
        for (f in features) if (f.kind == "runway" && near(f, lat, lon, f.width / 2 + 3)) return true to "⚠️ RWY ${f.ref}"
        for (f in features) if (f.kind == "taxiway" && f.ref.isNotEmpty() && near(f, lat, lon, f.width / 2 + 4)) return false to "TWY ${f.ref}"
        return null
    }

    private fun near(f: Feature, lat: Double, lon: Double, metres: Double): Boolean {
        val mx = 111320.0 * Math.cos(Math.toRadians(lat)); val my = 110540.0
        for (i in 0 until f.lat.size - 1) {
            val ax = (f.lon[i] - lon) * mx; val ay = (f.lat[i] - lat) * my
            val bx = (f.lon[i + 1] - lon) * mx; val by = (f.lat[i + 1] - lat) * my
            val l2 = (bx - ax) * (bx - ax) + (by - ay) * (by - ay)
            val t = if (l2 == 0.0) 0.0 else ((-ax * (bx - ax) - ay * (by - ay)) / l2).coerceIn(0.0, 1.0)
            if (hypot(ax + t * (bx - ax), ay + t * (by - ay)) < metres) return true
        }
        return false
    }

    private fun upright(c: Canvas, x: Float, y: Float, block: () -> Unit) {
        c.save()
        c.rotate(-map.mapOrientation, x, y)
        block()
        c.restore()
    }

    override fun draw(c: Canvas, mapView: MapView, shadow: Boolean) {
        if (shadow || mapView.zoomLevelDouble < 13.5) return
        val pr = mapView.projection
        // Hold-short lines.
        stroke.color = 0xFFF2C744.toInt()
        stroke.strokeWidth = 3 * d
        for (f in features) if (f.kind == "hold") {
            pr.toPixels(GeoPoint(f.lat[0], f.lon[0]), pt)
            pr.toPixels(GeoPoint(f.lat.last(), f.lon.last()), pt2)
            c.drawLine(pt.x.toFloat(), pt.y.toFloat(), pt2.x.toFloat(), pt2.y.toFloat(), stroke)
        }
        // Taxiway signs, one per name every few hundred metres.
        val placed = ArrayList<Triple<String, Double, Double>>()
        text.textSize = 12f * d
        for (f in features) {
            if (f.kind != "taxiway" || f.ref.isEmpty()) continue
            val m = f.lat.size / 2
            val lat = f.lat[m]; val lon = f.lon[m]
            if (placed.any { it.first == f.ref && Nav.distanceNm(it.second, it.third, lat, lon) < 0.18 }) continue
            placed.add(Triple(f.ref, lat, lon))
            pr.toPixels(GeoPoint(lat, lon), pt)
            val x = pt.x.toFloat(); val y = pt.y.toFloat()
            upright(c, x, y) {
                val w = text.measureText(f.ref) / 2 + 6 * d
                pill.set(x - w, y - 11 * d, x + w, y + 6 * d)
                fill.color = 0xFF111111.toInt()
                c.drawRoundRect(pill, 4 * d, 4 * d, fill)
                stroke.strokeWidth = 1.2f * d
                c.drawRoundRect(pill, 4 * d, 4 * d, stroke)
                text.color = 0xFFF2C744.toInt()
                c.drawText(f.ref, x, y, text)
            }
        }
        // Runway numbers: red signs with white figures, at the end each is read from on landing, once each.
        text.textSize = 15f * d
        run {
            val ends = runwayEnds().map { (label, e) ->
                val (th, far) = e
                val len = Nav.distanceNm(th.latitude, th.longitude, far.latitude, far.longitude)
                label to Nav.destination(th.latitude, th.longitude, Nav.bearingTrue(th.latitude, th.longitude, far.latitude, far.longitude), minOf(0.05, len / 5))
            }
            for ((label, g) in ends) {
                pr.toPixels(g, pt)
                val x = pt.x.toFloat(); val y = pt.y.toFloat()
                upright(c, x, y) {
                    val w = text.measureText(label) / 2 + 7 * d
                    pill.set(x - w, y - 13 * d, x + w, y + 7 * d)
                    fill.color = 0xFFC62828.toInt()
                    c.drawRoundRect(pill, 4 * d, 4 * d, fill)
                    text.color = 0xFFFFFFFF.toInt()
                    c.drawText(label, x, y, text)
                }
            }
        }
    }
}
