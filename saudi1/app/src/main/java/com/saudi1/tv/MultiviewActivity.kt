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
                       val name: TextView, val now: TextView, val sound: TextView, val empty: View) { var channel: Channel? = null }
    private val tiles = ArrayList<Tile>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val d = resources.displayMetrics.density
        val n = if (android.os.Build.MODEL.contains("Chromecast", true) || android.os.Build.MODEL.contains("Google TV", true)) 2 else 4
        val gap = (8 * d).toInt()
        val grid = GridLayout(this).apply {
            columnCount = 2; rowCount = if (n == 2) 1 else 2
            setBackgroundResource(R.drawable.multi_screen_bg); setPadding(gap * 2, gap * 2, gap * 2, gap * 2)
        }
        setContentView(grid)
        val round = object : ViewOutlineProvider() {
            override fun getOutline(v: View, o: Outline) { o.setRoundRect(0, 0, v.width, v.height, 15 * d) }
        }
        for (i in 0 until n) {
            val v = LayoutInflater.from(this).inflate(R.layout.item_multiview, grid, false)
            v.findViewById<View>(R.id.clip).apply { outlineProvider = round; clipToOutline = true }
            val pv = v.findViewById<PlayerView>(R.id.pv)
            // no audio focus: with it, each new screen took the focus and the other one paused (froze)
            val p = Players.make(this, live = true, audioFocus = false)
            pv.player = p
            val t = Tile(v, pv, p, v.findViewById(R.id.bar), v.findViewById(R.id.logo), v.findViewById(R.id.name),
                v.findViewById(R.id.now), v.findViewById(R.id.sound), v.findViewById(R.id.empty))
            val lp = GridLayout.LayoutParams(GridLayout.spec(i / 2, 1f), GridLayout.spec(i % 2, 1f)).apply {
                width = 0; height = 0; setMargins(gap, gap, gap, gap)
            }
            grid.addView(v, lp)
            val idx = i
            v.setOnClickListener { pick(idx) }
            v.setOnLongClickListener { tiles[idx].channel?.let { c -> openFull(c) }; true }
            v.setOnFocusChangeListener { view, f ->
                view.animate().scaleX(if (f) 1f else 0.97f).scaleY(if (f) 1f else 0.97f).alpha(if (f) 1f else 0.82f).setDuration(160).start()
                if (f) sound(idx)
            }
            v.scaleX = 0.97f; v.scaleY = 0.97f; v.alpha = 0.82f
            tiles.add(t)
        }
        val first = Api.byId[intent.getIntExtra("channel", -1)]
        if (first != null) set(0, first)
        // the other tiles start with the last channels watched
        History.ids().filter { it != first?.id }.mapNotNull { Api.byId[it] }.take(n - 1).forEachIndexed { k, c -> set(k + 1, c) }
        tiles[0].root.post { tiles[0].root.requestFocus() }
    }

    private fun sound(i: Int) {
        tiles.forEachIndexed { k, t ->
            t.player.volume = if (k == i) 1f else 0f
            t.sound.visibility = if (k == i && t.channel != null) View.VISIBLE else View.GONE
        }
    }

    private fun set(i: Int, c: Channel?) {
        val t = tiles[i]
        t.channel = c
        t.empty.visibility = if (c == null) View.VISIBLE else View.GONE
        t.bar.visibility = if (c == null) View.GONE else View.VISIBLE
        if (c == null) { t.player.stop(); t.player.clearMediaItems(); sound(tiles.indexOfFirst { it.root.hasFocus() }.coerceAtLeast(0)); return }
        t.name.text = "${c.num}   ${c.name}"; t.now.text = ""
        t.logo.load(c.logo.ifEmpty { null })
        // the TV's chip decodes 2 pictures at once only when they are light: a 4K / HEVC channel plays in its HD copy
        t.player.setMediaItem(MediaItem.fromUri(Api.streamUrl(light(c))))
        t.player.prepare(); t.player.playWhenReady = true
        sound(tiles.indexOfFirst { it.root.hasFocus() }.coerceAtLeast(0))
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

    private fun pick(i: Int) {
        val gs = Api.groups.filter { it.channels.isNotEmpty() }
        val recent = History.ids().mapNotNull { Api.byId[it] }.take(5)
        val names = recent.map { "↺   ${it.num}   ${it.name}" } + gs.map { "▸   " + it.name }
        AlertDialog.Builder(this).setTitle("Channel for this screen").setItems(names.toTypedArray()) { _, w ->
            if (w < recent.size) { set(i, recent[w]); return@setItems }
            val g = gs[w - recent.size]
            AlertDialog.Builder(this).setTitle(g.name).setItems(g.channels.map { "${it.num}   ${it.name}" }.toTypedArray()) { _, k -> set(i, g.channels[k]) }.show()
        }.show()
    }

    private fun openFull(c: Channel) {
        startActivity(android.content.Intent(this, LiveActivity::class.java).putExtra("channel", c.id).addFlags(android.content.Intent.FLAG_ACTIVITY_CLEAR_TOP))
        finish()
    }

    override fun dispatchKeyEvent(e: KeyEvent): Boolean {
        if (!overlayOpen && e.action == KeyEvent.ACTION_DOWN) {
            val i = tiles.indexOfFirst { it.root.hasFocus() }
            if ((e.keyCode == KeyEvent.KEYCODE_DPAD_CENTER || e.keyCode == KeyEvent.KEYCODE_ENTER) && e.repeatCount == 1) {
                tiles.getOrNull(i)?.channel?.let { openFull(it) }; return true
            }
            if (e.keyCode == KeyEvent.KEYCODE_MENU && i >= 0) {
                AlertDialog.Builder(this).setItems(arrayOf("Change channel", "Remove channel", "Full screen")) { _, w ->
                    when (w) { 0 -> pick(i); 1 -> set(i, null); 2 -> tiles[i].channel?.let { openFull(it) } }
                }.show(); return true
            }
        }
        return super.dispatchKeyEvent(e)
    }

    override fun onStop() { super.onStop(); tiles.forEach { it.player.pause() } }
    override fun onStart() { super.onStart(); tiles.forEach { if (it.channel != null) it.player.play() } }
    override fun onDestroy() { super.onDestroy(); tiles.forEach { it.player.release() } }
}
