package com.saudi1.tv

import android.graphics.Outline
import android.os.Bundle
import android.view.KeyEvent
import android.view.LayoutInflater
import android.view.View
import android.view.ViewOutlineProvider
import android.widget.GridLayout
import android.widget.ImageView
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.MediaItem
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import coil.load
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Multiview (owner, 25 Nov 2026): as many screens as the device has playlists (each screen its own playlist, so no
 *  provider cuts one off): 2 playlists = 2 screens; 3 or 4 = a choice of 2, 3 or 4 (⋮ › Screens). A Chromecast decodes
 *  2 pictures at most. One tap (OK) on a screen makes it the big one, a tap on the big one = all the same size;
 *  ⋮ (MENU) = the options of the selected screen. Hold OK = that channel full screen. */
class MultiviewActivity : BaseActivity() {
    private class Tile(val root: View, val pv: PlayerView, var player: ExoPlayer, val bar: View, val logo: ImageView,
                       val name: TextView, val now: TextView, val sound: TextView, val empty: View) {
        var channel: Channel? = null
        var src: OtherList? = null     // null = the device's playlist in use; else one of its other playlists
        var tries = 0
        var lastPos = -1L; var still = 0
    }
    private val tiles = ArrayList<Tile>()
    private lateinit var stage: android.widget.FrameLayout
    private var gap = 0
    private var dots: View? = null
    private var sel = 0          // the selected screen (touch: the last one tapped; remote: the focused one)

    /** how many screens this device may show: one per playlist, at least 2, at most 4 (2 on a Chromecast) */
    private fun maxScreens(): Int {
        val cap = if (android.os.Build.MODEL.contains("Chromecast", true) || android.os.Build.MODEL.contains("Google TV", true)) 2 else 4
        val lists = Device.playlists().count { it.optString("user").isNotEmpty() }
        return lists.coerceIn(2, cap)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val d = resources.displayMetrics.density
        val most = maxScreens()
        val n = App.prefs.getInt("mv_n", most).coerceIn(2, most)
        val two = n == 2
        gap = if (two) 0 else (5 * d).toInt()
        stage = android.widget.FrameLayout(this).apply { setBackgroundResource(R.drawable.multi_screen_bg) }
        setContentView(stage)
        fill = App.prefs.getBoolean("mv_fill", false)
        big = App.prefs.getInt("mv_big", -1).let { if (it >= 0) 0 else -1 }
        val ring = android.graphics.drawable.GradientDrawable().apply { setColor(0); setStroke((2.5f * d).toInt(), getColor(R.color.accent)); cornerRadius = if (two) 0f else 15 * d }
        val round = object : ViewOutlineProvider() {
            override fun getOutline(v: View, o: Outline) { o.setRoundRect(0, 0, v.width, v.height, 15 * d) }
        }
        for (i in 0 until n) {
            val v = LayoutInflater.from(this).inflate(R.layout.item_multiview, stage, false)
            if (two) { v.setPadding(0, 0, 0, 0); v.background = null } else v.findViewById<View>(R.id.clip).apply { outlineProvider = round; clipToOutline = true }
            val pv = v.findViewById<PlayerView>(R.id.pv)
            // no audio focus: with it, each new screen took the focus and the other one paused (froze)
            val p = Players.make(this, live = true, audioFocus = false, maxHd = true)
            pv.player = p
            val t = Tile(v, pv, p, v.findViewById(R.id.bar), v.findViewById(R.id.logo), v.findViewById(R.id.name),
                v.findViewById(R.id.now), v.findViewById(R.id.sound), v.findViewById(R.id.empty))
            // the small screens' pictures lie on top of the big one (two screens: the small one is inside the big one)
            if (i > 0) (pv.videoSurfaceView as? android.view.SurfaceView)?.setZOrderMediaOverlay(true)
            v.id = View.generateViewId()
            stage.addView(v, android.widget.FrameLayout.LayoutParams(10, 10))
            val idx = i
            v.setOnClickListener { sel = idx; tap(idx) }
            v.setOnLongClickListener { sel = idx; tiles[idx].channel?.let { openFull(it) }; true }   // touch; the remote's OK is read in dispatchKeyEvent
            v.setOnFocusChangeListener { view, f ->
                view.foreground = if (f) ring else null
                if (f) { sel = idx; sound(idx); flash(tiles[idx]) }
            }
            tiles.add(t)
            // a screen that fails or stops moving starts again by itself (then its other quality)
            p.addListener(object : androidx.media3.common.Player.Listener {
                // by player, not by screen: the screens can change places
                override fun onPlayerError(error: androidx.media3.common.PlaybackException) { tiles.firstOrNull { it.player === p }?.let { recover(it) } }
            })
        }
        // ⋮ : the options of the selected screen (phones and tablets; the remote has MENU)
        if (isTouch) dots = TextView(this).apply {
            text = "⋮"; textSize = 26f; setTextColor(0xFFFFFFFF.toInt()); gravity = android.view.Gravity.CENTER
            background = android.graphics.drawable.GradientDrawable().apply { shape = android.graphics.drawable.GradientDrawable.OVAL; setColor(0x99000000.toInt()) }
            setOnClickListener { menu(sel) }
        }.also { stage.addView(it, android.widget.FrameLayout.LayoutParams((44 * d).toInt(), (44 * d).toInt(), android.view.Gravity.TOP or android.view.Gravity.END).apply {
            val m = (12 * d).toInt(); setMargins(m, m, m, m) }) }
        stage.post { relayout() }
        lifecycleScope.launch {
            while (true) {
                kotlinx.coroutines.delay(4000)
                for (t in tiles) {
                    if (t.channel == null) continue
                    val pos = t.player.currentPosition
                    if (t.player.playWhenReady && pos == t.lastPos) { if (++t.still >= 3) { t.still = 0; recover(t) } } else t.still = 0
                    t.lastPos = pos
                }
            }
        }
        first = Api.byId[intent.getIntExtra("channel", -1)]?.takeIf { it.id > 0 }
        if (first != null) set(0, first)
        // each other screen gets its own playlist of the device, in order (none left: it shares the one in use)
        others = Device.playlists().filter { it.optString("name") != Device.active && it.optString("user").isNotEmpty() }.map { OtherList(it) }
        fillOthers()
        tiles[0].root.post { tiles[0].root.requestFocus() }
    }

