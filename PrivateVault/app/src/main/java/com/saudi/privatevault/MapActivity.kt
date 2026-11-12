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
import android.os.Build
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
import android.widget.TextView
import android.view.Gravity
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
class MapActivity : BaseActivity(), NeonHost {
    override val alwaysDark = true

    private lateinit var b: ActivityMapBinding
    private lateinit var map: MapView
    private lateinit var draw: MapDrawOverlay
    private lateinit var airportsLayer: AirportsOverlay
    private lateinit var ownship: OwnshipOverlay
    private lateinit var weather: WeatherOverlay
    private lateinit var rings: RangeRingsOverlay
    private lateinit var insetOv: DiagramInsetOverlay
    private lateinit var procOv: ProcedureOverlay
    private lateinit var route: RouteOverlay
    private var radar: RadarOverlay? = null
    private lateinit var hazard: HazardOverlay
    private lateinit var airspace: AirspaceOverlay
    private lateinit var patternOv: PatternOverlay
    private var patternFor = ""
    private lateinit var traffic: TrafficOverlay
    private var radarProvider: MapTileProviderBasic? = null
    private var plan = FlightPlan()
    private var airports: List<AviationData.Airport> = emptyList()
    private var layer = AviationData.LAYERS[0]
    private var following = false
    private lateinit var strip: InstrumentStrip
    private var trackUp = false
    /** Track up with the aircraft low on the screen, the chart ahead of it (ForeFlight's "Track Up Forward"). */
    private var ahead = false
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
        CrashReport.showIfAny(this)
        ChartUpdates.autoUpdate(this)
        setContentView(b.root)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setSupportActionBar(b.toolbar)
        b.toolbar.setNavigationOnClickListener { finish() }
        cockpitLook()

