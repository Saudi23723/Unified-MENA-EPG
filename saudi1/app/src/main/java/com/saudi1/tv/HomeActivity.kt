package com.saudi1.tv

import android.content.Intent
import android.os.Bundle
import android.text.SpannableString
import android.text.Spanned
import android.text.style.ForegroundColorSpan
import android.view.LayoutInflater
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class HomeActivity : BaseActivity() {
    private lateinit var status: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_home)
        status = findViewById(R.id.status)
        val logo = SpannableString("SAUDI.TV")
        logo.setSpan(ForegroundColorSpan(getColor(R.color.accent)), 5, 8, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        findViewById<TextView>(R.id.logo).text = logo
        findViewById<TextView>(R.id.footer).text = "Version " + BuildConfig.VERSION_NAME

        val tiles = findViewById<LinearLayout>(R.id.tiles)
        fun tile(icon: String, label: String, go: () -> Unit) {
            val v = LayoutInflater.from(this).inflate(R.layout.item_tile, tiles, false)
            v.findViewById<TextView>(R.id.icon).text = icon
            v.findViewById<TextView>(R.id.label).apply { text = label; setTextColor(getColorStateList(R.color.on_focus)) }
            v.setOnClickListener { go() }
            tiles.addView(v)
        }
        tile("📺", "Live TV") { open(LiveActivity::class.java) }
        tile("🗓", "TV Guide") { open(GuideActivity::class.java) }
        tile("🎬", "Movies") { startActivity(Intent(this, VodActivity::class.java).putExtra("series", false)) }
        tile("🎞", "Series") { startActivity(Intent(this, VodActivity::class.java).putExtra("series", true)) }
        tile("⚽", "Sports today") { open(SportsActivity::class.java) }
        tile("🔍", "Search") { open(SearchActivity::class.java) }
        tile("☰", "Playlists") { playlists() }
        tile("⚙", "Settings") { startActivity(Intent(this, SettingsActivity::class.java)) }
        tiles.getChildAt(0).requestFocus()
        if (isTouch) {  // phones: everything closer together so it fits a phone held sideways
            val dd = resources.displayMetrics.density
            findViewById<View>(R.id.homeCol).setPadding(0, (14 * dd).toInt(), 0, (40 * dd).toInt())
            (findViewById<View>(R.id.tilesScroll).layoutParams as LinearLayout.LayoutParams).topMargin = (18 * dd).toInt()
            (findViewById<View>(R.id.reload).layoutParams as LinearLayout.LayoutParams).topMargin = (14 * dd).toInt()
        }

        findViewById<TextView>(R.id.reload).apply {
            setTextColor(getColorStateList(R.color.on_focus))
            setOnClickListener { reload() }
        }
        lifecycleScope.launch {
            val clock = findViewById<TextView>(R.id.clock)
            val f = SimpleDateFormat("EEEE d MMMM  ·  h:mm a", Locale.ENGLISH)
            while (true) { clock.text = f.format(Date()); delay(15_000) }
        }
    }

    override fun onResume() {
        super.onResume()
        // opened again from the TV's home screen: straight back to the channel that was on (like TiviMate)
        val fresh = !resumedOnce; resumedOnce = true
        if (fresh || BaseActivity.cameBack) {
            BaseActivity.cameBack = false
            if (Prefs.ready && App.prefs.contains("last_channel") && App.prefs.getBoolean("open_last", true)) {
                startActivity(Intent(this, LiveActivity::class.java).putExtra("channel", Prefs.lastChannel)); return
            }
        }
        if (!Prefs.ready) { startActivity(Intent(this, SetupActivity::class.java)); return }
        status.text = (Device.name.ifEmpty { Prefs.server.substringAfter("://") }) + "   ·   Device " + Device.pretty
        // the lists are ready before Live TV opens: from the copy on the TV first, then fresh in the background
        lifecycleScope.launch(Dispatchers.IO) {
            if (Api.groups.isEmpty()) try { Api.load(cached = true) } catch (_: Exception) { }
            // stopped / expired / moved to another playlist on the admin site
            if (!Device.manual && Device.check() != "offline" && !Prefs.ready) {
                withContext(Dispatchers.Main) { startActivity(Intent(this@HomeActivity, SetupActivity::class.java)) }
                return@launch
            }
            // the VPN starts by itself when it is on (Android asked for permission once, in Settings)
            if (Vpn.wanted && !Vpn.up && Vpn.conf.isNotBlank() && android.net.VpnService.prepare(this@HomeActivity) == null) Vpn.start(this@HomeActivity)
            if (Api.groups.isEmpty() || System.currentTimeMillis() - lastLoad > 15 * 60_000) {
                try { if (Api.load(cached = false)) lastLoad = System.currentTimeMillis() } catch (_: Exception) { }
            }
        }
    }

    private var lastLoad = 0L
    private var resumedOnce = false

    private fun playlists() {
        val ps = Device.playlists()
        if (ps.size < 2) { android.widget.Toast.makeText(this, if (ps.isEmpty()) "One playlist on this device" else "Playlist: " + ps[0].optString("name"), android.widget.Toast.LENGTH_LONG).show(); return }
        val cur = ps.indexOfFirst { it.optString("name") == Device.active }.coerceAtLeast(0)
        androidx.appcompat.app.AlertDialog.Builder(this).setTitle("Playlists")
            .setSingleChoiceItems(ps.map { it.optString("name").replaceFirstChar { c -> c.uppercase() } }.toTypedArray(), cur) { d, w ->
                d.dismiss()
                if (w == cur) return@setSingleChoiceItems
                Device.use(ps[w]); reload()
            }.show()
    }

    private fun dim() {
        nightDialog()
    }

    private fun open(c: Class<*>) = startActivity(Intent(this, c))

    private fun soon() = android.widget.Toast.makeText(this, "Coming in the next update", android.widget.Toast.LENGTH_SHORT).show()

    private fun reload() {
        status.text = "Loading…"
        lifecycleScope.launch {
            val ok = withContext(Dispatchers.IO) {
                // the owner may have changed this device's playlist or login on the admin site
                if (!Device.manual) Device.check()
                try { Prefs.ready && Api.load(cached = false) } catch (e: Exception) { false }
            }
            if (!Prefs.ready) { startActivity(Intent(this@HomeActivity, SetupActivity::class.java)); return@launch }
            val n = Api.groups.firstOrNull { it.id == Api.ALL }?.channels?.size ?: 0
            status.text = if (ok) "Updated · $n channels" else "Could not reach the server"
        }
    }
}
