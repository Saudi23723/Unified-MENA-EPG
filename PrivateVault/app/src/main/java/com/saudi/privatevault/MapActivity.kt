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
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.CustomZoomButtonsController
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.ScaleBarOverlay
import org.osmdroid.events.MapEventsReceiver
import org.osmdroid.tileprovider.MapTileProviderBasic
import org.osmdroid.views.overlay.MapEventsOverlay
import org.osmdroid.views.overlay.TilesOverlay
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
    private lateinit var ownship: OwnshipOverlay
    private lateinit var weather: WeatherOverlay
    private lateinit var route: RouteOverlay
    private var radar: TilesOverlay? = null
    private var radarProvider: MapTileProviderBasic? = null
    private var plan = FlightPlan()
    private var airports: List<AviationData.Airport> = emptyList()
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
            // More tiles at once, so the chart fills in quickly.
            setTileDownloadThreads(8.toShort())
            setTileFileSystemThreads(8.toShort())
            setCacheMapTileCount(64.toShort())
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
        // Past a chart's finest scale the tiles are enlarged, so it zooms in as far as wanted.
        map.maxZoomLevel = 20.0
        map.isTilesScaledToDpi = !prefs.getBoolean("map_sharp", false)
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
        // A long press on the chart: fly direct there, or add it to the route.
        map.overlays.add(MapEventsOverlay(object : MapEventsReceiver {
            override fun singleTapConfirmedHelper(p: GeoPoint?): Boolean = false
            override fun longPressHelper(p: GeoPoint?): Boolean {
                if (p == null || draw.tool != MapDrawOverlay.MapTool.PAN) return false
                pointMenu(p)
                return true
            }
        }))
        weather = WeatherOverlay(map).apply {
            showAirmets = prefs.getBoolean("wx_airmet", true)
            showTfrs = prefs.getBoolean("wx_tfr", true)
            showPireps = prefs.getBoolean("wx_pirep", false)
            onPick = { texts ->
                MaterialAlertDialogBuilder(this@MapActivity)
                    .setMessage(texts.joinToString("\n\n────────\n\n"))
                    .setPositiveButton(android.R.string.ok, null)
                    .show()
            }
        }
        map.overlays.add(weather)
        plan = FlightPlan.load(this)
        route = RouteOverlay(map, { plan }, { if (::ownship.isInitialized) ownship.position() else null })
        map.overlays.add(route)
        airportsLayer = AirportsOverlay(map).apply { onPick = { showAirport(it) } }
        map.overlays.add(airportsLayer)
        draw = MapDrawOverlay(map)
        draw.cruiseKt = prefs.getFloat("cruise_kt", 100f).toDouble()
        draw.showMeasures = prefs.getBoolean("map_measures", true)
        map.overlays.add(draw)
        ownship = OwnshipOverlay(map, airplane()).apply { onUserPan = { if (following) follow() } }
        map.overlays.add(ownship)

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
        b.zoomIn.setOnClickListener { map.controller.zoomIn() }
        b.zoomOut.setOnClickListener { map.controller.zoomOut() }
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
        if (prefs.getBoolean("wx_radar", false)) setRadar(true)
        refreshWeather()
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
        b.root.removeCallbacks(frame)
        b.root.post(frame)
        b.root.removeCallbacks(weatherTimer)
        b.root.postDelayed(weatherTimer, 5 * 60000L)
    }

    override fun onPause() {
        super.onPause()
        map.onPause()
        b.root.removeCallbacks(frame)
        b.root.removeCallbacks(weatherTimer)
        plan.save(this)
        val c = map.mapCenter
        prefs.edit().putFloat("map_lat", c.latitude.toFloat()).putFloat("map_lon", c.longitude.toFloat())
            .putFloat("map_zoom", map.zoomLevelDouble.toFloat()).apply()
        pushDrawings()
    }

    override fun onDestroy() {
        super.onDestroy()
        stopGps()
        radarProvider?.detach()
        map.onDetach()
    }

    // ---- layers, airports and weather ----

    /** The chart underneath, and what is drawn over it. */
    private fun chooseLayer() {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(8), dp(20), 0)
        }
        val group = android.widget.RadioGroup(this)
        for ((i, l) in AviationData.LAYERS.withIndex()) {
            group.addView(android.widget.RadioButton(this).apply {
                id = 1000 + i
                text = getString(l.label)
                isChecked = l == layer
            })
        }
        box.addView(group)
        box.addView(android.widget.TextView(this).apply {
            text = getString(R.string.map_overlays)
            setPadding(0, dp(14), 0, dp(4))
            setTypeface(typeface, android.graphics.Typeface.BOLD)
        })
        fun check(label: Int, on: Boolean) = android.widget.CheckBox(this).apply {
            text = getString(label)
            isChecked = on
            box.addView(this)
        }
        val cRadar = check(R.string.wx_radar, radar != null)
        val cAirmet = check(R.string.wx_airmet, weather.showAirmets)
        val cTfr = check(R.string.wx_tfr, weather.showTfrs)
        val cPirep = check(R.string.wx_pirep, weather.showPireps)
        val cAirports = check(R.string.map_airports, prefs.getBoolean("map_airports", true))
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.map_layers)
            .setView(android.widget.ScrollView(this).apply { addView(box) })
            .setPositiveButton(R.string.ok) { _, _ ->
                val chosen = AviationData.LAYERS.getOrNull(group.checkedRadioButtonId - 1000) ?: layer
                if (chosen != layer) {
                    layer = chosen
                    prefs.edit().putString("map_layer", layer.key).apply()
                    map.setTileSource(layer.source())
                }
                if (cRadar.isChecked != (radar != null)) setRadar(cRadar.isChecked)
                weather.showAirmets = cAirmet.isChecked
                weather.showTfrs = cTfr.isChecked
                weather.showPireps = cPirep.isChecked
                val airportsOn = cAirports.isChecked
                val airportsChanged = airportsOn != prefs.getBoolean("map_airports", true)
                prefs.edit().putBoolean("wx_radar", cRadar.isChecked).putBoolean("wx_airmet", cAirmet.isChecked)
                    .putBoolean("wx_tfr", cTfr.isChecked).putBoolean("wx_pirep", cPirep.isChecked)
                    .putBoolean("map_airports", airportsOn).apply()
                if (airportsChanged) {
                    lastWeatherBox = ""
                    loadAirports()
                }
                refreshWeather()
                map.invalidate()
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    // ---- weather over the chart ----

    private val weatherTimer: Runnable = object : Runnable {
        override fun run() {
            if (radar != null) { setRadar(false); setRadar(true) }
            lastWeatherBox = ""
            refreshWeather()
            idle()
            b.root.postDelayed(this, 5 * 60000L)
        }
    }

    /** NEXRAD radar, see-through over the chart, just above it. */
    private fun setRadar(on: Boolean) {
        radar?.let { map.overlays.remove(it) }
        radarProvider?.detach()
        radar = null
        radarProvider = null
        if (on) {
            val provider = MapTileProviderBasic(applicationContext, AviationData.radarSource())
            radarProvider = provider
            radar = TilesOverlay(provider, this).apply {
                setLoadingBackgroundColor(android.graphics.Color.TRANSPARENT)
                setLoadingLineColor(android.graphics.Color.TRANSPARENT)
                setColorFilter(android.graphics.ColorMatrixColorFilter(android.graphics.ColorMatrix(floatArrayOf(
                    1f, 0f, 0f, 0f, 0f, 0f, 1f, 0f, 0f, 0f, 0f, 0f, 1f, 0f, 0f, 0f, 0f, 0f, 0.7f, 0f,
                ))))
            }
            provider.setTileRequestCompleteHandler(map.tileRequestCompleteHandler)
            map.overlays.add(0, radar)
        }
        map.invalidate()
    }

    private fun refreshWeather() {
        lifecycleScope.launch {
            if (weather.showAirmets) {
                val list = withContext(Dispatchers.IO) { AviationData.airspaceWeather() }
                if (list.isNotEmpty() || weather.areas.isEmpty()) weather.areas = list
            }
            if (weather.showTfrs) {
                val list = withContext(Dispatchers.IO) { AviationData.tfrs() }
                if (list.isNotEmpty()) weather.tfrs = list
            }
            map.invalidate()
        }
    }

    private fun loadAirports() {
        lifecycleScope.launch {
            val list = withContext(Dispatchers.IO) { AviationData.airports(this@MapActivity) }
            airports = list
            airportsLayer.airports = if (prefs.getBoolean("map_airports", true)) list else emptyList()
            draw.snapTo = list
            map.invalidate()
            idle()
        }
    }

    private var lastWeatherBox = ""

    /** After the map settles: the weather of the airports in view. */
    private fun idle(): Boolean {
        overzoom()
        if (map.zoomLevelDouble < 7) return true
        val bb = map.boundingBox
        val key = "%.1f,%.1f,%.1f,%.1f".format(bb.latSouth, bb.lonWest, bb.latNorth, bb.lonEast)
        if (key == lastWeatherBox) return true
        lastWeatherBox = key
        if (weather.showPireps) lifecycleScope.launch {
            val list = withContext(Dispatchers.IO) { AviationData.pireps(bb.latSouth - 1, bb.lonWest - 1, bb.latNorth + 1, bb.lonEast + 1) }
            weather.pireps = list
            map.invalidate()
        }
        if (!prefs.getBoolean("map_airports", true)) return true
        lifecycleScope.launch {
            val list = withContext(Dispatchers.IO) { AviationData.metars(bb.latSouth, bb.lonWest, bb.latNorth, bb.lonEast) }
            if (list.isNotEmpty()) {
                airportsLayer.weather = airportsLayer.weather + list.associateBy { it.station }
                map.invalidate()
            }
        }
        return true
    }

    private var overzoomBox = ""

    /**
     * Zoomed in past the chart's finest scale: the tiles of that scale are
     * fetched for the view, and enlarged from there.
     */
    private fun overzoom() {
        val z = layer.maxZoom
        if (map.zoomLevelDouble <= z) return
        val bb = map.boundingBox
        val key = "${layer.key}%.2f,%.2f,%.2f,%.2f".format(bb.latSouth, bb.lonWest, bb.latNorth, bb.lonEast)
        if (key == overzoomBox) return
        overzoomBox = key
        try {
            val cm = CacheManager(map)
            if (cm.possibleTilesInArea(bb, z, z) > 200) return
            cm.downloadAreaAsyncNoUI(this, bb, z, z, object : CacheManager.CacheManagerCallback {
                override fun onTaskComplete() {
                    map.tileProvider.clearTileCache()
                    map.invalidate()
                }
                override fun updateProgress(progress: Int, currentZoomLevel: Int, zoomMin: Int, zoomMax: Int) {}
                override fun downloadStarted() {}
                override fun setPossibleTilesInArea(total: Int) {}
                override fun onTaskFailed(errors: Int) {
                    map.tileProvider.clearTileCache()
                    map.invalidate()
                }
            })
        } catch (e: Exception) {
        }
    }

    private fun showAirport(a: AviationData.Airport) {
        val wp = FlightPlan.Waypoint(a.icao.ifEmpty { a.ident }, a.lat, a.lon)
        AirportSheet(this, a, airportsLayer.station(a), ownship.position() ?: map.mapCenter as GeoPoint,
            onDirect = { directTo(wp) },
            onAddToRoute = { addToRoute(wp) },
        ).show()
    }

    // ---- the route ----

    private fun directTo(w: FlightPlan.Waypoint) {
        plan.direct = w
        plan.save(this)
        updateNav()
        map.invalidate()
        Toast.makeText(this, "→ ${w.id}", Toast.LENGTH_SHORT).show()
    }

    private fun addToRoute(w: FlightPlan.Waypoint) {
        plan.points.add(w)
        plan.save(this)
        updateNav()
        map.invalidate()
        Toast.makeText(this, getString(R.string.plan_added, w.id, plan.points.size), Toast.LENGTH_SHORT).show()
    }

    private fun pointMenu(g: GeoPoint) {
        val n = plan.points.count { it.id.startsWith("WP") } + 1
        val wp = FlightPlan.Waypoint("WP$n", g.latitude, g.longitude)
        val from = ownship.position()
        val where = "%.4f, %.4f".format(g.latitude, g.longitude) + (from?.let {
            "\n${Nav.deg(Nav.magnetic(Nav.bearingTrue(it.latitude, it.longitude, g.latitude, g.longitude), it.latitude, it.longitude))}M · %.1f nm"
                .format(Nav.distanceNm(it.latitude, it.longitude, g.latitude, g.longitude))
        } ?: "")
        MaterialAlertDialogBuilder(this)
            .setTitle(where)
            .setItems(arrayOf(getString(R.string.apt_direct), getString(R.string.apt_add_route))) { _, i ->
                if (i == 0) directTo(wp) else addToRoute(wp)
            }
            .show()
    }

    private fun findWaypoint(token: String): FlightPlan.Waypoint? {
        val t = token.trim().uppercase()
        if (t.isEmpty()) return null
        Regex("^(-?\\d+(?:\\.\\d+)?)[,/](-?\\d+(?:\\.\\d+)?)$").find(t)?.let { m ->
            return FlightPlan.Waypoint("WP", m.groupValues[1].toDouble(), m.groupValues[2].toDouble())
        }
        val a = airports.firstOrNull { it.icao == t || it.ident == t }
            ?: airports.firstOrNull { t.length == 4 && t.startsWith("K") && it.ident == t.substring(1) }
            ?: plan.points.firstOrNull { it.id == t }?.let { return it }
            ?: return null
        return FlightPlan.Waypoint(a.icao.ifEmpty { a.ident }, a.lat, a.lon)
    }

    /** The nav log of the route, and the flight's settings. */
    private fun navLog() {
        val text = android.widget.TextView(this).apply {
            typeface = android.graphics.Typeface.MONOSPACE
            textSize = 12f
            setTextIsSelectable(true)
            layoutDirection = View.LAYOUT_DIRECTION_LTR
            textDirection = View.TEXT_DIRECTION_LTR
            setPadding(dp(16), dp(8), dp(16), dp(8))
            this.text = if (plan.points.size < 2) getString(R.string.plan_empty) else
                plan.points.joinToString(" ") { it.id } + "\n\n" + plan.navLog()
        }
        val scroll = android.widget.ScrollView(this).apply {
            addView(android.widget.HorizontalScrollView(this@MapActivity).apply { addView(text) })
        }
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.plan_title)
            .setView(scroll)
            .setPositiveButton(R.string.plan_edit) { _, _ -> editPlan() }
            .setNeutralButton(R.string.plan_more) { _, _ ->
                val opts = arrayOf(getString(R.string.plan_reverse), getString(R.string.plan_clear), getString(R.string.plan_share),
                    getString(R.string.plan_cancel_direct), getString(R.string.wb_title))
                MaterialAlertDialogBuilder(this).setItems(opts) { _, i ->
                    when (i) {
                        0 -> { plan.points.reverse(); plan.active = 1 }
                        1 -> { plan.points.clear(); plan.direct = null; plan.active = 1 }
                        2 -> startActivity(android.content.Intent.createChooser(android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                            type = "text/plain"
                            putExtra(android.content.Intent.EXTRA_TEXT, plan.points.joinToString(" ") { it.id } + "\n\n" + plan.navLog())
                        }, null))
                        3 -> plan.direct = null
                        4 -> openWb()
                    }
                    plan.save(this)
                    updateNav()
                    map.invalidate()
                }.show()
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun openWb() {
        val burn = plan.legs().sumOf { it.fuel }
        startActivity(android.content.Intent(this, WeightBalanceActivity::class.java).putExtra(WeightBalanceActivity.EXTRA_BURN, burn))
    }

    private fun editPlan() {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(8), dp(20), 0)
            layoutDirection = View.LAYOUT_DIRECTION_LTR
        }
        fun field(label: Int, value: String, number: Boolean = true): EditText {
            box.addView(android.widget.TextView(this).apply { text = getString(label); setPadding(0, dp(8), 0, 0) })
            return EditText(this).apply {
                inputType = if (number) InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
                    else InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS
                setText(value)
                box.addView(this)
            }
        }
        val routeField = field(R.string.plan_route, plan.points.joinToString(" ") { it.id }, number = false)
        val alt = field(R.string.plan_alt, plan.altitude.toString())
        val tas = field(R.string.plan_tas, plan.tas.toString())
        val gph = field(R.string.plan_gph, plan.gph.toString())
        val fob = field(R.string.plan_fob, plan.fuelOnBoard.toString())
        val wind = field(R.string.plan_wind, "%03d/%d".format(plan.windDir, plan.windKt), number = false)
        val auto = com.google.android.material.button.MaterialButton(this).apply {
            text = getString(R.string.plan_wind_auto)
            isAllCaps = false
            setOnClickListener {
                val pts = plan.points.ifEmpty { listOf(FlightPlan.Waypoint("C", map.mapCenter.latitude, map.mapCenter.longitude)) }
                val lat = pts.sumOf { it.lat } / pts.size
                val lon = pts.sumOf { it.lon } / pts.size
                val altFt = alt.text.toString().toIntOrNull() ?: plan.altitude
                lifecycleScope.launch {
                    val text = withContext(Dispatchers.IO) { AviationData.windsAloft() }
                    val w = AviationData.windAt(text, lat, lon, altFt)
                    if (w == null) Toast.makeText(this@MapActivity, R.string.plan_wind_fail, Toast.LENGTH_LONG).show()
                    else wind.setText("%03d/%d".format(w.first, w.second))
                }
            }
        }
        box.addView(auto)
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.plan_edit)
            .setView(android.widget.ScrollView(this).apply { addView(box) })
            .setPositiveButton(R.string.ok) { _, _ ->
                val tokens = routeField.text.toString().split(Regex("[\\s,]+")).filter { it.isNotBlank() }
                val pts = ArrayList<FlightPlan.Waypoint>()
                val unknown = ArrayList<String>()
                for (t in tokens) findWaypoint(t)?.let { pts.add(if (it.id == "WP") FlightPlan.Waypoint("WP${pts.size + 1}", it.lat, it.lon) else it) } ?: unknown.add(t)
                plan.points.clear()
                plan.points.addAll(pts)
                plan.active = 1
                alt.text.toString().toIntOrNull()?.let { plan.altitude = it }
                tas.text.toString().toIntOrNull()?.takeIf { it in 30..400 }?.let { plan.tas = it }
                gph.text.toString().toDoubleOrNull()?.let { plan.gph = it }
                fob.text.toString().toDoubleOrNull()?.let { plan.fuelOnBoard = it }
                wind.text.toString().split('/', ' ', '@').mapNotNull { it.trim().toIntOrNull() }.let {
                    if (it.size >= 2) { plan.windDir = it[0] % 361; plan.windKt = it[1] }
                }
                plan.save(this)
                updateNav()
                map.invalidate()
                if (unknown.isNotEmpty()) Toast.makeText(this, getString(R.string.plan_unknown, unknown.joinToString(" ")), Toast.LENGTH_LONG).show()
                navLog()
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    /** The second HUD line: the waypoint ahead, its bearing, distance, time and ETA. */
    private fun updateNav() {
        val t = plan.target()
        val here = ownship.position()
        if (t == null || here == null) {
            b.hudNav.visibility = if (t != null) View.VISIBLE else View.GONE
            if (t != null) b.hudNav.text = "→ ${t.id}"
            return
        }
        val dist = Nav.distanceNm(here.latitude, here.longitude, t.lat, t.lon)
        val brg = Nav.magnetic(Nav.bearingTrue(here.latitude, here.longitude, t.lat, t.lon), here.latitude, here.longitude)
        val gs = ownship.speedKt()
        val ete = if (gs > 20) dist / gs * 60 else Double.NaN
        val eta = if (ete.isNaN()) "--:--" else java.text.SimpleDateFormat("HH:mm", java.util.Locale.US)
            .format(java.util.Date(System.currentTimeMillis() + (ete * 60000).toLong()))
        b.hudNav.text = "→ %s  BRG %sM  %.1f nm  ETE %s  ETA %s".format(t.id, Nav.deg(brg), dist,
            if (ete.isNaN()) "--:--" else FlightPlan.hm(ete), eta)
        b.hudNav.visibility = View.VISIBLE
    }

    // ---- the aircraft ----

    private fun askGps() {
        val fine = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        if (fine) startGps()
        else locationPermission.launch(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION))
    }

    private var lm: LocationManager? = null
    private var gotGps = false
    private var lastAlt = Double.NaN
    private var lastAltAt = 0L
    private var vs = 0.0
    private val listener = LocationListener { l -> onFix(l) }
    private val coarse = LocationListener { l -> if (!gotGps) onFix(l) }
    private var satellites: Any? = null

    @SuppressLint("MissingPermission")
    private fun startGps() {
        lm = getSystemService(LocationManager::class.java)
        val m = lm ?: return
        b.hud.visibility = View.VISIBLE
        b.hudGs.text = getString(R.string.map_no_gps)
        // Show the last known position at once, then the network's rough one, until the GPS locks.
        listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER, LocationManager.PASSIVE_PROVIDER)
            .mapNotNull { p -> try { m.getLastKnownLocation(p) } catch (e: Exception) { null } }
            .maxByOrNull { it.time }
            ?.takeIf { System.currentTimeMillis() - it.time < 10 * 60000 }
            ?.let { onFix(it, quiet = true) }
        try {
            m.requestLocationUpdates(LocationManager.GPS_PROVIDER, 0L, 0f, listener, mainLooper)
        } catch (e: Exception) {
        }
        try {
            m.requestLocationUpdates(LocationManager.NETWORK_PROVIDER, 2000L, 0f, coarse, mainLooper)
        } catch (e: Exception) {
        }
        try {
            val cb = object : android.location.GnssStatus.Callback() {
                override fun onSatelliteStatusChanged(status: android.location.GnssStatus) {
                    var used = 0
                    for (k in 0 until status.satelliteCount) if (status.usedInFix(k)) used++
                    val acc = ownship.fix?.takeIf { it.hasAccuracy() && gotGps }?.accuracy
                    b.hudGps.text = "GPS $used" + (acc?.let { "\n±%d m".format(Math.round(it)) } ?: "")
                }
            }
            m.registerGnssStatusCallback(cb, android.os.Handler(mainLooper))
            satellites = cb
        } catch (e: Exception) {
        }
    }

    private fun stopGps() {
        try {
            lm?.removeUpdates(listener)
            lm?.removeUpdates(coarse)
            (satellites as? android.location.GnssStatus.Callback)?.let { lm?.unregisterGnssStatusCallback(it) }
        } catch (e: Exception) {
        }
    }

    /** Ground speed in knots, track in degrees magnetic, altitude in feet MSL, vertical speed in feet per minute. */
    private fun onFix(l: Location, quiet: Boolean = false) {
        if (l.provider == LocationManager.GPS_PROVIDER && !quiet) {
            if (!gotGps) {
                gotGps = true
                try { lm?.removeUpdates(coarse) } catch (e: Exception) {}
            }
        }
        ownship.update(l)
        val kt = if (l.hasSpeed()) l.speed * 1.943844 else 0.0
        b.hudGs.text = if (gotGps) "GS %d".format(Math.round(kt)) else getString(R.string.map_no_gps)
        b.hudTrk.text = if (l.hasBearing() && kt > 5) Nav.deg(Nav.magnetic(l.bearing.toDouble(), l.latitude, l.longitude)) + "M" else "---°"
        b.hudAlt.text = if (l.hasAltitude() && gotGps) "%,d ft".format(Math.round(l.altitude * 3.28084)) else "--- ft"
        if (l.hasAltitude() && gotGps) {
            val now = android.os.SystemClock.elapsedRealtime()
            val ft = l.altitude * 3.28084
            if (!lastAlt.isNaN() && now > lastAltAt) {
                val rate = (ft - lastAlt) / ((now - lastAltAt) / 60000.0)
                vs = vs * 0.7 + rate.coerceIn(-6000.0, 6000.0) * 0.3
            }
            lastAlt = ft
            lastAltAt = now
            b.hudVs.text = "%+d".format((Math.round(vs / 50) * 50).toInt())
        } else {
            b.hudVs.text = "VS"
        }
        if (!gotGps) b.hudGps.text = "GPS…"
        if (plan.sequence(l.latitude, l.longitude)) {
            plan.save(this)
            map.invalidate()
        }
        updateNav()
        if (following && quiet) map.controller.setCenter(GeoPoint(l.latitude, l.longitude))
    }

    /** About 30 times a second: the aircraft glides between fixes, and the map follows it smoothly. */
    private val frame: Runnable = object : Runnable {
        private var heading = Float.NaN
        private var lastIdle = 0L
        override fun run() {
            // While the map keeps following, it never settles: refresh what is in view every 15 s.
            val now = android.os.SystemClock.elapsedRealtime()
            if (following && now - lastIdle > 15000) {
                lastIdle = now
                idle()
            }
            val fix = ownship.fix
            val moving = ownship.speedKt() > 3
            if (fix != null) {
                if (following) {
                    ownship.position()?.let { map.controller.setCenter(it) }
                    if (trackUp && fix.hasBearing() && moving) {
                        // Turn the chart gently towards the track instead of snapping.
                        val want = fix.bearing
                        heading = if (heading.isNaN()) want else heading + (((want - heading + 540) % 360) - 180) * 0.15f
                        map.mapOrientation = -heading
                    }
                } else if (moving) {
                    map.invalidate()
                }
            }
            b.root.postDelayed(this, if (moving || following) 33L else 250L)
        }
    }

    private fun follow() {
        following = !following
        ownship.position()?.let { if (following) map.controller.animateTo(it) }
        if (following && map.zoomLevelDouble < 9) map.controller.setZoom(10.0)
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
        val tools = listOf(
            Triple(MapDrawOverlay.MapTool.PAN, R.drawable.ic_tool_hand, R.string.pen_hand),
            Triple(MapDrawOverlay.MapTool.RULER, R.drawable.ic_ruler, R.string.map_ruler),
            Triple(MapDrawOverlay.MapTool.SELECT, R.drawable.ic_tool_select, R.string.pen_select),
            Triple(MapDrawOverlay.MapTool.PEN, R.drawable.ic_tool_pen, R.string.pen_pen),
            Triple(MapDrawOverlay.MapTool.LINE, R.drawable.ic_tool_line, R.string.pen_line),
            Triple(MapDrawOverlay.MapTool.ARROW, R.drawable.ic_tool_arrow, R.string.pen_arrow),
            Triple(MapDrawOverlay.MapTool.CIRCLE, R.drawable.ic_tool_oval, R.string.map_circle),
            Triple(MapDrawOverlay.MapTool.RECT, R.drawable.ic_tool_rect, R.string.pen_rect),
            Triple(MapDrawOverlay.MapTool.TEXT, R.drawable.ic_tool_text, R.string.pen_text),
            Triple(MapDrawOverlay.MapTool.ERASER, R.drawable.ic_tool_eraser, R.string.pen_eraser),
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
        pick(MapDrawOverlay.MapTool.PAN)
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
        menu.add(0, 10, 0, R.string.plan_title)
        menu.add(0, 11, 0, R.string.map_find)
        menu.add(0, 12, 0, R.string.wb_title)
        menu.add(0, 13, 0, R.string.wx_winds)
        menu.add(0, 14, 0, R.string.map_sharp).setCheckable(true).isChecked = prefs.getBoolean("map_sharp", false)
        menu.add(0, 15, 0, R.string.map_clear_trail)
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
            10 -> navLog()
            11 -> findAirport()
            12 -> openWb()
            13 -> windsAloft()
            14 -> {
                val on = !item.isChecked
                item.isChecked = on
                prefs.edit().putBoolean("map_sharp", on).apply()
                map.isTilesScaledToDpi = !on
                map.invalidate()
            }
            15 -> { ownship.clearTrail(); map.invalidate() }
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

    private fun findAirport() {
        val input = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS
            hint = "KBVU"
        }
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.map_find)
            .setView(FrameLayout(this).apply { setPadding(dp(20), dp(8), dp(20), 0); addView(input) })
            .setPositiveButton(R.string.ok) { _, _ ->
                val t = input.text.toString().trim().uppercase()
                val a = airports.firstOrNull { it.icao == t || it.ident == t }
                    ?: airports.firstOrNull { t.length == 4 && t.startsWith("K") && it.ident == t.substring(1) }
                    ?: airports.firstOrNull { it.name.contains(t) || it.city.contains(t) }
                if (a == null) {
                    Toast.makeText(this, R.string.map_not_found, Toast.LENGTH_SHORT).show()
                    return@setPositiveButton
                }
                if (following) follow()
                map.controller.setZoom(11.0)
                map.controller.setCenter(GeoPoint(a.lat, a.lon))
                showAirport(a)
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun windsAloft() {
        val text = android.widget.TextView(this).apply {
            typeface = android.graphics.Typeface.MONOSPACE
            textSize = 11f
            setTextIsSelectable(true)
            layoutDirection = View.LAYOUT_DIRECTION_LTR
            textDirection = View.TEXT_DIRECTION_LTR
            setPadding(dp(12), dp(8), dp(12), dp(8))
            this.text = getString(R.string.map_loading_wx)
        }
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.wx_winds)
            .setView(android.widget.ScrollView(this).apply { addView(android.widget.HorizontalScrollView(this@MapActivity).apply { addView(text) }) })
            .setPositiveButton(android.R.string.ok, null)
            .show()
        lifecycleScope.launch {
            val t = withContext(Dispatchers.IO) { AviationData.windsAloft() }
            text.text = t.ifEmpty { getString(R.string.plan_wind_fail) }
        }
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
                    plan.tas = it
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