    private var first: Channel? = null
    private var fill = false
    /** -1 = all the same size, 0 = screen 0 is the big one (the others small) */
    private var big = -1

    /** where every screen goes: all the same size, or one big and the others small */
    private fun relayout() {
        val sw = stage.width.takeIf { it > 0 } ?: resources.displayMetrics.widthPixels
        val sh = stage.height.takeIf { it > 0 } ?: resources.displayMetrics.heightPixels
        val n = tiles.size
        fun put(t: Tile, x: Int, y: Int, w: Int, h: Int) {
            val lp = t.root.layoutParams as android.widget.FrameLayout.LayoutParams
            lp.gravity = android.view.Gravity.TOP or android.view.Gravity.START
            lp.width = w; lp.height = h; lp.leftMargin = x; lp.topMargin = y
            t.root.layoutParams = lp
        }
        val zoom = androidx.media3.ui.AspectRatioFrameLayout.RESIZE_MODE_ZOOM
        val fit = androidx.media3.ui.AspectRatioFrameLayout.RESIZE_MODE_FIT
        tiles.forEach { it.pv.resizeMode = fit }
        if (n == 2 && big < 0) {
            // the same size, side by side; fill = each half of the TV all picture (the sides cut)
            val w = sw / 2; val h = if (fill) sh else minOf(sh, w * 9 / 16)
            tiles.forEachIndexed { k, t -> put(t, k * w, (sh - h) / 2, w, h); if (fill) t.pv.resizeMode = zoom }
        } else if (n == 2) {
            // big = the whole TV, small = a picture in the corner on top of it
            put(tiles[0], 0, 0, sw, sh)
            val w = sw * 30 / 100; val m = sw * 2 / 100; val h = w * 9 / 16
            put(tiles[1], sw - w - m, sh - h - m, w, h)
        } else if (big < 0) {
            // 3 or 4 the same size: two rows of two (three: the last one in the middle of the second row)
            val w = (sw - gap * 3) / 2; val h = minOf((sh - gap * 3) / 2, w * 9 / 16)
            val top = (sh - h * 2 - gap) / 2
            tiles.forEachIndexed { k, t ->
                val row = k / 2; val col = k % 2
                val x = if (n == 3 && k == 2) (sw - w) / 2 else gap + col * (w + gap)
                put(t, x, top + row * (h + gap), w, h)
            }
        } else {
            // one big on the left, the others small in a column on the right
            val sideW = (sw - gap * 3) * 30 / 100
            val bigW = sw - gap * 3 - sideW
            val bigH = minOf(sh - gap * 2, bigW * 9 / 16)
            put(tiles[0], gap, (sh - bigH) / 2, bigW, bigH)
            val k = n - 1
            val h = minOf((sh - gap * (k + 1)) / k, sideW * 9 / 16)
            val top = (sh - h * k - gap * (k - 1)) / 2
            for (j in 1 until n) put(tiles[j], gap * 2 + bigW, top + (j - 1) * (h + gap), sideW, h)
        }
        for (j in 1 until n) tiles[j].root.bringToFront()
        dots?.bringToFront()
    }

