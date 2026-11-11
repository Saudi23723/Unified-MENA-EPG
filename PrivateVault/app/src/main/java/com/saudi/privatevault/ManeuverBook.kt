package com.saudi.privatevault

import android.app.Activity
import android.app.Dialog
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import android.util.LruCache
import android.view.Gravity
import android.view.View
import android.widget.FrameLayout
import android.widget.HorizontalScrollView
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import java.io.File

/**
 * The pilot's own copy of Jeppesen's Private Pilot Maneuvers, carried in the app: its pages
 * shown beside each maneuver, and a reader that turns them with a swipe and zooms with a pinch.
 * The two cover photos are left out; the book starts at the preface.
 */
object ManeuverBook {
    private const val ASSET = "library/jeppesen_maneuvers.pdf"
    /** First page shown (1-based): the preface, after the two covers. */
    const val FIRST = 3

    /** The book's maneuvers by number and title, with their pages in the file (1-based, inclusive). */
    class Entry(val no: Int, val title: String, val chapter: String, val pages: IntRange)

    val ENTRIES = listOf(
        Entry(1, "Preflight Inspection", "Ground Operations", 9..14),
        Entry(2, "Engine Starting", "Ground Operations", 15..18),
        Entry(3, "Taxiing", "Ground Operations", 19..22),
        Entry(4, "Before Takeoff Check", "Ground Operations", 23..27),
        Entry(5, "Postflight Procedures", "Ground Operations", 28..31),
        Entry(6, "Straight-and-Level Flight", "Basic Maneuvers", 36..37),
        Entry(7, "Climbs", "Basic Maneuvers", 38..39),
        Entry(8, "Descents", "Basic Maneuvers", 40..41),
        Entry(9, "Turns", "Basic Maneuvers", 42..46),
        Entry(10, "Normal Takeoff and Climb", "Airport Operations", 50..53),
        Entry(11, "Crosswind Takeoff and Climb", "Airport Operations", 54..55),
        Entry(12, "Traffic Patterns", "Airport Operations", 56..61),
        Entry(13, "Normal Approach and Landing", "Airport Operations", 62..67),
        Entry(14, "Forward Slip to a Landing", "Airport Operations", 68..69),
        Entry(15, "Go-Around", "Airport Operations", 70..71),
        Entry(16, "Crosswind Approach and Landing", "Airport Operations", 72..73),
        Entry(17, "Systems and Equipment Malfunctions", "Emergency Operations", 78..81),
        Entry(18, "Emergency Descent", "Emergency Operations", 82..83),
        Entry(19, "Emergency Approach and Landing", "Emergency Operations", 84..89),
        Entry(20, "Slow Flight", "Flight Maneuvers", 93..94),
        Entry(21, "Power-Off Stalls", "Flight Maneuvers", 95..98),
        Entry(22, "Power-On Stalls", "Flight Maneuvers", 99..102),
        Entry(23, "Demonstrated Stalls and Spin Awareness", "Flight Maneuvers", 103..108),
        Entry(24, "Steep Turns", "Flight Maneuvers", 109..110),
        Entry(25, "Rectangular Course", "Ground Reference Maneuvers", 114..115),
        Entry(26, "S-Turns", "Ground Reference Maneuvers", 116..117),
        Entry(27, "Turns Around a Point", "Ground Reference Maneuvers", 118..119),
        Entry(28, "Short-Field Takeoff and Maximum Performance Climb", "Performance Takeoffs and Landings", 123..124),
        Entry(29, "Short-Field Approach and Landing", "Performance Takeoffs and Landings", 125..127),
        Entry(30, "Soft-Field Takeoff and Climb", "Performance Takeoffs and Landings", 128..129),
        Entry(31, "Soft-Field Approach and Landing", "Performance Takeoffs and Landings", 130..131),
        Entry(32, "Basic Instrument Maneuvers", "Special Flight Operations", 135..145),
        Entry(33, "Night Operations", "Special Flight Operations", 146..152),
    )

    /** The book's maneuver for each of the app's animated ones. */
    val FOR = mapOf(
        "pattern" to 12, "normal_to" to 10, "xwind_to" to 11, "short_to" to 28, "soft_to" to 30,
        "normal_ldg" to 13, "xwind_ldg" to 16, "short_ldg" to 29, "soft_ldg" to 31, "slip" to 14,
        "go_around" to 15, "steep" to 24, "rect" to 25, "sturns" to 26, "tap" to 27, "slow" to 20,
        "stall_off" to 21, "stall_on" to 22, "emer" to 19,
    )

    fun entry(no: Int?) = ENTRIES.firstOrNull { it.no == no }

    private var renderer: PdfRenderer? = null
    private val cache = object : LruCache<String, Bitmap>(48 * 1024 * 1024) {
        override fun sizeOf(key: String, value: Bitmap) = value.byteCount
    }

    private fun file(ctx: Context): File {
        val f = File(ctx.filesDir, "jeppesen_maneuvers.pdf")
        if (!f.exists() || f.length() < 1_000_000) {
            val tmp = File(ctx.filesDir, "jeppesen_maneuvers.tmp")
            ctx.assets.open(ASSET).use { i -> tmp.outputStream().use { o -> i.copyTo(o) } }
            tmp.renameTo(f)
        }
        return f
    }

