package com.saudi.privatevault

import android.app.Activity
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView

/**
 * The bar across the top of the chart, laid out the way an electronic flight bag lays it out:
 * the layer button carrying the name of the chart on show, then the flight plan, the map settings,
 * the instrument panel and the saved routes; the search box; and at the far end the button that
 * brings the map back to the aeroplane and stays lit while it follows.
 *
 * It replaces a long written-out menu. Everything that used to be a line of text now sits either
 * on this bar, in the layers sheet, or in the settings sheet behind the gear — three places a pilot
 * can learn, instead of one list to read every time.
 */
class MapToolbar(private val act: Activity, private val host: LinearLayout) {

    private val d = act.resources.displayMetrics.density
    private fun dp(v: Int) = (v * d).toInt()

    private val ink = 0xFFE8EDF3.toInt()
    private val dim = 0xFF93A0AD.toInt()
    private val lit = 0xFF2F80ED.toInt()
    private val chip = 0xFF222A33.toInt()

    var onLayers: (() -> Unit)? = null
    var onFpl: (() -> Unit)? = null
    var onSettings: (() -> Unit)? = null
    var onInstruments: (() -> Unit)? = null
    var onRoutes: (() -> Unit)? = null
    var onSearch: ((String) -> Unit)? = null
    var onCentre: (() -> Unit)? = null
    var onBack: (() -> Unit)? = null

    private var layerBtn: TextView? = null
    private var fplBtn: TextView? = null
    private var centreBtn: TextView? = null
    private var instBtn: TextView? = null

    private fun button(label: String, wide: Boolean = false, go: () -> Unit): TextView =
        TextView(act).apply {
            text = label
            textSize = if (wide) 12.5f else 15f
            setTextColor(ink)
            gravity = Gravity.CENTER
            typeface = if (wide) EfbUi.MEDIUM else Typeface.DEFAULT
            background = GradientDrawable().apply { cornerRadius = dp(7).toFloat(); setColor(chip) }
            setPadding(dp(if (wide) 11 else 9), dp(7), dp(if (wide) 11 else 9), dp(7))
            setOnClickListener { go() }
        }

    /** Builds the bar into its host, replacing whatever was there. */
    fun build(layerName: String) {
        host.removeAllViews()
        host.orientation = LinearLayout.HORIZONTAL
        host.gravity = Gravity.CENTER_VERTICAL
        host.layoutDirection = View.LAYOUT_DIRECTION_LTR
        host.setPadding(dp(6), dp(5), dp(6), dp(5))

        fun add(v: View, marginEnd: Int = 5) = host.addView(v, LinearLayout.LayoutParams(-2, -2).apply { this.marginEnd = dp(marginEnd) })

        onBack?.let { back -> add(button("‹") { back() }) }
        // The chart on show, named on its own button, as the layer menu names it.
        layerBtn = button("≡  $layerName", wide = true) { onLayers?.invoke() }.also { add(it) }
        fplBtn = button("FPL", wide = true) { onFpl?.invoke() }.also { add(it) }
        add(button("⚙") { onSettings?.invoke() })
        instBtn = button("◴") { onInstruments?.invoke() }.also { add(it) }
        add(button("★") { onRoutes?.invoke() })

        val search = EditText(act).apply {
            hint = act.getString(R.string.map_find)
            textSize = 13f
            setTextColor(ink); setHintTextColor(dim)
            setSingleLine()
            background = GradientDrawable().apply { cornerRadius = dp(7).toFloat(); setColor(0xFF1A2129.toInt()) }
            setPadding(dp(10), dp(7), dp(10), dp(7))
            imeOptions = android.view.inputmethod.EditorInfo.IME_ACTION_SEARCH
            setOnEditorActionListener { _, _, _ ->
                onSearch?.invoke(text.toString().trim())
                text.clear()
                clearFocus()
                true
            }
        }
        host.addView(search, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(5) })
        centreBtn = button("⌖") { onCentre?.invoke() }.also { host.addView(it, LinearLayout.LayoutParams(-2, -2)) }
    }

    fun setLayerName(name: String) { layerBtn?.text = "≡  $name" }

    private fun paint(v: TextView?, on: Boolean) {
        v ?: return
        v.setTextColor(if (on) 0xFFFFFFFF.toInt() else ink)
        (v.background as? GradientDrawable)?.setColor(if (on) lit else chip)
    }

    /** The button stays lit while the map is following the aeroplane. */
    fun setCentred(on: Boolean) = paint(centreBtn, on)
    fun setFplOpen(on: Boolean) = paint(fplBtn, on)
    fun setInstruments(on: Boolean) = paint(instBtn, on)
}