    /** two screens change places without connecting again: the players swap their pictures */
    private fun swap(i: Int, j: Int) {
        if (i == j) return
        val a = tiles[i]; val b = tiles[j]
        val pa = a.player; val pb = b.player
        a.pv.player = null; b.pv.player = null
        a.player = pb; b.player = pa
        a.pv.player = pb; b.pv.player = pa
        val c = a.channel; a.channel = b.channel; b.channel = c
        val sr = a.src; a.src = b.src; b.src = sr
        for (t in listOf(a, b)) {
            t.tries = 0; t.still = 0; t.lastPos = -1
            val ch = t.channel
            t.empty.visibility = if (ch == null) View.VISIBLE else View.GONE
            t.bar.visibility = if (ch == null) View.GONE else View.VISIBLE
            if (ch != null) { t.name.text = "${ch.num}   ${ch.name}" + (t.src?.let { "   ·   " + it.name } ?: ""); t.now.text = ""; t.logo.load(ch.logo.ifEmpty { null }) }
            else (t.empty as? TextView)?.text = "＋\nAdd a channel" + (t.src?.let { "\n(${it.name})" } ?: "")
        }
    }

    /** one tap: an empty screen = choose its channel; a small screen = it becomes the big one; the big one = all the same size */
    private fun tap(i: Int) {
        if (tiles[i].channel == null) { pick(i); return }
        if (big >= 0 && i == 0) { setBig(-1); say("Same size") }
        else { swap(0, i); setBig(0); say("Big") }
        tiles[0].root.requestFocus(); sel = 0; sound(0)
    }
    private fun say(s: String) = android.widget.Toast.makeText(this, s, android.widget.Toast.LENGTH_SHORT).show()
    private var okHeld = false
    private var okDown = false

    private fun setBig(i: Int) { big = i; App.prefs.edit().putInt("mv_big", i).apply(); relayout() }

    /** two screens: whole picture (16:9, black above / below) or fill the TV (the sides of each picture are cut) */
    private fun setFill(on: Boolean) {
        fill = on; App.prefs.edit().putBoolean("mv_fill", on).apply()
        relayout()
    }
    private var others: List<OtherList> = emptyList()

    /** "Second screen · which playlist?" — the same one, or another playlist of this device (its own connection) */
    private fun choosePlaylist(title: String = "Other screen", now: OtherList? = null, done: (OtherList?) -> Unit) {
        // every playlist of the device, the one in use marked; a playlist another screen uses shares its connection
        val names = arrayOf("${Device.active}" + (if (now == null) "   ✓" else "")) + others.map { it.name + (if (it === now) "   ✓" else "") }
        AlertDialog.Builder(this).setTitle("$title · which playlist?").setItems(names) { _, w -> done(if (w == 0) null else others[w - 1]) }
            .setOnCancelListener { if (title == "Other screen") done(others.firstOrNull()) }.show()
    }

