package com.saudi.privatevault

import android.os.Bundle
import android.widget.LinearLayout
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Airports, as ForeFlight's first tab: one airport on a page of its own (the home field first,
 * any other by search): its facts, weather, runways and traffic pattern, procedures and NOTAMs.
 */
class AirportsActivity : BaseActivity() {
    private lateinit var col: LinearLayout
    private var airports: List<AviationData.Airport> = emptyList()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        col = EfbUi.screen(this, getString(R.string.ff_airports)) { bar ->
            bar.menu.add(0, 1, 0, R.string.map_find).setIcon(R.drawable.ic_search).apply {
                icon?.setTint(EfbUi.TEXT); setShowAsAction(android.view.MenuItem.SHOW_AS_ACTION_ALWAYS)
            }
            bar.menu.add(0, 2, 0, "NRST").setShowAsAction(android.view.MenuItem.SHOW_AS_ACTION_ALWAYS)
            bar.setOnMenuItemClickListener { item ->
                when (item.itemId) {
                    1 -> AirportSearch.show(this, airports, null) { a -> show(a) }
                    2 -> startActivity(android.content.Intent(this, MapActivity::class.java).putExtra(MapActivity.EXTRA_NRST, true)
                        .addFlags(android.content.Intent.FLAG_ACTIVITY_REORDER_TO_FRONT))
                }
                true
            }
        }
        lifecycleScope.launch {
            airports = withContext(Dispatchers.IO) { AviationData.airports(this@AirportsActivity) }
            val want = VaultLock.prefs(this@AirportsActivity).getString("airports_ident", null)
                ?: VaultLock.prefs(this@AirportsActivity).getString("efb_home", "KBVU") ?: "KBVU"
            airports.firstOrNull { it.icao == want || it.ident == want }?.let { show(it) }
        }
    }

    private fun show(a: AviationData.Airport) {
        VaultLock.prefs(this).edit().putString("airports_ident", a.icao.ifEmpty { a.ident }).apply()
        col.removeAllViews()
        AirportSheet(this, a, a.icao.ifEmpty { a.ident }, null,
            onDirect = { startActivity(android.content.Intent(this, MapActivity::class.java).putExtra(MapActivity.EXTRA_AIRPORT, a.ident)) },
            onAddToRoute = { startActivity(android.content.Intent(this, MapActivity::class.java).putExtra(MapActivity.EXTRA_AIRPORT, a.ident)) },
        ).showIn(col)
    }
}
