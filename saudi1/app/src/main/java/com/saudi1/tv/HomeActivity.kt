package com.saudi1.tv

import android.content.Intent
import android.os.Bundle
import android.text.SpannableString
import android.text.Spanned
import android.text.style.ForegroundColorSpan
import android.view.LayoutInflater
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
        tile("🌙", "Dimming") { dim() }
        tile("⚙", "Settings") { startActivity(Intent(this, SettingsActivity::class.java)) }
        tiles.getChildAt(0).requestFocus()

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
            if (Api.groups.isEmpty() || System.currentTimeMillis() - lastLoad > 15 * 60_000) {
                try { if (Api.load(cached = false)) lastLoad = System.currentTimeMillis() } catch (_: Exception) { }
            }
        }
    }

    private var lastLoad = 0L

    private fun dim() {
        androidx.appcompat.app.AlertDialog.Builder(this).setTitle("Night dimming")
            .setSingleChoiceItems(Dim.levels.map { if (it == 0) "Off" else "$it %" }.toTypedArray(), Dim.levels.indexOf(Dim.level).coerceAtLeast(0)) { d, w ->
                Dim.level = Dim.levels[w]; applyDim(); d.dismiss()
            }.show()
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
