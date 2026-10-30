package com.saudi.privatevault

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.os.SystemClock
import android.view.MotionEvent
import android.view.View
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Writing over a page of text: a pen and a highlighter that stay (kept in
 * [file], relative to the width so they fit any screen), and a neon laser
 * that glows while drawn and fades away after four seconds, for explaining.
 */
@SuppressLint("ViewConstructor")
class InkLayer(ctx: Context, private val file: File) : View(ctx) {
    enum class Tool { NONE, PEN, HIGHLIGHT, LASER, ERASER }

    private class Stroke(val tool: Tool, val color: Int, val pts: FloatArray)
    private class Laser(val color: Int, val pts: ArrayList<Float>, var ended: Long = 0L)

    var tool = Tool.NONE
    var color = 0xFF4DA3FF.toInt()

    private val strokes = ArrayList<Stroke>()
    private val lasers = ArrayList<Laser>()
    private var current: ArrayList<Float>? = null
    private var laser: Laser? = null
    private val d = ctx.resources.displayMetrics.density
    private val hl = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND }
    private val glow = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND }

    init {
        try {
            val a = JSONArray(file.readText())
            for (i in 0 until a.length()) {
                val o = a.getJSONObject(i)
                val p = o.getJSONArray("p")
                strokes.add(Stroke(Tool.valueOf(o.getString("t")), o.getInt("c"), FloatArray(p.length()) { p.getDouble(it).toFloat() }))
            }
        } catch (e: Exception) {
        }
    }

    private fun save() {
        file.parentFile?.mkdirs()
        file.writeText(JSONArray().apply {
            for (s in strokes) put(JSONObject().put("t", s.tool.name).put("c", s.color).put("p", JSONArray().apply { s.pts.forEach { put(Math.round(it * 10000) / 10000.0) } }))
        }.toString())
    }

    // Only as tall as the page it lies on: left to fill the rest of a short screen,
    // it pushed the buttons under the section out of sight.
    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) = setMeasuredDimension(
        MeasureSpec.getSize(widthMeasureSpec),
        if (MeasureSpec.getMode(heightMeasureSpec) == MeasureSpec.EXACTLY) MeasureSpec.getSize(heightMeasureSpec) else 0
    )

    /** Page units: fractions of the width, so the ink stays on its words at any size. */
    private fun screen(pts: FloatArray) = FloatArray(pts.size) { pts[it] * width }

    private fun path(xy: FloatArray) = Path().apply {
        moveTo(xy[0], xy[1])
        var i = 2
        while (i + 1 < xy.size) { lineTo(xy[i], xy[i + 1]); i += 2 }
    }

    override fun onDraw(c: Canvas) {
        for (s in strokes) drawStroke(c, s.tool, s.color, screen(s.pts))
        current?.let { drawStroke(c, tool, color, screen(it.toFloatArray())) }
        // The laser: full while drawn and for three seconds, then gone within the fourth.
        val now = SystemClock.uptimeMillis()
        lasers.removeAll { it.ended > 0 && now - it.ended > 4000 }
        for (l in lasers) {
            val age = if (l.ended == 0L) 0L else now - l.ended
            val a = if (age < 3000) 1f else 1f - (age - 3000) / 1000f
            val xy = l.pts.toFloatArray()
            if (xy.size < 4) continue
            val p = path(xy)
            glow.color = l.color; glow.alpha = (70 * a).toInt(); glow.strokeWidth = 14 * d; c.drawPath(p, glow)
            glow.alpha = (150 * a).toInt(); glow.strokeWidth = 6 * d; c.drawPath(p, glow)
            glow.color = 0xFFFFFFFF.toInt(); glow.alpha = (230 * a).toInt(); glow.strokeWidth = 2 * d; c.drawPath(p, glow)
        }
        if (lasers.isNotEmpty()) postInvalidateOnAnimation()
    }

    private fun drawStroke(c: Canvas, t: Tool, color: Int, xy: FloatArray) {
        if (xy.size < 2) return
        when (t) {
            Tool.PEN -> PenInk.draw(c, PenStyle.BALLPOINT, color, 2.6f * d, xy)
            Tool.HIGHLIGHT -> {
                hl.color = color; hl.alpha = 0x66; hl.strokeWidth = 16 * d; hl.strokeCap = Paint.Cap.SQUARE
                c.drawPath(path(xy), hl)
            }
            else -> {}
        }
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(e: MotionEvent): Boolean {
        if (tool == Tool.NONE) return false
        parent?.requestDisallowInterceptTouchEvent(true)
        val x = e.x; val y = e.y
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> when (tool) {
                Tool.LASER -> laser = Laser(color, arrayListOf(x, y)).also { lasers.add(it) }
                Tool.ERASER -> erase(x, y)
                else -> current = arrayListOf(x / width, y / width)
            }
            MotionEvent.ACTION_MOVE -> when (tool) {
                Tool.LASER -> laser?.pts?.apply { add(x); add(y) }
                Tool.ERASER -> erase(x, y)
                else -> current?.apply { add(x / width); add(y / width) }
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                laser?.ended = SystemClock.uptimeMillis(); laser = null
                current?.let { if (it.size >= 4) { strokes.add(Stroke(tool, color, it.toFloatArray())); save() } }
                current = null
            }
        }
        invalidate()
        return true
    }

    private fun erase(x: Float, y: Float) {
        val r = 18 * d
        val before = strokes.size
        strokes.removeAll { s -> val xy = screen(s.pts); (0 until xy.size / 2).any { Math.hypot((xy[2 * it] - x).toDouble(), (xy[2 * it + 1] - y).toDouble()) < r } }
        if (strokes.size != before) save()
    }

    fun undo() { if (strokes.isNotEmpty()) { strokes.removeAt(strokes.size - 1); save(); invalidate() } }
    fun clear() { strokes.clear(); save(); invalidate() }
}
