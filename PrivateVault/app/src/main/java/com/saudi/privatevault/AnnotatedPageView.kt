package com.saudi.privatevault

import android.content.Context
import android.graphics.Canvas
import android.graphics.Matrix
import android.util.AttributeSet
import android.view.MotionEvent

/**
 * A PDF page that can be written on, like a notes app: pen, highlighter,
 * shapes, text and an eraser over the page, drawn in page coordinates so
 * marks follow zoom and panning.
 *
 * With a stylus (S Pen), the pen writes and fingers keep turning pages and
 * zooming; the pen's side button erases. Without one, a finger writes and two
 * fingers zoom and pan.
 */
class AnnotatedPageView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : ZoomImageView(context, attrs) {

    var tool = Tool.HAND
    var color = MarkPainter.INK[0]
    var widthLevel = 1

    /** The highlighter draws a straight band, level with the line of text, unless set free. */
    var straightMarker = true

    /** False once a stylus has been seen: then only the stylus writes. */
    var fingerDraws = true

    /** The marks of the page shown; set by the reader when the page changes. */
    var marks: MutableList<Mark> = mutableListOf()
        set(value) {
            field = value
            current = null
            invalidate()
        }

    /** A mark was added or removed: [undo] puts it back the other way. */
    var onEdit: ((Edit) -> Unit)? = null
    var onStylusSeen: (() -> Unit)? = null

    /** The text tool was tapped at this page point (fractions). */
    var onTextAt: ((Float, Float) -> Unit)? = null

    sealed class Edit {
        class Added(val mark: Mark) : Edit()
        class Removed(val removed: List<Pair<Int, Mark>>) : Edit()
    }

    private var current: Mark? = null
    private var currentPoints = ArrayList<Float>()
    private var erased = ArrayList<Pair<Int, Mark>>()
    private var navigating = false
    private var stylusSeen = false
    private val inverse = Matrix()
    private val pt = FloatArray(2)

    private fun pageW() = drawable?.intrinsicWidth?.toFloat() ?: 0f
    private fun pageH() = drawable?.intrinsicHeight?.toFloat() ?: 0f

    /** Screen point to page fractions; false while no page is shown. */
    private fun toPage(x: Float, y: Float): Boolean {
        val w = pageW()
        val h = pageH()
        if (w <= 0f || h <= 0f || !imageMatrix.invert(inverse)) return false
        pt[0] = x
        pt[1] = y
        inverse.mapPoints(pt)
        pt[0] = pt[0] / w
        pt[1] = pt[1] / h
        return true
    }