        layer = AviationData.LAYERS.firstOrNull { it.key == prefs.getString("map_layer", "sectional") } ?: AviationData.LAYERS[0]
        // The chart at its printed sharpness: one chart pixel to one screen pixel, enlarged smoothly past that.
        map = MapView(this, SmoothTileProvider(applicationContext, layer.source()))
        b.mapHolder.addView(map, FrameLayout.LayoutParams(-1, -1))
        map.setMultiTouchControls(true)
        map.zoomController.setVisibility(CustomZoomButtonsController.Visibility.NEVER)
        map.minZoomLevel = 5.0
        map.isTilesScaledToDpi = prefs.getBoolean("map_big", false)
        zoomLimit()
        map.overlayManager.tilesOverlay.setLoadingBackgroundColor(0xFFEDE8DA.toInt())
        map.overlayManager.tilesOverlay.setLoadingLineColor(0xFFEDE8DA.toInt())

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
                // On a TFR: NORAD's three keys (Plan, Talk, Squawk).
                val tfr = texts.any { it.contains("TFR", true) }
                MaterialAlertDialogBuilder(this@MapActivity)
                    .setMessage(texts.joinToString("\n\n────────\n\n") + if (tfr) "\n\n────────\n\n" + getString(R.string.tfr_keys) else "")
                    .setPositiveButton(android.R.string.ok, null)
                    .show()
            }
        }
        // Terrain awareness under everything else drawn on the chart.
        Terrain.init(this)
        Voice.init(this)
        hazard = HazardOverlay(map).apply { altitudeFt = prefs.getInt("hazard_alt", 5500).toDouble() }
        if (prefs.getBoolean("wx_terrain", false)) map.overlays.add(hazard)
        airspace = AirspaceOverlay(map).apply {
            onPick = { texts -> MaterialAlertDialogBuilder(this@MapActivity).setMessage(texts.joinToString("\n\n")).setPositiveButton(android.R.string.ok, null).show() }
        }
        if (prefs.getBoolean("wx_airspace", true)) map.overlays.add(airspace)
        lifecycleScope.launch { withContext(Dispatchers.IO) { try { Airspace.load(this@MapActivity) } catch (e: Throwable) {} }; map.invalidate() }
        map.overlays.add(weather)
        plan = FlightPlan.load(this)
        route = RouteOverlay(map, { plan }, { if (::ownship.isInitialized) ownship.position() else null })
        map.overlays.add(route)
        patternOv = PatternOverlay(map)
        if (prefs.getBoolean("tp_on", true)) map.overlays.add(patternOv)
        airportsLayer = AirportsOverlay(map).apply { onPick = { showAirport(it) } }
        setStationData(AirportsOverlay.Data.values().firstOrNull { it.name == prefs.getString("map_data", "NONE") } ?: AirportsOverlay.Data.NONE, prefs.getInt("winds_alt", 6000))
        map.overlays.add(airportsLayer)
        draw = MapDrawOverlay(map)
        draw.cruiseKt = prefs.getFloat("cruise_kt", 100f).toDouble()
        draw.showMeasures = prefs.getBoolean("map_measures", true)
        map.overlays.add(draw)
        ownship = OwnshipOverlay(map, airplane()).apply { onUserPan = { if (following) follow() } }
        glide = GlideRing(map, { if (gotGps) ownship.position() else null }, { if (lastAlt.isNaN()) null else lastAlt })
        glide.ratio = prefs.getString("glide_ratio", "")?.toDoubleOrNull() ?: 0.0
        map.overlays.add(glide)
        map.overlays.add(ownship)
        traffic = TrafficOverlay(map) { ownship.fix?.takeIf { it.hasAltitude() && gotGps }?.altitude?.times(3.28084) }.apply {
            near = { t -> trafficClose(t) != null }
            onTap = { t -> targetCard(t) }
        }
        // Traffic on from the start, as ForeFlight shows it: online ADS-B near you, and a Stratux / Sentry when connected.
        if (prefs.getBoolean("wx_traffic", true)) { map.overlays.add(traffic); Traffic.startReceiver() }

        marks = DocumentMarks.forItem(this, "flight-map")
        draw.marks.addAll(marks.on(0))
        setUpPen()
        pullDrawings()

        map.addMapListener(DelayedMapListener(object : MapListener {
            override fun onScroll(event: ScrollEvent?): Boolean { autoDiagrams(); return idle() }
            override fun onZoom(event: ZoomEvent?): Boolean { autoDiagrams(); return idle() }
        }, 900))

        // The instrument strip in place of the four plain readouts.
        for (i in 0 until b.hud.childCount) b.hud.getChildAt(i).visibility = View.GONE
        strip = InstrumentStrip(this)
        b.hud.visibility = View.GONE
        b.fabLayers.setOnClickListener { chooseLayer() }
        b.fabDraw.setOnClickListener { toggleDrawing() }
        styleControls()
        foreflightLayout()
        b.root.post { wxBar() }
        // Range rings around the aircraft, on and off from the menu.
        rings = RangeRingsOverlay(map) { if (gotGps) ownship.position() else null }
        if (prefs.getBoolean("rings", true)) map.overlays.add(rings)
        // The diagram as a big card beside its field at any zoom; a tap on it goes there.
        insetOv = DiagramInsetOverlay(map) { ins -> showCard(ins) }
        map.overlays.add(insetOv)
        buildCard()
        procOv = ProcedureOverlay(map)
        map.overlays.add(map.overlays.indexOf(insetOv).coerceAtLeast(0), procOv)
        b.root.postDelayed({ autoDiagrams() }, 2500)
        b.fabLocate.setOnClickListener { cycleView() }
        b.fabSos.setOnClickListener { emergency() }
        b.zoomIn.setOnClickListener {
            if (map.zoomLevelDouble >= map.maxZoomLevel - 0.05) Toast.makeText(this, R.string.map_max_zoom, Toast.LENGTH_SHORT).show()
            map.controller.zoomIn()
        }
        // Two fingers turn the chart; a long press on the position button puts north back up.
        map.overlays.add(org.osmdroid.views.overlay.gestures.RotationGestureOverlay(map).apply { isEnabled = true })
        b.fabLocate.setOnLongClickListener {
            trackUp = false; ahead = false
            map.mapOrientation = 0f
            Toast.makeText(this, "N↑", Toast.LENGTH_SHORT).show()
            true
        }
        // Any finger on the chart lets go of the aircraft, so the chart moves freely.
        map.setOnTouchListener { _, e ->
            if (e.actionMasked == android.view.MotionEvent.ACTION_MOVE && following && draw.tool == MapDrawOverlay.MapTool.PAN) follow()
            false
        }
        b.zoomOut.setOnClickListener { map.controller.zoomOut() }
        // The compass turns with the chart; a tap puts north back up.
        b.northUp.setOnClickListener {
            trackUp = false
            val from = map.mapOrientation
            val delta = ((0f - from + 540) % 360) - 180
            android.animation.ValueAnimator.ofFloat(0f, 1f).apply {
                duration = 500
                addUpdateListener { map.mapOrientation = from + delta * (it.animatedValue as Float) }
                start()
            }
        }
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
        // Track up stays on from one flight to the next until it is unticked.
        if (prefs.getBoolean("track_up_on", false)) trackUp = true
        // Back to the chart as it was flown: following, track up, ahead.
        if (prefs.getBoolean("view_follow", false)) b.root.postDelayed({
            trackUp = prefs.getBoolean("view_track", false); ahead = prefs.getBoolean("view_ahead", false)
            if (!following) follow(quiet = true)
            b.fabLocate.setImageResource(viewIcon())
        }, 400)
        if (intent.getBooleanExtra(EXTRA_NAVLOG, false)) b.root.post { navLog() }
        b.root.post { showRoutePanel() }
        if (intent.getBooleanExtra(EXTRA_PROFILE, false)) b.root.post { profile() }
        if (intent.getBooleanExtra(EXTRA_NRST, false)) b.root.postDelayed({ nearest() }, 1500)
    }

    // The edition in force, always on the chart, as on a commercial EFB.
    private var currency: android.widget.TextView? = null
    private var pilotage = false

    private fun showCurrency() {
        val (text, ok) = DataCurrency.mapLine(this)
        val t = currency ?: android.widget.TextView(this).apply {
            textSize = 10.5f
            setPadding(dp(8), dp(3), dp(8), dp(3))
            setOnClickListener { startActivity(android.content.Intent(this@MapActivity, EfbCheckActivity::class.java)) }
            b.root.addView(this, android.widget.FrameLayout.LayoutParams(-2, -2, android.view.Gravity.BOTTOM or android.view.Gravity.START).apply {
                setMargins(dp(8), 0, 0, dp(10))
            })
            currency = this
        }
        t.text = (if (pilotage) "🧭 PILOTAGE · " else "") + text
        t.setTextColor(if (ok) 0xFFE8F5E9.toInt() else 0xFF1A1A1A.toInt())
        t.background = EfbUi.cardBg(this, if (ok) 0xCC1B5E20.toInt() else 0xEEFFB300.toInt(), 10).apply { setStroke(0, 0) }
    }

    /** Practice for the checkride's pilotage and dead reckoning: the aircraft and GPS readouts hidden. */
    private fun setPilotage(on: Boolean) {
        pilotage = on
        ownship.isEnabled = !on
        if (on && following) follow()
        strip.visibility = if (on) View.GONE else View.VISIBLE
        map.invalidate()
        showCurrency()
        Toast.makeText(this, if (on) R.string.pilotage_on else R.string.pilotage_off, Toast.LENGTH_LONG).show()
    }

    /** Brought back by a tab: the map as it was, plus what the tab asked for. */
    override fun onNewIntent(intent: android.content.Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (intent.getBooleanExtra(EXTRA_NAVLOG, false)) b.root.post { navLog() }
        if (intent.getBooleanExtra(EXTRA_NRST, false)) b.root.post { nearest() }
    }

    override fun onResume() {
        super.onResume()
        ProcedureUi.pending?.let { (p, t) -> ProcedureUi.pending = null; b.root.post { showProcedure(p, t) } }
        map.onResume()
        showCurrency()
        setOfficial()
        Terrain.onTile = { map.postInvalidate() }
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
        AvionicsPanel.close(this)
        super.onDestroy()
        stopGps()
        Traffic.stopReceiver()
        radarProvider?.detach()
        officialProvider?.detach()
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
        // Overlays as an EFB shows them: a grid of tiles, each ticked when on.
        val grid = android.widget.GridLayout(this).apply { columnCount = 2 }
        box.addView(grid)
        class Tile(val v: android.widget.TextView) { var isChecked = false
            fun paint() { v.setTextColor(if (isChecked) EfbUi.ACCENT else EfbUi.TEXT); v.text = (if (isChecked) "✓  " else "     ") + (v.tag as String)
                v.background = EfbUi.cardBg(this@MapActivity, if (isChecked) 0x221E88E5 else EfbUi.CARD, 10).apply { setStroke(dp(1), if (isChecked) EfbUi.ACCENT else EfbUi.CARD_LINE) } } }
        fun check(label: Int, on: Boolean): Tile {
            val v = android.widget.TextView(this).apply { tag = getString(label); textSize = 14f; setPadding(dp(10), dp(12), dp(10), dp(12)); maxLines = 2 }
            val t = Tile(v); t.isChecked = on; t.paint()
            v.setOnClickListener { t.isChecked = !t.isChecked; t.paint() }
            grid.addView(v, android.widget.GridLayout.LayoutParams().apply {
                width = 0; columnSpec = android.widget.GridLayout.spec(android.widget.GridLayout.UNDEFINED, 1f); setMargins(dp(3), dp(3), dp(3), dp(3))
            })
            return t
        }
        val cRadar = check(R.string.wx_radar, radar != null)
        val cAirmet = check(R.string.wx_airmet, weather.showAirmets)
        val cTfr = check(R.string.wx_tfr, weather.showTfrs)
        val cPirep = check(R.string.wx_pirep, weather.showPireps)
        val cTerrain = check(R.string.wx_terrain, map.overlays.contains(hazard))
        val cAirspace = check(R.string.wx_airspace, map.overlays.contains(airspace))
        val cTraffic = check(R.string.wx_traffic, map.overlays.contains(traffic))
        val cAirports = check(R.string.map_airports, prefs.getBoolean("map_airports", true))
        val cPattern = check(R.string.tp_layer, prefs.getBoolean("tp_on", true))
        // One kind of data on the airports at a time: none, the weather (station model), or the winds aloft.
        box.addView(android.widget.TextView(this).apply {
            text = getString(R.string.map_station_data); setPadding(0, dp(14), 0, dp(4)); setTypeface(typeface, android.graphics.Typeface.BOLD)
        })
        val dataGroup = android.widget.RadioGroup(this)
        val dataNames = listOf(R.string.map_data_none, R.string.map_data_weather, R.string.map_data_winds)
        for ((i, n) in dataNames.withIndex()) dataGroup.addView(android.widget.RadioButton(this).apply { id = 2000 + i; text = getString(n); isChecked = airportsLayer.data.ordinal == i })
        box.addView(dataGroup)
        val altRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; layoutDirection = View.LAYOUT_DIRECTION_LTR }
        var windAlt = prefs.getInt("winds_alt", 6000)
        val altViews = ArrayList<Pair<Int, android.widget.TextView>>()
        fun paintAlt() = altViews.forEach { (a, v) -> v.setTextColor(if (a == windAlt) 0xFFFFFFFF.toInt() else EfbUi.ACCENT); v.background = EfbUi.cardBg(this, if (a == windAlt) EfbUi.ACCENT else EfbUi.CARD, 8) }
        for (a in listOf(3000, 6000, 9000, 12000, 18000)) {
            val v = android.widget.TextView(this).apply { text = "${a / 1000}k"; gravity = android.view.Gravity.CENTER; setPadding(dp(4), dp(8), dp(4), dp(8)); setOnClickListener { windAlt = a; paintAlt() } }
            altViews.add(a to v); altRow.addView(v, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(4) })
        }
        paintAlt()
        box.addView(altRow)
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.map_layers)
            .setView(android.widget.ScrollView(this).apply { addView(box) })
            .setPositiveButton(R.string.ok) { _, _ ->
                val chosen = AviationData.LAYERS.getOrNull(group.checkedRadioButtonId - 1000) ?: layer
                if (chosen != layer) {
                    layer = chosen
                    prefs.edit().putString("map_layer", layer.key).apply()
                    map.setTileSource(layer.source())
                    zoomLimit()
                    setOfficial()
                }
                if (cRadar.isChecked != (radar != null)) setRadar(cRadar.isChecked)
                weather.showAirmets = cAirmet.isChecked
                weather.showTfrs = cTfr.isChecked
                weather.showPireps = cPirep.isChecked
                map.overlays.remove(hazard)
                if (cTerrain.isChecked) map.overlays.add(map.overlays.indexOf(weather).coerceAtLeast(0), hazard)
                prefs.edit().putBoolean("wx_terrain", cTerrain.isChecked).putBoolean("wx_airspace", cAirspace.isChecked)
                    .putBoolean("wx_traffic", cTraffic.isChecked).apply()
                map.overlays.remove(airspace)
                if (cAirspace.isChecked) map.overlays.add(map.overlays.indexOf(weather).coerceAtLeast(0), airspace)
                map.overlays.remove(traffic)
                if (cTraffic.isChecked) { map.overlays.add(traffic); Traffic.startReceiver(); pollTraffic() } else Traffic.stopReceiver()
                prefs.edit().putBoolean("tp_on", cPattern.isChecked).apply()
                map.overlays.remove(patternOv)
                if (cPattern.isChecked) { map.overlays.add(map.overlays.indexOf(airportsLayer).coerceAtLeast(0), patternOv); patternFor = ""; showPattern() }
                val airportsOn = cAirports.isChecked
                val airportsChanged = airportsOn != prefs.getBoolean("map_airports", true)
                prefs.edit().putBoolean("wx_radar", cRadar.isChecked).putBoolean("wx_airmet", cAirmet.isChecked)
                    .putBoolean("wx_tfr", cTfr.isChecked).putBoolean("wx_pirep", cPirep.isChecked)
                    .putBoolean("map_airports", airportsOn).apply()
                if (airportsChanged) {
                    lastWeatherBox = ""
                    loadAirports()
                }
                val data = AirportsOverlay.Data.values().getOrElse(dataGroup.checkedRadioButtonId - 2000) { AirportsOverlay.Data.NONE }
                prefs.edit().putString("map_data", data.name).putInt("winds_alt", windAlt).apply()
                setStationData(data, windAlt)
                refreshWeather()
                wxBar()
                map.invalidate()
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    /** Weather or winds aloft on every airport; the winds are read once and kept for the session. */
    private fun setStationData(data: AirportsOverlay.Data, alt: Int) {
        airportsLayer.data = data
        airportsLayer.windsAlt = alt
        if (data == AirportsOverlay.Data.WINDS && airportsLayer.winds.isEmpty()) lifecycleScope.launch {
            val fb = withContext(Dispatchers.IO) { try { AviationData.windsAloft(6) } catch (e: Exception) { "" } }
            airportsLayer.winds = fb
            map.invalidate()
        }
        map.invalidate()
    }

    // ---- weather over the chart ----

    private val weatherTimer: Runnable = object : Runnable {
        override fun run() {
            radar?.refresh()
            lastWeatherBox = ""
            refreshWeather()
            idle()
            b.root.postDelayed(this, 5 * 60000L)
        }
    }

    /** NEXRAD radar, see-through over the chart, just above it. */
    private var official: TilesOverlay? = null
    private var officialProvider: org.osmdroid.tileprovider.MapTileProviderBase? = null
    private var officialFile: java.io.File? = null

    /**
     * The FAA's own GeoTIFF chart, when on the phone, laid over the chart service where it
     * covers (under the weather and everything drawn).
     */
    private fun setOfficial() {
        val f = OfficialCharts.fileFor(this, layer.key)
        if (f != null && f == officialFile && official != null) return
        official?.let { map.overlays.remove(it) }
        officialProvider?.detach()
        official = null; officialProvider = null; officialFile = null
        if (f != null) try {
            val provider = org.osmdroid.tileprovider.modules.OfflineTileProvider(org.osmdroid.tileprovider.util.SimpleRegisterReceiver(this), arrayOf(f))
            officialProvider = provider
            official = TilesOverlay(provider, this).apply {
                setLoadingBackgroundColor(android.graphics.Color.TRANSPARENT)
                setLoadingLineColor(android.graphics.Color.TRANSPARENT)
            }
            officialFile = f
            provider.setTileRequestCompleteHandler(map.tileRequestCompleteHandler)
            map.overlays.add(0, official)
            // Weather stays above the chart.
            radar?.let { map.overlays.remove(it); map.overlays.add(1, it) }
        } catch (e: Exception) {
        }
        map.invalidate()
    }

    private fun setRadar(on: Boolean) {
        radar?.let { map.overlays.remove(it); it.onDetach(map) }
        radar = null
        if (on) {
            // Over the chart (and the official chart), under everything drawn on it.
            val r = RadarOverlay(map)
            radar = r
            map.overlays.add(if (official != null) 1 else 0, r)
        }
        map.invalidate()
        if (::weather.isInitialized) wxBar()
    }

    // ---- an aircraft tapped on the chart: its floating card ----

    private var targetView: View? = null
    private var targetId: String? = null
    private val targetTick = object : Runnable {
        override fun run() {
            val id = targetId ?: return
            val t = Traffic.targets[id]
            if (t == null) { closeTarget(); return }
            fillTarget(t)
            b.root.postDelayed(this, 2000)
        }
    }
    private var tgtLines: List<TextView> = emptyList()
    private var tgtRoute: TextView? = null

    private fun closeTarget() {
        targetId = null; b.root.removeCallbacks(targetTick)
        targetView?.let { b.root.removeView(it) }; targetView = null
    }

    /** As ForeFlight's traffic pop-up: who it is, the airline and type, its route, and height, speed, climb, distance from me. */
    private fun targetCard(t: Traffic.Target) {
        closeTarget()
        targetId = t.id
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; layoutDirection = View.LAYOUT_DIRECTION_LTR
            background = EfbUi.cardBg(this@MapActivity, 0xF21B1D22.toInt(), 14).apply { setStroke(dp(1), 0xFF3A3D44.toInt()) }
            setPadding(dp(14), dp(10), dp(10), dp(12)); elevation = dp(12).toFloat(); isClickable = true
        }
        val head = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        val title = EfbUi.text(this, "", 18f, 0xFFFFFFFF.toInt(), bold = true)
        head.addView(title, LinearLayout.LayoutParams(0, -2, 1f))
        head.addView(TextView(this).apply {
            text = "✕"; textSize = 17f; setTextColor(0xFFB8BCC4.toInt()); setPadding(dp(10), dp(2), dp(6), dp(2))
            setOnClickListener { closeTarget() }
        })
        card.addView(head)
        val sub = EfbUi.text(this, "", 13f, 0xFF7FD3FF.toInt(), bold = true)
        card.addView(sub)
        val route = EfbUi.text(this, "Route: …", 13.5f, 0xFFFFFFFF.toInt()).apply { setPadding(0, dp(4), 0, dp(4)) }
        tgtRoute = route
        card.addView(route)
        val grid = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(6), 0, 0) }
        val cells = ArrayList<TextView>()
        for (label in listOf("ALT", "GS", "VS", "DIST")) {
            val cell = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
            cell.addView(EfbUi.text(this, label, 10.5f, 0xFF9A9CA3.toInt(), bold = true))
            val v = EfbUi.text(this, "—", 15f, 0xFFFFFFFF.toInt(), bold = true)
            cells.add(v); cell.addView(v)
            grid.addView(cell, LinearLayout.LayoutParams(0, -2, 1f))
        }
        card.addView(grid)
        val foot = EfbUi.text(this, "", 11.5f, 0xFF9A9CA3.toInt()).apply { setPadding(0, dp(6), 0, 0) }
        card.addView(foot)
        tgtLines = listOf(title, sub, foot) + cells
        b.root.addView(card, android.widget.FrameLayout.LayoutParams(minOf(dp(340), (resources.displayMetrics.widthPixels * 0.9).toInt()), -2,
            Gravity.TOP or Gravity.CENTER_HORIZONTAL).apply { topMargin = dp(118) })
        targetView = card
        fillTarget(t)
        b.root.postDelayed(targetTick, 2000)
        // The route, from the callsign database.
        val call = t.call
        lifecycleScope.launch {
            val r = withContext(Dispatchers.IO) { if (Traffic.airline(call) != null) Traffic.route(call) else null }
            if (targetId != t.id) return@launch
            val now = Traffic.targets[t.id] ?: t
            val phase = phaseOf(now)
            // The database's route only when the aircraft really is on it: between the two fields and heading for the second.
            val checked = r?.let { routeFits(it, now) }
            route.text = listOfNotNull(phase, when {
                r != null && checked == true -> "Route $r"
                r != null -> "Database route ($r) does not match where it flies — out of date"
                Traffic.airline(call) == null -> "Private / GA: no public route"
                else -> null
            }).joinToString("\n").ifEmpty { "Route: unknown" }
        }
    }

    private fun apt(code: String) = airports.firstOrNull { it.icao == code || it.ident == code || "K" + it.ident == code }

    /** True when the aircraft lies on the way from the first field to the last and points at the last. */
    private fun routeFits(route: String, t: Traffic.Target): Boolean? {
        val ends = route.split(" → ").map { it.trim() }
        val a = apt(ends.first()) ?: return null
        val b = apt(ends.last()) ?: return null
        val total = Nav.distanceNm(a.lat, a.lon, b.lat, b.lon)
        val via = Nav.distanceNm(a.lat, a.lon, t.lat, t.lon) + Nav.distanceNm(t.lat, t.lon, b.lat, b.lon)
        val toB = Nav.bearingTrue(t.lat, t.lon, b.lat, b.lon)
        val off = Math.abs(((t.track - toB + 540) % 360) - 180)
        val nearB = Nav.distanceNm(t.lat, t.lon, b.lat, b.lon) < 25
        val vs = t.vsFpm ?: 0
        // Coming down near where the database says it left from: it is landing there, so that route is not this flight's.
        if (Nav.distanceNm(t.lat, t.lon, a.lat, a.lon) < 30 && vs < -300 && (t.altFt ?: 99999) < 12000) return false
        // Climbing out near where the database says it goes: the same, the other way.
        if (nearB && vs > 300 && (t.altFt ?: 99999) < 12000) return false
        return via <= total * 1.3 + 20 && (off < 70 || nearB)
    }

    /** What the aircraft is doing by itself: arriving at or leaving the nearest field (low, near it, descending or climbing), or en route. */
    private fun phaseOf(t: Traffic.Target): String? {
        val alt = t.altFt ?: return null
        val vs = t.vsFpm ?: 0
        fun off(a: AviationData.Airport) = Math.abs(((t.track - Nav.bearingTrue(t.lat, t.lon, a.lat, a.lon) + 540) % 360) - 180)
        val close = airports.map { it to Nav.distanceNm(t.lat, t.lon, it.lat, it.lon) }.filter { it.second < 30 }
        if (close.isEmpty()) return null
        val (nearest, dn) = close.minByOrNull { it.second }!!
        if (alt <= 0 || (t.gsKt < 40 && dn < 2)) return "On the ground at ${nearest.icao.ifEmpty { nearest.ident }}"
        if (vs < -300) {
            // Coming down: the field ahead whose 3° glide path (about 318 ft a mile) best fits its height.
            val best = close.filter { off(it.first) < 50 && alt - it.first.elevation in -300..9000 }
                .minByOrNull { (a, d) -> Math.abs((alt - a.elevation) - 318 * d) + 40 * off(a) }
            if (best != null) return "Arriving ${best.first.icao.ifEmpty { best.first.ident }} (likely) · %.0f nm · %,d fpm".format(best.second, vs)
        }
        if (vs > 300 && alt - nearest.elevation < 9000 && off(nearest) > 90) return "Departing ${nearest.icao.ifEmpty { nearest.ident }} (likely) · climbing"
        return null
    }

    private fun fillTarget(t: Traffic.Target) {
        val (title, sub, foot) = tgtLines
        val alt = tgtLines[3]; val gs = tgtLines[4]; val vs = tgtLines[5]; val dist = tgtLines[6]
        val airline = Traffic.airline(t.call)
        title.text = t.call.ifEmpty { t.reg.ifEmpty { t.id.uppercase() } }
        sub.text = listOfNotNull(airline ?: t.owner.ifEmpty { null }, t.desc.ifEmpty { t.type.ifEmpty { null } }, t.reg.takeIf { it.isNotEmpty() && it != t.call })
            .joinToString("  ·  ").ifEmpty { "Aircraft" }
        alt.text = t.altFt?.let { if (it <= 0) "GND" else "%,d ft".format(it) } ?: "—"
        gs.text = "${t.gsKt} kt"
        vs.text = t.vsFpm?.let { if (Math.abs(it) < 100) "level" else "%+,d".format(it) } ?: "—"
        val me = ownship.position()
        dist.text = me?.let { "%.1f nm".format(Nav.distanceNm(it.latitude, it.longitude, t.lat, t.lon)) } ?: "—"
        foot.text = listOfNotNull("Track %03.0f°".format(t.track), t.squawk.takeIf { it.isNotEmpty() }?.let { "Squawk $it" },
            "hex ${t.id.uppercase()}", if (t.fromReceiver) "ADS-B receiver" else Traffic.source.ifEmpty { "ADS-B network" }).joinToString("  ·  ")
    }

    // ---- the weather bar, as ForeFlight's: hazard buttons, the radar loop and its dBZ scale ----

    private var wxPanel: LinearLayout? = null
    private var loopOn = false
    private var loopIdx = 0
    private val LOOP = listOf(50, 40, 30, 20, 10, 0)
    private val loopStep = object : Runnable {
        override fun run() {
            val r = radar ?: run { loopOn = false; return }
            if (!loopOn) return
            loopIdx = (loopIdx + 1) % LOOP.size
            r.age = LOOP[loopIdx]
            loopLabel?.text = if (r.age == 0) "Now" else "−${r.age} min"
            b.root.postDelayed(this, if (r.age == 0) 1800L else 750L)
        }
    }
    private var loopLabel: TextView? = null
    private var playBtn: TextView? = null

    /** Shows or hides the bar above the instrument band, as the radar and the AIRMET layers are on. */
    private fun wxBar() {
        val showHaz = weather.showAirmets
        val showRadar = radar != null
        if (!showHaz && !showRadar) { wxPanel?.visibility = View.GONE; loopOn = false; return }
        val panel = wxPanel ?: LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER_HORIZONTAL
            layoutDirection = View.LAYOUT_DIRECTION_LTR; elevation = dp(7).toFloat()
            b.root.addView(this, android.widget.FrameLayout.LayoutParams(-2, -2, Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL))
            wxPanel = this
        }
        panel.removeAllViews()
        panel.visibility = View.VISIBLE
        (panel.layoutParams as android.widget.FrameLayout.LayoutParams).bottomMargin = stripHeight() + dp(10)
        if (showHaz) {
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; background = EfbUi.cardBg(this@MapActivity, 0xF01B1D22.toInt(), 10); setPadding(dp(3), dp(3), dp(3), dp(3)) }
            val chosen = (prefs.getString("wx_hz", "") ?: "").split(',').filter { it.isNotEmpty() }.toMutableSet()
            weather.hazards = chosen
            for ((key, label) in listOf("ICE" to "Ice", "TURB HI" to "Turb\nHigh", "TURB LO" to "Turb\nLow", "IFR" to "IFR", "TS" to "TS")) {
                val t = TextView(this).apply {
                    text = label; textSize = 12.5f; typeface = EfbUi.MEDIUM; gravity = Gravity.CENTER; setTextColor(0xFFFFFFFF.toInt())
                    setPadding(dp(10), dp(6), dp(10), dp(6)); minWidth = dp(48)
                }
                fun paint() { t.background = EfbUi.cardBg(this, if (key in chosen) 0xFF2D8CFF.toInt() else 0x00000000, 8) }
                paint()
                t.setOnClickListener {
                    if (key in chosen) chosen.remove(key) else chosen.add(key)
                    prefs.edit().putString("wx_hz", chosen.joinToString(",")).apply()
                    weather.hazards = chosen.toSet(); paint(); map.invalidate()
                }
                row.addView(t, LinearLayout.LayoutParams(-2, dp(44)).apply { marginEnd = dp(2) })
            }
            panel.addView(row)
        }
        if (showRadar) {
            val box = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL; background = EfbUi.cardBg(this@MapActivity, 0xF01B1D22.toInt(), 10)
                setPadding(dp(10), dp(6), dp(10), dp(6))
            }
            // The scale: rain from 5 to 75 dBZ in the radar's own colours.
            val scale = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
            scale.addView(EfbUi.text(this, "dBZ", 11f, 0xFFFFFFFF.toInt(), bold = true), LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(6) })
            val ramp = intArrayOf(0xFF04E9E7.toInt(), 0xFF019FF4.toInt(), 0xFF0300F4.toInt(), 0xFF02FD02.toInt(), 0xFF01C501.toInt(), 0xFF008E00.toInt(),
                0xFFFDF802.toInt(), 0xFFE5BC00.toInt(), 0xFFFD9500.toInt(), 0xFFFD0000.toInt(), 0xFFD40000.toInt(), 0xFFBC0000.toInt(), 0xFFF800FD.toInt(), 0xFF9854C6.toInt())
            val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
            col.addView(View(this).apply { background = android.graphics.drawable.GradientDrawable(android.graphics.drawable.GradientDrawable.Orientation.LEFT_RIGHT, ramp).apply { cornerRadius = dp(2).toFloat() } },
                LinearLayout.LayoutParams(dp(190), dp(9)))
            val nums = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            for (v in listOf("5", "25", "45", "65", "75")) nums.addView(EfbUi.text(this, v, 10f, 0xFFDDDDDD.toInt()), LinearLayout.LayoutParams(0, -2, 1f))
            col.addView(nums, LinearLayout.LayoutParams(dp(190), -2))
            scale.addView(col)
            box.addView(scale)
            // The loop: ▶ plays the last 50 minutes, the slider-like label says when.
            val ctl = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(0, dp(4), 0, 0) }
            val play = TextView(this).apply {
                text = if (loopOn) "❚❚" else "▶"; textSize = 16f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
                background = EfbUi.cardBg(this@MapActivity, 0xFF2D8CFF.toInt(), 18)
            }
            playBtn = play
            val label = EfbUi.text(this, if ((radar?.age ?: 0) == 0) "Now" else "−${radar?.age} min", 14f, 0xFFFFFFFF.toInt(), bold = true)
            loopLabel = label
            play.setOnClickListener {
                loopOn = !loopOn
                play.text = if (loopOn) "❚❚" else "▶"
                b.root.removeCallbacks(loopStep)
                if (loopOn) { loopIdx = LOOP.size - 1; b.root.post(loopStep) } else { radar?.age = 0; label.text = "Now" }
            }
            ctl.addView(play, LinearLayout.LayoutParams(dp(40), dp(34)))
            ctl.addView(EfbUi.text(this, "  Radar  ", 12f, 0xFFB8BCC4.toInt()))
            ctl.addView(label)
            box.addView(ctl)
            panel.addView(box, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(6) })
        }
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
            intent.getStringExtra(EXTRA_AIRPORT)?.let { id ->
                intent.removeExtra(EXTRA_AIRPORT)
                list.firstOrNull { it.ident == id }?.let { flyTo(it) }
            }
            airportsLayer.airports = if (prefs.getBoolean("map_airports", true)) list else emptyList()
            draw.snapTo = list
            map.invalidate()
            idle()
        }
    }

    private var lastWeatherBox = ""

    /** After the map settles: the weather of the airports in view. */
    private val patternEnds = HashMap<String, Map<String, Pair<GeoPoint, GeoPoint>>>()
    // The runways whose pattern is on, per airport (tapped in the box), and the airport shown in the box.
    private val patternPicked = HashMap<String, MutableSet<String>>()
    private var patternBoxFor = ""
    private var patternBox: LinearLayout? = null
    private val patternLoading = HashSet<String>()

    /** Zoomed in: the traffic patterns of every airport in view, each runway, the one into the wind bright. */
    private fun showPattern() {
        if (!::patternOv.isInitialized) return
        if (!prefs.getBoolean("tp_on", true)) { patternBox?.visibility = View.GONE; return }
        if (map.zoomLevelDouble < 11) { if (patternOv.fields.isNotEmpty()) { patternOv.fields.clear(); map.invalidate() }; patternPanel(); return }
        val bb = map.boundingBox
        val c = map.mapCenter
        val inView = airports.filter { it.lat in bb.latSouth..bb.latNorth && it.lon in bb.lonWest..bb.lonEast }
            .sortedBy { Nav.distanceNm(c.latitude, c.longitude, it.lat, it.lon) }.take(8)
        patternOv.isRight = { id, r -> PatternOverlay.isRight(this, id, r) }
        patternOv.fields.keys.retainAll(inView.map { it.ident }.toSet())
        for (a in inView) {
            val ends = patternEnds[a.ident]
            if (ends != null) {
                if (ends.isEmpty()) continue
                val metar = airportsLayer.weather[airportsLayer.station(a)]?.json
                patternOv.fields[a.ident] = PatternOverlay.Field(a.ident, a.icao.ifEmpty { a.ident }, ends, PatternOverlay.tpa(a.elevation),
                    PatternOverlay.favored(a.ident, ends.keys, metar, a.lat, a.lon)).apply { shown = patternPicked.getOrPut(a.ident) { HashSet() } }
                continue
            }
            if (!patternLoading.add(a.ident)) continue
            lifecycleScope.launch {
                val json = withContext(Dispatchers.IO) { try { AirportDiagramActivity.fetch(this@MapActivity, a.ident, a.lat, a.lon, refresh = false) } catch (e: Exception) { null } }
                patternEnds[a.ident] = PatternOverlay.endsFrom(json)
                patternLoading.remove(a.ident)
                showPattern()
            }
        }
        patternPanel()
        map.invalidate()
    }

    /**
     * The small box at the bottom of the chart: an airport in view (a tap goes to the next) and its runways;
     * a tap on a runway shows or hides its pattern. ★ is the runway into the wind.
     */
    private fun patternPanel() {
        val fields = patternOv.fields.values.toList()
        val box = patternBox ?: LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = android.view.Gravity.CENTER_VERTICAL
            background = EfbUi.cardBg(this@MapActivity, 0xEE0F1318.toInt(), 14).apply { setStroke(dp(1), 0xFF29313D.toInt()) }
            setPadding(dp(6), dp(4), dp(6), dp(4))
            // Up at the top, under the instruments and clear of the zoom column: the buttons at the bottom stay free.
            // (top right: the route card keeps the top left)
            b.root.addView(this, android.widget.FrameLayout.LayoutParams(-2, -2, android.view.Gravity.TOP or android.view.Gravity.END).apply {
                setMargins(dp(90), b.topBar.height + dp(6), dp(8), 0)
            })
            b.topBar.addOnLayoutChangeListener { _, _, top, _, bottom, _, _, _, _ ->
                (layoutParams as? android.widget.FrameLayout.LayoutParams)?.let { lp ->
                    val want = (bottom - top) + dp(6)
                    if (lp.topMargin != want) { lp.topMargin = want; layoutParams = lp }
                }
            }
            patternBox = this
        }
        if (fields.isEmpty() || !prefs.getBoolean("tp_on", true) || map.zoomLevelDouble < 11) { box.visibility = View.GONE; return }
        box.visibility = View.VISIBLE
        val f = fields.firstOrNull { it.ident == patternBoxFor } ?: fields.first()
        patternBoxFor = f.ident
        box.removeAllViews()
        box.addView(android.widget.TextView(this).apply {
            text = "🛫 ${f.name}" + if (fields.size > 1) " ›" else ""
            textSize = 13f; setTextColor(0xFFF1F4F8.toInt()); setTypeface(typeface, android.graphics.Typeface.BOLD)
            setPadding(dp(6), dp(6), dp(8), dp(6))
            setOnClickListener {
                val i = fields.indexOfFirst { it.ident == f.ident }
                patternBoxFor = fields[(i + 1) % fields.size].ident
                patternPanel()
            }
        })
        val picked = patternPicked.getOrPut(f.ident) { HashSet() }
        val chips = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        for (r in f.ends.keys.sortedBy { it.takeWhile { c -> c.isDigit() }.toIntOrNull() ?: 99 }) {
            val on = r in picked
            chips.addView(android.widget.TextView(this).apply {
                text = "$r ${if (PatternOverlay.isRight(this@MapActivity, f.ident, r)) "R" else "L"}" + if (r == f.active) " ★" else ""
                textSize = 13f; setTypeface(typeface, android.graphics.Typeface.BOLD)
                setTextColor(if (on) 0xFFFFFFFF.toInt() else 0xFFB0BEC5.toInt())
                background = EfbUi.cardBg(this@MapActivity, if (on) 0xFF1A6FE0.toInt() else 0xFF1A2029.toInt(), 10).apply { setStroke(0, 0) }
                setPadding(dp(10), dp(6), dp(10), dp(6))
                setOnClickListener {
                    if (!picked.add(r)) picked.remove(r)
                    patternOv.fields[f.ident]?.shown = picked
                    patternPanel()
                    map.invalidate()
                }
            }, LinearLayout.LayoutParams(-2, -2).apply { marginStart = dp(5) })
        }
        box.addView(android.widget.HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; addView(chips) })
    }

    private fun idle(): Boolean {
        overzoom()
        showPattern()
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

    // ---- the airport diagram card: a floating window, dragged, sized, pinned ----

    private lateinit var cardFrame: LinearLayout
    private lateinit var cardView: DiagramCardView
    private lateinit var cardTitle: TextView
    private lateinit var cardPin: TextView

    private fun buildCard() {
        cardView = DiagramCardView(this) { if (gotGps) ownship.fix else null }
        cardFrame = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; visibility = View.GONE; layoutDirection = View.LAYOUT_DIRECTION_LTR
            background = EfbUi.cardBg(this@MapActivity, 0xFFFFFFFF.toInt(), 12).apply { setStroke(dp(2), 0xFF1B1D22.toInt()) }
            elevation = dp(14).toFloat(); clipToOutline = true
        }
        val head = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setBackgroundColor(0xF01B1D22.toInt())
            setPadding(dp(10), dp(2), dp(4), dp(2))
        }
        cardTitle = EfbUi.text(this, "", 14f, 0xFFFFFFFF.toInt(), bold = true).apply { maxLines = 1 }
        head.addView(cardTitle, LinearLayout.LayoutParams(0, -2, 1f))
        fun hb(t: String, go: (TextView) -> Unit) = TextView(this).apply {
            text = t; textSize = 16f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
            setOnClickListener { go(this) }
        }.also { head.addView(it, LinearLayout.LayoutParams(dp(38), dp(36))) }
        cardPin = hb("📌") {
            val cur = insetOv.current ?: return@hb
            insetOv.pinned = if (insetOv.pinned == cur.ident) null else cur.ident
            paintPin(); map.invalidate()
        }
        hb("−") { sizeCard(-40) }
        hb("+") { sizeCard(40) }
        hb("⤢") {
            val cur = insetOv.current ?: return@hb
            if (following) follow(quiet = true)
            diagramBoxes.entries.firstOrNull { e -> airports.any { it.ident == e.key && it.icao.ifEmpty { it.ident } == cur.ident } }?.value
                ?.let { map.zoomToBoundingBox(it, true, dp(12)) }
        }
        hb("✕") {
            insetOv.current?.let { insetOv.hidden += it.ident; if (insetOv.pinned == it.ident) insetOv.pinned = null }
            cardFrame.visibility = View.GONE; map.invalidate()
        }
        cardFrame.addView(head)
        cardFrame.addView(cardView, LinearLayout.LayoutParams(-1, -2))
        insetOv.card = cardFrame
        val w = prefs.getInt("dc_w", 300)
        b.root.addView(cardFrame, android.widget.FrameLayout.LayoutParams(dp(w), -2, Gravity.TOP or Gravity.START).apply { topMargin = dp(130); leftMargin = dp(70) })
        cardFrame.translationX = prefs.getFloat("dc_x", 0f); cardFrame.translationY = prefs.getFloat("dc_y", 0f)
        // Dragged by its title bar, as the scratchpad.
        var sx = 0f; var sy = 0f; var tx = 0f; var ty = 0f
        head.setOnTouchListener { _, e ->
            when (e.actionMasked) {
                android.view.MotionEvent.ACTION_DOWN -> { sx = e.rawX; sy = e.rawY; tx = cardFrame.translationX; ty = cardFrame.translationY }
                android.view.MotionEvent.ACTION_MOVE -> { cardFrame.translationX = tx + e.rawX - sx; cardFrame.translationY = ty + e.rawY - sy; map.invalidate() }
                android.view.MotionEvent.ACTION_UP -> prefs.edit().putFloat("dc_x", cardFrame.translationX).putFloat("dc_y", cardFrame.translationY).apply()
            }
            true
        }
    }

    /** One field's diagram on the map, chosen from its airport page: laid, pinned, its card shown. */
    fun diagramFor(a: AviationData.Airport) {
        prefs.edit().putBoolean("auto_diagrams", true).apply()
        val key = a.icao.ifEmpty { a.ident }
        insetOv.hidden.remove(key)
        Toast.makeText(this, getString(R.string.apt_plates_loading), Toast.LENGTH_SHORT).show()
        lifecycleScope.launch {
            if (a.ident !in diagrams) {
                val made = withContext(Dispatchers.IO) { buildDiagram(a) }
                if (made == null) { Toast.makeText(this@MapActivity, R.string.plate_on_map_none, Toast.LENGTH_LONG).show(); return@launch }
                addDiagram(a.ident, made)
            }
            insetOv.pinned = key
            if (map.zoomLevelDouble >= insetOv.closeZoom) map.controller.zoomTo(12.5)
            map.controller.animateTo(GeoPoint(a.lat, a.lon))
            map.invalidate()
        }
    }

    private fun paintPin() {
        cardPin.background = if (insetOv.pinned != null && insetOv.pinned == insetOv.current?.ident)
            EfbUi.cardBg(this, 0xFF2D8CFF.toInt(), 8) else null
    }

    private fun sizeCard(by: Int) {
        val lp = cardFrame.layoutParams as android.widget.FrameLayout.LayoutParams
        val wdp = ((lp.width / resources.displayMetrics.density).toInt() + by).coerceIn(180, (resources.displayMetrics.widthPixels / resources.displayMetrics.density * 0.96).toInt())
        lp.width = dp(wdp); cardFrame.layoutParams = lp
        prefs.edit().putInt("dc_w", wdp).apply()
        map.invalidate()
    }

    private fun showCard(ins: DiagramInsetOverlay.Inset?) {
        if (!::cardFrame.isInitialized) return
        if (ins == null) { cardFrame.visibility = View.GONE; return }
        cardView.inset = ins
        cardTitle.text = "${ins.ident} · Airport diagram"
        cardFrame.visibility = View.VISIBLE
        paintPin()
    }

    /** Live tracking for the people on the ground: start and share the link, share it again, or stop. */
    private fun liveTrackMenu() {
        if (LiveTrack.on(this)) {
            val link = LiveTrack.link(this) ?: ""
            MaterialAlertDialogBuilder(this).setTitle("📡 Live tracking is on").setMessage("$link\n\nYour position goes to this private link every 10 seconds.")
                .setPositiveButton("Share link") { _, _ -> LiveTrack.share(this, link) }
                .setNegativeButton("Stop tracking") { _, _ -> LiveTrack.stop(this); invalidateOptionsMenu(); Toast.makeText(this, "Live tracking stopped", Toast.LENGTH_SHORT).show() }
                .setNeutralButton(R.string.cancel, null).show()
            return
        }
        val fix = ownship.fix
        val name = plan.points.let { if (it.size >= 2) "${it.first().id} → ${it.last().id}" else "Live flight" }
        Toast.makeText(this, "Making your private tracking link…", Toast.LENGTH_SHORT).show()
        lifecycleScope.launch {
            val link = withContext(Dispatchers.IO) { LiveTrack.start(this@MapActivity, fix, name) }
            if (link != null) { invalidateOptionsMenu(); LiveTrack.share(this@MapActivity, link); return@launch }
            val why = LaptopClient.trackProblem
            if (why == "update") {
                withContext(Dispatchers.IO) { LaptopClient.updateCloud(this@MapActivity) }
                Toast.makeText(this@MapActivity, "The cloud is updating to add live tracking — try again in 2 minutes.", Toast.LENGTH_LONG).show()
            } else Toast.makeText(this@MapActivity, "Could not start live tracking: $why", Toast.LENGTH_LONG).show()
        }
    }

    /** An approach at the destination (or the nearest field): chosen, read in the advisor, drawn, added to the route. */
    private fun approachMenu() {
        val dest = plan.points.lastOrNull()?.id?.takeIf { it.length in 3..4 && airports.any { a -> a.icao == it || a.ident == it } }
        val c = ownship.position() ?: map.mapCenter as GeoPoint
        val near = airports.minByOrNull { Nav.distanceNm(c.latitude, c.longitude, it.lat, it.lon) }
        val icao = dest ?: near?.let { it.icao.ifEmpty { it.ident } } ?: return
        ProcedureUi.choose(this, icao, { p, t -> showProcedure(p, t) }, { p, t -> addProcedure(p, t) })
    }

    private var plateOv: org.osmdroid.views.overlay.GroundOverlay? = null

    /**
     * The approach's FAA plate laid on the chart where it really is, as ForeFlight's plates on maps:
     * its plan view placed from the fixes' true positions (CIFP) against their symbols on the plate.
     */
    private fun plateOnChart(p: Cifp.Procedure) {
        plateOv?.let { map.overlays.remove(it); it.image?.recycle() }; plateOv = null
        val ident = p.icao.removePrefix("K").takeIf { p.icao.length == 4 && p.icao.startsWith("K") } ?: p.icao
        lifecycleScope.launch {
            val made = withContext(Dispatchers.IO) {
                try {
                    val res = AviationData.plates(this@MapActivity, ident) ?: return@withContext null
                    val norm = { s: String -> s.uppercase().replace(" ", "").replace("RWY", "") }
                    val pl = res.second.firstOrNull { it.code == "IAP" && norm(it.name) == norm(p.name) } ?: return@withContext null
                    val f = AviationData.platePdf(this@MapActivity, res.first, pl.pdf) ?: return@withContext null
                    val fx = Cifp.fixesFor(this@MapActivity, p.icao)
                    val geo = PdfLinks.open(this@MapActivity, f)?.use { it.plateGeo(0, fx) } ?: return@withContext null
                    // The plan view: between the briefing strip and the profile.
                    val x0 = 0.03; val x1 = 0.97; val y0 = 0.155; val y1 = 0.665
                    val bmp = android.graphics.pdf.PdfRenderer(android.os.ParcelFileDescriptor.open(f, android.os.ParcelFileDescriptor.MODE_READ_ONLY)).use { r ->
                        r.openPage(0).use { pg ->
                            val pw = pg.width.toDouble(); val ph = pg.height.toDouble()
                            val cw = 1400; val s = cw / ((x1 - x0) * pw); val ch = ((y1 - y0) * ph * s).toInt()
                            android.graphics.Bitmap.createBitmap(cw, ch, android.graphics.Bitmap.Config.ARGB_8888).also {
                                it.eraseColor(android.graphics.Color.WHITE)
                                pg.render(it, null, android.graphics.Matrix().apply { postScale(s.toFloat(), s.toFloat()); postTranslate((-x0 * pw * s).toFloat(), (-y0 * ph * s).toFloat()) },
                                    android.graphics.pdf.PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                            }
                        }
                    }
                    val nw = geo.ground(x0, y0); val se = geo.ground(x1, y1)
                    Triple(bmp, GeoPoint(nw[0], nw[1]), GeoPoint(se[0], se[1]))
                } catch (e: Throwable) { null }
            }
            if (made == null) {
                Toast.makeText(this@MapActivity, "This plate could not be placed exactly (its fixes' symbols were not found) — open it from the advisor instead.", Toast.LENGTH_LONG).show()
                return@launch
            }
            val o = org.osmdroid.views.overlay.GroundOverlay().apply { image = made.first; setPosition(made.second, made.third); transparency = 0.08f }
            map.overlays.add(map.overlays.indexOf(procOv).coerceAtLeast(1), o)
            plateOv = o
            map.invalidate()
        }
    }

    fun showProcedure(p: Cifp.Procedure, trans: String?) {
        procOv.proc = p; procOv.transition = trans
        plateOnChart(p)
        val pts = p.legs(trans).mapNotNull { l -> if (l.lat != null && l.lon != null) GeoPoint(l.lat, l.lon) else null }
        if (pts.size >= 2) {
            if (following) follow(quiet = true)
            map.zoomToBoundingBox(org.osmdroid.util.BoundingBox.fromGeoPoints(pts), true, dp(60))
        }
        map.invalidate()
        Toast.makeText(this, "${p.name} · ${trans ?: "vectors"} — tap the menu's Approach again to change", Toast.LENGTH_LONG).show()
    }

    /** The approach's fixes into the route, before the destination when it is this airport. */
    fun addProcedure(p: Cifp.Procedure, trans: String?) {
        val wps = p.legs(trans).filter { !it.missed && it.lat != null && it.lon != null && it.fix.isNotEmpty() && !it.fix.startsWith("RW") }
            .map { FlightPlan.Waypoint(it.fix, it.lat!!, it.lon!!) }.distinctBy { it.id }
        if (wps.isEmpty()) return
        val last = plan.points.lastOrNull()
        val isDest = last != null && (last.id == p.icao || "K" + last.id == p.icao || last.id == p.icao.removePrefix("K"))
        if (isDest) plan.points.addAll(plan.points.size - 1, wps) else plan.points.addAll(wps)
        plan.save(this); updateNav()
        showProcedure(p, trans)
        Toast.makeText(this, "${p.name}: ${wps.joinToString(" › ") { it.id }} added", Toast.LENGTH_LONG).show()
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
        // The airport nearest the press (within 10 nm), with its weather.
        val near = airports.minByOrNull { Nav.distanceNm(g.latitude, g.longitude, it.lat, it.lon) }
            ?.takeIf { Nav.distanceNm(g.latitude, g.longitude, it.lat, it.lon) < 10 }
        val target = near?.let { FlightPlan.Waypoint(it.icao.ifEmpty { it.ident }, it.lat, it.lon) } ?: wp
        val around = airports.map { it to Nav.distanceNm(g.latitude, g.longitude, it.lat, it.lon) }
            .filter { it.second < 25 }.sortedBy { it.second }.take(5).map { it.first }
        PointSheet(this, near?.lat ?: g.latitude, near?.lon ?: g.longitude, near, from?.let { it.latitude to it.longitude },
            onDirect = { directTo(target) }, onAdd = { addToRoute(target) },
            onAirport = near?.let { a -> { showAirport(a) } },
            press = g.latitude to g.longitude, nearby = around, onNearby = { a -> showAirport(a) }).show()
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
    /** Each leg its own forecast wind and temperature at the planned altitude, from the nearest winds-aloft station. */
    private fun windsPerLeg() {
        if (plan.points.size < 2) { Toast.makeText(this, R.string.plan_empty, Toast.LENGTH_LONG).show(); return }
        Toast.makeText(this, R.string.plan_winds_fetching, Toast.LENGTH_SHORT).show()
        lifecycleScope.launch {
            val text = withContext(Dispatchers.IO) { AviationData.windsAloft(6) }
            if (text.isBlank()) { Toast.makeText(this@MapActivity, R.string.plan_winds_none, Toast.LENGTH_LONG).show(); return@launch }
            plan.legWinds.clear()
            for (i in 1 until plan.points.size) {
                val a = plan.points[i - 1]; val b = plan.points[i]
                AviationData.windAt(text, (a.lat + b.lat) / 2, (a.lon + b.lon) / 2, plan.altitude)?.let { plan.legWinds[i - 1] = it }
            }
            plan.save(this@MapActivity)
            updateNav(); routePanel?.refresh()
            navLog()
        }
    }

    /** The navigation log printed, or saved as PDF, from the system's print screen. */
    private fun printNavLog() {
        if (plan.points.size < 2) { Toast.makeText(this, R.string.plan_empty, Toast.LENGTH_LONG).show(); return }
        val web = android.webkit.WebView(this)
        val title = plan.points.first().id + " → " + plan.points.last().id
        web.webViewClient = object : android.webkit.WebViewClient() {
            override fun onPageFinished(v: android.webkit.WebView, url: String) {
                val pm = getSystemService(android.print.PrintManager::class.java)
                pm.print("NavLog $title", v.createPrintDocumentAdapter("NavLog $title"), android.print.PrintAttributes.Builder()
                    .setMediaSize(android.print.PrintAttributes.MediaSize.NA_LETTER.asLandscape()).build())
            }
        }
        web.loadDataWithBaseURL(null, FlightPlan.html(plan, title), "text/html", "utf-8", null)
        printWeb = web
    }

    private var printWeb: android.webkit.WebView? = null

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
                    getString(R.string.plan_cancel_direct), getString(R.string.wb_title), getString(R.string.map_profile),
                    getString(R.string.plan_winds_legs), getString(R.string.plan_print))
                MaterialAlertDialogBuilder(this).setItems(opts) { _, i ->
                    when (i) {
                        0 -> { plan.points.reverse(); plan.active = 1; plan.legWinds.clear() }
                        1 -> { plan.points.clear(); plan.direct = null; plan.active = 1; plan.legWinds.clear() }
                        6 -> windsPerLeg()
                        7 -> printNavLog()
                        2 -> startActivity(android.content.Intent.createChooser(android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                            type = "text/plain"
                            putExtra(android.content.Intent.EXTRA_TEXT, plan.points.joinToString(" ") { it.id } + "\n\n" + plan.navLog())
                        }, null))
                        3 -> plan.direct = null
                        4 -> openWb()
                        5 -> profile()
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
    /**
     * Where the aeroplane is, as said on the radio: the nearest airport, how far
     * and which way from it, and the altitude; read aloud on request.
     */
    private fun positionReport() {
        val here = ownship.position() ?: run { Toast.makeText(this, R.string.map_no_gps, Toast.LENGTH_LONG).show(); return }
        val a = airports.minByOrNull { Nav.distanceNm(here.latitude, here.longitude, it.lat, it.lon) } ?: return
        val dist = Nav.distanceNm(a.lat, a.lon, here.latitude, here.longitude)
        val brg = Nav.bearingTrue(a.lat, a.lon, here.latitude, here.longitude)
        val dirs = arrayOf("north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest")
        val dir = dirs[(((brg + 22.5) % 360) / 45).toInt()]
        val alt = if (lastAlt.isNaN()) null else (Math.round(lastAlt / 100) * 100).toInt()
        val call = prefs.getString("callsign", "")?.ifEmpty { null } ?: getString(R.string.pos_callsign)
        val name = a.name.lowercase().split(' ').joinToString(" ") { it.replaceFirstChar { c -> c.uppercase() } }
        val text = "$name traffic, $call, " + (if (dist < 1.5) "over the field" else "%.0f miles $dir".format(dist)) +
            (alt?.let { ", %,d".format(it) } ?: "") + ", $name."
        val input = android.widget.EditText(this).apply { setText(prefs.getString("callsign", "")); hint = getString(R.string.pos_callsign_hint) }
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.pos_report)
            .setMessage(text + "\n\n" + getString(R.string.pos_note))
            .setView(android.widget.FrameLayout(this).apply { setPadding(dp(20), 0, dp(20), 0); addView(input) })
            .setPositiveButton(R.string.pos_speak) { _, _ ->
                prefs.edit().putString("callsign", input.text.toString().trim()).apply()
                Voice.say(this, "pos" + System.currentTimeMillis(), text, 0)
            }
            .setNeutralButton(R.string.pos_save) { _, _ -> prefs.edit().putString("callsign", input.text.toString().trim()).apply() }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    /**
     * The map's buttons as an EFB draws them: dark rounded squares with white icons
     * over the chart, the emergency one in red, the aircraft one in blue.
     */
    private fun styleControls() {
        val dark = android.content.res.ColorStateList.valueOf(0xEB1C1F24.toInt())
        val white = android.content.res.ColorStateList.valueOf(0xFFFFFFFF.toInt())
        val shape = com.google.android.material.shape.ShapeAppearanceModel.builder()
            .setAllCorners(com.google.android.material.shape.CornerFamily.ROUNDED, dp(14).toFloat()).build()
        for (f in listOf(b.northUp, b.zoomIn, b.zoomOut, b.fabSos, b.fabLayers, b.fabDraw, b.fabLocate)) {
            f.backgroundTintList = dark
            f.imageTintList = white
            f.shapeAppearanceModel = shape
            f.rippleColor = 0x44FFFFFF
            f.compatElevation = dp(6).toFloat()
        }
        b.fabSos.imageTintList = android.content.res.ColorStateList.valueOf(0xFFFF453A.toInt())
        b.fabLocate.backgroundTintList = android.content.res.ColorStateList.valueOf(0xFF2E9BFF.toInt())
        b.penBar.background = android.graphics.drawable.GradientDrawable().apply {
            cornerRadius = dp(30).toFloat(); setColor(0xF01C1C1E.toInt()); setStroke(dp(1), 0xFF3A3A3C.toInt())
        }
        b.hudNav.setBackgroundColor(0xF0101418.toInt())
    }

    /** Every line on the map that can go, in one list: the route, the Direct-To, the drawings, the track. */
    private fun clearLines() {
        val opts = arrayOf(
            getString(R.string.plan_cancel_direct), getString(R.string.plan_clear),
            getString(R.string.clear_drawings, draw.marks.size), getString(R.string.clear_track), getString(R.string.clear_all_lines),
        )
        MaterialAlertDialogBuilder(this).setTitle(R.string.clear_lines).setItems(opts) { _, i ->
            if (i == 0 || i == 4) plan.direct = null
            if (i == 1 || i == 4) { plan.points.clear(); plan.direct = null; plan.active = 1 }
            if ((i == 2 || i == 4) && draw.marks.isNotEmpty()) {
                // Undoable, like any rubbing out.
                val gone = draw.marks.mapIndexed { k, m -> k to m }
                draw.marks.clear()
                draw.selected = null
                undo.addLast(AnnotatedPageView.Edit.Removed(gone)); redo.clear()
                saveDrawings()
            }
            if (i == 3 || i == 4) ownship.clearTrail()
            draw.clearRuler()
            plan.save(this)
            updateNav()
            map.invalidate()
            Toast.makeText(this, R.string.cleared, Toast.LENGTH_SHORT).show()
        }.show()
    }

    /** The glide ratio from the POH, so the ring can be drawn; empty takes it off. */
    private fun askGlide() {
        val input = android.widget.EditText(this).apply {
            inputType = android.text.InputType.TYPE_CLASS_NUMBER or android.text.InputType.TYPE_NUMBER_FLAG_DECIMAL
            setText(prefs.getString("glide_ratio", "")); hint = "e.g. from the POH"
        }
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.glide_menu)
            .setMessage(R.string.glide_msg)
            .setView(android.widget.FrameLayout(this).apply { setPadding(dp(20), 0, dp(20), 0); addView(input) })
            .setPositiveButton(R.string.ok) { _, _ ->
                prefs.edit().putString("glide_ratio", input.text.toString().trim()).apply()
                glide.ratio = input.text.toString().toDoubleOrNull() ?: 0.0
                map.invalidate()
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    /** A tap on the line to the waypoint: take the Direct-To off, clear the whole route, or see the nav log. */
    private fun routeMenu() {
        val opts = arrayOf(getString(R.string.plan_cancel_direct), getString(R.string.plan_clear), getString(R.string.plan_title))
        MaterialAlertDialogBuilder(this).setTitle(R.string.route_line).setItems(opts) { _, i ->
            when (i) {
                0 -> plan.direct = null
                1 -> { plan.points.clear(); plan.direct = null; plan.active = 1 }
                2 -> { navLog(); return@setItems }
            }
            plan.save(this)
            updateNav()
            map.invalidate()
        }.show()
    }

    private var routePanel: RoutePanel? = null

    /** The floating route card: made once, then kept up with the plan. */
    private fun showRoutePanel() {
        val rp = routePanel ?: RoutePanel(this, b.root, { plan }, listOf(
            getString(R.string.route_edit) to { editPlan() },
            getString(R.string.route_navlog) to { navLog() },
            getString(R.string.plan_reverse) to { plan.points.reverse(); plan.active = 1; plan.save(this); updateNav(); map.invalidate() },
            getString(R.string.map_profile) to { profile() },
            getString(R.string.wb_title) to { openWb() },
            getString(R.string.plan_clear) to { plan.points.clear(); plan.direct = null; plan.active = 1; plan.save(this); updateNav(); map.invalidate() },
        )).also { routePanel = it }
        rp.topOffset = b.topBar.height
        rp.refresh()
    }

    private fun updateNav() {
        showRoutePanel()
        if (!b.hudNav.hasOnClickListeners()) b.hudNav.setOnClickListener { routeMenu() }
        val t = plan.target()
        val here = ownship.position()
        if (t == null || here == null) {
            b.hudNav.visibility = if (t != null) View.VISIBLE else View.GONE
            if (t != null) b.hudNav.text = "→ ${t.id}   ✕"
            return
        }
        val dist = Nav.distanceNm(here.latitude, here.longitude, t.lat, t.lon)
        val brg = Nav.magnetic(Nav.bearingTrue(here.latitude, here.longitude, t.lat, t.lon), here.latitude, here.longitude)
        val gs = ownship.speedKt()
        val ete = if (gs > 20) dist / gs * 60 else Double.NaN
        val eta = if (ete.isNaN()) "--:--" else java.text.SimpleDateFormat("HH:mm", java.util.Locale.US)
            .format(java.util.Date(System.currentTimeMillis() + (ete * 60000).toLong()))
        b.hudNav.text = "→ %s  BRG %sM  %.1f nm  ETE %s  ETA %s   ✕".format(t.id, Nav.deg(brg), dist,
            if (ete.isNaN()) "--:--" else FlightPlan.hm(ete), eta)
        b.hudNav.visibility = View.VISIBLE
        if (dist < 2 && gs > 30) Voice.say(this, "wp" + t.id, "Approaching ${t.id.toCharArray().joinToString(" ")}, two miles.", 600)
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
    private lateinit var glide: GlideRing
    private var lastAltAt = 0L
    private var vs = 0.0
    private val listener = LocationListener { l -> onFix(l) }
    private val coarse = LocationListener { l -> if (!gotGps) onFix(l) }
    private var satellites: Any? = null

    @SuppressLint("MissingPermission")
    private fun startGps() {
        lm = getSystemService(LocationManager::class.java)
        val m = lm ?: return
        strip.visibility = View.VISIBLE
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
        // Keep the fixes coming with the map in the background or the screen off.
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED)
            requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 77)
        TrackingService.start(this)
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
        TrackingService.stop(this)
        try {
            lm?.removeUpdates(listener)
            lm?.removeUpdates(coarse)
            (satellites as? android.location.GnssStatus.Callback)?.let { lm?.unregisterGnssStatusCallback(it) }
        } catch (e: Exception) {
        }
    }

    private var diagramFor = ""

    /**
     * Taxiing at a field (moving on the ground, 2–30 kt, within a mile): its airport diagram opens by
     * itself with the aircraft on it, as ForeFlight does, once per field until flying again.
     */
    private fun autoDiagram(l: Location, kt: Double) {
        if (!gotGps || !prefs.getBoolean("auto_diagram", true)) return
        if (kt > 45) { diagramFor = ""; return }
        if (kt < 2 || kt > 30) return
        val apt = airports.minByOrNull { Nav.distanceNm(l.latitude, l.longitude, it.lat, it.lon) } ?: return
        if (Nav.distanceNm(l.latitude, l.longitude, apt.lat, apt.lon) > 1.0 || apt.ident == diagramFor) return
        diagramFor = apt.ident
        AirportDiagramActivity.open(this, apt)
    }

    private fun stripHeight() = if (::strip.isInitialized && strip.visibility == View.VISIBLE) (strip.height.takeIf { it > 0 } ?: dp(56)) else 0

    /**
     * ForeFlight's layout of the map: the instruments in a band along the bottom, the tools in a
     * slim column on the left (layers, draw, position, north up, zoom, SOS), the chart free between.
     */
    private fun foreflightLayout() {
        b.fabs.visibility = View.GONE
        b.zoomBox.visibility = View.GONE
        strip.setBackgroundColor(0xEB16171A.toInt())
        b.root.addView(strip, android.widget.FrameLayout.LayoutParams(-1, -2, android.view.Gravity.BOTTOM))
        strip.elevation = dp(6).toFloat()
        // The bottom panels (ruler, pen) sit above the band.
        strip.addOnLayoutChangeListener { _, _, top, _, bottom, _, _, _, _ -> (b.fabs.parent as View).setPadding(0, 0, 0, bottom - top) }
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = EfbUi.cardBg(this@MapActivity, 0xEB16171A.toInt(), 10).apply { setStroke(dp(1), 0x33FFFFFF) }
            elevation = dp(6).toFloat()
            setPadding(0, dp(4), 0, dp(4))
        }
        fun tool(icon: Int, tint: Int = EfbUi.TEXT, click: () -> Unit, long: (() -> Unit)? = null) = android.widget.ImageView(this).apply {
            setImageResource(icon); setColorFilter(tint)
            setPadding(dp(11), dp(11), dp(11), dp(11))
            setBackgroundResource(R.drawable.item_focus_bg)
            setOnClickListener { click() }
            long?.let { l -> setOnLongClickListener { l(); true } }
        }.also { col.addView(it, LinearLayout.LayoutParams(dp(46), dp(46))) }
        fun line() = col.addView(View(this).apply { setBackgroundColor(0x33FFFFFF) }, LinearLayout.LayoutParams(dp(30), 1).apply { gravity = android.view.Gravity.CENTER_HORIZONTAL; setMargins(0, dp(2), 0, dp(2)) })
        tool(R.drawable.ic_layers, click = { b.fabLayers.performClick() })
        tool(R.drawable.ic_fab_pencil, click = { b.fabDraw.performClick() })
        val locate = tool(R.drawable.ic_my_location, EfbUi.ACCENT, click = { b.fabLocate.performClick() }, long = { b.fabLocate.performLongClick() })
        locateTool = locate
        val north = tool(R.drawable.ic_compass, click = { b.northUp.performClick() })
        northTool = north
        line()
        tool(R.drawable.ic_add, click = { b.zoomIn.performClick() })
        tool(R.drawable.ic_remove, click = { b.zoomOut.performClick() })
        line()
        tool(R.drawable.ic_sos, 0xFFFF453A.toInt(), click = { b.fabSos.performClick() })
        b.root.addView(col, android.widget.FrameLayout.LayoutParams(-2, -2, android.view.Gravity.START or android.view.Gravity.CENTER_VERTICAL).apply { marginStart = dp(8) })
    }

    private var northTool: View? = null
    private var locateTool: android.widget.ImageView? = null

    /** Every box of the instrument strip, from this fix and the route. */
    private fun fillStrip(l: Location, kt: Double) {
        if (!::strip.isInitialized) return
        val good = gotGps
        fun m(t: Double) = Nav.deg(Nav.magnetic(t, l.latitude, l.longitude)) + "M"
        strip.set("GS", if (good) "%d kts".format(Math.round(kt)) else "---")
        strip.set("ALT", if (good && l.hasAltitude()) "%,d'".format(Math.round(l.altitude * 3.28084)) else "---")
        strip.set("TRK", if (l.hasBearing() && kt > 5) m(l.bearing.toDouble()) else "---")
        strip.set("VS", if (good && !lastAlt.isNaN()) "%d fpm".format((Math.round(vs / 50) * 50).toInt()) else "---")
        strip.set("ACC", if (l.hasAccuracy()) "%d m".format(Math.round(l.accuracy)) else "---")
        fun dm(v: Double, p: Char, n: Char): String { val a = Math.abs(v); val dd = a.toInt(); return "%c%d°%04.1f'".format(if (v >= 0) p else n, dd, (a - dd) * 60) }
        strip.set("POS", dm(l.latitude, 'N', 'S') + " " + dm(l.longitude, 'E', 'W'))
        val t = plan.target()
        if (t == null) { for (k in listOf("DTK", "BRG", "MH", "DIS", "ETE", "DEST", "ETED", "ETA", "XTK")) strip.set(k, "---"); return }
        val dist = Nav.distanceNm(l.latitude, l.longitude, t.lat, t.lon)
        strip.set("BRG", m(Nav.bearingTrue(l.latitude, l.longitude, t.lat, t.lon)))
        strip.set("DIS", if (dist < 10) "%.1f nm".format(dist) else "%.0f nm".format(dist))
        val from = if (plan.direct != null) null else plan.points.getOrNull(plan.active - 1)
        if (from != null) {
            val leg = plan.leg(from, t)
            strip.set("DTK", m(leg.tc))
            strip.set("MH", Nav.deg(leg.mh))
            // Cross track: the distance off the line from the leg's start, right (R) or left (L).
            val d13 = Nav.distanceNm(from.lat, from.lon, l.latitude, l.longitude) / 3440.065
            val b13 = Math.toRadians(Nav.bearingTrue(from.lat, from.lon, l.latitude, l.longitude))
            val b12 = Math.toRadians(leg.tc)
            val xt = Math.asin(Math.sin(d13) * Math.sin(b13 - b12)) * 3440.065
            strip.set("XTK", "%.1f%s".format(Math.abs(xt), if (xt >= 0) "R" else "L"))
        } else { strip.set("DTK", m(Nav.bearingTrue(l.latitude, l.longitude, t.lat, t.lon))); strip.set("MH", "---"); strip.set("XTK", "---") }
        // Along the route to its last point.
        var rest = dist
        if (plan.direct == null) for (i in plan.active + 1 until plan.points.size) rest += Nav.distanceNm(plan.points[i - 1].lat, plan.points[i - 1].lon, plan.points[i].lat, plan.points[i].lon)
        strip.set("DEST", if (rest < 10) "%.1f nm".format(rest) else "%.0f nm".format(rest))
        if (kt > 20) {
            strip.set("ETE", FlightPlan.hm(dist / kt * 60))
            strip.set("ETED", FlightPlan.hm(rest / kt * 60))
            strip.set("ETA", java.text.SimpleDateFormat("HH:mm", java.util.Locale.US).format(java.util.Date(System.currentTimeMillis() + (rest / kt * 3600000).toLong())))
        } else for (k in listOf("ETE", "ETED", "ETA")) strip.set(k, "--:--")
    }

    /** Ground speed in knots, track in degrees magnetic, altitude in feet MSL, vertical speed in feet per minute. */
    private fun onFix(l: Location, quiet: Boolean = false) {
        if (!quiet && l.provider == LocationManager.GPS_PROVIDER) LiveTrack.onFix(this, l)
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
        fillStrip(l, kt)
        autoDiagram(l, kt)
        if (gotGps) svt?.update(l)
        if (gotGps) AvionicsPanel.feed(kt, if (l.hasAltitude()) l.altitude * 3.28084 else Double.NaN, if (lastAlt.isNaN()) Double.NaN else vs,
            if (l.hasBearing() && kt > 5) Nav.magnetic(l.bearing.toDouble(), l.latitude, l.longitude) else Double.NaN)
        // The flight is noticed and timed from the GPS, then offered to the logbook.
        if (gotGps && !quiet) FlightRecorder.onFix(this, l, airports)?.let { e -> offerLog(e) }
        if (gotGps && !quiet) checkAirspace(l)
        if (gotGps && !quiet) { checkControlled(l); checkTraffic(l); fuelWatch() }
        // Terrain is judged against the GPS altitude in flight, the planned altitude on the ground.
        val flying = gotGps && l.hasAltitude() && kt > 35
        hazard.altitudeFt = if (flying) l.altitude * 3.28084 else plan.altitude.toDouble()
        if (flying && l.hasBearing()) {
            val altFt = l.altitude * 3.28084
            for (min in listOf(0.5, 1.0, 2.0)) {
                val g = Nav.destination(l.latitude, l.longitude, l.bearing.toDouble(), kt * min / 60)
                val e = Terrain.elevationFt(g.latitude, g.longitude) ?: continue
                if (e >= altFt - 300 && System.currentTimeMillis() - terrainAlertAt > 30000) {
                    terrainAlertAt = System.currentTimeMillis()
                    Voice.say(this, "terrain", if (min <= 1.0) "Caution, terrain. Pull up." else "Caution, terrain ahead.", 30)
                    alert("⛰ TERRAIN AHEAD · ${if (min < 1) "30 SEC" else "${min.toInt()} MIN"}", "Ground %,d ft MSL ahead, aircraft %,d ft".format(e.toInt(), altFt.toInt()))
                    break
                }
            }
        }
        // Gliding range above the nearest field's elevation, at about 1.5 nm per 1000 ft.
        ownship.glideNm = if (gotGps && l.hasAltitude() && kt > 35) {
            val ground = airports.minByOrNull { Nav.distanceNm(l.latitude, l.longitude, it.lat, it.lon) }?.elevation ?: 0
            ((l.altitude * 3.28084 - ground) / 1000 * 1.5).coerceAtLeast(0.0)
        } else 0.0
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
        private var lastTraffic = 0L
        override fun run() {
            // While the map keeps following, it never settles: refresh what is in view every 15 s.
            val now = android.os.SystemClock.elapsedRealtime()
            if (b.northUp.rotation != map.mapOrientation) { b.northUp.rotation = map.mapOrientation; northTool?.rotation = map.mapOrientation }
            // The position tool shows the view in use: free, follow, track up, ahead.
            locateTool?.let { t -> val ic = viewIcon(); if (t.tag != ic) { t.setImageResource(ic); t.tag = ic; t.alpha = if (following) 1f else 0.7f } }
            if (timerStart > 0) {
                val t = (now - timerStart) / 1000
                val text = "⏱ %d:%02d:%02d".format(t / 3600, t / 60 % 60, t % 60)
                if (b.toolbar.subtitle?.toString() != text) b.toolbar.subtitle = text
            }
            // Every 5 s, as close to live as the networks are.
            if (now - lastTraffic > 5000) { lastTraffic = now; pollTraffic() }
            if (following && now - lastIdle > 15000) {
                lastIdle = now
                idle()
            }
            val fix = ownship.fix
            val moving = ownship.speedKt() > 3
            if (fix != null) {
                if (following) {
                    ownship.position()?.let { p ->
                        if (ahead && trackUp && fix.hasBearing() && moving && map.height > 0) {
                            // The aircraft a third of the way up from the bottom: the chart's centre lies ahead on the track.
                            val pr = map.projection
                            val a = pr.fromPixels(0, 0); val bb = pr.fromPixels(0, 200)
                            val nmPerPx = Nav.distanceNm(a.latitude, a.longitude, bb.latitude, bb.longitude) / 200.0
                            val c = Nav.destination(p.latitude, p.longitude, (if (heading.isNaN()) fix.bearing else heading).toDouble(), nmPerPx * map.height * 0.28)
                            map.controller.setCenter(c)
                        } else map.controller.setCenter(p)
                    }
                } else if (moving) {
                    map.invalidate()
                }
                if (trackUp && fix.hasBearing() && moving) {
                    // Turn the chart gently towards the track instead of snapping.
                    val want = fix.bearing
                    heading = if (heading.isNaN()) want else heading + (((want - heading + 540) % 360) - 180) * 0.15f
                    map.mapOrientation = -heading
                }
            }
            b.root.postDelayed(this, if (moving || following) 33L else 250L)
        }
    }

    private var timerStart = 0L
    private var terrainAlertAt = 0L

    // ---- controlled airspace, traffic, fuel ----

    private val airspaceSaid = HashMap<String, Long>()

    /** Class B, C, D and restricted or prohibited areas the aircraft is in, or will be within 2 minutes, at its altitude. */
    private fun checkControlled(l: Location) {
        val kt = if (l.hasSpeed()) l.speed * 1.943844 else 0.0
        if (kt < 35 || !l.hasAltitude()) return
        val alt = l.altitude * 3.28084
        for (min in listOf(0.0, 1.0, 2.0)) {
            val p = if (min == 0.0 || !l.hasBearing()) GeoPoint(l.latitude, l.longitude) else Nav.destination(l.latitude, l.longitude, l.bearing.toDouble(), kt * min / 60)
            val hit = Airspace.areas.firstOrNull { it.kind in setOf("B", "C", "D", "R", "P") && it.contains(p.latitude, p.longitude) && it.spans(alt) } ?: continue
            val key = hit.kind + hit.name
            val t = System.currentTimeMillis()
            if (t - (airspaceSaid[key] ?: 0L) < 10 * 60000) return
            airspaceSaid[key] = t
            val name = Airspace.spoken(hit.kind)
            alert(if (min == 0.0) "⛔ IN ${hit.kind} · ${hit.name}" else "⚠️ ${hit.kind} AHEAD · ${min.toInt()} MIN · ${hit.limits()}", "${hit.name}\n${hit.limits()}\n${hit.note}")
            Voice.say(this, "cls$key", if (min == 0.0) "$name airspace." else "Caution. $name airspace ahead.", 600)
            return
        }
    }

    /** A target within 2 nm and 1000 ft: its clock position, distance and relative altitude. */
    private fun trafficClose(t: Traffic.Target): String? {
        if (t.id == Traffic.meId) return null
        val l = ownship.fix ?: return null
        val alt = l.takeIf { it.hasAltitude() && gotGps }?.altitude?.times(3.28084) ?: return null
        val tAlt = t.altFt ?: return null
        val dist = Nav.distanceNm(l.latitude, l.longitude, t.lat, t.lon)
        if (dist > 2 || Math.abs(tAlt - alt) > 1000) return null
        val rel = (Nav.bearingTrue(l.latitude, l.longitude, t.lat, t.lon) - (if (l.hasBearing()) l.bearing.toDouble() else 0.0) + 360) % 360
        val clock = Math.round(rel / 30).toInt().let { if (it == 0) 12 else it }
        val dAlt = Math.round((tAlt - alt) / 100).toInt() * 100
        return "Traffic. $clock o'clock. ${"%.0f".format(Math.max(1.0, dist))} mile${if (dist >= 1.5) "s" else ""}. " +
            when { dAlt > 200 -> "High."; dAlt < -200 -> "Low."; else -> "Same altitude." }
    }

    private fun checkTraffic(l: Location) {
        if (!map.overlays.contains(traffic) || (if (l.hasSpeed()) l.speed * 1.943844 else 0.0) < 35) return
        for (t in Traffic.targets.values) {
            val say = trafficClose(t) ?: continue
            Voice.say(this, "tfc" + t.id, say, 60)
        }
    }

    private fun pollTraffic() {
        if (!map.overlays.contains(traffic)) return
        val c = ownship.position() ?: map.mapCenter as GeoPoint
        lifecycleScope.launch {
            withContext(Dispatchers.IO) { Traffic.prune(); Traffic.fetch(c.latitude, c.longitude) }
            findMe()
            map.invalidate()
            if (::cardView.isInitialized) cardView.invalidate()
        }
    }

    private var meAnnounced: String? = null

    /**
     * Am I seen? In flight, the target where I am — within half a mile, 400 ft and 25 kt of my own
     * GPS — is my aircraft's ADS-B Out as every other aircraft and ATC receive it. It is not drawn as
     * traffic, and the map says once that I am visible.
     */
    private fun findMe() {
        val l = ownship.fix?.takeIf { gotGps } ?: return
        val kt = ownship.speedKt()
        if (kt < 35) { Traffic.meId = null; return }
        val alt = l.takeIf { it.hasAltitude() }?.altitude?.times(3.28084)
        val me = Traffic.targets.values.filter { t ->
            Nav.distanceNm(l.latitude, l.longitude, t.lat, t.lon) < 0.5 &&
                (alt == null || t.altFt == null || Math.abs(t.altFt!! - alt) < 400) && Math.abs(t.gsKt - kt) < 25
        }.minByOrNull { Nav.distanceNm(l.latitude, l.longitude, it.lat, it.lon) }
        Traffic.meId = me?.id
        if (me != null && meAnnounced != me.id) {
            meAnnounced = me.id
            val name = me.call.ifEmpty { me.reg.ifEmpty { me.id.uppercase() } }
            Toast.makeText(this, "📡 ADS-B Out seen: $name — other aircraft and ATC can see you", Toast.LENGTH_LONG).show()
        }
        b.toolbar.subtitle = if (me != null) "📡 Visible on ADS-B · ${me.call.ifEmpty { me.reg }}" else b.toolbar.subtitle
    }

    /**
     * Who is around: my position from the GPS, theirs from the ADS-B networks; each aircraft by
     * distance, clock position from my track, and height above or below me. A tap shows it on the map.
     */
    private fun trafficList() {
        if (!map.overlays.contains(traffic)) { map.overlays.add(traffic); Traffic.startReceiver(); prefs.edit().putBoolean("wx_traffic", true).apply() }
        val me = ownship.fix
        val here = ownship.position() ?: map.mapCenter as GeoPoint
        val myAlt = me?.takeIf { it.hasAltitude() && gotGps }?.altitude?.times(3.28084)
        val myTrk = me?.takeIf { it.hasBearing() && ownship.speedKt() > 5 }?.bearing?.toDouble() ?: 0.0
        lifecycleScope.launch {
            withContext(Dispatchers.IO) { Traffic.prune(); Traffic.fetch(here.latitude, here.longitude) }
            val list = Traffic.targets.values.map { t -> t to Nav.distanceNm(here.latitude, here.longitude, t.lat, t.lon) }.sortedBy { it.second }.take(40)
            if (list.isEmpty()) {
                Toast.makeText(this@MapActivity, getString(R.string.traffic_none) + Traffic.lastError.takeIf { it.isNotEmpty() }?.let { "\n$it" }.orEmpty(), Toast.LENGTH_LONG).show()
                return@launch
            }
            val rows = list.map { (t, d) ->
                val brg = Nav.bearingTrue(here.latitude, here.longitude, t.lat, t.lon)
                val clock = (((brg - myTrk + 360) % 360) / 30.0).let { Math.round(it).toInt() }.let { if (it == 0) 12 else it }
                val rel = if (t.altFt != null && myAlt != null) "%+,d ft".format(((t.altFt!! - myAlt) / 100).toInt() * 100) else (t.altFt?.let { "%,d ft".format(it) } ?: "—")
                val name = t.call.ifEmpty { t.id.uppercase() } + if (t.type.isNotEmpty()) " · ${t.type}" else ""
                "%.1f nm  ·  %d o'clock  ·  %s  ·  %d kt\n%s".format(d, clock, rel, t.gsKt, name)
            }
            MaterialAlertDialogBuilder(this@MapActivity)
                .setTitle(getString(R.string.traffic_list) + "  (" + Traffic.source.ifEmpty { "ADS-B" } + ")")
                .setItems(rows.toTypedArray()) { _, i -> list.getOrNull(i)?.first?.let { t -> if (following) follow(); map.controller.animateTo(GeoPoint(t.lat, t.lon)) } }
                .setNegativeButton(R.string.cancel, null).show()
        }
    }

    private var svt: SvtView? = null

    /**
     * Synthetic vision beside the chart, as ForeFlight splits its map: the terrain ahead with speed,
     * altitude and heading on one side (left in landscape, top in portrait), the map on the other.
     */
    private fun svtSplit() {
        val holder = b.mapHolder
        svt?.let { v ->
            (v.parent as? android.view.ViewGroup)?.removeView(v); svt = null
            (holder.layoutParams as android.widget.FrameLayout.LayoutParams).apply { leftMargin = 0; topMargin = 0 }.also { holder.layoutParams = it }
            prefs.edit().putBoolean("svt_split", false).apply()
            return
        }
        Terrain.init(this)
        val v = SvtView(this).apply { airports = this@MapActivity.airports }
        ownship.fix?.let { v.update(it) }
        val land = resources.displayMetrics.widthPixels > resources.displayMetrics.heightPixels
        val w = resources.displayMetrics.widthPixels; val h = resources.displayMetrics.heightPixels
        if (land) {
            b.root.addView(v, 0, android.widget.FrameLayout.LayoutParams((w * 0.45).toInt(), -1, android.view.Gravity.START))
            (holder.layoutParams as android.widget.FrameLayout.LayoutParams).apply { leftMargin = (w * 0.45).toInt() }.also { holder.layoutParams = it }
        } else {
            val top = b.topBar.height
            b.root.addView(v, 0, android.widget.FrameLayout.LayoutParams(-1, (h * 0.38).toInt(), android.view.Gravity.TOP).apply { topMargin = top })
            (holder.layoutParams as android.widget.FrameLayout.LayoutParams).apply { topMargin = top + (h * 0.38).toInt() }.also { holder.layoutParams = it }
        }
        svt = v
        Terrain.onTile = { map.postInvalidate(); v.postInvalidate() }
        prefs.edit().putBoolean("svt_split", true).apply()
    }

    /** The FAA diagrams on the chart, by airport, and the fields known to have none. */
    private val diagrams = LinkedHashMap<String, org.osmdroid.views.overlay.GroundOverlay>()
    private val noDiagram = HashSet<String>()
    private val diagramBoxes = HashMap<String, org.osmdroid.util.BoundingBox>()
    private var diagramsBusy = false

    /**
     * A diagram as ForeFlight lays it on the map: no white paper, a dark glass panel and the
     * runways, taxiways and labels in light ink, readable over the chart, the satellite or the night.
     */
    private fun nightInk(src: android.graphics.Bitmap): android.graphics.Bitmap {
        val w = src.width; val h = src.height
        val px = IntArray(w * h)
        src.getPixels(px, 0, w, 0, 0, w, h)
        src.recycle()
        for (i in px.indices) {
            val c = px[i]
            val r = (c shr 16) and 0xFF; val g = (c shr 8) and 0xFF; val b = c and 0xFF
            val ink = 255 - (r * 30 + g * 59 + b * 11) / 100          // 0 paper … 255 black ink
            val k = (ink * 1.3f).coerceAtMost(255f) / 255f
            val a = 0xF2
            val cr = (0x14 + (0xF2 - 0x14) * k).toInt(); val cg = (0x18 + (0xF6 - 0x18) * k).toInt(); val cb = (0x22 + (0xFF - 0x22) * k).toInt()
            px[i] = (a shl 24) or (cr shl 16) or (cg shl 8) or cb
        }
        return android.graphics.Bitmap.createBitmap(px, w, h, android.graphics.Bitmap.Config.ARGB_8888)
    }

    /**
     * Plates on maps, as ForeFlight has them: zoomed in, every airport on the screen shows its
     * official FAA diagram where it really lies (from the latitude and longitude printed on its
     * border, turned north up when printed turned). The menu item turns it on and off.
     */
    private fun plateOnMap() {
        val on = !prefs.getBoolean("auto_diagrams", true) || diagrams.isEmpty()
        prefs.edit().putBoolean("auto_diagrams", on).apply()
        if (!on) { map.overlays.removeAll(diagrams.values.toSet()); diagrams.clear(); insetOv.insets.clear(); insetOv.hidden.clear(); insetOv.pinned = null; noDiagram.clear(); map.invalidate(); return }
        // As ForeFlight does it: go to the nearest field that has a diagram and fill the screen with it.
        val c = ownship.position() ?: map.mapCenter as GeoPoint
        val near = airports.map { it to Nav.distanceNm(c.latitude, c.longitude, it.lat, it.lon) }
            .filter { it.second <= 30 }.sortedBy { it.second }.map { it.first }.take(10)
        Toast.makeText(this, getString(R.string.apt_plates_loading), Toast.LENGTH_SHORT).show()
        diagramsBusy = true
        lifecycleScope.launch {
            var shown: GeoPoint? = null; var box: org.osmdroid.util.BoundingBox? = null
            for (a in near) {
                if (a.ident in diagrams) { box = diagramBoxes[a.ident]; shown = GeoPoint(a.lat, a.lon) }
                if (box != null) break
                if (a.ident in noDiagram) continue
                val made = withContext(Dispatchers.IO) { buildDiagram(a) }
                if (made == null) { noDiagram += a.ident; continue }
                addDiagram(a.ident, made)
                box = org.osmdroid.util.BoundingBox(made.second.latitude, made.third.longitude, made.third.latitude, made.second.longitude)
                shown = GeoPoint(a.lat, a.lon)
                break
            }
            diagramsBusy = false
            val bb = box
            if (bb == null) { Toast.makeText(this@MapActivity, R.string.plate_on_map_none, Toast.LENGTH_LONG).show(); return@launch }
            // No zoom needed: the card shows it big beside the field.
            map.invalidate()
            map.postDelayed({ autoDiagrams() }, 1200)
        }
    }

    private fun addDiagram(ident: String, made: Triple<android.graphics.Bitmap, GeoPoint, GeoPoint>) {
        val o = org.osmdroid.views.overlay.GroundOverlay().apply {
            image = made.first
            setPosition(made.second, made.third)
            transparency = 0f
        }
        // Under the aircraft, the route and traffic.
        map.overlays.add(1.coerceAtMost(map.overlays.size), o)
        diagrams[ident] = o
        diagramBoxes[ident] = org.osmdroid.util.BoundingBox(made.second.latitude, made.third.longitude, made.third.latitude, made.second.longitude)
        airports.firstOrNull { it.ident == ident }?.let { a ->
            insetOv.insets[a.icao.ifEmpty { a.ident }] = DiagramInsetOverlay.Inset(a.icao.ifEmpty { a.ident }, made.first, made.second.latitude, made.second.longitude,
                made.third.latitude, made.third.longitude, a.lat, a.lon)
        }
        map.invalidate()
    }

    /** Lays the diagrams of the airports now on the screen, a few at a time, nearest the centre first. */
    private fun autoDiagrams() {
        // Seen only close in: from afar a diagram is a stamp on the chart.
        val close = map.zoomLevelDouble >= insetOv.closeZoom
        for (o in diagrams.values) o.isEnabled = close
        if (!prefs.getBoolean("auto_diagrams", true) || diagramsBusy || map.zoomLevelDouble < 9.0) return
        val bb = map.boundingBox; val c = map.mapCenter
        val want = airports.filter { it.lat in bb.latSouth..bb.latNorth && it.lon in bb.lonWest..bb.lonEast && it.ident !in diagrams && it.ident !in noDiagram }
            .sortedBy { Nav.distanceNm(c.latitude, c.longitude, it.lat, it.lon) }.take(if (close) 3 else 2)
        if (want.isEmpty()) return
        diagramsBusy = true
        lifecycleScope.launch {
            for (a in want) {
                val made = withContext(Dispatchers.IO) { buildDiagram(a) }
                if (made == null) { noDiagram += a.ident; continue }
                addDiagram(a.ident, made)
                // Memory: keep the nearest six.
                while (diagrams.size > 6) {
                    val cc = map.mapCenter
                    val far = diagrams.keys.filter { k -> airports.firstOrNull { it.ident == k }?.let { it.icao.ifEmpty { it.ident } } != insetOv.pinned }.maxByOrNull { k -> airports.firstOrNull { it.ident == k }?.let { Nav.distanceNm(cc.latitude, cc.longitude, it.lat, it.lon) } ?: 0.0 } ?: break
                    insetOv.insets.remove(airports.firstOrNull { it.ident == far }?.let { it.icao.ifEmpty { it.ident } } ?: far)
                    diagrams.remove(far)?.let { map.overlays.remove(it); it.image?.recycle() }
                }
                map.invalidate()
            }
            diagramsBusy = false
        }
    }

    /**
     * One field's FAA diagram as ForeFlight lays plates on maps: only the airport, cut along the
     * chart's own latitude/longitude grid (no title, frequencies or notes), drawn sharp at the size
     * it will be seen, on paper by day and dark by night; null when it has none or no printed scale.
     */
    private fun buildDiagram(cand: AviationData.Airport): Triple<android.graphics.Bitmap, GeoPoint, GeoPoint>? = try {
        val res = AviationData.plates(this@MapActivity, cand.ident)
        val apd = res?.second?.firstOrNull { it.code == "APD" }
        val f = apd?.let { AviationData.platePdf(this@MapActivity, res.first, it.pdf) }
        val geo = f?.let { PdfLinks.open(this@MapActivity, it)?.use { l -> l.georef(0) } }
        if (f == null || geo == null) null else {
            // The drawing: the page without its edges, title band and footer (the runways often run
            // past the last printed coordinate, so the grid alone would cut them).
            val x0 = 0.04; val x1 = 0.96
            val y0 = if (geo.turn == 0f) 0.085 else 0.05; val y1 = if (geo.turn == 0f) 0.925 else 0.95
            val pfd = android.os.ParcelFileDescriptor.open(f, android.os.ParcelFileDescriptor.MODE_READ_ONLY)
            var bmp = android.graphics.pdf.PdfRenderer(pfd).use { r ->
                r.openPage(0).use { pg ->
                    val pw = pg.width.toDouble(); val ph = pg.height.toDouble()
                    val cw = 1300
                    val s = cw / ((x1 - x0) * pw)
                    val ch = ((y1 - y0) * ph * s).toInt().coerceIn(200, 2600)
                    android.graphics.Bitmap.createBitmap(cw, ch, android.graphics.Bitmap.Config.ARGB_8888).also {
                        it.eraseColor(android.graphics.Color.WHITE)
                        val m = android.graphics.Matrix().apply {
                            postScale(s.toFloat(), s.toFloat())
                            postTranslate((-x0 * pw * s).toFloat(), (-y0 * ph * s).toFloat())
                        }
                        pg.render(it, null, m, android.graphics.pdf.PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                    }
                }
            }
            val corners = listOf(geo.ground(x0, y0), geo.ground(x1, y0), geo.ground(x1, y1), geo.ground(x0, y1))
            val north = corners.maxOf { it[0] }; val south = corners.minOf { it[0] }
            val west = corners.minOf { it[1] }; val east = corners.maxOf { it[1] }
            val turn = -geo.turn
            if (turn != 0f) bmp = android.graphics.Bitmap.createBitmap(bmp, 0, 0, bmp.width, bmp.height,
                android.graphics.Matrix().apply { postRotate(turn) }, true)
            Triple(bmp, GeoPoint(north, west), GeoPoint(south, east))
        }
    } catch (e: Throwable) { null }

    private var tankReminded = 0

    /** Fuel left from the fuel on board and the burn, and a reminder every 30 minutes to check fuel and switch tanks. */
    private fun fuelWatch() {
        if (!FlightRecorder.inProgress(this)) return
        val min = FlightRecorder.airborneMinutes(this)
        val left = plan.fuelOnBoard - plan.gph * min / 60
        val endurance = if (plan.gph > 0) left / plan.gph * 60 else 0.0
        if (timerStart == 0L) b.toolbar.subtitle = "⛽ %.1f gal · %s".format(left.coerceAtLeast(0.0), FlightPlan.hm(endurance))
        if (prefs.getBoolean("tank_reminder", true) && min >= (tankReminded + 1) * 30) {
            tankReminded = (min / 30).toInt()
            alert("⛽ FUEL CHECK · %.1f gal left".format(left), getString(R.string.fuel_tank_note))
            Voice.say(this, "fuel$tankReminded", "Fuel check. About ${Math.max(0, left.toInt())} gallons left. Consider switching tanks.", 600)
        }
        if (left < plan.gph * 0.5 + 0.01) Voice.say(this, "fuel_low", "Warning. Fuel reserve.", 300)
    }

    /** One tap in an emergency: the essentials, the nearest airports within gliding distance, and the checklist. */
    private fun emergency() {
        val here = ownship.position() ?: map.mapCenter as GeoPoint
        val alt = ownship.fix?.takeIf { it.hasAltitude() && gotGps }?.altitude?.times(3.28084)
        val list = airports.sortedBy { Nav.distanceNm(here.latitude, here.longitude, it.lat, it.lon) }.take(4)
        val rows = list.map { a ->
            val d = Nav.distanceNm(here.latitude, here.longitude, a.lat, a.lon)
            val brg = Nav.magnetic(Nav.bearingTrue(here.latitude, here.longitude, a.lat, a.lon), here.latitude, here.longitude)
            val glide = alt?.let { (it - a.elevation) / 1000 * 1.5 }
            "${if (glide != null && d <= glide) "🟢" else if (glide != null) "🔴" else "•"} ${a.icao.ifEmpty { a.ident }}  ${Nav.deg(brg)}M  %.1f nm".format(d)
        }
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.sos_title)
            .setItems((listOf(getString(R.string.sos_essentials), getString(R.string.sos_checklist)) + rows).toTypedArray()) { _, i ->
                when (i) {
                    0 -> {}
                    1 -> startActivity(android.content.Intent(this, ChecklistActivity::class.java).putExtra("emergency", true))
                    else -> {
                        val a = list[i - 2]
                        directTo(FlightPlan.Waypoint(a.icao.ifEmpty { a.ident }, a.lat, a.lon))
                        if (!following) follow()
                    }
                }
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    // ---- staying out of trouble ----

    private val warned = HashSet<String>()
    private var banner: android.widget.TextView? = null

    /** Inside a TFR or SIGMET, or about to be within five minutes along the track: a red banner and a buzz. */
    private fun checkAirspace(l: Location) {
        val kt = if (l.hasSpeed()) l.speed * 1.943844 else 0.0
        val probes = mutableListOf(0.0)
        if (kt > 30 && l.hasBearing()) probes.addAll(listOf(2.0, 5.0))
        for (min in probes) {
            val p = if (min == 0.0) GeoPoint(l.latitude, l.longitude) else Nav.destination(l.latitude, l.longitude, l.bearing.toDouble(), kt * min / 60)
            val hit = (weather.tfrs + weather.areas.filter { it.kind == "SIGMET" }).firstOrNull { it.contains(p.latitude, p.longitude) } ?: continue
            val key = hit.text + (min == 0.0)
            if (!warned.add(key)) return
            alert(if (min == 0.0) "⛔ INSIDE ${hit.label}" else "⚠️ ${hit.label} AHEAD · ${min.toInt()} MIN", hit.text)
            Voice.say(this, "air" + key, if (min == 0.0) "Warning. Inside ${hit.kind}." else "Caution. ${hit.kind} ahead, ${min.toInt()} minutes.", 120)
            return
        }
    }

    private fun alert(title: String, detail: String) {
        val v = banner ?: android.widget.TextView(this).apply {
            setBackgroundColor(0xFFC62828.toInt())
            setTextColor(0xFFFFFFFF.toInt())
            textSize = 16f
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            gravity = android.view.Gravity.CENTER
            setPadding(dp(12), dp(8), dp(12), dp(8))
            setOnClickListener { MaterialAlertDialogBuilder(this@MapActivity).setMessage(tag as? String ?: "").setPositiveButton(android.R.string.ok, null).show() }
            b.topBar.addView(this)
            banner = this
        }
        v.text = title
        v.tag = detail
        v.visibility = View.VISIBLE
        v.alpha = 0f
        v.animate().alpha(1f).setDuration(200).start()
        (getSystemService(VIBRATOR_SERVICE) as? android.os.Vibrator)?.let {
            try { it.vibrate(android.os.VibrationEffect.createWaveform(longArrayOf(0, 300, 150, 300, 150, 300), -1)) } catch (e: Exception) {}
        }
        b.root.removeCallbacks(hideBanner)
        b.root.postDelayed(hideBanner, 15000)
    }

    private val hideBanner = Runnable { banner?.animate()?.alpha(0f)?.setDuration(400)?.withEndAction { banner?.visibility = View.GONE }?.start() }

    /** The nearest airports, the ones within gliding distance marked green; a tap flies direct. */
    private fun nearest() {
        val here = ownship.position() ?: map.mapCenter as GeoPoint
        val fix = ownship.fix
        val gs = ownship.speedKt()
        val altFt = fix?.takeIf { it.hasAltitude() && gotGps }?.altitude?.times(3.28084)
        val list = airports.sortedBy { Nav.distanceNm(here.latitude, here.longitude, it.lat, it.lon) }.take(15)
        if (list.isEmpty()) return
        val rows = list.map { a ->
            val d = Nav.distanceNm(here.latitude, here.longitude, a.lat, a.lon)
            val brg = Nav.magnetic(Nav.bearingTrue(here.latitude, here.longitude, a.lat, a.lon), here.latitude, here.longitude)
            // About 1.5 nm for each 1000 ft above the field, at best glide.
            val glide = altFt?.let { (it - a.elevation) / 1000 * 1.5 }
            val cat = airportsLayer.weather[airportsLayer.station(a)]?.category ?: ""
            val mark = when {
                glide == null -> "•"
                d <= glide -> "🟢"
                d <= glide * 1.3 -> "🟡"
                else -> "🔴"
            }
            "$mark ${a.icao.ifEmpty { a.ident }}  ${Nav.deg(brg)}M  %.1f nm".format(d) +
                (if (gs > 30) "  ${FlightPlan.hm(d / gs * 60)}" else "") + (if (cat.isNotEmpty()) "  $cat" else "")
        }
        MaterialAlertDialogBuilder(this)
            .setTitle(getString(R.string.nrst_title) + (altFt?.let { " · %,d ft".format(Math.round(it)) } ?: ""))
            .setItems(rows.toTypedArray()) { _, i ->
                val a = list[i]
                directTo(FlightPlan.Waypoint(a.icao.ifEmpty { a.ident }, a.lat, a.lon))
                if (!following) follow()
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    /** The airports of the route, the home field, and those within 8 nm of the line. */
    private fun routeAirports(): List<AviationData.Airport> {
        val out = LinkedHashSet<AviationData.Airport>()
        val home = prefs.getString("efb_home", "KBVU")!!
        airports.firstOrNull { it.icao == home || it.ident == home }?.let { out.add(it) }
        for (w in plan.points) airports.firstOrNull { it.icao == w.id || it.ident == w.id }?.let { out.add(it) }
        for (i in 1 until plan.points.size) {
            val a = plan.points[i - 1]; val c = plan.points[i]
            val steps = (Nav.distanceNm(a.lat, a.lon, c.lat, c.lon) / 5).toInt().coerceAtLeast(1)
            for (k in 0..steps) {
                val lat = a.lat + (c.lat - a.lat) * k / steps
                val lon = a.lon + (c.lon - a.lon) * k / steps
                airports.filter { Nav.distanceNm(lat, lon, it.lat, it.lon) < 8 }.forEach { out.add(it) }
            }
        }
        if (plan.points.size < 2) {
            val bb = map.boundingBox
            airports.filter { it.lat in bb.latSouth..bb.latNorth && it.lon in bb.lonWest..bb.lonEast }.take(15).forEach { out.add(it) }
        }
        return out.toList()
    }

    /** Before the flight, on Wi-Fi: the pilot picks what to save, for which airports, and which charts along the way. */
    private fun packFlight() {
        val list = routeAirports()
        val what = arrayOf(getString(R.string.pack_plates), getString(R.string.pack_cs), getString(R.string.pack_info),
            getString(R.string.pack_diagram), getString(R.string.pack_charts_route))
        val on = BooleanArray(what.size) { prefs.getBoolean("pack_$it", true) }
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.pack_title)
            .setMultiChoiceItems(what, on) { _, i, v -> on[i] = v }
            .setPositiveButton(R.string.pack_next) { _, _ ->
                prefs.edit().apply { on.forEachIndexed { i, v -> putBoolean("pack_$i", v) } }.apply()
                if (on.take(4).any { it } && list.isNotEmpty()) pickAirports(list) { chosen -> pickCharts(on, chosen) } else pickCharts(on, emptyList())
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun pickAirports(list: List<AviationData.Airport>, then: (List<AviationData.Airport>) -> Unit) {
        val names = list.map { "${it.icao.ifEmpty { it.ident }}  ${it.name}" }.toTypedArray()
        val on = BooleanArray(list.size) { true }
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.pack_airports)
            .setMultiChoiceItems(names, on) { _, i, v -> on[i] = v }
            .setPositiveButton(R.string.pack_next) { _, _ -> then(list.filterIndexed { i, _ -> on[i] }) }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun pickCharts(parts: BooleanArray, airportsChosen: List<AviationData.Airport>) {
        if (!parts[4]) { runPack(parts, airportsChosen, emptyList()); return }
        val layers = AviationData.LAYERS
        val names = layers.map { getString(it.label) }.toTypedArray()
        val on = BooleanArray(layers.size) { layers[it] == layer }
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.pack_which_charts)
            .setMultiChoiceItems(names, on) { _, i, v -> on[i] = v }
            .setPositiveButton(R.string.map_download_go) { _, _ -> runPack(parts, airportsChosen, layers.filterIndexed { i, _ -> on[i] }) }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun runPack(parts: BooleanArray, chosen: List<AviationData.Airport>, charts: List<AviationData.Layer>) {
        val status = android.widget.TextView(this).apply { setPadding(dp(24), dp(16), dp(24), dp(8)); textSize = 15f }
        var stop = false
        val d = MaterialAlertDialogBuilder(this).setTitle(R.string.pack_title).setView(status)
            .setNegativeButton(R.string.cancel) { _, _ -> stop = true }.setCancelable(false).show()
        val what = OfflinePack.Parts(plates = parts[0], supplement = parts[1], info = parts[2], diagram = parts[3])
        lifecycleScope.launch {
            var files = 0
            for ((i, a) in chosen.withIndex()) {
                if (stop) break
                files += withContext(Dispatchers.IO) {
                    OfflinePack.airport(this@MapActivity, a, what) { step -> runOnUiThread { status.text = "${i + 1}/${chosen.size}  $step" } }
                }
            }
            if (!stop) ChartUpdates.rememberAirports(this@MapActivity, chosen.map { it.icao.ifEmpty { it.ident } }, what)
            // Terrain for awareness, synthetic vision and the profile, along the route.
            val tpts = if (plan.points.size > 1) plan.points else chosen.map { FlightPlan.Waypoint(it.ident, it.lat, it.lon) }
            if (tpts.isNotEmpty()) withContext(Dispatchers.IO) {
                runOnUiThread { status.text = getString(R.string.pack_terrain) }
                Terrain.prefetch(tpts.minOf { it.lat } - 0.3, tpts.minOf { it.lon } - 0.4, tpts.maxOf { it.lat } + 0.3, tpts.maxOf { it.lon } + 0.4)
            }
            d.dismiss()
            if (stop) return@launch
            val writer = (map.tileProvider as? org.osmdroid.tileprovider.MapTileProviderBasic)?.tileWriter
            var tiles = 0
            // The satellite photo of each airport, close in, for the airport view without signal.
            if (what.diagram && writer != null) {
                val imagery = AviationData.LAYERS.first { it.key == "imagery" }
                for (a in chosen) try {
                    val box = org.osmdroid.util.BoundingBox(a.lat + 0.02, a.lon + 0.025, a.lat - 0.02, a.lon - 0.025)
                    val cm = CacheManager(imagery.source(), writer, 12, 17)
                    tiles += cm.possibleTilesInArea(box, 12, 17)
                    cm.downloadAreaAsyncNoUI(this@MapActivity, box, 12, 17, quietCallback)
                } catch (e: Exception) {
                }
            }
            // The chosen charts along the route, from overview to their finest scale.
            if (charts.isNotEmpty() && writer != null) {
                val pts = if (plan.points.size > 1) plan.points.map { GeoPoint(it.lat, it.lon) } else listOf(map.mapCenter as GeoPoint)
                val box = org.osmdroid.util.BoundingBox(
                    pts.maxOf { it.latitude } + 0.25, pts.maxOf { it.longitude } + 0.3,
                    pts.minOf { it.latitude } - 0.25, pts.minOf { it.longitude } - 0.3,
                )
                for (l in charts) try {
                    ChartUpdates.rememberArea(this@MapActivity, l.key, box, 6, l.maxZoom)
                    val cm = CacheManager(l.source(), writer, 6, l.maxZoom)
                    tiles += cm.possibleTilesInArea(box, 6, l.maxZoom)
                    cm.downloadAreaAsyncNoUI(this@MapActivity, box, 6, l.maxZoom, quietCallback)
                } catch (e: Exception) {
                }
            }
            Toast.makeText(this@MapActivity, getString(R.string.pack_done2, files, tiles), Toast.LENGTH_LONG).show()
        }
    }

    private val quietCallback = object : CacheManager.CacheManagerCallback {
        override fun onTaskComplete() {}
        override fun updateProgress(progress: Int, currentZoomLevel: Int, zoomMin: Int, zoomMax: Int) {}
        override fun downloadStarted() {}
        override fun setPossibleTilesInArea(total: Int) {}
        override fun onTaskFailed(errors: Int) {}
    }

    /** The route from the side: the ground along it against the planned altitude, and the aircraft on it. */
    private fun profile() {
        if (plan.points.size < 2) {
            Toast.makeText(this, R.string.plan_empty, Toast.LENGTH_LONG).show()
            return
        }
        val v = ProfileView(this, plan).apply { minimumHeight = dp(340) }
        ownship.position()?.let { here ->
            // Where along the route the aircraft is: distance flown to the nearest point of it.
            var best = Double.MAX_VALUE; var along = 0.0; var at = 0.0
            for (i in 1 until plan.points.size) {
                val a = plan.points[i - 1]; val c = plan.points[i]
                val len = Nav.distanceNm(a.lat, a.lon, c.lat, c.lon)
                var s = 0.0
                while (s <= len) {
                    val g = Nav.destination(a.lat, a.lon, Nav.bearingTrue(a.lat, a.lon, c.lat, c.lon), s)
                    val dd = Nav.distanceNm(here.latitude, here.longitude, g.latitude, g.longitude)
                    if (dd < best) { best = dd; along = at + s }
                    s += 0.5
                }
                at += len
            }
            if (best < 5) {
                v.aircraftNm = along
                v.aircraftFt = ownship.fix?.takeIf { it.hasAltitude() }?.altitude?.times(3.28084)
            }
        }
        MaterialAlertDialogBuilder(this)
            .setTitle(getString(R.string.map_profile) + " · %,d ft".format(plan.altitude))
            .setView(v)
            .setPositiveButton(android.R.string.ok, null)
            .show()
        Thread { v.sample() }.start()
    }

    /** Every Chart Supplement page of Nevada and California, on the phone for good (about 50 MB). */
    private fun supplementsWest() {
        val list = airports.filter { it.lat in 32.4..42.1 && it.lon in -124.6..-114.0 }
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.cs_bulk)
            .setMessage(getString(R.string.cs_bulk_msg, list.size))
            .setPositiveButton(R.string.map_download_go) { _, _ ->
                val status = android.widget.TextView(this).apply { setPadding(dp(24), dp(16), dp(24), dp(8)); textSize = 15f }
                var stop = false
                val d = MaterialAlertDialogBuilder(this).setTitle(R.string.cs_bulk).setView(status)
                    .setNegativeButton(R.string.cancel) { _, _ -> stop = true }.setCancelable(false).show()
                lifecycleScope.launch {
                    var got = 0
                    for ((i, a) in list.withIndex()) {
                        if (stop) break
                        status.text = "${i + 1}/${list.size}  ${a.icao.ifEmpty { a.ident }}  ·  $got ✓"
                        if (withContext(Dispatchers.IO) { OfflinePack.supplement(this@MapActivity, a.ident, a.icao) }.isNotEmpty()) got++
                    }
                    d.dismiss()
                    Toast.makeText(this@MapActivity, getString(R.string.cs_bulk_done, got), Toast.LENGTH_LONG).show()
                }
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    /** The weather along the route: each airport's METAR and TAF, and every SIGMET, AIRMET and TFR the line crosses. */
    private fun briefing() {
        if (plan.points.size < 2) {
            Toast.makeText(this, R.string.plan_empty, Toast.LENGTH_LONG).show()
            return
        }
        val text = android.widget.TextView(this).apply {
            typeface = android.graphics.Typeface.MONOSPACE
            textSize = 12f
            setTextIsSelectable(true)
            layoutDirection = View.LAYOUT_DIRECTION_LTR
            textDirection = View.TEXT_DIRECTION_LTR
            setPadding(dp(14), dp(8), dp(14), dp(8))
            this.text = getString(R.string.map_loading_wx)
        }
        MaterialAlertDialogBuilder(this).setTitle(R.string.brief_title)
            .setView(android.widget.ScrollView(this).apply { addView(text) })
            .setPositiveButton(android.R.string.ok, null).show()
        val stations = plan.points.mapNotNull { w -> airports.firstOrNull { it.icao == w.id || it.ident == w.id }?.let { airportsLayer.station(it) } }.distinct()
        lifecycleScope.launch {
            val sb = StringBuilder(plan.points.joinToString(" ") { it.id }).append("\n\n")
            for (st in stations) {
                val (m, t) = withContext(Dispatchers.IO) { AviationData.metar(st) to AviationData.taf(st) }
                sb.append("■ $st ${m?.category ?: ""}\n${m?.raw ?: "no METAR"}\n${t ?: ""}\n\n")
            }
            val hazards = LinkedHashSet<String>()
            for (i in 1 until plan.points.size) {
                val a = plan.points[i - 1]; val c = plan.points[i]
                val steps = (Nav.distanceNm(a.lat, a.lon, c.lat, c.lon) / 3).toInt().coerceAtLeast(1)
                for (k in 0..steps) {
                    val lat = a.lat + (c.lat - a.lat) * k / steps
                    val lon = a.lon + (c.lon - a.lon) * k / steps
                    (weather.areas + weather.tfrs).filter { it.contains(lat, lon) }.forEach { hazards.add(it.text) }
                }
            }
            sb.append(if (hazards.isEmpty()) "✅ No SIGMET, AIRMET or TFR on the route line.\n" else "⚠️ ON THE ROUTE\n\n" + hazards.joinToString("\n\n────\n\n"))
            sb.append("\n\nCheck NOTAMs and get an official briefing (1800wxbrief.com).")
            text.text = sb.toString()
        }
    }

    private fun offerLog(e: LogEntry) {
        // Into the logbook at once: a flight is never lost to a closed dialog or a killed app.
        Logbook.keepRecorded(this, e)
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.log_flight_done)
            .setMessage("${e.from} → ${e.to}\n%.1f h · ${e.dayLdg} ldg · %.0f nm\n\n✓ ".format(e.total, e.distanceNm) + getString(R.string.log_saved_auto))
            .setPositiveButton(R.string.log_edit) { _, _ ->
                startActivity(android.content.Intent(this, LogbookActivity::class.java).putExtra(LogbookActivity.EXTRA_EDIT, e.id))
            }
            .setNegativeButton(android.R.string.ok, null)
            .show()
    }

    /**
     * The position button, one tap at a time, as on ForeFlight:
     * free chart → follow, north up → track up, centred → track up, ahead (the aircraft low, the way ahead in view) → free.
     */
    private fun cycleView() {
        val mode = when { !following -> 0; !trackUp -> 1; !ahead -> 2; else -> 3 }
        when ((mode + 1) % 4) {
            0 -> { trackUp = false; ahead = false; if (following) follow(); map.mapOrientation = 0f; viewToast("✋ " + getString(R.string.map_view_free)) }
            1 -> { trackUp = false; ahead = false; map.mapOrientation = 0f; if (!following) follow(quiet = true); viewToast("📍 " + getString(R.string.map_view_north)) }
            2 -> { trackUp = true; ahead = false; if (!following) follow(quiet = true); viewToast("🧭 " + getString(R.string.map_view_track)) }
            3 -> { trackUp = true; ahead = true; if (!following) follow(quiet = true); viewToast("✈︎ " + getString(R.string.map_view_ahead)) }
        }
        b.fabLocate.setImageResource(viewIcon())
        keepView()
    }

    private fun viewIcon() = when { ahead && trackUp -> R.drawable.ic_track_ahead; trackUp -> R.drawable.ic_compass; else -> R.drawable.ic_my_location }

    private var viewToastShown: Toast? = null
    private fun viewToast(t: String) { viewToastShown?.cancel(); viewToastShown = Toast.makeText(this, t, Toast.LENGTH_SHORT).also { it.show() } }

    /** The way the chart was being flown, kept: back from notes, the radio or traffic, it is the same. */
    private fun keepView() = prefs.edit().putBoolean("view_follow", following).putBoolean("view_track", trackUp).putBoolean("view_ahead", ahead)
        .putBoolean("track_up_on", trackUp).apply()

    private fun follow(quiet: Boolean = false) {
        following = !following
        ownship.position()?.let { if (following) map.controller.animateTo(it) }
        if (following && map.zoomLevelDouble < 9) map.controller.setZoom(10.0)
        if (!following) map.mapOrientation = 0f
        b.fabLocate.alpha = if (following) 1f else 0.6f
        // Track up, once ticked, stays: panning the chart lets go of the aircraft, not of the track.
        if (!following && !prefs.getBoolean("track_up_on", false)) { trackUp = false; ahead = false }
        b.fabLocate.setImageResource(viewIcon())
        keepView()
        if (!quiet) Toast.makeText(this, if (following) "📍 ${getString(R.string.map_follow)}" else "✋", Toast.LENGTH_SHORT).show()
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
        // As iPadOS's tool palette: a capsule floating over the chart, dragged by its grip anywhere, its place kept.
        val grip = TextView(this).apply { text = "⋮⋮"; textSize = 16f; setTextColor(0xFF8E8E93.toInt()); setPadding(dp(10), dp(8), dp(6), dp(8)) }
        bar.addView(grip)
        var gx = 0f; var gy = 0f; var px = 0f; var py = 0f
        grip.setOnTouchListener { _, e ->
            when (e.actionMasked) {
                android.view.MotionEvent.ACTION_DOWN -> { gx = e.rawX; gy = e.rawY; px = b.penBar.translationX; py = b.penBar.translationY }
                android.view.MotionEvent.ACTION_MOVE -> { b.penBar.translationX = px + e.rawX - gx; b.penBar.translationY = py + e.rawY - gy }
                android.view.MotionEvent.ACTION_UP -> prefs.edit().putFloat("pen_x", b.penBar.translationX).putFloat("pen_y", b.penBar.translationY).apply()
            }
            true
        }
        b.root.post {
            // Out of the bottom row, floating above everything on the chart.
            (b.penBar.parent as? android.view.ViewGroup)?.removeView(b.penBar)
            b.root.addView(b.penBar, android.widget.FrameLayout.LayoutParams(-2, -2, Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL).apply {
                bottomMargin = stripHeight() + dp(90); leftMargin = dp(10); rightMargin = dp(10)
            })
            b.penBar.elevation = dp(16).toFloat()
            b.penBar.translationX = prefs.getFloat("pen_x", 0f); b.penBar.translationY = prefs.getFloat("pen_y", 0f)
        }
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
        // The pen: a long press, or a tap when it is in hand, picks the kind of pen.
        draw.penStyle = prefs.getInt("map_pen_style", 0)
        fun penKinds() = PenInk.choose(this, draw.penStyle, onLaser = { LaserLayer.start(this) }) { i ->
            draw.penStyle = i
            prefs.edit().putInt("map_pen_style", i).apply()
            pick(MapDrawOverlay.MapTool.PEN)
        }
        toolButtons[MapDrawOverlay.MapTool.PEN]?.setOnClickListener { if (draw.tool == MapDrawOverlay.MapTool.PEN) penKinds() else pick(MapDrawOverlay.MapTool.PEN) }
        toolButtons[MapDrawOverlay.MapTool.PEN]?.setOnLongClickListener { penKinds(); true }
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

    /** Neon that stays: the neon pen on the map, kept with its drawings. */
    override fun neonPen() {
        if (b.penBar.visibility != View.VISIBLE) toggleDrawing()
        draw.penStyle = PenStyle.NEON.ordinal
        prefs.edit().putInt("map_pen_style", draw.penStyle).apply()
        pick(MapDrawOverlay.MapTool.PEN)
    }

    private fun toggleDrawing() {
        val on = b.penBar.visibility != View.VISIBLE
        b.penBar.visibility = if (on) View.VISIBLE else View.GONE
        b.fabs.visibility = View.GONE
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
            is AnnotatedPageView.Edit.Moved -> {}
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
            is AnnotatedPageView.Edit.Moved -> {}
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
        // On the bar: search, nearest, the radio, the panel.
        menu.add(0, 11, 0, R.string.map_find).setIcon(R.drawable.ic_search).let {
            it.setShowAsAction(MenuItem.SHOW_AS_ACTION_ALWAYS)
            it.icon?.setTint(EfbUi.TEXT)
        }
        menu.add(0, 20, 0, "NRST").setShowAsAction(MenuItem.SHOW_AS_ACTION_ALWAYS)
        menu.add(0, 43, 0, "🎧").setShowAsAction(MenuItem.SHOW_AS_ACTION_ALWAYS)
        menu.add(0, 40, 0, R.string.av_menu).setShowAsAction(MenuItem.SHOW_AS_ACTION_ALWAYS)
        // In flight, first.
        menu.add(0, 3, 0, R.string.map_track_up).setCheckable(true).isChecked = trackUp
        menu.add(0, 42, 0, R.string.traffic_list)
        menu.add(0, 44, 0, R.string.plate_on_map).setCheckable(true).isChecked = prefs.getBoolean("auto_diagrams", true)
        menu.add(0, 47, 0, "✈  Approaches")
        menu.add(0, 48, 0, "📡  Share live tracking").setCheckable(true).isChecked = LiveTrack.on(this)
        menu.add(0, 46, 0, "◎  Range rings").setCheckable(true).isChecked = prefs.getBoolean("rings", true)
        menu.add(0, 37, 0, R.string.glide_menu)
        menu.add(0, 30, 0, R.string.freq_title)
        menu.add(0, 36, 0, R.string.pos_report)
        menu.add(0, 23, 0, R.string.timer_title)
        // Planning.
        menu.add(0, 10, 0, R.string.plan_title)
        menu.add(0, 22, 0, R.string.brief_title)
        menu.add(0, 26, 0, R.string.map_profile)
        menu.add(0, 13, 0, R.string.wx_winds)
        menu.add(0, 12, 0, R.string.wb_title)
        menu.add(0, 31, 0, R.string.notes_title)
        // What the chart shows, and the alerts.
        menu.add(0, 1, 0, R.string.map_airports).setCheckable(true).isChecked = prefs.getBoolean("map_airports", true)
        menu.add(0, 2, 0, R.string.map_measures).setCheckable(true).isChecked = draw.showMeasures
        menu.add(0, 14, 0, R.string.map_sharp).setCheckable(true).isChecked = prefs.getBoolean("map_big", false)
        menu.add(0, 28, 0, R.string.voice_on).setCheckable(true).isChecked = prefs.getBoolean("voice_on", true)
        menu.add(0, 29, 0, R.string.fuel_reminder).setCheckable(true).isChecked = prefs.getBoolean("tank_reminder", true)
        // Before the flight, on Wi-Fi.
        menu.add(0, 21, 0, R.string.pack_title)
        menu.add(0, 4, 0, R.string.map_download)
        menu.add(0, 25, 0, R.string.cs_bulk)
        menu.add(0, 5, 0, R.string.map_aircraft)
        // Clearing.
        menu.add(0, 15, 0, R.string.map_clear_trail)
        menu.add(0, 38, 0, R.string.clear_lines)
        menu.add(0, 6, 0, R.string.map_clear)
        return true
    }

    /** The ticks follow what is on, however it was turned on (the position button, a pan…). */
    override fun onPrepareOptionsMenu(menu: Menu): Boolean {
        menu.findItem(3)?.isChecked = trackUp
        menu.findItem(44)?.isChecked = prefs.getBoolean("auto_diagrams", true)
        menu.findItem(2)?.isChecked = draw.showMeasures
        return super.onPrepareOptionsMenu(menu)
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
                if (!trackUp) { map.mapOrientation = 0f; ahead = false }
                else if (!following) follow(quiet = true)
                keepView()
            }
            4 -> downloadArea()
            10 -> navLog()
            20 -> nearest()
            32 -> ChartUpdates.show(this)
            34 -> { setPilotage(!pilotage); item.isChecked = pilotage }
            35 -> startActivity(android.content.Intent(this, EfbCheckActivity::class.java))
            31 -> if (NotePad.isOpen()) NotePad.close(this) else Notebooks.choose(this, null)
            36 -> positionReport()
            38 -> clearLines()
            40 -> AvionicsPanel.toggle(this)
            42 -> trafficList()
            44 -> { plateOnMap(); item.isChecked = prefs.getBoolean("auto_diagrams", true) }
            47 -> approachMenu()
            48 -> liveTrackMenu()
            46 -> {
                val on = !prefs.getBoolean("rings", true)
                prefs.edit().putBoolean("rings", on).apply(); item.isChecked = on
                map.overlays.remove(rings); if (on) map.overlays.add(rings)
                map.invalidate()
            }
            45 -> svtSplit()
            43 -> RadioPlayer.choose(this)
            41 -> MaterialAlertDialogBuilder(this).setTitle(R.string.map_view_menu).setMessage(R.string.map_view_help).setPositiveButton(android.R.string.ok, null).show()
            37 -> askGlide()
            30 -> {
                val here = ownship.position() ?: map.mapCenter as GeoPoint
                FrequenciesActivity.open(this, null, here.latitude, here.longitude, plan.points.map { it.id })
            }
            21 -> packFlight()
            22 -> briefing()
            26 -> profile()
            27 -> startActivity(android.content.Intent(this, SvtActivity::class.java))
            28 -> { val on = !item.isChecked; item.isChecked = on; prefs.edit().putBoolean("voice_on", on).apply() }
            29 -> { val on = !item.isChecked; item.isChecked = on; prefs.edit().putBoolean("tank_reminder", on).apply() }
            25 -> supplementsWest()
            23 -> { timerStart = if (timerStart == 0L) android.os.SystemClock.elapsedRealtime() else 0L; b.toolbar.subtitle = null }
            24 -> Lang.choose(this)
            11 -> findAirport()
            12 -> openWb()
            13 -> windsAloft()
            14 -> {
                val on = !item.isChecked
                item.isChecked = on
                prefs.edit().putBoolean("map_big", on).apply()
                map.isTilesScaledToDpi = on
                zoomLimit()
                map.invalidate()
            }
            15 -> { ownship.clearTrail(); map.invalidate() }
            16 -> { tilt(!tilted); item.isChecked = tilted }
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

    /** How far in a chart can be read: two to three steps past its printed scale. */
    private fun zoomLimit() {
        // A scanned chart holds about one step of enlargement before its print goes soft; closer in, the airport diagram takes over.
        map.maxZoomLevel = layer.maxZoom + if (layer.maxZoom >= 16) 1.5 else if (map.isTilesScaledToDpi) 0.3 else 1.0
        if (map.zoomLevelDouble > map.maxZoomLevel) map.controller.setZoom(map.maxZoomLevel)
    }

    private var tilted = false

    /** The chart laid down in perspective, the horizon ahead, the aircraft low on the screen. */
    private fun tilt(on: Boolean) {
        tilted = on
        val h = b.mapHolder.height.toFloat().coerceAtLeast(1f)
        map.pivotX = map.width / 2f
        map.pivotY = h
        map.cameraDistance = 12000 * resources.displayMetrics.density
        map.animate().rotationX(if (on) 38f else 0f).scaleX(if (on) 1.55f else 1f).scaleY(if (on) 1.35f else 1f)
            .setDuration(650).setInterpolator(android.view.animation.DecelerateInterpolator()).start()
        b.mapHolder.background = if (on) android.graphics.drawable.GradientDrawable(
            android.graphics.drawable.GradientDrawable.Orientation.TOP_BOTTOM,
            intArrayOf(0xFF0B1A33.toInt(), 0xFF2D5C8A.toInt(), 0xFF9EC3E0.toInt()),
        ) else null
        map.setMapCenterOffset(0, if (on) (h * 0.22f).toInt() else 0)
    }

    /** The cockpit colours: dark bars, glowing buttons, and nothing under the status bar. */
    private fun cockpitLook() {
        window.statusBarColor = EfbUi.BG
        window.navigationBarColor = EfbUi.BG
        b.toolbar.setBackgroundColor(EfbUi.BG)
        b.toolbar.setTitleTextColor(EfbUi.TEXT)
        b.toolbar.navigationIcon?.setTint(EfbUi.TEXT)
        b.toolbar.overflowIcon?.setTint(EfbUi.TEXT)
        b.northUp.backgroundTintList = android.content.res.ColorStateList.valueOf(0xF016213A.toInt())
        b.northUp.imageTintList = null
        b.fabSos.backgroundTintList = android.content.res.ColorStateList.valueOf(0xFFC62828.toInt())
        for (f in listOf(b.fabLayers, b.fabDraw, b.fabLocate, b.zoomIn, b.zoomOut)) {
            f.backgroundTintList = android.content.res.ColorStateList.valueOf(0xF016213A.toInt())
            f.imageTintList = android.content.res.ColorStateList.valueOf(EfbUi.ACCENT)
        }
        androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(b.root) { _, insets ->
            val bars = insets.getInsets(androidx.core.view.WindowInsetsCompat.Type.systemBars())
            b.topBar.setPadding(0, bars.top, 0, 0)
            b.topBar.setBackgroundColor(EfbUi.BG)
            // With the tab bar below, the bar takes the gesture area itself.
            (b.fabs.parent as View).setPadding(0, 0, 0, stripHeight() + if (ForeTabs.wants(this)) 0 else bars.bottom)
            insets
        }
    }

    /** Search by FAA identifier, ICAO code, name or city; the map flies there and opens the airport. */
    private fun findAirport() {
        AirportSearch.show(this, airports, ownship.position() ?: map.mapCenter as GeoPoint) { a -> flyTo(a) }
    }

    private fun flyTo(a: AviationData.Airport) {
        if (following) follow()
        map.controller.animateTo(GeoPoint(a.lat, a.lon), layer.maxZoom.toDouble(), 1400L)
        b.root.postDelayed({ showAirport(a) }, 1300)
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
    companion object {
        const val EXTRA_NAVLOG = "navlog"
        const val EXTRA_AIRPORT = "airport"
        const val EXTRA_PROFILE = "profile"
        const val EXTRA_NRST = "nrst"
    }

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
                ChartUpdates.rememberArea(this, layer.key, bb, zMin, zMax)
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
