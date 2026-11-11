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

/** Multiview: 2 channels on a Chromecast (its video chip decodes two at once), up to 4 on phones / tablets.
 *  Rounded tiles with a gap, the channel logo and what is on now; the focused tile glows and has the sound.
 *  OK = choose its channel · hold OK = that channel full screen · MENU = remove the channel. */
class MultiviewActivity : BaseActivity() {
    private class Tile(val root: View, val pv: PlayerView, val player: ExoPlayer, val bar: View, val logo: ImageView,
                       val name: TextView, val now: TextView, val sound: TextView, val empty: View) {
        var channel: Channel? = null
        var src: OtherList? = null     // null = the device's playlist in use; else one of its other playlists
        var tries = 0
        var lastPos = -1L; var still = 0
    }
    private val tiles = ArrayList<Tile>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val d = resources.displayMetrics.density
        val n = if (android.os.Build.MODEL.contains("Chromecast", true) || android.os.Build.MODEL.contains("Google TV", true)) 2 else 4
        val two = n == 2
        // two screens: edge to edge, no gaps, no rounded corners — each half of the TV is all picture
        val gap = if (two) 0 else (5 * d).toInt()
        val grid = GridLayout(this).apply {
            columnCount = 2; rowCount = if (n == 2) 1 else 2
            setBackgroundResource(R.drawable.multi_screen_bg); setPadding(gap, gap, gap, gap)
            // two screens: each as big as half the TV allows, 16:9, in the middle (no tall empty tiles)
            if (n == 2) { useDefaultMargins = false; alignmentMode = GridLayout.ALIGN_BOUNDS }
        }
        setContentView(android.widget.FrameLayout(this).apply {
            setBackgroundResource(R.drawable.multi_screen_bg)
            addView(grid, android.widget.FrameLayout.LayoutParams(-1, if (n == 2) -2 else -1, android.view.Gravity.CENTER))
        })
        val sw = resources.displayMetrics.widthPixels
        val tileW = if (two) sw / 2 else (sw - gap * 2) / 2 - gap * 2
        fill = App.prefs.getBoolean("mv_fill", false)
        tileH = { if (fill) resources.displayMetrics.heightPixels else tileW * 9 / 16 }
        big = App.prefs.getInt("mv_big", -1).takeIf { two } ?: -1
        val ring = android.graphics.drawable.GradientDrawable().apply { setColor(0); setStroke((2.5f * d).toInt(), getColor(R.color.accent)) }
        val round = object : ViewOutlineProvider() {
            override fun getOutline(v: View, o: Outline) { o.setRoundRect(0, 0, v.width, v.height, 15 * d) }
        }
        for (i in 0 until n) {
            val v = LayoutInflater.from(this).inflate(R.layout.item_multiview, grid, false)
            if (two) { v.setPadding(0, 0, 0, 0); v.background = null } else v.findViewById<View>(R.id.clip).apply { outlineProvider = round; clipToOutline = true }
            val pv = v.findViewById<PlayerView>(R.id.pv)
            if (two && fill) pv.resizeMode = androidx.media3.ui.AspectRatioFrameLayout.RESIZE_MODE_ZOOM
            // no audio focus: with it, each new screen took the focus and the other one paused (froze)
            val p = Players.make(this, live = true, audioFocus = false, maxHd = true)
            pv.player = p
            val t = Tile(v, pv, p, v.findViewById(R.id.bar), v.findViewById(R.id.logo), v.findViewById(R.id.name),
                v.findViewById(R.id.now), v.findViewById(R.id.sound), v.findViewById(R.id.empty))
            val lp = (if (n == 2) GridLayout.LayoutParams(GridLayout.spec(0), GridLayout.spec(i)).apply { width = tileW; height = tileH() }
                else GridLayout.LayoutParams(GridLayout.spec(i / 2, 1f), GridLayout.spec(i % 2, 1f)).apply { width = 0; height = 0 })
                .apply { setMargins(gap, gap, gap, gap) }
            grid.addView(v, lp)
            val idx = i
            v.setOnClickListener { pick(idx) }
            v.setOnLongClickListener { holdOk(idx); true }   // touch; the remote's OK is read in dispatchKeyEvent
            v.setOnFocusChangeListener { view, f ->
                if (two) view.foreground = if (f) ring else null
                else view.animate().scaleX(if (f) 1f else 0.97f).scaleY(if (f) 1f else 0.97f).alpha(if (f) 1f else 0.82f).setDuration(160).start()
                if (f) { sound(idx); flash(tiles[idx]) }
            }
            if (!two) { v.scaleX = 0.97f; v.scaleY = 0.97f; v.alpha = 0.82f }
            tiles.add(t)
            // a screen that fails or stops moving starts again by itself (then its other quality)
            p.addListener(object : androidx.media3.common.Player.Listener {
                override fun onPlayerError(error: androidx.media3.common.PlaybackException) { recover(t) }
            })
        }
        lifecycleScope.launch {
            while (true) {
                kotlinx.coroutines.delay(4000)
                for (t in tiles) {
                    val c = t.channel ?: continue
                    val pos = t.player.currentPosition
                    if (t.player.playWhenReady && pos == t.lastPos) { if (++t.still >= 3) { t.still = 0; recover(t) } } else t.still = 0
                    t.lastPos = pos
                }
            }
        }
        first = Api.byId[intent.getIntExtra("channel", -1)]?.takeIf { it.id > 0 }
        if (first != null) set(0, first)
        // the device has more than one playlist (admin site): the viewer picks the playlist of the other screen(s)
        others = Device.playlists().filter { it.optString("name") != Device.active && it.optString("user").isNotEmpty() }.map { OtherList(it) }
        // the other screen never opens on the playlist that is already playing (its provider would cut one of the two):
        // one other playlist = that one at once; more = the viewer picks among the others (owner, 10 Nov 2026)
        when (others.size) {
            0 -> fillOthers(null)
            1 -> fillOthers(others[0])
            else -> AlertDialog.Builder(this).setTitle("Other screen · which playlist?").setItems(others.map { it.name }.toTypedArray()) { _, w -> fillOthers(others[w]) }
                .setOnCancelListener { fillOthers(others[0]) }.show()
        }
        tiles[0].root.post { tiles[0].root.requestFocus() }
        if (big >= 0) grid.post { relayout() }
    }

    private var first: Channel? = null
    private var fill = false
    private var tileH: () -> Int = { 0 }
    /** two screens: -1 = same size, else that screen is big (2/3 of the TV) and the other small (1/3) */
    private var big = -1

    /** sizes of the two screens for the chosen layout (same size / big + small) and picture mode (whole / fill) */
    private fun relayout() {
        if (tiles.size != 2) return
        val sw = resources.displayMetrics.widthPixels; val sh = resources.displayMetrics.heightPixels
        tiles.forEachIndexed { k, t ->
            val w = when (big) { -1 -> sw / 2; k -> sw * 2 / 3; else -> sw - sw * 2 / 3 }
            val lp = t.root.layoutParams as GridLayout.LayoutParams
            lp.width = w; lp.height = if (fill) sh else w * 9 / 16
            lp.setGravity(android.view.Gravity.CENTER_VERTICAL)
            t.root.layoutParams = lp
        }
    }

    /** hold OK: two screens = this one big / both the same size; four screens = full screen */
    private fun holdOk(i: Int) {
        if (tiles.size != 2) { tiles[i].channel?.let { openFull(it) }; return }
        // every hold is the next step, in this order: this screen big → the same size → this screen small → big again
        val next = when (big) { i -> { cameFromBig = true; -1 }; -1 -> if (cameFromBig) 1 - i else i; else -> i }
        if (next != -1) cameFromBig = false
        setBig(next); flash(tiles[i])
        android.widget.Toast.makeText(this, when (next) { i -> "Big"; -1 -> "Same size"; else -> "Small" }, android.widget.Toast.LENGTH_SHORT).show()
    }
    private var cameFromBig = false
    private var okHeld = false
    private var okDown = false

    private fun setBig(i: Int) { big = i; App.prefs.edit().putInt("mv_big", i).apply(); relayout() }

    /** two screens: whole picture (16:9, black above / below) or fill the TV (the sides of each picture are cut) */
    private fun setFill(on: Boolean) {
        fill = on; App.prefs.edit().putBoolean("mv_fill", on).apply()
        tiles.forEach { t ->
            t.pv.resizeMode = if (on) androidx.media3.ui.AspectRatioFrameLayout.RESIZE_MODE_ZOOM else androidx.media3.ui.AspectRatioFrameLayout.RESIZE_MODE_FIT
        }
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

    private fun fillOthers(src: OtherList?) {
        for (k in 1 until tiles.size) tiles[k].src = src
        val recent = History.ids().filter { it != first?.id && it > 0 }.mapNotNull { Api.byId[it] }
        tiles.forEachIndexed { k, t ->
            if (k == 0) return@forEachIndexed
            val src = t.src
            val want = recent.getOrNull(k - 1) ?: first
            if (src == null) { want?.let { set(k, it) }; return@forEachIndexed }
            // the other playlist: the same channel there when it has it
            t.empty.let { (it as? TextView)?.text = "＋\nAdd a channel\n(${src.name})" }
            lifecycleScope.launch {
                val ok = withContext(Dispatchers.IO) { try { src.load() } catch (e: Exception) { false } }
                if (!ok) { (t.empty as? TextView)?.text = "${src.name}: could not load"; return@launch }
                (want?.let { src.same(it) } ?: first?.let { src.same(it) })?.let { set(k, it) }
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

    override fun dispatchKeyEvent(e: KeyEvent): Boolean {
        if (!overlayOpen && e.action == KeyEvent.ACTION_DOWN) {
            val i = tiles.indexOfFirst { it.root.hasFocus() }
            // OK on a screen is read here and nowhere else (the screen's own long press also fired and switched the size
            // straight back): a short press = pick a channel (on release), a hold = the next size, once per hold
            if ((e.keyCode == KeyEvent.KEYCODE_DPAD_CENTER || e.keyCode == KeyEvent.KEYCODE_ENTER) && i >= 0) {
                if (e.repeatCount == 0) { okHeld = false; okDown = true }
                else if (!okHeld && e.repeatCount >= 1) { okHeld = true; holdOk(i) }
                return true
            }
            if (e.keyCode == KeyEvent.KEYCODE_MENU && i >= 0) {
                val items = arrayListOf("Change channel", "Remove channel", "Full screen")
                if (others.isNotEmpty()) items.add("Change playlist")
                val fillItem = if (tiles.size == 2) (if (fill) "Show the whole picture" else "Fill the screen (crop the sides)") else null
                fillItem?.let { items.add(it) }
                val bigItem = if (tiles.size == 2) (if (big == i) "Same size" else "Make this screen big") else null
                bigItem?.let { items.add(it) }
                AlertDialog.Builder(this).setItems(items.toTypedArray()) { _, w ->
                    when (w) {
                        0 -> pick(i); 1 -> set(i, null); 2 -> tiles[i].channel?.let { openFull(it) }
                        items.indexOf(fillItem ?: "\u0000") -> setFill(!fill)
                        items.indexOf(bigItem ?: "\u0000") -> setBig(if (big == i) -1 else i)
                        3 -> choosePlaylist("This screen", tiles[i].src) { src -> val c = tiles[i].channel; tiles[i].src = src; set(i, null)
                            if (src == null) c?.let { ch -> (Api.byId[ch.id] ?: Api.byId.values.firstOrNull { Api.baseName(it.name) == Api.baseName(ch.name) } ?: first)?.let { set(i, it) } }
                            else lifecycleScope.launch {
                                val ok = withContext(Dispatchers.IO) { try { src.load() } catch (e: Exception) { false } }
                                if (!ok) { android.widget.Toast.makeText(this@MultiviewActivity, "${src.name}: could not load", android.widget.Toast.LENGTH_LONG).show(); return@launch }
                                c?.let { src.same(it) }?.let { set(i, it) } ?: pick(i)
                            } }
                    }
                }.show(); return true
            }
        }
        if (!overlayOpen && e.action == KeyEvent.ACTION_UP && (e.keyCode == KeyEvent.KEYCODE_DPAD_CENTER || e.keyCode == KeyEvent.KEYCODE_ENTER)) {
            val i = tiles.indexOfFirst { it.root.hasFocus() }
            // only a press that began on the screen (not the end of an OK that closed a list)
            if (i >= 0 && okDown) { okDown = false; if (!okHeld) pick(i); okHeld = false; return true }
        }
        return super.dispatchKeyEvent(e)
    }

    override fun onStop() { super.onStop(); tiles.forEach { it.player.pause() } }
    override fun onStart() { super.onStart(); tiles.forEach { if (it.channel != null) it.player.play() } }
    override fun onDestroy() { super.onDestroy(); tiles.forEach { it.player.release() } }
}