    /** screen k (k ≥ 1) gets the k-th other playlist of the device (none left: the one in use), and a channel:
     *  the same as screen 0's there, else one of the last watched */
    private fun fillOthers() {
        val recent = History.ids().filter { it != first?.id && it > 0 }.mapNotNull { Api.byId[it] }
        tiles.forEachIndexed { k, t ->
            if (k == 0) return@forEachIndexed
            val src = others.getOrNull(k - 1)
            t.src = src
            val want = recent.getOrNull(k - 1) ?: first
            if (src == null) { want?.let { set(k, it) }; return@forEachIndexed }
            (t.empty as? TextView)?.text = "＋\nAdd a channel\n(${src.name})"
            lifecycleScope.launch {
                val ok = withContext(Dispatchers.IO) { try { src.load() } catch (e: Exception) { false } }
                if (!ok) { (t.empty as? TextView)?.text = "${src.name}: could not load"; return@launch }
                (first?.let { src.same(it) } ?: want?.let { src.same(it) })?.let { if (t.src === src) set(k, it) }
            }
        }
    }

    private fun recover(t: Tile) {
        val c = t.channel ?: return
        t.tries++
        val pick = if (t.src != null) c else if (t.tries % 2 == 0) Api.qualities(c).filter { it.id != c.id }.getOrNull(t.tries / 2 - 1) ?: light(c) else light(c)
        // most subscriptions allow ONE stream at a time: a second screen is refused by the provider. Two tries only,
        // so the other screen is not kicked off again and again.
        if (t.tries > 2) { t.now.text = if (t.src != null) "⚠ ${t.src?.name}: not available right now" else "⚠ The subscription allows 1 screen — add a 2nd playlist on the admin site"; hide[t]?.let { t.bar.removeCallbacks(it) }; t.bar.alpha = 1f; t.bar.visibility = View.VISIBLE; return }
        t.now.text = "Reconnecting…"; flash(t)
        t.player.setMediaItem(MediaItem.fromUri(Api.streamUrl(pick)))
        t.player.prepare(); t.player.playWhenReady = true
    }

    /** the channel name shows for 4 s (new channel, or the screen gets the focus), then fades away: all picture */
    private val hide = HashMap<Tile, Runnable>()
    private fun flash(t: Tile) {
        if (t.channel == null) return
        hide[t]?.let { t.bar.removeCallbacks(it) }
        t.bar.animate().cancel(); t.bar.alpha = 1f; t.bar.visibility = View.VISIBLE
        val r = Runnable { t.bar.animate().alpha(0f).setDuration(400).withEndAction { t.bar.visibility = View.INVISIBLE }.start() }
        hide[t] = r; t.bar.postDelayed(r, 4000)
    }

    private fun sound(i: Int) {
        tiles.forEachIndexed { k, t ->
            t.player.volume = if (k == i) 1f else 0f
            t.sound.visibility = if (k == i && t.channel != null) View.VISIBLE else View.GONE
        }
    }

    private fun set(i: Int, c: Channel?) {
        val t = tiles[i]
        t.channel = c; t.tries = 0; t.still = 0; t.lastPos = -1
        t.empty.visibility = if (c == null) View.VISIBLE else View.GONE
        t.bar.visibility = if (c == null) View.GONE else View.VISIBLE
        if (c != null) flash(t)
        if (c == null) { t.player.stop(); t.player.clearMediaItems(); sound(tiles.indexOfFirst { it.root.hasFocus() }.coerceAtLeast(0)); return }
        t.name.text = "${c.num}   ${c.name}" + (t.src?.let { "   ·   " + it.name } ?: ""); t.now.text = ""
        t.logo.load(c.logo.ifEmpty { null })
        // the TV's chip decodes 2 pictures at once only when they are light: a 4K / HEVC channel plays in its HD copy
        t.player.setMediaItem(MediaItem.fromUri(Api.streamUrl(t.src?.let { lightIn(it, c) } ?: light(c))))
        t.player.prepare(); t.player.playWhenReady = true
        sound(tiles.indexOfFirst { it.root.hasFocus() }.coerceAtLeast(0))
        if (t.src != null) return
        lifecycleScope.launch {
            val list = withContext(Dispatchers.IO) { Api.guide(c) }
            val now = System.currentTimeMillis() / 1000
            if (t.channel?.id == c.id) t.now.text = list.firstOrNull { it.now(now) }?.title ?: ""
        }
    }

