package com.saudi.privatevault

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.os.Bundle
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.widget.ArrayAdapter
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.button.MaterialButton
import com.google.android.material.dialog.MaterialAlertDialogBuilder

/**
 * Weight and balance before a flight: the load at each station, the total
 * weight and CG at takeoff and at landing (after the trip's fuel), and both
 * points on the aircraft's CG envelope.
 */
class WeightBalanceActivity : BaseActivity() {

    private lateinit var aircraft: MutableList<Aircraft>
    private var current = 0
    private lateinit var body: LinearLayout
    private lateinit var result: TextView
    private lateinit var chart: EnvelopeView
    private var burn = 0.0

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        aircraft = Aircraft.all(this)
        current = VaultLock.prefs(this).getInt("wb_current", 0).coerceIn(0, aircraft.size - 1)
        burn = intent.getDoubleExtra(EXTRA_BURN, 0.0)

        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val bar = MaterialToolbar(this).apply {
            title = getString(R.string.wb_title)
            setNavigationIcon(R.drawable.ic_back)
            setNavigationOnClickListener { finish() }
            menu.add(R.string.wb_edit).setOnMenuItemClickListener { editAircraft(); true }
            elevation = dp(4).toFloat()
        }
        root.addView(bar)
        val scroll = ScrollView(this)
        body = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(12), dp(16), dp(24))
        }
        scroll.addView(body)
        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(root)
        result = TextView(this).apply {
            textSize = 15f
            typeface = android.graphics.Typeface.MONOSPACE
            layoutDirection = View.LAYOUT_DIRECTION_LTR
            textDirection = View.TEXT_DIRECTION_LTR
        }
        chart = EnvelopeView(this)
        build()
    }

    private fun save() {
        Aircraft.saveAll(this, aircraft)
        VaultLock.prefs(this).edit().putInt("wb_current", current).apply()
    }

    private fun build() {
        body.removeAllViews()
        val a = aircraft[current]
        val spinner = Spinner(this).apply {
            adapter = ArrayAdapter(this@WeightBalanceActivity, android.R.layout.simple_spinner_dropdown_item, aircraft.map { it.name })
            setSelection(current)
            onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
                override fun onItemSelected(p: android.widget.AdapterView<*>?, v: View?, pos: Int, id: Long) {
                    if (pos != current) {
                        current = pos
                        save()
                        build()
                    }
                }
                override fun onNothingSelected(p: android.widget.AdapterView<*>?) {}
            }
        }
        body.addView(spinner)
        if (a.example) {
            body.addView(TextView(this).apply {
                text = getString(R.string.wb_example)
                setTextColor(0xFFE65100.toInt())
                setPadding(0, dp(8), 0, dp(8))
            })
        }
        body.addView(TextView(this).apply {
            text = "Empty %.1f lb @ %.2f in · Max %.0f lb".format(a.emptyWeight, a.emptyArm, a.maxWeight)
            layoutDirection = View.LAYOUT_DIRECTION_LTR
            setPadding(0, dp(4), 0, dp(8))
        })
        for (s in a.stations) {
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                layoutDirection = View.LAYOUT_DIRECTION_LTR
            }
            row.addView(TextView(this).apply {
                text = "${s.name}\nmax ${s.max.toInt()} · arm ${s.arm}"
            }, LinearLayout.LayoutParams(0, -2, 1f))
            row.addView(EditText(this).apply {
                inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
                setText(if (s.load == 0.0) "" else trim(s.load))
                hint = "0"
                gravity = Gravity.END
                addTextChangedListener(object : TextWatcher {
                    override fun beforeTextChanged(t: CharSequence?, a1: Int, a2: Int, a3: Int) {}
                    override fun onTextChanged(t: CharSequence?, a1: Int, a2: Int, a3: Int) {}
                    override fun afterTextChanged(t: Editable?) {
                        s.load = t.toString().toDoubleOrNull() ?: 0.0
                        save()
                        recompute()
                    }
                })
            }, LinearLayout.LayoutParams(dp(110), -2))
            body.addView(row)
        }
        body.addView(LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            layoutDirection = View.LAYOUT_DIRECTION_LTR
            addView(TextView(this@WeightBalanceActivity).apply { text = getString(R.string.wb_burn) }, LinearLayout.LayoutParams(0, -2, 1f))
            addView(EditText(this@WeightBalanceActivity).apply {
                inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
                setText(if (burn > 0) "%.1f".format(burn) else "")
                hint = "0"
                gravity = Gravity.END
                addTextChangedListener(object : TextWatcher {
                    override fun beforeTextChanged(t: CharSequence?, a1: Int, a2: Int, a3: Int) {}
                    override fun onTextChanged(t: CharSequence?, a1: Int, a2: Int, a3: Int) {}
                    override fun afterTextChanged(t: Editable?) {
                        burn = t.toString().toDoubleOrNull() ?: 0.0
                        recompute()
                    }
                })
            }, LinearLayout.LayoutParams(dp(110), -2))
        })
        (result.parent as? LinearLayout)?.removeView(result)
        (chart.parent as? LinearLayout)?.removeView(chart)
        body.addView(result, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(16) })
        body.addView(chart, LinearLayout.LayoutParams(-1, dp(300)).apply { topMargin = dp(12) })
        body.addView(MaterialButton(this).apply {
            text = getString(R.string.wb_edit)
            setOnClickListener { editAircraft() }
        })
        recompute()
    }

    private fun trim(v: Double) = if (v == Math.floor(v)) v.toLong().toString() else v.toString()

    private fun recompute() {
        val a = aircraft[current]
        val (to, ld) = a.compute(burn)
        fun line(label: String, r: Aircraft.Result) =
            "%-8s %7.1f lb  CG %6.2f in  %s".format(label, r.weight, r.cg, if (r.inside) "✅" else "❌")
        val over = to.weight - a.maxWeight
        result.text = line("Takeoff", to) + "\n" + line("Landing", ld) + "\n" +
            (if (over > 0) "⚠️ %.1f lb over the maximum weight".format(over) else "Margin %.1f lb".format(-over))
        result.setTextColor(if (to.inside && ld.inside) 0xFF2E7D32.toInt() else 0xFFC62828.toInt())
        chart.show(a, to, ld)
    }

    private fun field(box: LinearLayout, label: String, value: String, decimal: Boolean = true): EditText {
        box.addView(TextView(this).apply { text = label; setPadding(0, dp(8), 0, 0) })
        return EditText(this).apply {
            inputType = if (decimal) InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL else InputType.TYPE_CLASS_TEXT
            setText(value)
            box.addView(this)
        }
    }

    /** The aircraft's numbers, from its own weight and balance sheet. */
    private fun editAircraft() {
        val a = aircraft[current]
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(8), dp(20), 0)
            layoutDirection = View.LAYOUT_DIRECTION_LTR
        }
        val name = field(box, "Name", a.name, decimal = false)
        val ew = field(box, "Empty weight (lb)", trim(a.emptyWeight))
        val ea = field(box, "Empty CG arm (in)", trim(a.emptyArm))
        val mw = field(box, "Max takeoff weight (lb)", trim(a.maxWeight))
        val arms = a.stations.map { s -> s to (field(box, "${s.name}: arm (in)", trim(s.arm)) to field(box, "${s.name}: max", trim(s.max))) }
        val env = field(box, getString(R.string.wb_envelope), a.envelope.joinToString("  ") { "${trim(it.first)},${trim(it.second)}" }, decimal = false)
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.wb_edit)
            .setView(ScrollView(this).apply { addView(box) })
            .setPositiveButton(R.string.ok) { _, _ ->
                try {
                    a.name = name.text.toString().trim().ifEmpty { a.name }
                    a.emptyWeight = ew.text.toString().toDouble()
                    a.emptyArm = ea.text.toString().toDouble()
                    a.maxWeight = mw.text.toString().toDouble()
                    for ((s, f) in arms) {
                        s.arm = f.first.text.toString().toDouble()
                        s.max = f.second.text.toString().toDouble()
                    }
                    val corners = env.text.toString().trim().split(Regex("\\s+")).map { c ->
                        c.split(',').let { it[0].toDouble() to it[1].toDouble() }
                    }
                    if (corners.size >= 3) a.envelope = corners.toMutableList()
                    a.example = false
                    save()
                    build()
                } catch (e: Exception) {
                    Toast.makeText(this, R.string.wb_bad_number, Toast.LENGTH_LONG).show()
                }
            }
            .setNeutralButton(R.string.wb_add) { _, _ ->
                aircraft.add(Aircraft.fromJson(a.toJson()).apply { this.name = a.name + " 2" })
                current = aircraft.size - 1
                save()
                build()
                editAircraft()
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    /** The CG envelope, weight up and CG across, with the takeoff (T) and landing (L) points. */
    class EnvelopeView(ctx: Context) : View(ctx) {
        private var a: Aircraft? = null
        private var to: Aircraft.Result? = null
        private var ld: Aircraft.Result? = null
        private val d = ctx.resources.displayMetrics.density
        private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0x332E7D32 }
        private val edge = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF2E7D32.toInt(); style = Paint.Style.STROKE; strokeWidth = 2.5f * d }
        private val axis = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF9E9E9E.toInt(); textSize = 11 * d; strokeWidth = d }
        private val point = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 13 * d; isFakeBoldText = true }

        fun show(a: Aircraft, to: Aircraft.Result, ld: Aircraft.Result) {
            this.a = a; this.to = to; this.ld = ld
            invalidate()
        }

        override fun onDraw(c: Canvas) {
            val a = a ?: return
            val pts = a.envelope + listOfNotNull(to?.let { it.cg to it.weight }, ld?.let { it.cg to it.weight })
            val x0 = pts.minOf { it.first }; val x1 = pts.maxOf { it.first }
            val y0 = pts.minOf { it.second }; val y1 = pts.maxOf { it.second }
            val padX = (x1 - x0).coerceAtLeast(1.0) * 0.08; val padY = (y1 - y0).coerceAtLeast(1.0) * 0.08
            val l = 44 * d; val r = width - 12 * d; val t = 12 * d; val b = height - 28 * d
            fun sx(v: Double) = (l + (v - x0 + padX) / (x1 - x0 + 2 * padX) * (r - l)).toFloat()
            fun sy(v: Double) = (b - (v - y0 + padY) / (y1 - y0 + 2 * padY) * (b - t)).toFloat()
            c.drawLine(l, b, r, b, axis)
            c.drawLine(l, t, l, b, axis)
            c.drawText("%.1f".format(x0), sx(x0) - 10 * d, b + 16 * d, axis)
            c.drawText("%.1f in".format(x1), sx(x1) - 30 * d, b + 16 * d, axis)
            c.drawText("%.0f".format(y0), 2 * d, sy(y0), axis)
            c.drawText("%.0f lb".format(y1), 2 * d, sy(y1) + 10 * d, axis)
            val path = Path()
            for ((i, p) in a.envelope.withIndex()) if (i == 0) path.moveTo(sx(p.first), sy(p.second)) else path.lineTo(sx(p.first), sy(p.second))
            path.close()
            c.drawPath(path, fill)
            c.drawPath(path, edge)
            val to = to; val ld = ld
            if (to != null && ld != null) {
                point.color = 0xFF616161.toInt()
                c.drawLine(sx(to.cg), sy(to.weight), sx(ld.cg), sy(ld.weight), point)
            }
            for ((res, label) in listOf(to to "T", ld to "L")) {
                res ?: continue
                point.color = if (res.inside) 0xFF1565C0.toInt() else 0xFFC62828.toInt()
                c.drawCircle(sx(res.cg), sy(res.weight), 6 * d, point)
                c.drawText(label, sx(res.cg) + 8 * d, sy(res.weight) - 6 * d, point)
            }
        }
    }

    companion object {
        const val EXTRA_BURN = "burn"
    }
}
