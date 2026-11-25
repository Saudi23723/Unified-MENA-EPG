package com.saudi.privatevault

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Movie
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.os.Bundle
import android.os.SystemClock
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.SeekBar
import android.widget.TextView

/**
 * One weather picture, the way an EFB shows it: the picture filling the width; for a loop, a time
 * slider under it to stop on any frame and step through them, with play and pause; and under that
 * the key to what the colours and symbols mean, so the picture can be read without guessing.
 */
@Suppress("DEPRECATION")
class ImageryViewerActivity : BaseActivity() {
    override val alwaysDark = true
    private fun dp(v: Int) = EfbUi.dp(this, v)

    /** Draws a GIF loop at a chosen moment, or plays it. */
    private inner class LoopView(ctx: Context) : View(ctx) {
        var movie: Movie? = null
        var still: Bitmap? = null
        var at = 0
        var playing = true
        private var started = 0L
        var onTick: ((Int) -> Unit)? = null
        init { setLayerType(LAYER_TYPE_SOFTWARE, null) }

        override fun onMeasure(w: Int, h: Int) {
            val width = MeasureSpec.getSize(w)
            val m = movie; val s = still
            val ratio = when {
                m != null && m.width() > 0 -> m.height().toFloat() / m.width()
                s != null && s.width > 0 -> s.height.toFloat() / s.width
                else -> 0.75f
            }
            setMeasuredDimension(width, (width * ratio).toInt())
        }

        override fun onDraw(c: Canvas) {
            val m = movie
            if (m != null) {
                val dur = m.duration().coerceAtLeast(1)
                if (playing) {
                    val now = SystemClock.uptimeMillis()
                    if (started == 0L) started = now - at
                    at = ((now - started) % dur).toInt()
                    onTick?.invoke(at)
                }
                m.setTime(at)
                val s = width.toFloat() / m.width().coerceAtLeast(1)
                c.save(); c.scale(s, s); m.draw(c, 0f, 0f); c.restore()
                if (playing) postInvalidateDelayed(60)
                return
            }
            still?.let { b -> c.drawBitmap(b, null, RectF(0f, 0f, width.toFloat(), height.toFloat()), null) }
        }

        fun seek(ms: Int) { at = ms; playing = false; started = 0L; invalidate() }
        fun play() { playing = true; started = 0L; invalidate() }
    }

    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        window.statusBarColor = 0xFF000000.toInt()
        val url = intent.getStringExtra("url") ?: return finish()
        val title = intent.getStringExtra("title") ?: ""
        val key = intent.getStringExtra("legend") ?: ""
        val fallback = intent.getStringExtra("still")

        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(0xFF000000.toInt()) }
        val head = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(6), dp(8), dp(12), dp(8)) }
        head.addView(TextView(this).apply {
            text = "✕"; textSize = 18f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(dp(42), dp(40)); setOnClickListener { finish() }
        })
        head.addView(EfbUi.text(this, title, 15f, 0xFFFFFFFF.toInt(), bold = true), LinearLayout.LayoutParams(0, -2, 1f))
        head.addView(TextView(this).apply {
            text = "🔍"; textSize = 18f; gravity = Gravity.CENTER; layoutParams = LinearLayout.LayoutParams(dp(42), dp(40))
            setOnClickListener { startActivity(Intent(this@ImageryViewerActivity, WebActivity::class.java).putExtra("title", title).putExtra("image", url)) }
        })
        root.addView(head)
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(ScrollView(this).apply { addView(col) }, LinearLayout.LayoutParams(-1, 0, 1f))

        val view = LoopView(this)
        col.addView(view, LinearLayout.LayoutParams(-1, -2))
        val status = EfbUi.text(this, "Loading…", 12f, 0xFF9AA4B2.toInt()).apply { setPadding(dp(12), dp(6), dp(12), 0) }
        col.addView(status)

        // The time slider, for loops.
        val bar = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(8), dp(4), dp(8), dp(4)); visibility = View.GONE }
        val playBtn = TextView(this).apply { text = "⏸"; textSize = 22f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER; layoutParams = LinearLayout.LayoutParams(dp(46), dp(44)) }
        val seek = SeekBar(this)
        bar.addView(playBtn); bar.addView(seek, LinearLayout.LayoutParams(0, -2, 1f))
        col.addView(bar)
        val ends = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(dp(56), 0, dp(16), 0); visibility = View.GONE }
        ends.addView(EfbUi.text(this, "oldest", 11f, 0xFF9AA4B2.toInt()), LinearLayout.LayoutParams(0, -2, 1f))
        ends.addView(EfbUi.text(this, "latest", 11f, 0xFF9AA4B2.toInt()))
        col.addView(ends)
        playBtn.setOnClickListener {
            if (view.playing) { view.playing = false; playBtn.text = "▶" } else { view.play(); playBtn.text = "⏸" }
        }
        seek.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(s: SeekBar, p: Int, user: Boolean) { if (user) { view.seek(p); playBtn.text = "▶" } }
            override fun onStartTrackingTouch(s: SeekBar) {}
            override fun onStopTrackingTouch(s: SeekBar) {}
        })
        view.onTick = { seek.progress = it }

        col.addView(legend(key), LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) })
        setContentView(root)
        androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(root) { _, ins ->
            val bars = ins.getInsets(androidx.core.view.WindowInsetsCompat.Type.systemBars())
            root.setPadding(0, bars.top, 0, bars.bottom); ins
        }

        Thread {
            fun get(u: String): ByteArray? = try {
                val c = java.net.URL(u).openConnection() as java.net.HttpURLConnection
                c.connectTimeout = 15000; c.readTimeout = 30000
                c.setRequestProperty("User-Agent", "PilotCompanion/1.0 (EFB)")
                try { if (c.responseCode == 200) c.inputStream.use { it.readBytes() } else null } finally { c.disconnect() }
            } catch (e: Exception) { null }
            var bytes = get(url)
            var usedFallback = false
            if (bytes == null && fallback != null) { bytes = get(fallback); usedFallback = true }
            val data = bytes
            val movie = if (data != null && (if (usedFallback) fallback!! else url).lowercase().endsWith(".gif"))
                try { Movie.decodeByteArray(data, 0, data.size)?.takeIf { it.duration() > 0 } } catch (e: Throwable) { null } else null
            val still = if (movie == null && data != null) try { BitmapFactory.decodeByteArray(data, 0, data.size) } catch (e: Throwable) { null } else null
            runOnUiThread {
                when {
                    movie != null -> {
                        view.movie = movie; seek.max = movie.duration(); bar.visibility = View.VISIBLE; ends.visibility = View.VISIBLE
                        status.text = "Loop · drag the slider to stop on a frame"
                    }
                    still != null -> { view.still = still; status.text = if (usedFallback) "The loop could not be read; the latest picture is shown." else "Latest picture" }
                    else -> status.text = "The picture could not be read. Check the connection."
                }
                view.requestLayout(); view.invalidate()
            }
        }.start()
    }

    /** The key to a product's colours and symbols. */
    private fun legend(key: String): View {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setPadding(dp(14), dp(12), dp(14), dp(14))
            background = EfbUi.cardBg(this@ImageryViewerActivity, 0xFF14181F.toInt(), 12)
        }
        fun t(s: String, size: Float = 12.5f, bold: Boolean = false, color: Int = 0xFFE6E9EE.toInt()) =
            card.addView(EfbUi.text(this, s, size, color, bold).apply { setPadding(0, dp(3), 0, dp(3)) })
        fun ramp(stops: IntArray, labels: List<String>) = card.addView(object : View(this) {
            val p = Paint(Paint.ANTI_ALIAS_FLAG)
            override fun onDraw(c: Canvas) {
                val w = width.toFloat() / stops.size
                for ((i, col) in stops.withIndex()) { p.color = col; c.drawRect(i * w, 0f, (i + 1) * w, height * 0.55f, p) }
                p.color = 0xFFBFC6D0.toInt(); p.textSize = 10.5f * resources.displayMetrics.density; p.textAlign = Paint.Align.CENTER
                for ((i, l) in labels.withIndex()) c.drawText(l, (i + 0.5f) * (width.toFloat() / labels.size), height - 2f, p)
            }
        }, LinearLayout.LayoutParams(-1, dp(38)))
        fun symbol(paintIt: (Canvas, Paint, Float, Float) -> Unit, label: String) {
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
            row.addView(object : View(this) {
                val p = Paint(Paint.ANTI_ALIAS_FLAG)
                override fun onDraw(c: Canvas) = paintIt(c, p, width.toFloat(), height.toFloat())
            }, LinearLayout.LayoutParams(dp(70), dp(22)))
            row.addView(EfbUi.text(this, label, 12.5f, 0xFFE6E9EE.toInt()).apply { setPadding(dp(10), 0, 0, 0) })
            card.addView(row, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(4) })
        }
        fun front(color: Int, kind: Int): (Canvas, Paint, Float, Float) -> Unit = { c, p, w, h ->
            p.color = color; p.strokeWidth = 2.5f * resources.displayMetrics.density; p.style = Paint.Style.STROKE
            c.drawLine(0f, h * 0.65f, w, h * 0.65f, p); p.style = Paint.Style.FILL
            val n = 4; val step = w / n
            for (i in 0 until n) {
                val x = step * (i + 0.5f); val y = h * 0.65f
                val col = if (kind == 3) (if (i % 2 == 0) 0xFF1565C0.toInt() else 0xFFD32F2F.toInt()) else color
                p.color = col
                val tri = kind == 0 || (kind == 2 && i % 2 == 0) || (kind == 3 && i % 2 == 0)
                if (tri) c.drawPath(Path().apply { moveTo(x - step * 0.25f, y); lineTo(x, y - h * 0.5f); lineTo(x + step * 0.25f, y); close() }, p)
                else c.drawArc(RectF(x - step * 0.22f, y - step * 0.22f, x + step * 0.22f, y + step * 0.22f), 180f, 180f, true, p)
            }
        }
        when (key) {
            "radar" -> {
                t("Radar reflectivity (dBZ)", 14f, true)
                ramp(intArrayOf(0xFF04E9E7.toInt(), 0xFF019FF4.toInt(), 0xFF0300F4.toInt(), 0xFF02FD02.toInt(), 0xFF01C501.toInt(), 0xFF008E00.toInt(),
                    0xFFFDF802.toInt(), 0xFFE5BC00.toInt(), 0xFFFD9500.toInt(), 0xFFFD0000.toInt(), 0xFFD40000.toInt(), 0xFFBC0000.toInt(),
                    0xFFF800FD.toInt(), 0xFF9854C6.toInt(), 0xFFFDFDFD.toInt()),
                    listOf("5", "15", "25", "35", "45", "55", "65", "75"))
                t("Blue: very light, often not reaching the ground · green: light to moderate rain · yellow and orange: heavy rain · red: very heavy, likely thunderstorms · magenta and white: extreme, hail likely.")
                t("Radar shows precipitation, not cloud: an empty radar does not mean VFR. Thunderstorms are given 20 nm.", color = 0xFFFFC857.toInt())
            }
            "vis" -> {
                t("Visible / GeoColor", 14f, true)
                t("Clouds as the eye sees them by day: thick cloud bright white, thin cloud grey and see-through, the ground in its own colours. At night GeoColor shows city lights and low cloud in a separate tint.")
            }
            "ir" -> {
                t("Infrared (band 13, 10.3 µm)", 14f, true)
                ramp(intArrayOf(0xFF202020.toInt(), 0xFF606060.toInt(), 0xFFA0A0A0.toInt(), 0xFFE0E0E0.toInt(), 0xFF3FA9F5.toInt(), 0xFF2ECC40.toInt(), 0xFFFFDC00.toInt(), 0xFFFF4136.toInt()),
                    listOf("warm", "", "", "", "", "", "", "cold"))
                t("The temperature of what the satellite sees: the colder, the higher the cloud top. Bright colours are the coldest, highest tops — deep convection. Low cloud and fog are almost as warm as the ground and are easy to miss here.")
            }
            "wv" -> {
                t("Water vapour (band 9, 6.9 µm)", 14f, true)
                t("Moisture in the middle and upper air, not cloud: dark is dry air aloft (often sinking, clear), white and coloured is moist air. Swirls and dark slots show the jet stream and storm systems coming.")
            }
            "sfc", "prog" -> {
                t(if (key == "sfc") "Surface analysis symbols" else "Prognostic chart symbols", 14f, true)
                symbol(front(0xFF1565C0.toInt(), 0), "Cold front (triangles point the way it moves)")
                symbol(front(0xFFD32F2F.toInt(), 1), "Warm front (half circles point the way it moves)")
                symbol(front(0xFF1565C0.toInt(), 3), "Stationary front")
                symbol(front(0xFF7B1FA2.toInt(), 2), "Occluded front")
                symbol({ c, p, w, h -> p.color = 0xFFFF9800.toInt(); p.style = Paint.Style.STROKE; p.strokeWidth = 2.5f * resources.displayMetrics.density
                    p.pathEffect = android.graphics.DashPathEffect(floatArrayOf(10f, 7f), 0f); c.drawLine(0f, h / 2, w, h / 2, p); p.pathEffect = null }, "Trough")
                symbol({ c, p, w, h -> p.color = 0xFF1565C0.toInt(); p.style = Paint.Style.FILL; p.textSize = h * 0.9f; p.isFakeBoldText = true; c.drawText("H", w / 2 - h / 3, h * 0.85f, p) }, "High pressure: usually settled weather")
                symbol({ c, p, w, h -> p.color = 0xFFD32F2F.toInt(); p.style = Paint.Style.FILL; p.textSize = h * 0.9f; p.isFakeBoldText = true; c.drawText("L", w / 2 - h / 3, h * 0.85f, p) }, "Low pressure: cloud, rain and wind around it")
                t("Thin lines are isobars, every 4 mb: the closer together, the stronger the wind." +
                    if (key == "prog") " Green shading is where precipitation is forecast; the symbols inside it give its kind (rain, snow, showers, thunderstorms)." else "")
            }
            else -> t("Source: NOAA / National Weather Service.", 12f)
        }
        t("Source: NOAA / NWS / NESDIS. Not an official briefing.", 11f, color = 0xFF9AA4B2.toInt())
        return card
    }

    companion object {
        fun open(ctx: Context, title: String, url: String, legend: String, still: String? = null) =
            ctx.startActivity(Intent(ctx, ImageryViewerActivity::class.java).putExtra("title", title).putExtra("url", url)
                .putExtra("legend", legend).putExtra("still", still))
    }
}
