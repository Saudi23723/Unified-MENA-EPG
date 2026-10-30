package com.saudi.privatevault

import android.app.Activity
import android.app.Dialog
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.BaseAdapter
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ListView
import android.widget.TextView
import org.osmdroid.util.GeoPoint

/**
 * Airport search as you type: the FAA identifier (BVU, L23, 0L7), the ICAO
 * code (KBVU), the name or the city, best matches first, every public
 * airport in the US.
 */
object AirportSearch {

    private fun score(a: AviationData.Airport, q: String): Int {
        val id = a.ident.uppercase()
        val icao = a.icao.uppercase()
        return when {
            id == q || icao == q -> 0
            q.length == 4 && q.startsWith("K") && id == q.substring(1) -> 1
            id.startsWith(q) || icao.startsWith(q) -> 2
            a.name.uppercase().startsWith(q) -> 3
            a.city.uppercase().startsWith(q) -> 4
            a.name.uppercase().contains(q) -> 5
            a.city.uppercase().contains(q) -> 6
            else -> 99
        }
    }

    fun find(airports: List<AviationData.Airport>, query: String, from: GeoPoint?, limit: Int = 60): List<AviationData.Airport> {
        val q = query.trim().uppercase()
        if (q.isEmpty()) {
            return if (from == null) emptyList() else airports.sortedBy { Nav.distanceNm(from.latitude, from.longitude, it.lat, it.lon) }.take(20)
        }
        return airports.asSequence().map { it to score(it, q) }.filter { it.second < 99 }
            .sortedWith(compareBy({ it.second }, { from?.let { f -> Nav.distanceNm(f.latitude, f.longitude, it.first.lat, it.first.lon) } ?: 0.0 }))
            .map { it.first }.take(limit).toList()
    }

    fun show(act: Activity, airports: List<AviationData.Airport>, from: GeoPoint?, onPick: (AviationData.Airport) -> Unit) {
        val d = EfbUi.dp(act, 1)
        val dialog = Dialog(act, android.R.style.Theme_DeviceDefault_NoActionBar)
        val root = LinearLayout(act).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(EfbUi.BG)
            fitsSystemWindows = true
            setPadding(14 * d, 14 * d, 14 * d, 0)
        }
        val input = EditText(act).apply {
            hint = act.getString(R.string.search_hint)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            setTextColor(EfbUi.TEXT)
            setHintTextColor(EfbUi.DIM)
            textSize = 20f
            background = EfbUi.cardBg(act, EfbUi.CARD, 14)
            setPadding(16 * d, 12 * d, 16 * d, 12 * d)
            setSingleLine()
            layoutDirection = View.LAYOUT_DIRECTION_LTR
            textDirection = View.TEXT_DIRECTION_LTR
        }
        root.addView(input, LinearLayout.LayoutParams(-1, -2))
        val count = EfbUi.text(act, "", 12f, EfbUi.DIM).apply { setPadding(4 * d, 8 * d, 4 * d, 4 * d) }
        root.addView(count)
        var results: List<AviationData.Airport> = emptyList()
        val adapter = object : BaseAdapter() {
            override fun getCount() = results.size
            override fun getItem(p: Int) = results[p]
            override fun getItemId(p: Int) = p.toLong()
            override fun getView(p: Int, convert: View?, parent: ViewGroup?): View {
                val a = results[p]
                val row = (convert as? LinearLayout) ?: LinearLayout(act).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.CENTER_VERTICAL
                    layoutDirection = View.LAYOUT_DIRECTION_LTR
                    setPadding(8 * d, 12 * d, 8 * d, 12 * d)
                    addView(EfbUi.text(act, "", 19f, EfbUi.ACCENT, bold = true, mono = true), LinearLayout.LayoutParams(84 * d, -2))
                    addView(LinearLayout(act).apply {
                        orientation = LinearLayout.VERTICAL
                        addView(EfbUi.text(act, "", 15f, EfbUi.TEXT, bold = true))
                        addView(EfbUi.text(act, "", 12f, EfbUi.DIM))
                    }, LinearLayout.LayoutParams(0, -2, 1f))
                    addView(EfbUi.text(act, "", 13f, EfbUi.DIM, mono = true))
                }
                (row.getChildAt(0) as TextView).text = a.ident
                val mid = row.getChildAt(1) as LinearLayout
                (mid.getChildAt(0) as TextView).text = a.name
                (mid.getChildAt(1) as TextView).text = listOf(a.icao.takeIf { it.isNotEmpty() && it != a.ident }, a.city, "%,d ft".format(a.elevation))
                    .filterNotNull().joinToString(" · ")
                (row.getChildAt(2) as TextView).text = from?.let { "%.0f nm".format(Nav.distanceNm(it.latitude, it.longitude, a.lat, a.lon)) } ?: ""
                return row
            }
        }
        val list = ListView(act).apply {
            this.adapter = adapter
            divider = android.graphics.drawable.ColorDrawable(EfbUi.CARD_LINE)
            dividerHeight = 1
            setOnItemClickListener { _, _, p, _ ->
                dialog.dismiss()
                onPick(results[p])
            }
        }
        root.addView(list, LinearLayout.LayoutParams(-1, 0, 1f))
        fun update() {
            results = find(airports, input.text.toString(), from)
            count.text = if (input.text.isBlank()) act.getString(R.string.search_nearby) else act.getString(R.string.search_count, results.size)
            adapter.notifyDataSetChanged()
        }
        input.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            override fun afterTextChanged(s: Editable?) = update()
        })
        input.setOnEditorActionListener { _, _, _ ->
            results.firstOrNull()?.let { dialog.dismiss(); onPick(it) }
            true
        }
        update()
        dialog.setContentView(root)
        dialog.window?.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_STATE_VISIBLE or WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
        dialog.show()
        input.requestFocus()
    }
}
