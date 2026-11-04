package com.saudi1.tv

import android.graphics.Typeface
import android.os.Bundle
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.GridLayout
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.media3.common.MediaItem
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.DefaultLoadControl
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.PlayerView

/** Multiview: 2 channels on a Chromecast (its video chip decodes two at once), up to 4 on phones / tablets.
 *  OK on a box = choose its channel; the box with the focus has the sound; hold OK = that channel full screen. */
class MultiviewActivity : BaseActivity() {
    private val boxes = ArrayList<FrameLayout>()
    private val players = ArrayList<ExoPlayer>()
    private val labels = ArrayList<TextView>()
    private val channels = ArrayList<Channel?>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val d = resources.displayMetrics.density
        val n = if (android.os.Build.MODEL.contains("Chromecast", true) || android.os.Build.MODEL.contains("Google TV", true)) 2 else 4
        val grid = GridLayout(this).apply { columnCount = 2; rowCount = if (n == 2) 1 else 2; setBackgroundColor(0xFF000000.toInt()) }
        setContentView(grid)
        val first = Api.byId[intent.getIntExtra("channel", -1)]
        for (i in 0 until n) {
            val box = FrameLayout(this).apply {
                isFocusable = true; isClickable = true
                setBackgroundResource(R.drawable.multi_bg); setPadding((3 * d).toInt(), (3 * d).toInt(), (3 * d).toInt(), (3 * d).toInt())
            }
            val pv = PlayerView(this).apply { useController = false; resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT; isFocusable = false }
            val p = ExoPlayer.Builder(this).setLoadControl(DefaultLoadControl.Builder().setBufferDurationsMs(5_000, 15_000, 1_000, 2_000).build())
                .setMediaSourceFactory(DefaultMediaSourceFactory(OkHttpDataSource.Factory(App.http))).build()
            pv.player = p
            val label = TextView(this).apply {
                textSize = 15f; setTypeface(typeface, Typeface.BOLD); setBackgroundResource(R.drawable.panel_bg)
                setPadding((10 * d).toInt(), (4 * d).toInt(), (10 * d).toInt(), (4 * d).toInt()); text = "OK = choose a channel"
            }
            box.addView(pv, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
            box.addView(label, FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.TOP or Gravity.START).apply { setMargins((10 * d).toInt(), (10 * d).toInt(), 0, 0) })
            val lp = GridLayout.LayoutParams(GridLayout.spec(i / 2, 1f), GridLayout.spec(i % 2, 1f)).apply { width = 0; height = 0 }
            if (n == 2) lp.height = ViewGroup.LayoutParams.MATCH_PARENT
            grid.addView(box, lp)
            val idx = i
            box.setOnClickListener { pick(idx) }
            box.setOnLongClickListener { channels[idx]?.let { c -> openFull(c) }; true }
            box.setOnFocusChangeListener { _, f -> if (f) sound(idx) }
            boxes.add(box); players.add(p); labels.add(label); channels.add(null)
        }
        if (first != null) set(0, first)
        boxes[0].post { boxes[0].requestFocus() }
    }

    private fun sound(i: Int) { players.forEachIndexed { k, p -> p.volume = if (k == i) 1f else 0f } }

    private fun set(i: Int, c: Channel) {
        channels[i] = c
        labels[i].text = "${c.num}  ${c.name}"
        players[i].setMediaItem(MediaItem.fromUri(Api.streamUrl(c)))
        players[i].prepare(); players[i].playWhenReady = true
        sound(boxes.indexOfFirst { it.hasFocus() }.coerceAtLeast(0))
    }

    private fun pick(i: Int) {
        val gs = Api.groups.filter { it.channels.isNotEmpty() }
        AlertDialog.Builder(this).setTitle("Group").setItems(gs.map { it.name }.toTypedArray()) { _, g ->
            val cs = gs[g].channels
            AlertDialog.Builder(this).setTitle(gs[g].name).setItems(cs.map { "${it.num}   ${it.name}" }.toTypedArray()) { _, w -> set(i, cs[w]) }.show()
        }.show()
    }

    private fun openFull(c: Channel) {
        startActivity(android.content.Intent(this, LiveActivity::class.java).putExtra("channel", c.id).addFlags(android.content.Intent.FLAG_ACTIVITY_CLEAR_TOP))
        finish()
    }

    override fun dispatchKeyEvent(e: KeyEvent): Boolean {
        if (!overlayOpen && e.action == KeyEvent.ACTION_DOWN && (e.keyCode == KeyEvent.KEYCODE_DPAD_CENTER || e.keyCode == KeyEvent.KEYCODE_ENTER) && e.repeatCount == 1) {
            val i = boxes.indexOfFirst { it.hasFocus() }
            channels.getOrNull(i)?.let { openFull(it) }
            return true
        }
        return super.dispatchKeyEvent(e)
    }

    override fun onStop() { super.onStop(); players.forEach { it.pause() } }
    override fun onStart() { super.onStart(); players.forEachIndexed { k, p -> if (channels.getOrNull(k) != null) p.play() } }
    override fun onDestroy() { super.onDestroy(); players.forEach { it.release() } }
}
