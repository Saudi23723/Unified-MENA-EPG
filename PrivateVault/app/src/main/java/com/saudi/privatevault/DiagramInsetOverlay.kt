package com.saudi.privatevault

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Point
import android.graphics.Rect
import android.graphics.RectF
import android.view.View
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay

/**
 * The airport diagram big at any zoom. This overlay chooses the field (the pinned one, else the
 * one with a diagram nearest the screen's centre) and draws the line from the field to its card;
 * the card itself is a floating window ([DiagramCardView] in a frame the map owns) that can be
 * dragged, made bigger or smaller, pinned to its field, sent there, or closed.
 */
class DiagramInsetOverlay(
    private val map: MapView,
    private val onChange: (Inset?) -> Unit,
) : Overlay() {
    class Inset(val ident: String, val bmp: Bitmap, val north: Double, val west: Double, val south: Double, val east: Double, val lat: Double, val lon: Double)

    val insets = LinkedHashMap<String, Inset>()
    /** At or above this zoom the diagram on the chart itself is big enough and the card steps aside. */
    var closeZoom = 14.0
    /** The field the card stays on, whatever the chart does. */
    var pinned: String? = null
    /** Fields whose card was closed (until diagrams are turned off and on). */
    val hidden = HashSet<String>()
    /** The card's frame, to tie the line to. */
    var card: View? = null
    var current: Inset? = null
        private set

    private val d = map.resources.displayMetrics.density
    private val lead = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; color = 0xFF2D8CFF.toInt(); strokeWidth = 2.5f * d }
    private val dot = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF2D8CFF.toInt() }
    private val pt = Point()

    private fun pick(mv: MapView): Inset? {
        // Close in, the diagram itself lies on the chart: no card, pinned or not.
        if (mv.zoomLevelDouble >= closeZoom) return null
        pinned?.let { p -> insets[p]?.let { return it } }
        val bb = mv.boundingBox; val c = mv.mapCenter
        return insets.values.filter { it.ident !in hidden && it.lat in bb.latSouth..bb.latNorth && it.lon in bb.lonWest..bb.lonEast }
            .minByOrNull { Nav.distanceNm(c.latitude, c.longitude, it.lat, it.lon) }
    }

    override fun draw(c: Canvas, mv: MapView, sh: Boolean) {
        if (sh) return
        val ins = pick(mv)
        if (ins !== current) { current = ins; mv.post { onChange(ins) } }
        if (ins == null) return
        val v = card ?: return
        if (v.visibility != View.VISIBLE || v.width == 0) return
        mv.projection.toPixels(GeoPoint(ins.lat, ins.lon), pt)
        // The card's place on the map's screen, its nearest side to the field.
        val ml = IntArray(2); mv.getLocationOnScreen(ml)
        val cl = IntArray(2); v.getLocationOnScreen(cl)
        val r = RectF((cl[0] - ml[0]).toFloat(), (cl[1] - ml[1]).toFloat(), (cl[0] - ml[0] + v.width).toFloat(), (cl[1] - ml[1] + v.height).toFloat())
        c.save(); c.rotate(-mv.mapOrientation, mv.width / 2f, mv.height / 2f)
        // The field's point in the same upright frame.
        val p = floatArrayOf(pt.x.toFloat(), pt.y.toFloat())
        android.graphics.Matrix().apply { setRotate(mv.mapOrientation, mv.width / 2f, mv.height / 2f) }.mapPoints(p)
        val ex = p[0].coerceIn(r.left, r.right); val ey = p[1].coerceIn(r.top, r.bottom)
        if (!r.contains(p[0], p[1])) c.drawLine(p[0], p[1], ex, ey, lead)
        c.drawCircle(p[0], p[1], 6 * d, dot)
        c.restore()
    }
}

/** The diagram picture with the aircraft and the traffic where they are on it. */
class DiagramCardView(ctx: Context, private val own: () -> android.location.Location?) : View(ctx) {
    var inset: DiagramInsetOverlay.Inset? = null
        set(v) { field = v; requestLayout(); invalidate() }
    private val d = ctx.resources.displayMetrics.density
    private val bmpPaint = Paint(Paint.FILTER_BITMAP_FLAG or Paint.ANTI_ALIAS_FLAG)
    private val ship = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF00B4FF.toInt() }
    private val edge = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; color = 0xFF000000.toInt(); strokeWidth = 1.6f * d }
    private val tf = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFF9500.toInt() }
    private val tfTx = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF111111.toInt(); textSize = 10.5f * d; isFakeBoldText = true }

    override fun onMeasure(w: Int, h: Int) {
        val width = MeasureSpec.getSize(w)
        val b = inset?.bmp
        setMeasuredDimension(width, if (b == null) width else (width.toLong() * b.height / b.width).toInt())
    }

    override fun onDraw(c: Canvas) {
        val ins = inset ?: return
        if (ins.bmp.isRecycled) return
        val img = RectF(0f, 0f, width.toFloat(), height.toFloat())
        c.drawBitmap(ins.bmp, Rect(0, 0, ins.bmp.width, ins.bmp.height), img, bmpPaint)
        fun at(lat: Double, lon: Double): FloatArray? {
            if (lat > ins.north || lat < ins.south || lon < ins.west || lon > ins.east) return null
            return floatArrayOf(((lon - ins.west) / (ins.east - ins.west) * img.width()).toFloat(), ((ins.north - lat) / (ins.north - ins.south) * img.height()).toFloat())
        }
        for (t in Traffic.targets.values) {
            if (t.id == Traffic.meId) continue
            val p = at(t.lat, t.lon) ?: continue
            c.save(); c.translate(p[0], p[1]); c.rotate(t.track.toFloat())
            val r = 8 * d
            val path = Path().apply { moveTo(0f, -r); lineTo(r * 0.7f, r * 0.7f); lineTo(0f, r * 0.3f); lineTo(-r * 0.7f, r * 0.7f); close() }
            c.drawPath(path, edge); c.drawPath(path, tf)
            c.restore()
            c.drawText(t.call.ifEmpty { t.id.uppercase() }, p[0] + 9 * d, p[1] - 4 * d, tfTx)
        }
        own()?.let { l ->
            at(l.latitude, l.longitude)?.let { p ->
                c.save(); c.translate(p[0], p[1]); if (l.hasBearing() && l.speed > 1.5f) c.rotate(l.bearing)
                val s = 11 * d
                val path = Path().apply {
                    moveTo(0f, -s); lineTo(s * 0.18f, -s * 0.2f); lineTo(s, s * 0.25f); lineTo(s, s * 0.45f); lineTo(s * 0.18f, s * 0.2f)
                    lineTo(s * 0.15f, s * 0.7f); lineTo(s * 0.45f, s); lineTo(-s * 0.45f, s); lineTo(-s * 0.15f, s * 0.7f)
                    lineTo(-s * 0.18f, s * 0.2f); lineTo(-s, s * 0.45f); lineTo(-s, s * 0.25f); lineTo(-s * 0.18f, -s * 0.2f); close()
                }
                c.drawPath(path, edge); c.drawPath(path, ship)
                c.restore()
            }
        }
    }
}
