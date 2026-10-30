package com.saudi.privatevault

import android.annotation.SuppressLint
import android.app.Activity
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.view.MotionEvent
import android.view.View
import android.widget.LinearLayout
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import java.io.File
import java.util.UUID

/** A signature written with a finger or the S Pen, saved as a trimmed PNG. */
@SuppressLint("ViewConstructor")
class SignaturePad(act: Activity) : View(act) {
    private val path = Path()
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = 0xFF0D2A6B.toInt()
        style = Paint.Style.STROKE
        strokeWidth = 3.2f * act.resources.displayMetrics.density
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }
    private val guide = Paint().apply { color = 0xFFB0BEC5.toInt(); strokeWidth = act.resources.displayMetrics.density }
    var empty = true
        private set

    init { setBackgroundColor(0xFFFFFFFF.toInt()) }

    override fun onDraw(c: Canvas) {
        c.drawLine(width * 0.06f, height * 0.78f, width * 0.94f, height * 0.78f, guide)
        c.drawPath(path, paint)
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(e: MotionEvent): Boolean {
        parent?.requestDisallowInterceptTouchEvent(true)
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> { path.moveTo(e.x, e.y); empty = false }
            MotionEvent.ACTION_MOVE -> {
                for (h in 0 until e.historySize) path.lineTo(e.getHistoricalX(h), e.getHistoricalY(h))
                path.lineTo(e.x, e.y)
            }
            MotionEvent.ACTION_UP -> path.lineTo(e.x, e.y)
        }
        invalidate()
        return true
    }

    fun clear() {
        path.reset()
        empty = true
        invalidate()
    }

    /** The ink alone, on transparent, cropped to what was written. */
    fun save(dir: File): String? {
        if (empty) return null
        val b = android.graphics.RectF()
        path.computeBounds(b, true)
        val pad = paint.strokeWidth * 2
        val w = (b.width() + 2 * pad).toInt().coerceAtLeast(2)
        val h = (b.height() + 2 * pad).toInt().coerceAtLeast(2)
        val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        val c = Canvas(bmp)
        c.translate(pad - b.left, pad - b.top)
        c.drawPath(path, paint)
        val name = "sig_" + UUID.randomUUID().toString().take(12) + ".png"
        File(dir, name).outputStream().use { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }
        return name
    }

    companion object {
        /** Asks for a signature; hands back the saved file's name. */
        fun ask(act: Activity, title: String, onSigned: (String) -> Unit) {
            val pad = SignaturePad(act)
            val d = act.resources.displayMetrics.density
            val box = LinearLayout(act).apply {
                orientation = LinearLayout.VERTICAL
                setPadding((16 * d).toInt(), (8 * d).toInt(), (16 * d).toInt(), 0)
                addView(pad, LinearLayout.LayoutParams(-1, (180 * d).toInt()))
            }
            MaterialAlertDialogBuilder(act)
                .setTitle(title)
                .setView(box)
                .setPositiveButton(R.string.log_save) { _, _ -> pad.save(Logbook.signatures(act))?.let(onSigned) }
                .setNeutralButton(R.string.sig_clear, null)
                .setNegativeButton(R.string.cancel, null)
                .show()
                .getButton(android.content.DialogInterface.BUTTON_NEUTRAL)?.setOnClickListener { pad.clear() }
        }
    }
}
