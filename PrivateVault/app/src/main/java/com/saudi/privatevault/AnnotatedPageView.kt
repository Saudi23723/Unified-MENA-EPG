package com.saudi.privatevault

import android.content.Context
import kotlin.math.hypot
import android.graphics.Canvas
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Path
import android.view.HapticFeedbackConstants
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
    var penStyle = 0
    var color = MarkPainter.INK[0]
    /** Line thickness for the pen, highlighter and shapes, as a fraction of the page width. */
    var size = 0.0038f

    /** Text size, as a fraction of the page width. */
    var textSize = 0.028f

    /** Highlights get rounded ends. */
    var roundMarker = false

    /** The highlighter draws a straight band, level with the line of text, unless set free. */
    var straightMarker = true

    /** False once a stylus has been seen: then only the stylus writes. */
    var fingerDraws = true

    /** The marks of the page shown; set by the reader when the page changes. */
    var marks: MutableList<Mark> = mutableListOf()
        set(value) {
            field = value
            current = null
            selected = null
            invalidate()
        }

    /** A mark was added or removed: [undo] puts it back the other way. */
    var onEdit: ((Edit) -> Unit)? = null
    var onStylusSeen: (() -> Unit)? = null

    /** The text tool was tapped at this page point (fractions). */
    var onTextAt: ((Float, Float) -> Unit)? = null

    /** The letters of the page shown, for selecting text with a long press; null until read. */
    var letters: List<PdfLinks.CharBox>? = null
        set(value) {
            field = value
            clearSelection()
            showFound()
        }

    /** Words searched for: shown on each page they are on, as a selection. */
    var find: String? = null
        set(value) {
            field = value
            clearSelection()
            showFound()
        }

    private fun showFound() {
        val q = find?.filterNot { it.isWhitespace() }?.lowercase() ?: return
        val ls = letters ?: return
        if (q.isEmpty()) return
        val sb = StringBuilder()
        val owner = ArrayList<Int>()
        ls.forEachIndexed { i, c -> for (ch in c.ch.lowercase()) { sb.append(ch); owner.add(i) } }
        val at = sb.indexOf(q)
        if (at < 0) return
        selFrom = owner[at]
        selTo = owner[at + q.length - 1]
        invalidate()
    }

    /** The top of the words now selected (a fraction of the page), for a read-later mark. */
    fun selectionTop(): Float = letters?.getOrNull(selFrom)?.top ?: 0f

    /** Words were selected: one band per line (l, t, r, b fractions) and the text. */
    var onSelection: ((FloatArray, String) -> Unit)? = null

    /** The ribbon takes the colour of the bookmark's group. */
    var ribbonColor: Int
        get() = ribbonPaint.color
        set(value) {
            ribbonPaint.color = value
            invalidate()
        }

    /** Shows a bookmark ribbon on the page's corner. */
    var bookmarked = false
        set(value) {
            field = value
            invalidate()
        }

    // Text selection: the word first pressed, and the letters now chosen.
    private var selecting = false
    private var anchorFrom = 0
    private var anchorTo = 0
    private var selFrom = -1
    private var selTo = -1
    private val selPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0x553D7BFF; style = Paint.Style.FILL }
    private val ribbonPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFE53935.toInt(); style = Paint.Style.FILL }
    private val ribbon = Path()

    init {
        onLongPress = { x, y -> beginSelection(x, y) }
    }

    sealed class Edit {
        class Added(val mark: Mark) : Edit()
        class Removed(val removed: List<Pair<Int, Mark>>) : Edit()

        /** Several marks moved together (a lasso), by (dx, dy) page fractions. */
        class Moved(val marks: List<Mark>, val dx: Float, val dy: Float) : Edit()

        /** Moved, resized or recoloured: the points and colour before and after. */
        class Changed(
            val mark: Mark, val before: FloatArray, val after: FloatArray, val colorBefore: Int, val colorAfter: Int,
            val widthBefore: Float = Float.NaN, val widthAfter: Float = Float.NaN,
        ) : Edit()
    }

    /** The mark picked for moving, resizing, recolouring or deleting. */
    var selected: Mark? = null
        set(value) {
            field = value
            onSelected?.invoke(value)
            invalidate()
        }
    var onSelected: ((Mark?) -> Unit)? = null

    private enum class Drag { NONE, MOVE, HANDLE }

    private var drag = Drag.NONE
    private var handle = -1
    private var lastX = 0f
    private var lastY = 0f
    private var before: FloatArray? = null
    private val dash = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        color = 0xFF1E88E5.toInt()
        pathEffect = android.graphics.DashPathEffect(floatArrayOf(10f, 8f), 0f)
    }
    private val knob = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF1E88E5.toInt() }
    private val knobRing = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFFFFFF.toInt() }

    private var current: Mark? = null

    // Held still at the end of a stroke: the stroke becomes the shape it looks like.
    private var snapped = false
    private var holdX = 0f
    private var holdY = 0f
    private val snap = Runnable {
        val m = current ?: return@Runnable
        if (snapped || !freehand()) return@Runnable
        val shape = ShapeSnap.recognize(currentPoints.toFloatArray(), pageW(), pageH(), m, tool == Tool.HIGHLIGHT) ?: return@Runnable
        current = shape
        snapped = true
        performHapticFeedback(android.view.HapticFeedbackConstants.LONG_PRESS)
        invalidate()
    }
    private fun holdSoon(x: Float, y: Float) {
        holdX = x; holdY = y
        removeCallbacks(snap)
        postDelayed(snap, 650)
    }

    // The lasso of the select tool, and the marks it caught (moved together).
    private var lasso: ArrayList<Float>? = null
    private var group: List<Mark> = emptyList()
    private var groupDx = 0f
    private var groupDy = 0f
    private var movingGroup = false
    private val lassoPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        color = 0xFF1E88E5.toInt()
    }
    private val lassoFill = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0x221E88E5; style = Paint.Style.FILL }

    private fun groupBounds(): android.graphics.RectF? {
        if (group.isEmpty()) return null
        val r = android.graphics.RectF(MarkPainter.bounds(group[0], pageW(), pageH()))
        for (m in group.drop(1)) r.union(MarkPainter.bounds(m, pageW(), pageH()))
        return r
    }

    /** The marks the lasso goes round: by the middle of each. */
    private fun inLasso(poly: FloatArray, x: Float, y: Float): Boolean {
        var inside = false
        var j = poly.size - 2
        var i = 0
        while (i < poly.size) {
            val xi = poly[i]; val yi = poly[i + 1]; val xj = poly[j]; val yj = poly[j + 1]
            if ((yi > y) != (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside
            j = i; i += 2
        }
        return inside
    }

    fun clearGroup() { group = emptyList(); lasso = null; invalidate() }
    fun deleteGroup() {
        if (group.isEmpty()) return
        val removed = group.map { marks.indexOf(it) to it }.filter { it.first >= 0 }.sortedBy { it.first }
        for ((_, m) in removed.asReversed()) marks.remove(m)
        group = emptyList()
        onEdit?.invoke(Edit.Removed(removed))
        invalidate()
    }
    var onGroup: ((Int) -> Unit)? = null
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
        selected?.let { drawSelected(canvas, it, w, h) }
        lasso?.let { l ->
            if (l.size >= 4) {
                val path = android.graphics.Path()
                path.moveTo(l[0] * w, l[1] * h)
                var k = 2
                while (k + 1 < l.size) { path.lineTo(l[k] * w, l[k + 1] * h); k += 2 }
                path.close()
                val sc = scaleNow()
                lassoPaint.strokeWidth = dpx(1.5f) / sc
                lassoPaint.pathEffect = android.graphics.DashPathEffect(floatArrayOf(dpx(6f) / sc, dpx(4f) / sc), 0f)
                canvas.drawPath(path, lassoFill)
                canvas.drawPath(path, lassoPaint)
            }
        }
        groupBounds()?.let { r ->
            val sc = scaleNow()
            r.inset(-dpx(8f) / sc, -dpx(8f) / sc)
            dash.strokeWidth = dpx(1.5f) / sc
            dash.pathEffect = android.graphics.DashPathEffect(floatArrayOf(dpx(5f) / sc, dpx(4f) / sc), 0f)
            canvas.drawRect(r, lassoFill)
            canvas.drawRect(r, dash)
        }
        val bands = selectionBands()
        var i = 0
        while (i + 3 < bands.size) {
            canvas.drawRect(bands[i] * w, bands[i + 1] * h, bands[i + 2] * w, bands[i + 3] * h, selPaint)
            i += 4
        }
        canvas.restore()
        if (bookmarked) drawRibbon(canvas, w)
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (selecting) return extendSelection(event)
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
        if (grab(event, erasing)) {
            invalidate()
            return true
        }
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
                    levelDecided = false
                    levelLocked = false
                    snapped = false
                    current = build()
                    if (freehand()) holdSoon(event.x, event.y)
                }
            }
            MotionEvent.ACTION_MOVE -> {
                if (erasing) {
                    for (i in 0 until event.historySize) eraseAt(event.getHistoricalX(i), event.getHistoricalY(i))
                    eraseAt(event.x, event.y)
                } else if (current != null && snapped) {
                    // A shape now: it stays as recognised until the finger lifts.
                } else if (current != null) {
                    if (freehand() && hypot(event.x - holdX, event.y - holdY) > dpx(7f)) holdSoon(event.x, event.y)
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
                    removeCallbacks(snap)
                    val m = current
                    current = null
                    if (m != null && worthKeeping(m)) {
                        marks.add(m)
                        onEdit?.invoke(Edit.Added(m))
                        // A new shape stays picked, so it can be moved or resized straight away.
                        if (isShape(m.tool)) selected = m
                    }
                }
            }
            MotionEvent.ACTION_CANCEL -> {
                removeCallbacks(snap)
                current = null
                restoreErased()
            }
        }
        invalidate()
        return true
    }

    private fun freehand() = tool == Tool.PEN || (tool == Tool.HIGHLIGHT && !straightMarker)

    // Whether this highlight is held level: decided once, after the first stretch of
    // the drag, so the band does not jump between level and slanted while moving.
    private var levelDecided = false
    private var levelLocked = false

    /** A highlight dragged roughly along a line of text lies exactly along it. */
    private fun level() {
        val s = scaleNow()
        val dx = (currentPoints[2] - currentPoints[0]) * pageW() * s
        val dy = (currentPoints[3] - currentPoints[1]) * pageH() * s
        if (!levelDecided) {
            // Until the finger has gone a little way, keep the band level.
            if (dx * dx + dy * dy < dpx(28f) * dpx(28f)) {
                currentPoints[3] = currentPoints[1]
                return
            }
            levelDecided = true
            levelLocked = kotlin.math.abs(dy) < kotlin.math.abs(dx) * 0.36f
        }
        if (levelLocked) currentPoints[3] = currentPoints[1]
    }

    // ---- picking, moving and resizing ----

    private fun isShape(t: Tool) = t == Tool.LINE || t == Tool.ARROW || t == Tool.RECT || t == Tool.OVAL

    /** Handles of a picked shape, as page fractions: line ends, or rectangle corners. */
    private fun handles(m: Mark): List<Pair<Float, Float>> {
        val p = m.points
        if (p.size < 4) return emptyList()
        return when (m.tool) {
            Tool.LINE, Tool.ARROW -> listOf(p[0] to p[1], p[2] to p[3])
            Tool.RECT, Tool.OVAL -> listOf(p[0] to p[1], p[2] to p[1], p[2] to p[3], p[0] to p[3])
            // A straight highlight: its two ends, to lengthen or shorten it.
            Tool.HIGHLIGHT -> if (p.size == 4) listOf(p[0] to p[1], p[2] to p[3]) else emptyList()
            else -> emptyList()
        }
    }

    private fun dpx(v: Float) = v * resources.displayMetrics.density

    private fun handleAt(m: Mark, x: Float, y: Float): Int {
        val s = scaleNow()
        for ((i, hp) in handles(m).withIndex()) {
            val dx = (hp.first - x) * pageW() * s
            val dy = (hp.second - y) * pageH() * s
            if (dx * dx + dy * dy < dpx(26f) * dpx(26f)) return i
        }
        return -1
    }

    private fun bodyAt(m: Mark, x: Float, y: Float): Boolean {
        val w = pageW()
        val h = pageH()
        val slack = dpx(14f) / scaleNow()
        val r = MarkPainter.bounds(m, w, h)
        r.inset(-slack, -slack)
        return r.contains(x * w, y * h)
    }

    /**
     * The select tool, and the shape tools on a picked shape: drag a handle to
     * resize, the body to move. False to let the tool draw as usual.
     */
    private fun grab(event: MotionEvent, erasing: Boolean): Boolean {
        if (erasing) return false
        val picking = tool == Tool.SELECT || isShape(tool)
        if (!picking) {
            if (event.actionMasked == MotionEvent.ACTION_DOWN && selected != null) selected = null
            return false
        }
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                if (!toPage(event.x, event.y)) return true
                val x = pt[0]
                val y = pt[1]
                lastX = x
                lastY = y
                drag = Drag.NONE
                val sel = selected
                if (sel != null) {
                    handle = handleAt(sel, x, y)
                    if (handle >= 0) drag = Drag.HANDLE else if (bodyAt(sel, x, y)) drag = Drag.MOVE
                }
                // Inside the lassoed marks: move them all.
                if (tool == Tool.SELECT && group.isNotEmpty()) {
                    val r = groupBounds()
                    if (r != null && r.apply { inset(-dpx(14f) / scaleNow(), -dpx(14f) / scaleNow()) }.contains(x * pageW(), y * pageH())) {
                        movingGroup = true; groupDx = 0f; groupDy = 0f
                        return true
                    }
                    group = emptyList()
                    onGroup?.invoke(0)
                }
                if (drag == Drag.NONE && tool == Tool.SELECT) {
                    val hit = marks.lastOrNull { MarkPainter.hits(it, x * pageW(), y * pageH(), pageW(), pageH(), dpx(14f) / scaleNow()) }
                        ?: marks.lastOrNull { bodyAt(it, x, y) }
                    selected = hit
                    if (hit != null) drag = Drag.MOVE
                }
                if (drag != Drag.NONE) {
                    before = selected?.points?.copyOf()
                    return true
                }
                if (tool != Tool.SELECT) selected = null
                // On nothing: draw a lasso round what to pick.
                if (tool == Tool.SELECT) lasso = arrayListOf(x, y)
                return tool == Tool.SELECT
            }
            MotionEvent.ACTION_MOVE -> {
                if (movingGroup) {
                    if (!toPage(event.x, event.y)) return true
                    val dx = pt[0] - lastX; val dy = pt[1] - lastY
                    for (m in group) { var i = 0; while (i + 1 < m.points.size) { m.points[i] += dx; m.points[i + 1] += dy; i += 2 } }
                    groupDx += dx; groupDy += dy
                    lastX = pt[0]; lastY = pt[1]
                    return true
                }
                lasso?.let { l -> if (toPage(event.x, event.y)) { l.add(pt[0]); l.add(pt[1]) }; return true }
                if (drag == Drag.NONE) return tool == Tool.SELECT
                val m = selected ?: return true
                if (!toPage(event.x, event.y)) return true
                val x = pt[0]
                val y = pt[1]
                val p = m.points
                if (drag == Drag.MOVE) {
                    val dx = x - lastX
                    val dy = y - lastY
                    var i = 0
                    while (i + 1 < p.size) {
                        p[i] += dx
                        p[i + 1] += dy
                        i += 2
                    }
                } else {
                    when (m.tool) {
                        Tool.LINE, Tool.ARROW, Tool.HIGHLIGHT -> if (handle == 0) { p[0] = x; p[1] = y } else { p[2] = x; p[3] = y }
                        else -> when (handle) {
                            0 -> { p[0] = x; p[1] = y }
                            1 -> { p[2] = x; p[1] = y }
                            2 -> { p[2] = x; p[3] = y }
                            else -> { p[0] = x; p[3] = y }
                        }
                    }
                }
                lastX = x
                lastY = y
                return true
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                if (movingGroup) {
                    movingGroup = false
                    if (groupDx != 0f || groupDy != 0f) onEdit?.invoke(Edit.Moved(group, groupDx, groupDy))
                    return true
                }
                lasso?.let { l ->
                    lasso = null
                    val poly = l.toFloatArray()
                    if (poly.size >= 6) {
                        val w = pageW(); val h = pageH()
                        group = marks.filter { m -> MarkPainter.bounds(m, w, h).let { r -> inLasso(poly, r.centerX() / w, r.centerY() / h) } }
                        if (group.size == 1) { selected = group[0]; group = emptyList() }
                        onGroup?.invoke(group.size)
                    }
                    return true
                }
                if (drag == Drag.NONE) return tool == Tool.SELECT
                val m = selected
                val b = before
                if (m != null && b != null && !b.contentEquals(m.points)) {
                    onEdit?.invoke(Edit.Changed(m, b, m.points.copyOf(), m.color, m.color))
                }
                drag = Drag.NONE
                before = null
                return true
            }
        }
        return drag != Drag.NONE
    }

    private fun drawSelected(canvas: Canvas, m: Mark, w: Float, h: Float) {
        val s = scaleNow()
        val r = MarkPainter.bounds(m, w, h)
        r.inset(-dpx(6f) / s, -dpx(6f) / s)
        dash.strokeWidth = dpx(1.5f) / s
        dash.pathEffect = android.graphics.DashPathEffect(floatArrayOf(dpx(5f) / s, dpx(4f) / s), 0f)
        canvas.drawRect(r, dash)
        for ((hx, hy) in handles(m)) {
            canvas.drawCircle(hx * w, hy * h, dpx(8f) / s, knobRing)
            canvas.drawCircle(hx * w, hy * h, dpx(6f) / s, knob)
        }
    }

    fun recolorSelected(color: Int) {
        val m = selected ?: return
        if (m.color == color) return
        val old = m.color
        m.color = color
        onEdit?.invoke(Edit.Changed(m, m.points.copyOf(), m.points.copyOf(), old, color))
        invalidate()
    }

    fun deleteSelected() {
        val m = selected ?: return
        val i = marks.indexOf(m)
        if (i < 0) return
        marks.removeAt(i)
        selected = null
        onEdit?.invoke(Edit.Removed(listOf(i to m)))
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

    private fun build(): Mark = Mark(tool, color, size, currentPoints.toFloatArray(), round = tool == Tool.HIGHLIGHT && roundMarker, pen = if (tool == Tool.PEN) penStyle else 0)

    /** A new thickness for the picked mark (a highlight, line or shape), undoable. */
    fun resizeSelected(w: Float, record: Boolean) {
        val m = selected ?: return
        val old = m.width
        m.width = w
        if (record) onEdit?.invoke(Edit.Changed(m, m.points.copyOf(), m.points.copyOf(), m.color, m.color, startWidth ?: old, w))
        startWidth = if (record) null else (startWidth ?: old)
        invalidate()
    }

    private var startWidth: Float? = null

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

    // ---- selecting words ----

    private fun pxW() = pageW()
    private fun pxH() = pageH()

    /** The letter under a screen point, or the nearest within a couple of lines. */
    private fun letterAt(x: Float, y: Float): Int {
        val ls = letters ?: return -1
        if (ls.isEmpty() || !toPage(x, y)) return -1
        val px = pt[0]
        val py = pt[1]
        var best = -1
        var bestD = Float.MAX_VALUE
        for ((i, c) in ls.withIndex()) {
            if (px >= c.left && px <= c.right && py >= c.top && py <= c.bottom) return i
            val dx = (if (px < c.left) c.left - px else if (px > c.right) px - c.right else 0f) * pxW()
            val dy = (if (py < c.top) c.top - py else if (py > c.bottom) py - c.bottom else 0f) * pxH()
            val d = dx * dx + dy * dy * 4f
            if (d < bestD) {
                bestD = d
                best = i
            }
        }
        val lineH = (ls[best].bottom - ls[best].top) * pxH()
        return if (bestD <= (lineH * 3f) * (lineH * 3f)) best else -1
    }

    private fun sameLine(a: PdfLinks.CharBox, b: PdfLinks.CharBox) =
        kotlin.math.abs(a.top - b.top) * pxH() < (a.bottom - a.top) * pxH() * 0.5f

    /** Whether a word ends between two neighbouring letters. */
    private fun gapBetween(a: PdfLinks.CharBox, b: PdfLinks.CharBox) =
        !sameLine(a, b) || (b.left - a.right) * pxW() > (a.bottom - a.top) * pxH() * 0.18f

    private fun beginSelection(x: Float, y: Float) {
        val ls = letters ?: return
        if (tool != Tool.HAND && fingerDraws) return
        val i = letterAt(x, y)
        if (i < 0) return
        var from = i
        var to = i
        while (from > 0 && !gapBetween(ls[from - 1], ls[from])) from--
        while (to < ls.size - 1 && !gapBetween(ls[to], ls[to + 1])) to++
        anchorFrom = from
        anchorTo = to
        selFrom = from
        selTo = to
        selecting = true
        parent?.requestDisallowInterceptTouchEvent(true)
        performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
        invalidate()
    }

    private fun extendSelection(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_MOVE -> {
                val i = letterAt(event.x, event.y)
                if (i >= 0) {
                    if (i < anchorFrom) {
                        selFrom = i
                        selTo = anchorTo
                    } else {
                        selFrom = anchorFrom
                        selTo = maxOf(i, anchorTo)
                    }
                    invalidate()
                }
            }
            MotionEvent.ACTION_UP -> {
                selecting = false
                val bands = selectionBands()
                if (bands.isNotEmpty()) onSelection?.invoke(bands, selectedText()) else clearSelection()
            }
            MotionEvent.ACTION_CANCEL -> {
                selecting = false
                clearSelection()
            }
        }
        return true
    }

    /** One band per line over the chosen letters. */
    private fun selectionBands(): FloatArray {
        val ls = letters ?: return FloatArray(0)
        if (selFrom < 0 || selTo < selFrom || selTo >= ls.size) return FloatArray(0)
        val out = ArrayList<Float>()
        var l = ls[selFrom].left
        var t = ls[selFrom].top
        var r = ls[selFrom].right
        var b = ls[selFrom].bottom
        for (i in selFrom + 1..selTo) {
            val c = ls[i]
            if (sameLine(ls[i - 1], c)) {
                l = minOf(l, c.left)
                t = minOf(t, c.top)
                r = maxOf(r, c.right)
                b = maxOf(b, c.bottom)
            } else {
                out.addAll(listOf(l, t, r, b))
                l = c.left
                t = c.top
                r = c.right
                b = c.bottom
            }
        }
        out.addAll(listOf(l, t, r, b))
        return out.toFloatArray()
    }

    private fun selectedText(): String {
        val ls = letters ?: return ""
        val sb = StringBuilder()
        for (i in selFrom..selTo) {
            if (i > selFrom) {
                if (!sameLine(ls[i - 1], ls[i])) sb.append('\n') else if (gapBetween(ls[i - 1], ls[i])) sb.append(' ')
            }
            sb.append(ls[i].ch)
        }
        return sb.toString()
    }

    fun clearSelection() {
        selFrom = -1
        selTo = -1
        selecting = false
        invalidate()
    }

    /** Keeps the chosen words as a highlight in the marker colour. */
    fun highlightSelection(color: Int) {
        val bands = selectionBands()
        clearSelection()
        if (bands.isEmpty()) return
        val m = Mark(Tool.TEXTMARK, color, 0f, bands, null, roundMarker)
        marks.add(m)
        onEdit?.invoke(Edit.Added(m))
        invalidate()
    }

    /** A small red ribbon hanging from the page's top corner. */
    private fun drawRibbon(canvas: Canvas, w: Float) {
        val corner = floatArrayOf(w, 0f)
        imageMatrix.mapPoints(corner)
        val d = resources.displayMetrics.density
        val right = minOf(corner[0], width.toFloat()) - 18 * d
        val top = maxOf(corner[1], 0f)
        ribbon.reset()
        ribbon.moveTo(right - 18 * d, top)
        ribbon.lineTo(right, top)
        ribbon.lineTo(right, top + 34 * d)
        ribbon.lineTo(right - 9 * d, top + 26 * d)
        ribbon.lineTo(right - 18 * d, top + 34 * d)
        ribbon.close()
        canvas.drawPath(ribbon, ribbonPaint)
    }

    fun addText(x: Float, y: Float, text: String) {
        val m = Mark(Tool.TEXT, color, textSize, floatArrayOf(x, y), text)
        marks.add(m)
        onEdit?.invoke(Edit.Added(m))
        invalidate()
    }
}
