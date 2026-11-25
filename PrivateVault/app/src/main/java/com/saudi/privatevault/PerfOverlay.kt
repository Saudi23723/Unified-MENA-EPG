package com.saudi.privatevault

import android.graphics.Canvas
import android.graphics.Paint
import android.os.SystemClock
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Overlay

/**
 * A readout for finding out why a map is slow, from the phone itself. Two of these bracket every
 * other overlay: the first notes the time, the last measures how long everything between them took
 * to draw and shows the frames per second, the average and worst draw time over the last second, and
 * how long the drawn sheet's picture took the last time it was redrawn. It draws nothing else and is
 * off unless asked for in the settings.
 */
class PerfOverlay(private val map: MapView, private val first: Boolean) : Overlay() {
    private val d = map.resources.displayMetrics.density
    private val bg = Paint().apply { color = 0xCC000000.toInt() }
    private val tx = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF7CFC00.toInt(); textSize = 12f * d; typeface = android.graphics.Typeface.MONOSPACE }

    companion object {
        @Volatile var t0 = 0L
        private var winStart = 0L
        private var frames = 0
        private var sum = 0L
        private var worst = 0L
        private var fps = 0
        private var avg = 0f
        private var worstShown = 0L
    }

    override fun draw(c: Canvas, mv: MapView, shadow: Boolean) {
        if (shadow) return
        val now = SystemClock.uptimeMillis()
        if (first) { t0 = now; return }
        val ms = now - t0
        frames++; sum += ms; if (ms > worst) worst = ms
        if (now - winStart >= 1000L) {
            fps = frames; avg = if (frames > 0) sum.toFloat() / frames else 0f; worstShown = worst
            frames = 0; sum = 0; worst = 0; winStart = now
        }
        val lines = listOf(
            "frames/s  $fps",
            "overlays  %.0f ms avg · %d ms worst".format(avg, worstShown),
            "sheet picture  ${AeroMap.lastRenderMs} ms · ${AeroMap.renders} redraws",
        )
        val w = lines.maxOf { tx.measureText(it) } + 16 * d
        val h = lines.size * 16 * d + 8 * d
        val x = 10 * d; val y = 150 * d
        c.save()
        c.rotate(-mv.mapOrientation, mv.width / 2f, mv.height / 2f)
        c.drawRect(x, y, x + w, y + h, bg)
        for ((i, s) in lines.withIndex()) c.drawText(s, x + 8 * d, y + (i + 1) * 16 * d, tx)
        c.restore()
    }
}
