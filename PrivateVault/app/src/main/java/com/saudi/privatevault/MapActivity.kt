package com.saudi.privatevault

import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.drawable.GradientDrawable
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import android.text.InputType
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.view.WindowManager
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.saudi.privatevault.databinding.ActivityMapBinding
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.osmdroid.config.Configuration
import org.osmdroid.events.DelayedMapListener
import org.osmdroid.events.MapListener
import org.osmdroid.events.ScrollEvent
import org.osmdroid.events.ZoomEvent
import org.osmdroid.tileprovider.cachemanager.CacheManager
import org.osmdroid.tileprovider.tilesource.OnlineTileSourceBase
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.CustomZoomButtonsController
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.ScaleBarOverlay
import org.osmdroid.views.overlay.mylocation.GpsMyLocationProvider
import org.osmdroid.views.overlay.mylocation.MyLocationNewOverlay
import java.io.File

/**
 * A moving map for VFR and IFR flying in the western US: FAA sectional, TAC
 * and IFR low charts (current cycle, straight from the FAA), airports coloured
 * by their weather, the aircraft's position, ground speed, track and altitude
 * from the GPS, drawing and measuring on the chart, and areas saved for
 * flying without signal. Drawings are shared through the linked vault.
 */
class MapActivity : BaseActivity() {

    private lateinit var b: ActivityMapBinding
    private lateinit var map: MapView
    private lateinit var draw: MapDrawOverlay
    private lateinit var airportsLayer: AirportsOverlay
    private var me: MyLocationNewOverlay? = null
    private var layer = AviationData.LAYERS[0]
    private var following = false
    private var trackUp = false
    private val prefs get() = VaultLock.prefs(this)

    // The drawings, stored like a document's notes on page 0, and their undo.
    private lateinit var marks: DocumentMarks
    private val undo = ArrayDeque<AnnotatedPageView.Edit>()
    private val redo = ArrayDeque<AnnotatedPageView.Edit>()
    private val toolButtons = HashMap<MapDrawOverlay.MapTool, ImageButton>()
    private var colorButton: ImageButton? = null
    private var sizeButton: ImageButton? = null

    private val locationPermission = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { r ->
        if (r.values.any { it }) startGps() else Toast.makeText(this, R.string.map_gps_needed, Toast.LENGTH_LONG).show()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Charts are kept in the app's own storage, never where other apps can read them.
        Configuration.getInstance().apply {
            userAgentValue = packageName
            osmdroidBasePath = File(filesDir, "osmdroid")
            osmdroidTileCache = File(filesDir, "osmdroid/tiles")
            tileFileSystemCacheMaxBytes = 3L * 1024 * 1024 * 1024
            tileFileSystemCacheTrimBytes = 2L * 1024 * 1024 * 1024
        }
        b = ActivityMapBinding.inflate(layoutInflater)
        setContentView(b.root)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setSupportActionBar(b.toolbar)
        b.toolbar.setNavigationOnClickListener { finish() }

        map = MapView(this)
        b.mapHolder.addView(map, FrameLayout.LayoutParams(-1, -1))
        map.setMultiTouchControls(true)
        map.zoomController.setVisibility(CustomZoomButtonsController.Visibility.NEVER)
        map.minZoomLevel = 4.0
        map.maxZoomLevel = 15.0
        map.isTilesScaledToDpi = true
        layer = AviationData.LAYERS.firstOrNull { it.key == prefs.getString("map_layer", "sectional") } ?: AviationData.LAYERS[0]
        map.setTileSource(layer.source())

        // Where the map was left; the first time, over Boulder City (KBVU).
        val lat = prefs.getFloat("map_lat", 35.9478f).toDouble()
        val lon = prefs.getFloat("map_lon", -114.8614f).toDouble()
        map.controller.setZoom(prefs.getFloat("map_zoom", 10f).toDouble())
        map.controller.setCenter(GeoPoint(lat, lon))

        map.overlays.add(ScaleBarOverlay(map).apply {
            setUnitsOfMeasure(ScaleBarOverlay.UnitsOfMeasure.nautical)
            setAlignBottom(true)
            setScaleBarOffset((16 * resources.displayMetrics.density).toInt(), (120 * resources.displayMetrics.density).toInt())
        })
        airportsLayer = AirportsOverlay(map).apply { onPick = { showAirport(it) } }
        map.overlays.add(airportsLayer)
        draw = MapDrawOverlay(map)
        draw.cruiseKt = prefs.getFloat("cruise_kt", 100f).toDouble()
        draw.showMeasures = prefs.getBoolean("map_measures", true)
        map.overlays.add(draw)

        marks = DocumentMarks.forItem(this, "flight-map")
        draw.marks.addAll(marks.on(0))
        setUpPen()
        pullDrawings()

        map.addMapListener(DelayedMapListener(object : MapListener {
            override fun onScroll(event: ScrollEvent?): Boolean = idle()
            override fun onZoom(event: ZoomEvent?): Boolean = idle()
        }, 900))

        b.fabLayers.setOnClickListener { chooseLayer() }
        b.fabDraw.setOnClickListener { toggleDrawing() }
        b.fabLocate.setOnClickListener { follow() }
        b.measureKeep.setOnClickListener { draw.keepRuler(); b.measureBar.visibility = View.GONE }
        b.measureClose.setOnClickListener { draw.clearRuler() }
        draw.onMeasure = { text ->
            if (text != null) {
                b.measureText.text = text
                b.measureBar.visibility = View.VISIBLE
                b.measureKeep.visibility = if (draw.tool == MapDrawOverlay.MapTool.RULER) View.VISIBLE else View.GONE
            } else if (draw.tool != MapDrawOverlay.MapTool.RULER) {
                b.measureBar.visibility = View.GONE
            }
        }

        loadAirports()
        if (!prefs.getBoolean("map_disclaimer_seen", false)) {
            MaterialAlertDialogBuilder(this)
                .setTitle(R.string.map_title)
                .setMessage(R.string.map_disclaimer)
                .setPositiveButton(android.R.string.ok) { _, _ -> prefs.edit().putBoolean("map_disclaimer_seen", true).apply() }
                .show()
        }
        askGps()
    }

