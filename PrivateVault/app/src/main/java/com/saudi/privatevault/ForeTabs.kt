package com.saudi.privatevault

import android.app.Activity
import android.content.Intent
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat

/**
 * The tab bar along the bottom of every flight-bag screen, as ForeFlight's: Airports, Maps, Plates,
 * Documents, Imagery, Flights, ScratchPads, Checklist, Logbook, More. A tab brings its screen back as
 * it was left (the map keeps flying its track), instead of starting it again.
 */
object ForeTabs {
    private const val TAG = "fore_tabs"

    private class Tab(val icon: Int, val label: Int, val owns: (Activity) -> Boolean, val go: (Activity) -> Unit)

    private fun open(a: Activity, c: Class<*>, extra: (Intent) -> Unit = {}) {
        val i = Intent(a, c).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)
        extra(i)
        a.startActivity(i)
        a.overridePendingTransition(0, 0)
    }

    private val TABS = listOf(
        Tab(R.drawable.ic_tab_airports, R.string.ff_airports, { it is AirportsActivity }) { a -> open(a, AirportsActivity::class.java) },
        Tab(R.drawable.ic_map, R.string.ff_maps, { it is MapActivity }) { a -> open(a, MapActivity::class.java) },
        Tab(R.drawable.ic_tab_plates, R.string.ff_plates, { it is PlatesActivity }) { a -> open(a, PlatesActivity::class.java) },
        Tab(R.drawable.ic_doc, R.string.ff_documents, { it is LibraryActivity || it is ManeuversActivity || it is JeppBookActivity || it is RegsActivity || it is HandbookActivity || it is CfrBrowseActivity }) { a -> open(a, LibraryActivity::class.java) },
        Tab(R.drawable.ic_tab_imagery, R.string.ff_imagery, { it is ImageryActivity }) { a -> open(a, ImageryActivity::class.java) },
        Tab(R.drawable.ic_tab_flights, R.string.ff_flights, { it is WeightBalanceActivity || it is E6bActivity || it is PerformanceActivity }) { a -> open(a, MapActivity::class.java) { it.putExtra(MapActivity.EXTRA_NAVLOG, true) } },
        Tab(R.drawable.ic_fab_pencil, R.string.ff_scratchpads, { it is ScratchPadActivity }) { a -> open(a, ScratchPadActivity::class.java) },
        Tab(R.drawable.ic_check, R.string.ff_checklist, { it is ChecklistActivity }) { a -> open(a, ChecklistActivity::class.java) },
        Tab(R.drawable.ic_tab_logbook, R.string.ff_logbook, { it is LogbookActivity }) { a -> open(a, LogbookActivity::class.java) },
        Tab(R.drawable.ic_more, R.string.ff_more, { it is EfbHomeActivity || it is SettingsActivity || it is FrequenciesActivity || it is EfbCheckActivity || it is TrainerActivity }) { a -> open(a, EfbHomeActivity::class.java) },
    )

    /** Plates: the home field's airport diagram and charts. */
    private fun plates(a: Activity) {
        val home = VaultLock.prefs(a).getString("efb_home", "KBVU") ?: "KBVU"
        Thread {
            val apt = try { AviationData.airports(a).firstOrNull { it.icao == home || it.ident == home || "K" + it.ident == home } } catch (e: Exception) { null }
            a.runOnUiThread { if (apt != null) AirportDiagramActivity.open(a, apt) else open(a, MapActivity::class.java) }
        }.start()
    }

    /** Screens that carry the bar: the flight bag's, not the reader, the player or the vault. */
    fun wants(a: Activity) = !Tv.isTv(a) && (a is EfbHomeActivity || a is MapActivity || a is LogbookActivity || a is ChecklistActivity ||
        a is ScratchPadActivity || a is LibraryActivity || a is SettingsActivity || a is FrequenciesActivity || a is E6bActivity ||
        a is WeightBalanceActivity || a is RegsActivity || a is EfbCheckActivity || a is TrainerActivity || a is AirportDiagramActivity ||
        a is HandbookActivity || a is CfrBrowseActivity || a is ImageryActivity || a is PlatesActivity || a is AirportsActivity || a is PerformanceActivity || a is ManeuversActivity || a is JeppBookActivity || a is WebActivity)

    fun attach(a: Activity) {
        if (!wants(a)) return
        val content = a.findViewById<FrameLayout>(android.R.id.content) ?: return
        if (content.findViewWithTag<View>(TAG) != null) return
        val screen = content.getChildAt(0) ?: return
        val d = a.resources.displayMetrics.density
        fun dp(v: Int) = (v * d).toInt()
        EfbUi.sync(a)
        val bar = LinearLayout(a).apply {
            tag = TAG; orientation = LinearLayout.VERTICAL; setBackgroundColor(EfbUi.BAR); elevation = dp(8).toFloat()
            isClickable = true
        }
        bar.addView(View(a).apply { setBackgroundColor(EfbUi.CARD_LINE) }, LinearLayout.LayoutParams(-1, 1))
        val row = LinearLayout(a).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; layoutDirection = View.LAYOUT_DIRECTION_LTR }
        val scroll = HorizontalScrollView(a).apply { isHorizontalScrollBarEnabled = false; isFillViewport = true; addView(row) }
        bar.addView(scroll, LinearLayout.LayoutParams(-1, dp(56)))
        val w = a.resources.displayMetrics.widthPixels
        // All ten across a tablet; on a phone each tab keeps a thumb's width and the bar slides.
        val cellW = maxOf(w / TABS.size, dp(70))
        var current: View? = null
        for (t in TABS) {
            val on = t.owns(a)
            val color = if (on) EfbUi.ACCENT else EfbUi.DIM
            val cell = LinearLayout(a).apply {
                orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER
                setPadding(0, dp(5), 0, dp(4))
                addView(ImageView(a).apply { setImageResource(t.icon); setColorFilter(color) }, LinearLayout.LayoutParams(dp(24), dp(24)))
                addView(TextView(a).apply {
                    text = a.getString(t.label); textSize = 10.5f; setTextColor(color); gravity = Gravity.CENTER; maxLines = 1
                    if (on) typeface = EfbUi.MEDIUM
                    setPadding(dp(2), dp(3), dp(2), 0)
                }, LinearLayout.LayoutParams(-1, -2))
                if (on) background = GradientDrawable().apply { setColor((EfbUi.ACCENT and 0x00FFFFFF) or 0x1F000000); cornerRadius = dp(12).toFloat() }
                setOnClickListener { if (!on) t.go(a) }
            }
            row.addView(cell, LinearLayout.LayoutParams(cellW, -1).apply { setMargins(dp(2), dp(3), dp(2), dp(3)) })
            if (on) current = cell
        }
        current?.let { c -> scroll.post { scroll.scrollTo((c.left - (scroll.width - c.width) / 2).coerceAtLeast(0), 0) } }
        content.addView(bar, FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM))
        // The screen stops above the bar; the bar sits above the gesture area.
        fun place(navInset: Int) {
            bar.setPadding(0, 0, 0, navInset)
            bar.post {
                (screen.layoutParams as? FrameLayout.LayoutParams)?.let { lp ->
                    // The screen ends where the bar starts: its whole height, the gesture strip included.
                    val want = bar.height
                    if (lp.bottomMargin != want) { lp.bottomMargin = want; screen.layoutParams = lp }
                }
            }
        }
        ViewCompat.setOnApplyWindowInsetsListener(bar) { _, insets ->
            place(insets.getInsets(WindowInsetsCompat.Type.navigationBars()).bottom)
            insets
        }
        place(0)
        ViewCompat.requestApplyInsets(bar)
    }
}
