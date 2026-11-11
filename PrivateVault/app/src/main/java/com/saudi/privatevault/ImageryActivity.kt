package com.saudi.privatevault

import android.content.Intent
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout

/**
 * Imagery, as ForeFlight's tab: the weather pictures a pilot reads before and during a flight,
 * grouped (radar, satellite, prognostic charts, aviation forecasts), each opened full screen to
 * zoom, the loops moving. Straight from the NWS, NOAA and the Aviation Weather Center.
 */
class ImageryActivity : BaseActivity() {
    private class Product(val icon: String, val name: String, val sub: String, val url: String, val page: Boolean = false)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val col = EfbUi.screen(this, getString(R.string.ff_imagery))
        group(col, "Radar", listOf(
            Product("📡", "Las Vegas radar (KESX) · loop", "Base reflectivity, the nearest NEXRAD to KBVU", "https://radar.weather.gov/ridge/standard/KESX_loop.gif"),
            Product("📡", "Southwest radar · loop", "Pacific Southwest mosaic", "https://radar.weather.gov/ridge/standard/PACSOUTHWEST_loop.gif"),
            Product("📡", "US radar · loop", "Continental mosaic", "https://radar.weather.gov/ridge/standard/CONUS_loop.gif"),
        ))
        group(col, "Satellite", listOf(
            Product("🛰", "Southwest · visible colour", "GOES-West GeoColor", "https://cdn.star.nesdis.noaa.gov/GOES18/ABI/SECTOR/psw/GEOCOLOR/1200x1200.jpg"),
            Product("🛰", "Southwest · infrared", "Cloud tops by temperature (band 13)", "https://cdn.star.nesdis.noaa.gov/GOES18/ABI/SECTOR/psw/13/1200x1200.jpg"),
            Product("🛰", "Southwest · water vapour", "Moisture aloft (band 9)", "https://cdn.star.nesdis.noaa.gov/GOES18/ABI/SECTOR/psw/09/1200x1200.jpg"),
        ))
        group(col, "Prognostic charts", listOf(
            Product("🗺", "Surface analysis", "Fronts and pressure now", "https://www.wpc.ncep.noaa.gov/sfc/namussfcwbg.gif"),
            Product("🗺", "12-hour prog", "Fronts, pressure and weather in 12 h", "https://www.wpc.ncep.noaa.gov/basicwx/92fwbg.gif"),
            Product("🗺", "24-hour prog", "In 24 h", "https://www.wpc.ncep.noaa.gov/basicwx/94fwbg.gif"),
        ))
        group(col, "Aviation weather (AWC)", listOf(
            Product("☁️", "Graphical forecasts (GFA)", "Clouds, weather, ceilings and visibility, by hour", "https://aviationweather.gov/gfa/", page = true),
            Product("⚠️", "SIGMETs · G-AIRMETs (West)", "Turbulence, icing, IFR, mountain obscuration — now", "data:sigmet"),
            Product("🌬", "Winds and temperatures aloft", "FB forecast, San Francisco and Salt Lake areas", "data:winds"),
            Product("✈️", "PIREPs near you", "What pilots reported in the last 3 hours, 150 nm", "data:pireps"),
        ))
        col.addView(EfbUi.text(this, getString(R.string.imagery_note), 11.5f, EfbUi.DIM).apply { setPadding(EfbUi.dp(this@ImageryActivity, 6), EfbUi.dp(this@ImageryActivity, 16), 0, 0) })
    }

    /** The text products, read here: no website in between. */
    private fun showData(p: Product) {
        val tv = EfbUi.text(this, "…", 13f, EfbUi.TEXT, mono = true).apply {
            setTextIsSelectable(true); textDirection = View.TEXT_DIRECTION_LTR
            setPadding(EfbUi.dp(this@ImageryActivity, 18), EfbUi.dp(this@ImageryActivity, 8), EfbUi.dp(this@ImageryActivity, 18), 0)
        }
        val dlg = com.google.android.material.dialog.MaterialAlertDialogBuilder(this).setTitle(p.name)
            .setView(android.widget.ScrollView(this).apply { addView(tv) }).setPositiveButton(android.R.string.ok, null).show()
        val home = VaultLock.prefs(this).getString("efb_home", "KBVU") ?: "KBVU"
        Thread {
            val text = try {
                when (p.url) {
                    "data:winds" -> AviationData.windsAloft()
                    "data:sigmet" -> AviationData.airspaceWeather().joinToString("\n\n————\n\n") { it.text }.ifEmpty { "No SIGMETs or G-AIRMETs over the West right now." }
                    else -> {
                        val apt = AviationData.airports(this).firstOrNull { it.icao == home || it.ident == home }
                        val la = apt?.lat ?: 35.95; val lo = apt?.lon ?: -114.86
                        AviationData.pireps(la - 2.5, lo - 3.0, la + 2.5, lo + 3.0).joinToString("\n\n") { (if (it.urgent) "⚠ UUA  " else "") + it.raw }
                            .ifEmpty { "No PIREPs within about 150 nm in the last 3 hours." }
                    }
                }
            } catch (e: Exception) { "Not available right now: " + (e.message ?: "") }
            runOnUiThread { if (dlg.isShowing) tv.text = text }
        }.start()
    }

    /** A group as ForeFlight lays imagery out: a grid of live thumbnails, each titled, a tap opens it full screen. */
    private fun group(col: LinearLayout, title: String, items: List<Product>) {
        col.addView(EfbUi.section(this, title))
        fun dp(v: Int) = EfbUi.dp(this, v)
        val wide = resources.displayMetrics.widthPixels / resources.displayMetrics.density > 600
        val grid = android.widget.GridLayout(this).apply { columnCount = if (wide) 3 else 2 }
        val cellW = (resources.displayMetrics.widthPixels - dp(28)) / grid.columnCount - dp(8)
        for (p in items) {
            val card = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                background = EfbUi.cardBg(this@ImageryActivity, EfbUi.CARD, 12)
                clipToOutline = true
            }
            val img = android.widget.ImageView(this).apply {
                scaleType = android.widget.ImageView.ScaleType.CENTER_CROP
                setBackgroundColor(0xFF0A0B0D.toInt())
            }
            val thumbH = (cellW * 0.72f).toInt()
            if (p.url.startsWith("http") && !p.page) {
                card.addView(img, LinearLayout.LayoutParams(-1, thumbH))
                Thread {
                    val bmp = try {
                        val bytes = java.net.URL(p.url).openStream().use { it.readBytes() }
                        val o = android.graphics.BitmapFactory.Options().apply { inJustDecodeBounds = true }
                        android.graphics.BitmapFactory.decodeByteArray(bytes, 0, bytes.size, o)
                        var s = 1; while (o.outWidth / (s * 2) >= cellW) s *= 2
                        android.graphics.BitmapFactory.decodeByteArray(bytes, 0, bytes.size, android.graphics.BitmapFactory.Options().apply { inSampleSize = s })
                    } catch (e: Exception) { null }
                    runOnUiThread { if (bmp != null) img.setImageBitmap(bmp) else img.setImageDrawable(null) }
                }.start()
            } else {
                // Text products and pages: a large symbol instead of a picture.
                card.addView(EfbUi.text(this, p.icon, 40f).apply { gravity = Gravity.CENTER; setBackgroundColor(EfbUi.BAND) }, LinearLayout.LayoutParams(-1, thumbH))
            }
            card.addView(EfbUi.text(this, p.name, 14f, EfbUi.TEXT).apply { typeface = EfbUi.MEDIUM; maxLines = 2; setPadding(dp(10), dp(8), dp(10), 0) })
            card.addView(EfbUi.text(this, p.sub, 11.5f, EfbUi.DIM).apply { maxLines = 2; setPadding(dp(10), dp(2), dp(10), dp(10)) })
            card.setOnClickListener {
                if (p.url.startsWith("data:")) { showData(p); return@setOnClickListener }
                val i2 = Intent(this, WebActivity::class.java).putExtra("title", p.name)
                if (p.page) i2.putExtra("url", p.url) else i2.putExtra("image", p.url)
                startActivity(i2)
            }
            grid.addView(card, android.widget.GridLayout.LayoutParams().apply { width = cellW; setMargins(dp(4), dp(4), dp(4), dp(4)) })
        }
        col.addView(grid)
    }
}
