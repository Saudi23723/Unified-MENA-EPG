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

        buildCards()
        findViewById<TextView>(R.id.reload).setOnClickListener { reload() }
        findViewById<TextView>(R.id.settingsChip).setOnClickListener { startActivity(Intent(this, SettingsActivity::class.java)) }
        lifecycleScope.launch {
            val clock = findViewById<TextView>(R.id.clock); val date = findViewById<TextView>(R.id.date); val hello = findViewById<TextView>(R.id.hello)
            val tf = SimpleDateFormat("h:mm a", Locale.ENGLISH); val df = SimpleDateFormat("EEEE d MMMM", Locale.ENGLISH)
            while (true) {
                val now = Date(); clock.text = tf.format(now); date.text = df.format(now)
                val h = java.util.Calendar.getInstance().get(java.util.Calendar.HOUR_OF_DAY)
                hello.text = when (h) { in 5..11 -> "Good morning"; in 12..16 -> "Good afternoon"; else -> "Good evening" }
                delay(15_000)
            }
        }
    }

    // ---------------- the cards ----------------
    private val d by lazy { resources.displayMetrics.density }
    private fun dp(v: Float) = (v * d).toInt()
    private var liveSub: TextView? = null

    /** a big card with a colour gradient: icon on top, name + one line below */
    private fun bigCard(row: LinearLayout, icon: String, title: String, sub: String, c1: Int, c2: Int, w: Float, go: () -> Unit): TextView {
        val bg = android.graphics.drawable.GradientDrawable(android.graphics.drawable.GradientDrawable.Orientation.TL_BR, intArrayOf(c1, c2)).apply { cornerRadius = 26 * d }
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; background = bg; isFocusable = true; isClickable = true
            setPadding(dp(24f), dp(20f), dp(24f), dp(20f)); gravity = android.view.Gravity.BOTTOM
        }
        val k = if (isTouch) 0.78f else 1f
        card.addView(TextView(this).apply { text = icon; textSize = 40f * k }, LinearLayout.LayoutParams(-2, 0, 1f))
        card.addView(TextView(this).apply { text = title; textSize = 24f * k; setTypeface(typeface, android.graphics.Typeface.BOLD); setTextColor(0xFFFFFFFF.toInt()) })
        val st = TextView(this).apply { text = sub; textSize = 14f * k; setTextColor(0xD9FFFFFF.toInt()); setSingleLine(); ellipsize = android.text.TextUtils.TruncateAt.END }
        card.addView(st)
        card.setOnClickListener { go() }
        focusFx(card) { f -> bg.setStroke(if (f) dp(3f) else 0, 0xFFFFFFFF.toInt()) }
        row.addView(card, LinearLayout.LayoutParams(dp(w * k), dp(196f * k)).apply { marginEnd = dp(18f) })
        return st
    }

    /** a smaller glass button: icon + name */
    private fun smallCard(row: LinearLayout, icon: String, label: String, go: () -> Unit) {
        val bg = android.graphics.drawable.GradientDrawable().apply { cornerRadius = 20 * d; setColor(0x1FFFFFFF); setStroke(dp(1f), 0x26FFFFFF) }
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; background = bg; isFocusable = true; isClickable = true
            gravity = android.view.Gravity.CENTER_VERTICAL; setPadding(dp(22f), 0, dp(26f), 0)
        }
        val ic = TextView(this).apply { text = icon; textSize = 22f }
        val lb = TextView(this).apply { text = label; textSize = 17f; setTypeface(typeface, android.graphics.Typeface.BOLD); setTextColor(getColor(R.color.text)) }
        card.addView(ic); card.addView(lb, LinearLayout.LayoutParams(-2, -2).apply { marginStart = dp(12f) })
        card.setOnClickListener { go() }
        focusFx(card) { f ->
            bg.setColor(if (f) 0xFFF2F4F8.toInt() else 0x1FFFFFFF); bg.setStroke(dp(1f), if (f) 0xFFFFFFFF.toInt() else 0x26FFFFFF)
            lb.setTextColor(if (f) getColor(R.color.textOnFocus) else getColor(R.color.text))
        }
        row.addView(card, LinearLayout.LayoutParams(-2, dp(if (isTouch) 54f else 66f)).apply { marginEnd = dp(14f) })
    }

    /** focus: the card grows a little and lifts, the others stay calm */
    private fun focusFx(v: View, also: (Boolean) -> Unit) {
        v.setOnFocusChangeListener { _, f ->
            also(f)
            v.animate().scaleX(if (f) 1.06f else 1f).scaleY(if (f) 1.06f else 1f).translationZ(if (f) 12 * d else 0f).setDuration(150).start()
        }
    }

    private fun buildCards() {
        val big = findViewById<LinearLayout>(R.id.bigRow); val small = findViewById<LinearLayout>(R.id.smallRow)
        liveSub = bigCard(big, "📺", "Live TV", "All your channels", 0xFF00B67A.toInt(), 0xFF0E6E8C.toInt(), 330f) { open(LiveActivity::class.java) }
        bigCard(big, "🎬", "Movies", "Latest added first", 0xFF7B3FE4.toInt(), 0xFF3A2A8C.toInt(), 230f) { startActivity(Intent(this, VodActivity::class.java).putExtra("series", false)) }
        bigCard(big, "🎞", "Series", "Continue where you left", 0xFFF2713A.toInt(), 0xFFB4365B.toInt(), 230f) { startActivity(Intent(this, VodActivity::class.java).putExtra("series", true)) }
        bigCard(big, "⚽", "Sports today", "Today's matches", 0xFF1F6FEB.toInt(), 0xFF0B3C8C.toInt(), 230f) { open(SportsActivity::class.java) }
        smallCard(small, "🗓", "TV Guide") { open(GuideActivity::class.java) }
        smallCard(small, "🔍", "Search") { open(SearchActivity::class.java) }
        smallCard(small, "☰", "Playlists") { playlists() }
        smallCard(small, "⚙", "Settings") { startActivity(Intent(this, SettingsActivity::class.java)) }
        big.getChildAt(0).requestFocus()
        if (isTouch) findViewById<View>(R.id.homeCol).setPadding(dp(22f), dp(14f), dp(22f), dp(40f))
    }

    /** Live TV card: the channel that was on and what is on it now */
    private fun showLast() {
        val c = Api.byId[Prefs.lastChannel] ?: return
        liveSub?.text = "▶  " + c.name
        lifecycleScope.launch {
            val p = withContext(Dispatchers.IO) { try { Api.guide(c) } catch (e: Exception) { emptyList() } }.firstOrNull { it.now() }
            if (p != null) liveSub?.text = "▶  " + c.name + "  ·  " + p.title
        }
    }

    override fun onResume() {
        super.onResume()
        // only when "Start on the last channel" is on: straight to the channel that was on
        val fresh = !resumedOnce; resumedOnce = true
        if (fresh || BaseActivity.cameBack) {
            BaseActivity.cameBack = false
            if (Prefs.ready && App.prefs.contains("last_channel") && App.prefs.getBoolean("open_last", false)) {
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
            withContext(Dispatchers.Main) { showLast() }
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
