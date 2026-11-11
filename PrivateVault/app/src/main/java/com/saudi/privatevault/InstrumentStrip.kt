package com.saudi.privatevault

import android.content.Context
import android.graphics.Typeface
import android.view.Gravity
import android.view.View
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.TextView

/**
 * The instrument strip across the top of the chart, as on ForeFlight: each box a small label over a
 * big value (GS, GPS ALT, TRK, DTK, BRG, distance and time to the next point and to the destination,
 * VS, GPS accuracy, position). It scrolls sideways; a long press on a box hides or shows it.
 */
class InstrumentStrip(ctx: Context) : HorizontalScrollView(ctx) {
    private val d = ctx.resources.displayMetrics.density
    private val row = LinearLayout(ctx).apply { orientation = LinearLayout.HORIZONTAL; layoutDirection = View.LAYOUT_DIRECTION_LTR }
    private val cells = LinkedHashMap<String, Pair<LinearLayout, TextView>>()
    private val prefs = VaultLock.prefs(ctx)

    init {
        isHorizontalScrollBarEnabled = false
        isFillViewport = true
        addView(row)
        for (k in ORDER) add(k)
    }

    private fun add(key: String) {
        val box = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER
            setPadding((8 * d).toInt(), (2 * d).toInt(), (8 * d).toInt(), (3 * d).toInt())
            minimumWidth = (84 * d).toInt()
        }
        box.addView(TextView(context).apply {
            text = LABEL[key] ?: key; textSize = 10.5f; setTextColor(0xFFB9BCC2.toInt()); gravity = Gravity.CENTER; maxLines = 1
            typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
        })
        val v = TextView(context).apply {
            text = "---"; textSize = 19f; setTextColor(COLOR[key] ?: 0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
            typeface = Typeface.create("sans-serif-medium", Typeface.BOLD); maxLines = 1
        }
        box.addView(v)
        // A thin divider between boxes.
        if (row.childCount > 0) row.addView(View(context).apply { setBackgroundColor(0x33FFFFFF) }, LinearLayout.LayoutParams((1 * d).toInt().coerceAtLeast(1), -1).apply { topMargin = (6 * d).toInt(); bottomMargin = (6 * d).toInt() })
        row.addView(box, LinearLayout.LayoutParams(0, -2, 1f))
        cells[key] = box to v
        box.visibility = if (prefs.getBoolean("strip_$key", key !in OFF)) View.VISIBLE else View.GONE
        box.setOnLongClickListener { choose(); true }
    }

    fun set(key: String, value: String) {
        val v = cells[key]?.second ?: return
        if (v.text != value) v.text = value
    }

    /** Which boxes show: a list to tick, kept. */
    fun choose() {
        val keys = ORDER.toTypedArray()
        val on = BooleanArray(keys.size) { cells[keys[it]]?.first?.visibility == View.VISIBLE }
        com.google.android.material.dialog.MaterialAlertDialogBuilder(context)
            .setTitle(R.string.strip_choose)
            .setMultiChoiceItems(keys.map { "${LABEL[it]} — ${HELP[it]}" }.toTypedArray(), on) { _, i, c -> on[i] = c }
            .setPositiveButton(android.R.string.ok) { _, _ ->
                val e = prefs.edit()
                keys.forEachIndexed { i, k -> e.putBoolean("strip_$k", on[i]); cells[k]?.first?.visibility = if (on[i]) View.VISIBLE else View.GONE }
                e.apply()
            }.show()
    }

    companion object {
        // ForeFlight's own order along the bottom; the rest a long press away.
        val ORDER = listOf("DIS", "ETED", "GS", "ALT", "TRK", "ACC", "VS", "POS", "ETE", "DTK", "BRG", "MH", "DEST", "ETA", "XTK")
        private val OFF = setOf("DTK", "MH", "DEST", "ETA", "XTK")
        private val LABEL = mapOf(
            "GS" to "Groundspeed", "ALT" to "GPS Altitude", "TRK" to "Track", "DTK" to "Desired Track", "BRG" to "Bearing Next", "MH" to "Heading (wind)",
            "DIS" to "Distance Next", "ETE" to "ETE Next", "DEST" to "Distance Dest", "ETED" to "ETE Dest", "ETA" to "ETA Dest",
            "VS" to "Vertical Speed", "XTK" to "Cross Track", "ACC" to "Accuracy", "POS" to "Current Coordinates",
        )
        private val HELP = mapOf(
            "GS" to "groundspeed", "ALT" to "GPS altitude, ft MSL", "TRK" to "track over the ground, magnetic",
            "DTK" to "desired track of the leg, magnetic", "BRG" to "bearing to the next point, magnetic",
            "MH" to "magnetic heading to hold the course in the planned wind", "DIS" to "distance to the next point",
            "ETE" to "time to the next point", "DEST" to "distance to the destination along the route", "ETED" to "time to the destination",
            "ETA" to "arrival time, local", "VS" to "vertical speed", "XTK" to "off course, left or right",
            "ACC" to "GPS accuracy, ft", "POS" to "latitude, longitude",
        )
        // White values as ForeFlight shows them; accuracy green when good.
        private val COLOR = mapOf("ACC" to 0xFF34C759.toInt())
    }
}
