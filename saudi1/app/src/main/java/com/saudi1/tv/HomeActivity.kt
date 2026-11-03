package com.saudi1.tv

import android.content.Intent
import android.os.Bundle
import android.text.SpannableString
import android.text.Spanned
import android.text.style.ForegroundColorSpan
import android.view.LayoutInflater
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class HomeActivity : AppCompatActivity() {
    private lateinit var status: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_home)
        status = findViewById(R.id.status)
        val logo = SpannableString("SAUDI.1")
        logo.setSpan(ForegroundColorSpan(getColor(R.color.accent)), 5, 7, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
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
        tile("🎬", "Movies") { soon() }
        tile("🎞", "Series") { soon() }
        tile("⚙", "Settings") { startActivity(Intent(this, SetupActivity::class.java)) }
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
        status.text = Prefs.server.substringAfter("://")
        // the lists are ready before Live TV opens: from the copy on the TV first, then fresh in the background
        if (Api.groups.isEmpty()) lifecycleScope.launch(Dispatchers.IO) {
            try { Api.load(cached = true) } catch (_: Exception) { }
            try { Api.load(cached = false) } catch (_: Exception) { }
        }
    }

    private fun open(c: Class<*>) = startActivity(Intent(this, c))

    private fun soon() = android.widget.Toast.makeText(this, "Coming in the next update", android.widget.Toast.LENGTH_SHORT).show()

    private fun reload() {
        status.text = "Loading…"
        lifecycleScope.launch {
            val ok = withContext(Dispatchers.IO) { try { Api.load(cached = false) } catch (e: Exception) { false } }
            val n = Api.groups.firstOrNull { it.id == Api.ALL }?.channels?.size ?: 0
            status.text = if (ok) "Updated · $n channels" else "Could not reach the server"
        }
    }
}
