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
        group(col, "Aviation forecasts (AWC)", listOf(
            Product("☁️", "Graphical forecasts (GFA)", "Clouds, weather, ceilings and visibility, by hour", "https://aviationweather.gov/gfa/", page = true),
            Product("⚠️", "SIGMETs · G-AIRMETs", "Turbulence, icing, IFR, mountain obscuration", "https://aviationweather.gov/gairmet/", page = true),
            Product("🌬", "Winds and temperatures aloft", "Forecast winds by altitude", "https://aviationweather.gov/windtemp/", page = true),
            Product("🧊", "Icing", "Current and forecast icing", "https://aviationweather.gov/icing/", page = true),
            Product("〰️", "Turbulence", "Graphical turbulence guidance", "https://aviationweather.gov/gtg/", page = true),
            Product("☁️", "Ceiling and visibility", "Analysis by station", "https://aviationweather.gov/cva/", page = true),
            Product("✈️", "PIREPs", "What pilots are reporting", "https://aviationweather.gov/pireps/", page = true),
        ))
        col.addView(EfbUi.text(this, getString(R.string.imagery_note), 11.5f, EfbUi.DIM).apply { setPadding(EfbUi.dp(this@ImageryActivity, 6), EfbUi.dp(this@ImageryActivity, 16), 0, 0) })
    }

    private fun group(col: LinearLayout, title: String, items: List<Product>) {
        col.addView(EfbUi.section(this, title))
        val card = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; background = EfbUi.cardBg(this@ImageryActivity, EfbUi.CARD, 12) }
        fun dp(v: Int) = EfbUi.dp(this, v)
        for ((i, p) in items.withIndex()) {
            if (i > 0) card.addView(View(this).apply { setBackgroundColor(EfbUi.CARD_LINE) }, LinearLayout.LayoutParams(-1, 1).apply { marginStart = dp(56) })
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(14), dp(12), dp(12), dp(12)) }
            row.addView(EfbUi.text(this, p.icon, 20f).apply { gravity = Gravity.CENTER }, LinearLayout.LayoutParams(dp(30), -2))
            val t = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(12), 0, dp(8), 0) }
            t.addView(EfbUi.text(this, p.name, 15.5f, EfbUi.TEXT).apply { typeface = EfbUi.MEDIUM })
            t.addView(EfbUi.text(this, p.sub, 12.5f, EfbUi.DIM))
            row.addView(t, LinearLayout.LayoutParams(0, -2, 1f))
            row.addView(EfbUi.text(this, "›", 22f, EfbUi.DIM))
            row.setOnClickListener {
                val i2 = Intent(this, WebActivity::class.java).putExtra("title", p.name)
                if (p.page) i2.putExtra("url", p.url) else i2.putExtra("image", p.url)
                startActivity(i2)
            }
            card.addView(row)
        }
        col.addView(card)
    }
}