    private val heavy = Regex("(?i)\\b(4k|uhd|8k|hevc|h265|2160p?|3840p?|raw)\\b")
    private fun light(c: Channel): Channel {
        if (!heavy.containsMatchIn(c.name)) return c
        val q = Api.qualities(c).filter { !heavy.containsMatchIn(it.name) }
        return q.firstOrNull { Regex("(?i)\\bfhd|1080").containsMatchIn(it.name) } ?: q.firstOrNull { Regex("(?i)\\bhd\\b").containsMatchIn(it.name) } ?: q.firstOrNull() ?: c
    }

    /** the same for a channel of the other playlist: its HD copy there when the channel is 4K / HEVC */
    private fun lightIn(src: OtherList, c: Channel): Channel {
        if (!heavy.containsMatchIn(c.name)) return c
        val b = Api.baseName(c.name)
        val q = src.groups.asSequence().flatMap { it.channels.asSequence() }.filter { Api.baseName(it.name) == b && !heavy.containsMatchIn(it.name) }.toList()
        return q.firstOrNull { Regex("(?i)\\bfhd|1080").containsMatchIn(it.name) } ?: q.firstOrNull() ?: c
    }

    private fun pick(i: Int) {
        val src = tiles[i].src
        if (src != null) {
            lifecycleScope.launch {
                val ok = withContext(Dispatchers.IO) { try { src.load() } catch (e: Exception) { false } }
                if (!ok) { android.widget.Toast.makeText(this@MultiviewActivity, "${src.name}: could not load", android.widget.Toast.LENGTH_LONG).show(); return@launch }
                AlertDialog.Builder(this@MultiviewActivity).setTitle("${src.name} · group").setItems(src.groups.map { it.name }.toTypedArray()) { _, g ->
                    val gr = src.groups[g]
                    AlertDialog.Builder(this@MultiviewActivity).setTitle(gr.name).setItems(gr.channels.map { "${it.num}   ${it.name}" }.toTypedArray()) { _, k -> set(i, gr.channels[k]) }.show()
                }.show()
            }
            return
        }
        val gs = Api.groups.filter { it.channels.isNotEmpty() }
        val recent = History.ids().mapNotNull { Api.byId[it] }.take(5)
        val names = recent.map { "↺   ${it.num}   ${it.name}" } + gs.map { "▸   " + it.name }
        AlertDialog.Builder(this).setTitle("Channel for this screen").setItems(names.toTypedArray()) { _, w ->
            if (w < recent.size) { set(i, recent[w]); return@setItems }
            val g = gs[w - recent.size]
            AlertDialog.Builder(this).setTitle(g.name).setItems(g.channels.map { "${it.num}   ${it.name}" }.toTypedArray()) { _, k -> set(i, g.channels[k]) }.show()
        }.show()
    }

    private fun openFull(c0: Channel) {
        // a channel of the other playlist opens full screen as the same channel of the playlist in use
        val c = if (Api.byId[c0.id]?.name == c0.name) c0 else Api.qualities(c0).firstOrNull { Api.byId[it.id] != null && it.url.isEmpty() } ?: c0
        startActivity(android.content.Intent(this, LiveActivity::class.java).putExtra("channel", c.id).addFlags(android.content.Intent.FLAG_ACTIVITY_CLEAR_TOP))
        finish()
    }