    @Synchronized fun count(ctx: Context): Int = open(ctx).pageCount

    @Synchronized private fun open(ctx: Context): PdfRenderer =
        renderer ?: PdfRenderer(ParcelFileDescriptor.open(file(ctx.applicationContext), ParcelFileDescriptor.MODE_READ_ONLY)).also { renderer = it }

    /** Page [page] (1-based) as a picture [width] pixels wide. Call off the main thread. */
    @Synchronized fun page(ctx: Context, page: Int, width: Int): Bitmap? {
        val key = "$page@$width"
        cache.get(key)?.let { return it }
        return try {
            val r = open(ctx)
            if (page < 1 || page > r.pageCount) return null
            val p = r.openPage(page - 1)
            try {
                val h = (width.toFloat() * p.height / p.width).toInt()
                val bm = Bitmap.createBitmap(width, h, Bitmap.Config.ARGB_8888)
                bm.eraseColor(Color.WHITE)
                p.render(bm, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                cache.put(key, bm)
                bm
            } finally { p.close() }
        } catch (e: Exception) { null }
    }

    /** A strip of a maneuver's pages, small; a tap opens the reader there. */
    fun strip(a: Activity, e: Entry): View {
        val d = a.resources.displayMetrics.density
        fun dp(v: Int) = (v * d).toInt()
        val row = LinearLayout(a).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(2), 0, dp(2)) }
        for (p in e.pages) {
            val img = ImageView(a).apply {
                scaleType = ImageView.ScaleType.CENTER_CROP
                background = GradientDrawable().apply { cornerRadius = dp(6).toFloat(); setColor(0xFF2A2C31.toInt()) }
                clipToOutline = true
                setOnClickListener { read(a, p, e.pages) }
                contentDescription = "Page $p"
            }
            row.addView(img, LinearLayout.LayoutParams(dp(112), dp(150)).apply { marginEnd = dp(10) })
            Thread {
                val bm = page(a, p, dp(112) * 2)
                a.runOnUiThread { if (bm != null) img.setImageBitmap(bm) }
            }.start()
        }
        return HorizontalScrollView(a).apply { isHorizontalScrollBarEnabled = false; addView(row) }
    }

    /**
     * The reader: one page fills the screen; swipe for the next or the previous, pinch or
     * double-tap to zoom. Within a maneuver it stays on its pages; for the whole book, all of it.
     */
    fun read(a: Activity, start: Int, range: IntRange? = null) {
        val d = a.resources.displayMetrics.density
        fun dp(v: Int) = (v * d).toInt()
        val dlg = Dialog(a, android.R.style.Theme_Black_NoTitleBar_Fullscreen)
        val root = FrameLayout(a).apply { setBackgroundColor(0xFF0B0B0D.toInt()) }
        val img = ZoomImageView(a)
        root.addView(img, FrameLayout.LayoutParams(-1, -1))
        val spin = ProgressBar(a)
        root.addView(spin, FrameLayout.LayoutParams(dp(40), dp(40), Gravity.CENTER))
        val label = TextView(a).apply {
            textSize = 13f; setTextColor(0xFFFFFFFF.toInt()); typeface = EfbUi.MEDIUM
            background = GradientDrawable().apply { cornerRadius = dp(14).toFloat(); setColor(0xB0000000.toInt()) }
            setPadding(dp(14), dp(6), dp(14), dp(6))
        }
        root.addView(label, FrameLayout.LayoutParams(-2, -2, Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL).apply { bottomMargin = dp(28) })
        root.addView(TextView(a).apply {
            text = "✕"; textSize = 20f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
            background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(0xB0000000.toInt()) }
            setOnClickListener { dlg.dismiss() }
        }, FrameLayout.LayoutParams(dp(42), dp(42), Gravity.TOP or Gravity.END).apply { setMargins(dp(12), dp(40), dp(14), 0) })

        var total = 0
        var cur = start
        val lo = { range?.first ?: FIRST }
        val hi = { range?.last ?: total }
        val w = minOf(2000, (a.resources.displayMetrics.widthPixels * 1.6f).toInt())
        fun show(p: Int) {
            cur = p
            val e = ENTRIES.firstOrNull { p in it.pages }
            label.text = (if (e != null) "${e.no} · ${e.title}   " else "") + "${p - lo() + 1} / ${hi() - lo() + 1}"
            spin.visibility = View.VISIBLE
            Thread {
                if (total == 0) total = try { count(a) } catch (x: Exception) { 0 }
                val bm = page(a, p, w)
                a.runOnUiThread {
                    if (cur != p) return@runOnUiThread
                    spin.visibility = View.GONE
                    if (bm != null) { img.setImageBitmap(bm); img.fit() }
                    label.text = (if (e != null) "${e.no} · ${e.title}   " else "") + "${p - lo() + 1} / ${hi() - lo() + 1}"
                    // The next page ready before it is asked for.
                    Thread { if (p + 1 <= hi()) page(a, p + 1, w) }.start()
                }
            }.start()
        }
        img.onSwipe = { dir -> val n = cur + dir; if (n >= lo() && (total == 0 || n <= hi())) show(n) }
        dlg.setContentView(root)
        dlg.show()
        show(start)
    }
}
