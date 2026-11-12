package com.saudi.privatevault

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Point
import android.graphics.Rect
import android.graphics.RectF
import android.view.MotionEvent
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay

/**
 * The airport diagram big at any zoom: from afar a field's diagram is a stamp on the chart, so
 * here it is drawn as a large card beside the field (about half the screen), tied to it by a
 * line, with the aircraft and the traffic placed on it where they really are. Close in, the
 * diagram lies on the chart itself and the card steps aside. A tap on the card goes there.
 */
class DiagramInsetOverlay(
    private val map: MapView,
    private val own: () -> android.location.Location?,
    private val onOpen: (Inset) -> Unit,
) : Overlay() {
    class Inset(val ident: String, val bmp: Bitmap, val north: Double, val west: Double, val south: Double, val east: Double, val lat: Double, val lon: Double)

    val insets = LinkedHashMap<String, Inset>()
    /** Below this zoom the card shows; at or above it the diagram on the chart is big enough. */
    var closeZoom = 14.0

    private val d = map.resources.displayMetrics.density
    private val card = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFFFFFF.toInt() }
    private val frame = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; color = 0xFF1B1D22.toInt(); strokeWidth = 2.5f * d }
    private val shadow = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0x55000000 }
    private val lead = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; color = 0xFF2D8CFF.toInt(); strokeWidth = 2.5f * d }
    private val dot = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF2D8CFF.toInt() }
    private val head = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xF01B1D22.toInt() }
    private val headTx = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFFFFFF.toInt(); textSize = 13f * d; isFakeBoldText = true }
    private val bmpPaint = Paint(Paint.FILTER_BITMAP_FLAG or Paint.ANTI_ALIAS_FLAG)
    private val ship = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF00B4FF.toInt() }
    private val shipEdge = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; color = 0xFF000000.toInt(); strokeWidth = 1.6f * d }
    private val tf = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFFFF9500.toInt() }
    private val tfTx = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF111111.toInt(); textSize = 10.5f * d; isFakeBoldText = true }
    private val pt = Point()
    private var shown: Inset? = null
    private val box = RectF()

    /** The field to show: the one with a diagram nearest the screen's centre, if it is on the screen. */
    private fun pick(mv: MapView): Inset? {
        if (mv.zoomLevelDouble >= closeZoom) return null
        val bb = mv.boundingBox; val c = mv.mapCenter
        return insets.values.filter { it.lat in bb.latSouth..bb.latNorth && it.lon in bb.lonWest..bb.lonEast }
            .minByOrNull { Nav.distanceNm(c.latitude, c.longitude, it.lat, it.lon) }
    }

    override fun draw(c: Canvas, mv: MapView, sh: Boolean) {
        if (sh) return
        val ins = pick(mv) ?: run { shown = null; return }
        shown = ins
        mv.projection.toPixels(GeoPoint(ins.lat, ins.lon), pt)
        // Undo the chart's turn for the card: it stays upright on the screen.
        c.save(); c.rotate(-mv.mapOrientation, mv.width / 2f, mv.height / 2f)
        val ax = pt.x.toFloat(); val ay = pt.y.toFloat()
        val w = minOf(mv.width, mv.height) * 0.56f
        val h = (w * ins.bmp.height / ins.bmp.width).coerceAtMost(mv.height * 0.62f)
        val cw = h * ins.bmp.width / ins.bmp.height
        val headH = 26 * d
        // Beside the field: to the side with more room, and inside the screen.
        val right = ax < mv.width / 2f
        var left = if (right) ax + 46 * d else ax - 46 * d - cw
        var top = ay - (h + headH) / 2
        left = left.coerceIn(8 * d, mv.width - cw - 8 * d)
        top = top.coerceIn(70 * d, (mv.height - h - headH - 90 * d).coerceAtLeast(70 * d))
        box.set(left, top, left + cw, top + headH + h)
        // The tie to the field.
        val ex = if (right) box.left else box.right
        c.drawLine(ax, ay, ex, box.centerY(), lead)
        c.drawCircle(ax, ay, 6 * d, dot)
        // The card.
        c.drawRoundRect(RectF(box.left + 3 * d, box.top + 4 * d, box.right + 3 * d, box.bottom + 4 * d), 10 * d, 10 * d, shadow)
        c.drawRoundRect(box, 10 * d, 10 * d, card)
        c.save()
        c.clipRect(box)
        c.drawRect(box.left, box.top, box.right, box.top + headH, head)
        c.drawText("${ins.ident}  ·  Airport diagram   (tap to go there)", box.left + 10 * d, box.top + 18 * d, headTx)
        val img = RectF(box.left, box.top + headH, box.right, box.bottom)
        c.drawBitmap(ins.bmp, Rect(0, 0, ins.bmp.width, ins.bmp.height), img, bmpPaint)
        fun at(lat: Double, lon: Double): FloatArray? {
            if (lat > ins.north || lat < ins.south || lon < ins.west || lon > ins.east) return null
            return floatArrayOf(img.left + ((lon - ins.west) / (ins.east - ins.west) * img.width()).toFloat(),
                img.top + ((ins.north - lat) / (ins.north - ins.south) * img.height()).toFloat())
        }
        // Everyone around, and me.
        for (t in Traffic.targets.values) {
            val p = at(t.lat, t.lon) ?: continue
            c.save(); c.translate(p[0], p[1]); c.rotate(t.track.toFloat())
            val r = 8 * d
            val path = Path().apply { moveTo(0f, -r); lineTo(r * 0.7f, r * 0.7f); lineTo(0f, r * 0.3f); lineTo(-r * 0.7f, r * 0.7f); close() }
            c.drawPath(path, shipEdge); c.drawPath(path, tf)
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
                c.drawPath(path, shipEdge); c.drawPath(path, ship)
                c.restore()
            }
        }
        c.restore()
        c.drawRoundRect(box, 10 * d, 10 * d, frame)
        c.restore()
    }

    override fun onSingleTapConfirmed(e: MotionEvent, mv: MapView): Boolean {
        val ins = shown ?: return false
        // The box is in the card's upright frame; turn the tap the same way.
        val p = floatArrayOf(e.x, e.y)
        android.graphics.Matrix().apply { setRotate(mv.mapOrientation, mv.width / 2f, mv.height / 2f) }.mapPoints(p)
        if (!box.contains(p[0], p[1])) return false
        onOpen(ins)
        return true
    }
}