    /** ⋮ / MENU: the options of screen i, and how many screens */
    private fun menu(i0: Int) {
        val i = i0.coerceIn(0, tiles.lastIndex)
        val items = arrayListOf("Change channel", "Remove channel", "Full screen")
        if (others.isNotEmpty()) items.add("Change playlist")
        val most = maxScreens()
        val screensItem = if (most > 2) "Screens: ${tiles.size}  (2 – $most)" else null
        screensItem?.let { items.add(it) }
        val fillItem = if (tiles.size == 2 && big < 0) (if (fill) "Show the whole picture" else "Fill the screen (crop the sides)") else null
        fillItem?.let { items.add(it) }
        val sizeItem = if (big >= 0) "All the same size" else "Make this screen big"
        items.add(sizeItem)
        AlertDialog.Builder(this).setTitle(tiles[i].channel?.name ?: "Screen ${i + 1}").setItems(items.toTypedArray()) { _, w ->
            when (items[w]) {
                "Change channel" -> pick(i)
                "Remove channel" -> set(i, null)
                "Full screen" -> tiles[i].channel?.let { openFull(it) }
                "Change playlist" -> choosePlaylist("This screen", tiles[i].src) { src -> val c = tiles[i].channel; tiles[i].src = src; set(i, null)
                    if (src == null) c?.let { ch -> (Api.byId[ch.id] ?: Api.byId.values.firstOrNull { Api.baseName(it.name) == Api.baseName(ch.name) } ?: first)?.let { set(i, it) } }
                    else lifecycleScope.launch {
                        val ok = withContext(Dispatchers.IO) { try { src.load() } catch (e: Exception) { false } }
                        if (!ok) { say("${src.name}: could not load"); return@launch }
                        c?.let { src.same(it) }?.let { set(i, it) } ?: pick(i)
                    } }
                screensItem -> {
                    val opts = (2..most).toList()
                    AlertDialog.Builder(this).setTitle("How many screens").setSingleChoiceItems(opts.map { "$it screens" }.toTypedArray(), opts.indexOf(tiles.size)) { d, k ->
                        d.dismiss(); if (opts[k] != tiles.size) { App.prefs.edit().putInt("mv_n", opts[k]).apply(); recreate() }
                    }.show()
                }
                fillItem -> setFill(!fill)
                sizeItem -> if (big >= 0) setBig(-1) else { swap(0, i); setBig(0); tiles[0].root.requestFocus(); sound(0) }
            }
        }.show()
    }

    override fun dispatchKeyEvent(e: KeyEvent): Boolean {
        if (!overlayOpen && e.action == KeyEvent.ACTION_DOWN) {
            val i = tiles.indexOfFirst { it.root.hasFocus() }
            // OK is read here: a short press = big / same size (on release), a hold = that channel full screen
            if ((e.keyCode == KeyEvent.KEYCODE_DPAD_CENTER || e.keyCode == KeyEvent.KEYCODE_ENTER) && i >= 0) {
                if (e.repeatCount == 0) { okHeld = false; okDown = true }
                else if (!okHeld && e.repeatCount >= 1) { okHeld = true; tiles[i].channel?.let { openFull(it) } ?: pick(i) }
                return true
            }
            if (e.keyCode == KeyEvent.KEYCODE_MENU && i >= 0) { menu(i); return true }
        }
        if (!overlayOpen && e.action == KeyEvent.ACTION_UP && (e.keyCode == KeyEvent.KEYCODE_DPAD_CENTER || e.keyCode == KeyEvent.KEYCODE_ENTER)) {
            val i = tiles.indexOfFirst { it.root.hasFocus() }
            // only a press that began on the screen (not the end of an OK that closed a list)
            if (i >= 0 && okDown) { okDown = false; if (!okHeld) tap(i); okHeld = false; return true }
        }
        return super.dispatchKeyEvent(e)
    }

    override fun onStop() { super.onStop(); tiles.forEach { it.player.pause() } }
    override fun onStart() { super.onStart(); tiles.forEach { if (it.channel != null) it.player.play() } }
    override fun onDestroy() { super.onDestroy(); tiles.forEach { it.player.release() } }
}