    private fun scaleNow(): Float {
        val v = FloatArray(9)
        imageMatrix.getValues(v)
        return v[Matrix.MSCALE_X].takeIf { it > 0f } ?: 1f
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val w = pageW()
        val h = pageH()
        if (w <= 0f || h <= 0f) return
        canvas.save()
        canvas.concat(imageMatrix)
        for (m in marks) MarkPainter.draw(canvas, m, w, h)
        current?.let { MarkPainter.draw(canvas, it, w, h) }
        canvas.restore()
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        val type = event.getToolType(0)
        val stylus = type == MotionEvent.TOOL_TYPE_STYLUS || type == MotionEvent.TOOL_TYPE_ERASER
        if (stylus && !stylusSeen) {
            stylusSeen = true
            fingerDraws = false
            onStylusSeen?.invoke()
        }
        val writing = tool != Tool.HAND && (stylus || fingerDraws)
        if (event.actionMasked == MotionEvent.ACTION_DOWN) navigating = !writing
        // A second finger while writing with a finger means zoom or pan instead.
        if (!navigating && !stylus && event.pointerCount > 1) {
            current = null
            restoreErased()
            navigating = true
            invalidate()
        }
        if (navigating) return super.onTouchEvent(event)

        val erasing = tool == Tool.ERASER || type == MotionEvent.TOOL_TYPE_ERASER ||
            (stylus && event.buttonState and MotionEvent.BUTTON_STYLUS_PRIMARY != 0)
        parent?.requestDisallowInterceptTouchEvent(true)
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                if (!toPage(event.x, event.y)) return true
                if (erasing) {
                    erased = ArrayList()
                    eraseAt(event.x, event.y)
                } else if (tool == Tool.TEXT) {
                    // Placed on lift, so a small slip of the finger does not matter.
                } else {
                    currentPoints = arrayListOf(pt[0], pt[1])
                    if (!freehand()) currentPoints.addAll(listOf(pt[0], pt[1]))
                    current = build()
                }
            }
            MotionEvent.ACTION_MOVE -> {
                if (erasing) {
                    for (i in 0 until event.historySize) eraseAt(event.getHistoricalX(i), event.getHistoricalY(i))
                    eraseAt(event.x, event.y)
                } else if (current != null) {
                    if (freehand()) {
                        for (i in 0 until event.historySize) addPoint(event.getHistoricalX(i), event.getHistoricalY(i))
                        addPoint(event.x, event.y)
                    } else if (toPage(event.x, event.y)) {
                        currentPoints[2] = pt[0]
                        currentPoints[3] = pt[1]
                        if (tool == Tool.HIGHLIGHT) level()
                    }
                    current = build()
                }
            }
            MotionEvent.ACTION_UP -> {
                if (erasing) {
                    if (erased.isNotEmpty()) onEdit?.invoke(Edit.Removed(erased))
                    erased = ArrayList()
                } else if (tool == Tool.TEXT) {
                    if (toPage(event.x, event.y)) onTextAt?.invoke(pt[0], pt[1])
                } else {
                    val m = current
                    current = null
                    if (m != null && worthKeeping(m)) {
                        marks.add(m)
                        onEdit?.invoke(Edit.Added(m))
                    }
                }
            }
            MotionEvent.ACTION_CANCEL -> {
                current = null
                restoreErased()
            }
        }
        invalidate()
        return true
    }

    private fun freehand() = tool == Tool.PEN || (tool == Tool.HIGHLIGHT && !straightMarker)

    /** A highlight dragged roughly along a line of text lies exactly along it. */
    private fun level() {
        val dx = (currentPoints[2] - currentPoints[0]) * pageW()
        val dy = (currentPoints[3] - currentPoints[1]) * pageH()
        if (kotlin.math.abs(dy) < kotlin.math.abs(dx) * 0.3f) currentPoints[3] = currentPoints[1]
    }

    private fun addPoint(x: Float, y: Float) {
        if (!toPage(x, y)) return
        val n = currentPoints.size
        // Skip points closer than about a pixel on screen.
        val minStep = 1.2f / (scaleNow() * pageW())
        if (n >= 2 && kotlin.math.abs(currentPoints[n - 2] - pt[0]) < minStep &&
            kotlin.math.abs(currentPoints[n - 1] - pt[1]) < minStep
        ) return
        currentPoints.add(pt[0])
        currentPoints.add(pt[1])
    }

    private fun build(): Mark {
        val widths = MarkPainter.widths(tool)
        // Lines stay the same thickness on screen whatever the zoom.
        val w = widths[widthLevel.coerceIn(0, 2)]
        return Mark(tool, color, w, currentPoints.toFloatArray())
    }

    /** A shape needs some size; a pen dot is fine. */
    private fun worthKeeping(m: Mark): Boolean {
        if (m.tool == Tool.PEN || m.tool == Tool.HIGHLIGHT) return m.points.size >= 2
        val p = m.points
        return kotlin.math.hypot((p[2] - p[0]) * pageW(), (p[3] - p[1]) * pageH()) * scaleNow() > 12f
    }

    private fun eraseAt(x: Float, y: Float) {
        if (!toPage(x, y)) return
        val w = pageW()
        val h = pageH()
        val slack = 14f / scaleNow()
        val px = pt[0] * w
        val py = pt[1] * h
        var i = marks.size - 1
        while (i >= 0) {
            if (MarkPainter.hits(marks[i], px, py, w, h, slack)) {
                erased.add(i to marks.removeAt(i))
            }
            i--
        }
    }

    private fun restoreErased() {
        for ((index, mark) in erased.asReversed()) marks.add(index.coerceAtMost(marks.size), mark)
        erased = ArrayList()
    }

    fun addText(x: Float, y: Float, text: String) {
        val m = Mark(Tool.TEXT, color, MarkPainter.widths(Tool.TEXT)[widthLevel.coerceIn(0, 2)], floatArrayOf(x, y), text)
        marks.add(m)
        onEdit?.invoke(Edit.Added(m))
        invalidate()
    }
}