    override fun onResume() {
        super.onResume()
        map.onResume()
    }

    override fun onPause() {
        super.onPause()
        map.onPause()
        val c = map.mapCenter
        prefs.edit().putFloat("map_lat", c.latitude.toFloat()).putFloat("map_lon", c.longitude.toFloat())
            .putFloat("map_zoom", map.zoomLevelDouble.toFloat()).apply()
        pushDrawings()
    }

    override fun onDestroy() {
        super.onDestroy()
        stopGps()
        map.onDetach()
    }

    // ---- layers, airports and weather ----

    private fun chooseLayer() {
        val labels = AviationData.LAYERS.map { getString(it.label) }.toTypedArray()
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.map_layers)
            .setSingleChoiceItems(labels, AviationData.LAYERS.indexOf(layer)) { d, which ->
                layer = AviationData.LAYERS[which]
                prefs.edit().putString("map_layer", layer.key).apply()
                map.setTileSource(layer.source())
                d.dismiss()
            }
            .show()
    }

    private fun loadAirports() {
        lifecycleScope.launch {
            val list = withContext(Dispatchers.IO) { AviationData.airports(this@MapActivity) }
            airportsLayer.airports = if (prefs.getBoolean("map_airports", true)) list else emptyList()
            draw.snapTo = list
            map.invalidate()
            idle()
        }
    }

    private var lastWeatherBox = ""

    /** After the map settles: the weather of the airports in view. */
    private fun idle(): Boolean {
        if (map.zoomLevelDouble < 7 || !prefs.getBoolean("map_airports", true)) return true
        val bb = map.boundingBox
        val key = "%.1f,%.1f,%.1f,%.1f".format(bb.latSouth, bb.lonWest, bb.latNorth, bb.lonEast)
        if (key == lastWeatherBox) return true
        lastWeatherBox = key
        lifecycleScope.launch {
            val list = withContext(Dispatchers.IO) { AviationData.metars(bb.latSouth, bb.lonWest, bb.latNorth, bb.lonEast) }
            if (list.isNotEmpty()) {
                airportsLayer.weather = airportsLayer.weather + list.associateBy { it.station }
                map.invalidate()
            }
        }
        return true
    }

    private fun showAirport(a: AviationData.Airport) {
        val station = airportsLayer.station(a)
        val head = "${a.ident}${if (a.icao.isNotEmpty() && a.icao != a.ident) " / " + a.icao else ""} — ${a.name}\n" +
            "${a.city.lowercase().replaceFirstChar { it.uppercase() }} · ${"%,d".format(a.elevation)} ft"
        val dialog = MaterialAlertDialogBuilder(this)
            .setTitle(a.ident)
            .setMessage(head + "\n\n" + getString(R.string.map_loading_wx))
            .setPositiveButton(android.R.string.ok, null)
            .show()
        lifecycleScope.launch {
            val (metar, taf) = withContext(Dispatchers.IO) { AviationData.metar(station) to AviationData.taf(station) }
            val wx = if (metar == null) getString(R.string.map_no_metar) else
                "${metar.category.ifEmpty { "—" }}\n\nMETAR\n${metar.raw}" + (taf?.let { "\n\nTAF\n$it" } ?: "")
            dialog.setMessage(head + "\n\n" + wx)
        }
    }

    // ---- the aircraft ----

    private fun askGps() {
        val fine = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        if (fine) startGps()
        else locationPermission.launch(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION))
    }

    private var lm: LocationManager? = null
    private val listener = LocationListener { l -> onFix(l) }

    @SuppressLint("MissingPermission")
    private fun startGps() {
        if (me == null) {
            val plane = airplane()
            me = MyLocationNewOverlay(GpsMyLocationProvider(this), map).apply {
                setPersonIcon(plane)
                setDirectionIcon(plane)
                setPersonAnchor(0.5f, 0.5f)
                setDirectionAnchor(0.5f, 0.5f)
                enableMyLocation()
            }
            map.overlays.add(me)
        }
        lm = getSystemService(LocationManager::class.java)
        try {
            lm?.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000L, 0f, listener)
            b.hud.visibility = View.VISIBLE
            b.hudGs.text = getString(R.string.map_no_gps)
        } catch (e: Exception) {
            // No GPS on this device.
        }
    }

    private fun stopGps() {
        try {
            lm?.removeUpdates(listener)
        } catch (e: Exception) {
        }
        me?.disableMyLocation()
    }

    /** Ground speed in knots, track in degrees magnetic, altitude in feet MSL. */
    private fun onFix(l: Location) {
        val kt = if (l.hasSpeed()) l.speed * 1.943844 else 0.0
        b.hudGs.text = "GS %d kt".format(Math.round(kt))
        b.hudTrk.text = if (l.hasBearing() && kt > 5) "TRK " + Nav.deg(Nav.magnetic(l.bearing.toDouble(), l.latitude, l.longitude)) + "M" else "TRK ---"
        b.hudAlt.text = if (l.hasAltitude()) "ALT %,d ft".format(Math.round(l.altitude * 3.28084)) else "ALT ---"
        if (following) {
            map.controller.animateTo(GeoPoint(l.latitude, l.longitude))
            if (trackUp && l.hasBearing() && kt > 5) map.mapOrientation = -l.bearing
        }
    }

    private fun follow() {
        following = !following
        val fix = me?.myLocation
        if (following && fix != null) map.controller.animateTo(fix)
        if (!following) map.mapOrientation = 0f
        b.fabLocate.alpha = if (following) 1f else 0.6f
        Toast.makeText(this, if (following) "📍 ${getString(R.string.map_follow)}" else "✋", Toast.LENGTH_SHORT).show()
    }

    /** A simple airplane seen from above, pointing up. */
    private fun airplane(): Bitmap {
        val s = (36 * resources.displayMetrics.density).toInt()
        val bmp = Bitmap.createBitmap(s, s, Bitmap.Config.ARGB_8888)
        val c = Canvas(bmp)
        val f = s / 24f
        val p = Path().apply {
            moveTo(12 * f, 1 * f); lineTo(13.5f * f, 8 * f); lineTo(22 * f, 13 * f); lineTo(22 * f, 15 * f)
            lineTo(13.5f * f, 12.5f * f); lineTo(13 * f, 19 * f); lineTo(16 * f, 21 * f); lineTo(16 * f, 22.5f * f)
            lineTo(12 * f, 21.5f * f); lineTo(8 * f, 22.5f * f); lineTo(8 * f, 21 * f); lineTo(11 * f, 19 * f)
            lineTo(10.5f * f, 12.5f * f); lineTo(2 * f, 15 * f); lineTo(2 * f, 13 * f); lineTo(10.5f * f, 8 * f); close()
        }
        c.drawPath(p, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFFFFFF.toInt(); style = Paint.Style.STROKE; strokeWidth = 2.5f * f })
        c.drawPath(p, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF0D47A1.toInt() })
        return bmp
    }

    // ---- drawing on the chart ----

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun setUpPen() {
        val bar = b.penTools
        fun button(icon: Int, label: String, onClick: () -> Unit) = ImageButton(this).apply {
            setImageResource(icon)
            contentDescription = label
            tooltipText = label
            background = null
            setPadding(dp(10), dp(10), dp(10), dp(10))
            setOnClickListener { onClick() }
            bar.addView(this, LinearLayout.LayoutParams(dp(46), dp(46)).apply { setMargins(dp(2), 0, dp(2), 0) })
        }
        val T = MapDrawOverlay.MapTool
        val tools = listOf(
            Triple(T.PAN, R.drawable.ic_tool_hand, R.string.pen_hand),
            Triple(T.RULER, R.drawable.ic_ruler, R.string.map_ruler),
            Triple(T.SELECT, R.drawable.ic_tool_select, R.string.pen_select),
            Triple(T.PEN, R.drawable.ic_tool_pen, R.string.pen_pen),
            Triple(T.LINE, R.drawable.ic_tool_line, R.string.pen_line),
            Triple(T.ARROW, R.drawable.ic_tool_arrow, R.string.pen_arrow),
            Triple(T.CIRCLE, R.drawable.ic_tool_oval, R.string.map_circle),
            Triple(T.RECT, R.drawable.ic_tool_rect, R.string.pen_rect),
            Triple(T.TEXT, R.drawable.ic_tool_text, R.string.pen_text),
            Triple(T.ERASER, R.drawable.ic_tool_eraser, R.string.pen_eraser),
        )
        for ((tool, icon, label) in tools) toolButtons[tool] = button(icon, getString(label)) { pick(tool) }
        bar.addView(View(this).apply { setBackgroundColor(0x33000000) }, LinearLayout.LayoutParams(dp(1), dp(28)).apply { setMargins(dp(6), 0, dp(6), 0) })
        colorButton = button(R.drawable.ic_tool_pen, getString(R.string.pen_color)) { chooseColor() }
        sizeButton = button(R.drawable.ic_tool_pen, getString(R.string.pen_size)) {
            draw.widthDp = when (draw.widthDp) { 2f -> 3.5f; 3.5f -> 6f; else -> 2f }
            prefs.edit().putFloat("map_width", draw.widthDp).apply()
            paintSwatches()
        }
        button(R.drawable.ic_undo, getString(R.string.pen_undo)) { undoLast() }
        button(R.drawable.ic_redo, getString(R.string.pen_redo)) { redoLast() }
        button(R.drawable.ic_delete, getString(R.string.pen_delete)) { draw.deleteSelected() }
        button(R.drawable.ic_check, getString(R.string.pen_done)) { toggleDrawing() }
        draw.color = prefs.getInt("map_color", 0xFFD32F2F.toInt())
        draw.widthDp = prefs.getFloat("map_width", 3.5f)
        draw.onEdit = { e ->
            undo.addLast(e)
            redo.clear()
            saveDrawings()
        }
        draw.onTextAt = { g -> askText(g) }
        pick(T.PAN)
    }

    private fun toggleDrawing() {
        val on = b.penBar.visibility != View.VISIBLE
        b.penBar.visibility = if (on) View.VISIBLE else View.GONE
        b.fabs.visibility = if (on) View.GONE else View.VISIBLE
        pick(if (on) MapDrawOverlay.MapTool.RULER else MapDrawOverlay.MapTool.PAN)
    }

    private fun pick(tool: MapDrawOverlay.MapTool) {
        draw.tool = tool
        if (tool != MapDrawOverlay.MapTool.SELECT) draw.selected = null
        if (tool != MapDrawOverlay.MapTool.RULER) draw.clearRuler()
        for ((t, btn) in toolButtons) btn.background = if (t == tool) getDrawable(R.drawable.tool_selected_bg) else null
        paintSwatches()
    }

    private fun paintSwatches() {
        colorButton?.setImageDrawable(GradientDrawable().apply {
            shape = GradientDrawable.OVAL
            setColor(draw.color)
            setStroke(dp(2), 0x33000000)
            setSize(dp(22), dp(22))
        })
        val d = when (draw.widthDp) { 2f -> 6; 3.5f -> 11; else -> 17 }
        sizeButton?.setImageDrawable(GradientDrawable().apply {
            shape = GradientDrawable.OVAL
            setColor(0xFF616161.toInt())
            setSize(dp(d), dp(d))
        })
    }

    private fun chooseColor() {
        val grid = android.widget.GridLayout(this).apply {
            columnCount = 6
            setPadding(dp(14), dp(10), dp(14), dp(4))
            layoutDirection = View.LAYOUT_DIRECTION_LTR
        }
        val picked = draw.selected
        val current = picked?.color ?: draw.color
        val dialog = MaterialAlertDialogBuilder(this).setTitle(R.string.pen_color).setView(grid).show()
        for (c in MarkPainter.INK) {
            grid.addView(View(this).apply {
                background = GradientDrawable().apply {
                    shape = GradientDrawable.OVAL
                    setColor(c)
                    setStroke(dp(if (c == current) 4 else 1), if (c == current) 0xFF1E88E5.toInt() else 0x44000000)
                }
                setOnClickListener {
                    if (picked != null) draw.recolorSelected(c) else {
                        draw.color = c
                        prefs.edit().putInt("map_color", c).apply()
                    }
                    paintSwatches()
                    dialog.dismiss()
                }
            }, android.widget.GridLayout.LayoutParams().apply {
                width = dp(40)
                height = dp(40)
                setMargins(dp(5), dp(5), dp(5), dp(5))
            })
        }
    }

    private fun askText(at: GeoPoint) {
        val input = EditText(this).apply { minLines = 2 }
        val box = FrameLayout(this).apply {
            setPadding(dp(20), dp(8), dp(20), 0)
            addView(input)
        }
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.pen_text)
            .setView(box)
            .setPositiveButton(R.string.ok) { _, _ -> input.text.toString().trim().takeIf { it.isNotEmpty() }?.let { draw.addText(at, it) } }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun undoLast() {
        val e = undo.removeLastOrNull() ?: return
        when (e) {
            is AnnotatedPageView.Edit.Added -> draw.marks.remove(e.mark)
            is AnnotatedPageView.Edit.Removed -> for ((i, m) in e.removed.asReversed()) draw.marks.add(i.coerceAtMost(draw.marks.size), m)
            is AnnotatedPageView.Edit.Changed -> { e.before.copyInto(e.mark.points); e.mark.color = e.colorBefore }
        }
        redo.addLast(e)
        draw.selected = null
        saveDrawings()
    }

    private fun redoLast() {
        val e = redo.removeLastOrNull() ?: return
        when (e) {
            is AnnotatedPageView.Edit.Added -> draw.marks.add(e.mark)
            is AnnotatedPageView.Edit.Removed -> for ((_, m) in e.removed) draw.marks.remove(m)
            is AnnotatedPageView.Edit.Changed -> { e.after.copyInto(e.mark.points); e.mark.color = e.colorAfter }
        }
        undo.addLast(e)
        draw.selected = null
        saveDrawings()
    }

    // ---- keeping and sharing the drawings ----

    private val pushSoon = Runnable { pushDrawings() }

    private fun saveDrawings() {
        val list = marks.on(0)
        list.clear()
        list.addAll(draw.marks)
        marks.touch(0)
        val text = marks.snapshot()
        CoroutineScope(Dispatchers.IO).launch { marks.write(text) }
        map.invalidate()
        b.root.removeCallbacks(pushSoon)
        b.root.postDelayed(pushSoon, 2500)
    }

    private fun pullDrawings() {
        if (!LaptopClient.isLinked(this)) return
        lifecycleScope.launch {
            val remote = withContext(Dispatchers.IO) { LaptopClient.syncKv(this@MapActivity, "map", null) } ?: return@launch
            applyRemote(remote)
            pushDrawings()
        }
    }

    private fun pushDrawings() {
        if (!LaptopClient.isLinked(this)) return
        val text = marks.snapshot()
        CoroutineScope(Dispatchers.IO).launch {
            val merged = LaptopClient.syncKv(this@MapActivity, "map", text) ?: return@launch
            runOnUiThread { if (!isDestroyed) applyRemote(merged) }
        }
    }

    private fun applyRemote(remote: org.json.JSONObject) {
        if (marks.merge(remote).isEmpty()) return
        draw.marks.clear()
        draw.marks.addAll(marks.on(0))
        undo.clear()
        redo.clear()
        map.invalidate()
        val text = marks.snapshot()
        CoroutineScope(Dispatchers.IO).launch { marks.write(text) }
    }

    // ---- menu ----

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menu.add(0, 1, 0, R.string.map_airports).setCheckable(true).isChecked = prefs.getBoolean("map_airports", true)
        menu.add(0, 2, 0, R.string.map_measures).setCheckable(true).isChecked = draw.showMeasures
        menu.add(0, 3, 0, R.string.map_track_up).setCheckable(true).isChecked = trackUp
        menu.add(0, 4, 0, R.string.map_download)
        menu.add(0, 5, 0, R.string.map_aircraft)
        menu.add(0, 6, 0, R.string.map_clear)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        when (item.itemId) {
            1 -> {
                val on = !item.isChecked
                item.isChecked = on
                prefs.edit().putBoolean("map_airports", on).apply()
                lastWeatherBox = ""
                loadAirports()
            }
            2 -> {
                draw.showMeasures = !item.isChecked
                item.isChecked = draw.showMeasures
                prefs.edit().putBoolean("map_measures", draw.showMeasures).apply()
                map.invalidate()
            }
            3 -> {
                trackUp = !item.isChecked
                item.isChecked = trackUp
                if (!trackUp) map.mapOrientation = 0f
            }
            4 -> downloadArea()
            5 -> askCruise()
            6 -> MaterialAlertDialogBuilder(this)
                .setMessage(R.string.map_clear_confirm)
                .setPositiveButton(R.string.delete) { _, _ ->
                    val removed = draw.marks.withIndex().map { it.index to it.value }
                    draw.marks.clear()
                    undo.addLast(AnnotatedPageView.Edit.Removed(removed))
                    saveDrawings()
                }
                .setNegativeButton(R.string.cancel, null)
                .show()
            else -> return super.onOptionsItemSelected(item)
        }
        return true
    }

    private fun askCruise() {
        val input = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_NUMBER
            setText(draw.cruiseKt.toInt().toString())
        }
        val box = FrameLayout(this).apply {
            setPadding(dp(20), dp(8), dp(20), 0)
            addView(input)
        }
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.map_aircraft)
            .setMessage("Evektor SportStar ≈ 100 kt · Cessna 172 ≈ 110 kt\n" + getString(R.string.map_cruise))
            .setView(box)
            .setPositiveButton(R.string.ok) { _, _ ->
                input.text.toString().toIntOrNull()?.takeIf { it in 30..400 }?.let {
                    draw.cruiseKt = it.toDouble()
                    prefs.edit().putFloat("cruise_kt", it.toFloat()).apply()
                    map.invalidate()
                }
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    /** Saves the charts of the area on screen, down to the chart's finest scale, for flying offline. */
    private fun downloadArea() {
        val bb = map.boundingBox
        val zMin = map.zoomLevelDouble.toInt().coerceIn(4, layer.maxZoom)
        val zMax = layer.maxZoom.coerceAtMost(zMin + 4)
        val cm = CacheManager(map)
        val count = cm.possibleTilesInArea(bb, zMin, zMax)
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.map_download)
            .setMessage(getString(R.string.map_download_msg, count, getString(layer.label), (count * 25 / 1024).coerceAtLeast(1)))
            .setPositiveButton(R.string.map_download_go) { _, _ ->
                cm.downloadAreaAsync(this, bb, zMin, zMax, object : CacheManager.CacheManagerCallback {
                    override fun onTaskComplete() {
                        Toast.makeText(this@MapActivity, R.string.map_download_done, Toast.LENGTH_LONG).show()
                    }
                    override fun updateProgress(progress: Int, currentZoomLevel: Int, zoomMin: Int, zoomMax: Int) {}
                    override fun downloadStarted() {}
                    override fun setPossibleTilesInArea(total: Int) {}
                    override fun onTaskFailed(errors: Int) {
                        Toast.makeText(this@MapActivity, getString(R.string.map_download_fail, errors), Toast.LENGTH_LONG).show()
                    }
                })
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }
}
