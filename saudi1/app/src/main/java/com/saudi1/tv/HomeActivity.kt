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
        findViewById<View>(R.id.homeBg).setLayerType(View.LAYER_TYPE_HARDWARE, null)
        status = findViewById(R.id.status)
        val logo = SpannableString("SAUDI.TV")
        logo.setSpan(ForegroundColorSpan(getColor(R.color.accent)), 5, 8, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        findViewById<TextView>(R.id.logo).text = logo
        findViewById<TextView>(R.id.footer).text = "Version " + BuildConfig.VERSION_NAME

        buildCards()
        // the first opening on this device: the welcome and a short tour (again from Settings → How to use)
        if (!Intro.seen && Prefs.ready) Intro.show(this)
        lifecycleScope.launch {
            val clock = findViewById<TextView>(R.id.clock); val date = findViewById<TextView>(R.id.date); val hello = findViewById<TextView>(R.id.hello)
            val tf = SimpleDateFormat("h:mm a", Locale.ENGLISH); val df = SimpleDateFormat("EEEE d MMMM", Locale.ENGLISH)
            while (true) {
                val now = Date(); clock.text = tf.format(now); date.text = df.format(now)
                val h = java.util.Calendar.getInstance().get(java.util.Calendar.HOUR_OF_DAY)
                // the name the owner gave this device on the admin site greets its viewer
                val who = Device.name.trim().substringBefore(' ').takeIf { it.length in 2..20 }?.let { ", $it" } ?: ""
                hello.text = (when (h) { in 5..11 -> "Good morning"; in 12..16 -> "Good afternoon"; else -> "Good evening" }) + who
                delay(15_000)
            }
        }
    }

    // ---------------- the cards ----------------
    // one calm style: dark slate glass cards, each with its own colour in a round icon badge; the focused card
    // fills with its colour, gets an even white edge and grows a little.
    private val d by lazy { resources.displayMetrics.density }
    private fun dp(v: Float) = (v * d).toInt()
    private val k by lazy { if (isTouch) 0.8f else 1f }
    private var liveName: TextView? = null
    private var liveNow: TextView? = null
    private var liveBar: android.widget.ProgressBar? = null
    private val SLATE = 0xFF141B2B.toInt()
    private fun grad(a: Int, b: Int, r: Float) = android.graphics.drawable.GradientDrawable(
        android.graphics.drawable.GradientDrawable.Orientation.TL_BR, intArrayOf(a, b)).apply { cornerRadius = r * d }
    private fun solid(c: Int, r: Float, line: Int = 0) = android.graphics.drawable.GradientDrawable().apply {
        cornerRadius = r * d; setColor(c); if (line != 0) setStroke(dp(1f), line) }
    private fun tv(t: String, size: Float, color: Int, bold: Boolean = false) = TextView(this).apply {
        text = t; textSize = size * k; setTextColor(color); if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
        setSingleLine(); ellipsize = android.text.TextUtils.TruncateAt.END
    }

    /** focus: fill with the card's colour, even white edge, eased grow */
    private fun focusFx(v: View, rest: android.graphics.drawable.Drawable, on: android.graphics.drawable.Drawable, r: Float, also: (Boolean) -> Unit = {}) {
        val ring = solid(0, r).apply { setStroke(dp(2.5f), 0xFFFFFFFF.toInt()) }
        v.background = rest
        v.setOnFocusChangeListener { _, f ->
            v.background = if (f) on else rest
            v.foreground = if (f) ring else null
            also(f)
            v.animate().cancel()
            v.animate().scaleX(if (f) 1.045f else 1f).scaleY(if (f) 1.045f else 1f).setDuration(200)
                .setInterpolator(android.view.animation.DecelerateInterpolator(2f)).withLayer().start()
        }
    }

    private fun badge(icon: String, color: Int, size: Float) = TextView(this).apply {
        text = icon; textSize = size * 0.48f * k; gravity = android.view.Gravity.CENTER
        background = solid((color and 0x00FFFFFF) or 0x33000000, size / 2)
        layoutParams = LinearLayout.LayoutParams(dp(size * k), dp(size * k))
    }

    /** a grid card: badge top-left, name and one line at the bottom */
    private fun card(parent: LinearLayout, icon: String, title: String, sub: String, c1: Int, c2: Int, endGap: Boolean, go: () -> Unit) {
        val v = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; isFocusable = true; isClickable = true; setPadding(dp(20f), dp(18f), dp(20f), dp(16f)) }
        val b = badge(icon, c1, 46f); v.addView(b)
        v.addView(View(this), LinearLayout.LayoutParams(1, 0, 1f))
        v.addView(tv(title, 19f, 0xFFFFFFFF.toInt(), true))
        val st = tv(sub, 13f, 0xFF8B95A9.toInt()); v.addView(st)
        v.setOnClickListener { go() }
        focusFx(v, solid(SLATE, 22f, 0x1AFFFFFF), grad(c1, c2, 22f), 22f) { f ->
            st.setTextColor(if (f) 0xE6FFFFFF.toInt() else 0xFF8B95A9.toInt())
            b.background = solid(if (f) 0x40FFFFFF else (c1 and 0x00FFFFFF) or 0x33000000, 23f)
        }
        parent.addView(v, LinearLayout.LayoutParams(0, -1, 1f).apply { if (endGap) marginEnd = dp(18f) })
    }

    /** a shortcut in the bottom row */
    private fun chip(row: LinearLayout, icon: String, label: String, last: Boolean = false, go: () -> Unit) {
        val v = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = android.view.Gravity.CENTER; isFocusable = true; isClickable = true }
        val ic = tv(icon, 18f, 0xFFFFFFFF.toInt()); val lb = tv(label, 16f, 0xFFE6E9F0.toInt(), true)
        v.addView(ic); v.addView(lb, LinearLayout.LayoutParams(-2, -2).apply { marginStart = dp(10f) })
        v.setOnClickListener { go() }
        focusFx(v, solid(0x14FFFFFF, 16f, 0x1AFFFFFF), solid(0xFFF2F4F8.toInt(), 16f), 16f) { f -> lb.setTextColor(if (f) 0xFF0B0E14.toInt() else 0xFFE6E9F0.toInt()) }
        row.addView(v, LinearLayout.LayoutParams(0, dp(54f * k), 1f).apply { if (!last) marginEnd = dp(16f) })
    }

    private fun buildCards() {
        val main = findViewById<LinearLayout>(R.id.mainRow); val small = findViewById<LinearLayout>(R.id.smallRow)
        val h = dp(286f * k)
        // Live TV: the big card on the left — the channel that was on, what is on it and how far along
        val live = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; isFocusable = true; isClickable = true; setPadding(dp(28f), dp(24f), dp(28f), dp(24f)) }
        val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = android.view.Gravity.CENTER_VERTICAL }
        top.addView(badge("📺", 0xFF10B981.toInt(), 54f))
        top.addView(View(this), LinearLayout.LayoutParams(0, 1, 1f))
        top.addView(tv("●  LIVE", 13f, 0xFFFFFFFF.toInt(), true).apply { background = solid(0xFFEF4444.toInt(), 12f); setPadding(dp(12f), dp(5f), dp(12f), dp(5f)) })
        live.addView(top)
        live.addView(View(this), LinearLayout.LayoutParams(1, 0, 1f))
        live.addView(tv("Live TV", 30f, 0xFFFFFFFF.toInt(), true))
        liveName = tv("All your channels", 17f, 0xE6FFFFFF.toInt()).also { live.addView(it, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(4f) }) }
        liveNow = tv("", 14f, 0xB3FFFFFF.toInt()).also { live.addView(it, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(2f) }) }
        liveBar = android.widget.ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 1000; progressDrawable = resources.getDrawable(R.drawable.progress_white, theme); visibility = View.INVISIBLE
        }.also { live.addView(it, LinearLayout.LayoutParams(-1, dp(4f)).apply { topMargin = dp(12f) }) }
        live.setOnClickListener { open(LiveActivity::class.java) }
        focusFx(live, grad(0xFF0F766E.toInt(), 0xFF134E6F.toInt(), 26f), grad(0xFF10B981.toInt(), 0xFF0EA5E9.toInt(), 26f), 26f)
        main.addView(live, LinearLayout.LayoutParams(0, h, 1.15f).apply { marginEnd = dp(18f) })

        // 2 × 2 beside it
        val grid = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; clipChildren = false }
        fun row() = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; clipChildren = false }
        val r1 = row(); val r2 = row()
        card(r1, "🎬", "Movies", "Latest added first", 0xFF8B5CF6.toInt(), 0xFF6366F1.toInt(), true) { startActivity(Intent(this, VodActivity::class.java).putExtra("series", false)) }
        card(r1, "🎞", "Series", "Continue watching", 0xFFF97316.toInt(), 0xFFE11D48.toInt(), false) { startActivity(Intent(this, VodActivity::class.java).putExtra("series", true)) }
        card(r2, "⚽", "Sports today", "Today's matches", 0xFF3B82F6.toInt(), 0xFF06B6D4.toInt(), true) { open(SportsActivity::class.java) }
        card(r2, "🗓", "TV Guide", "What's on", 0xFFF59E0B.toInt(), 0xFFEA580C.toInt(), false) { open(GuideActivity::class.java) }
        grid.addView(r1, LinearLayout.LayoutParams(-1, 0, 1f).apply { bottomMargin = dp(18f) })
        grid.addView(r2, LinearLayout.LayoutParams(-1, 0, 1f))
        main.addView(grid, LinearLayout.LayoutParams(0, h, 1.85f))

        chip(small, "🔍", "Search") { open(SearchActivity::class.java) }
        chip(small, "☰", "Playlists") { playlists() }
        chip(small, "⟳", "Reload") { reload() }
        chip(small, "⚙", "Settings", last = true) { startActivity(Intent(this, SettingsActivity::class.java)) }
        live.requestFocus()
        if (isTouch) findViewById<View>(R.id.homeCol).setPadding(dp(22f), dp(14f), dp(22f), dp(40f))
    }

    /** Live TV card: the channel that was on, what is on it now and how far along it is */
    private fun showLast() {
        val c = Api.byId[Prefs.lastChannel]?.takeIf { it.id > 0 && it.group != Api.DASH } ?: return
        liveName?.text = c.name
        lifecycleScope.launch {
            val p = withContext(Dispatchers.IO) { try { Api.guide(c) } catch (e: Exception) { emptyList() } }.firstOrNull { it.now() } ?: return@launch
            val now = System.currentTimeMillis() / 1000
            liveNow?.text = "\u200E" + SimpleDateFormat("h:mm", Locale.ENGLISH).format(Date(p.start * 1000)) + " – " +
                SimpleDateFormat("h:mm", Locale.ENGLISH).format(Date(p.stop * 1000)) + "   " + p.title
            liveBar?.apply { progress = ((now - p.start) * 1000 / (p.stop - p.start).coerceAtLeast(1)).toInt(); visibility = View.VISIBLE }
        }
    }

    // nobody touches the remote on Home for a minute and a half: the showcase of new and top rated titles
    private var idleJob: kotlinx.coroutines.Job? = null
    private fun armIdle() {
        idleJob?.cancel()
        if (!App.prefs.getBoolean("showcase", true) || !Prefs.ready || isTouch) return
        idleJob = lifecycleScope.launch { delay(90_000); if (!overlayOpen && hasWindowFocus()) startActivity(Intent(this@HomeActivity, ShowcaseActivity::class.java)) }
    }
    override fun dispatchKeyEvent(event: android.view.KeyEvent): Boolean { armIdle(); return super.dispatchKeyEvent(event) }
    override fun onPause() { super.onPause(); idleJob?.cancel() }

    override fun onResume() {
        super.onResume()
        armIdle()
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
