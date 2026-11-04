package com.saudi1.tv

import android.os.Bundle
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.TrackSelectionOverride
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.util.Locale

/** Movies / episodes: ◀ ▶ = 10 s (hold = faster and faster), ⏪ ⏩ = 1 min, hold OK = options;
 *  the place is remembered, and a series goes on to the next episode by itself. */
class PlayerActivity : BaseActivity() {
    private lateinit var player: ExoPlayer
    private lateinit var view: PlayerView
    private lateinit var seekLabel: TextView
    private var key = ""; private var title = ""; private var url = ""; private var poster = ""
    private val nextUrls = ArrayList<String>(); private val nextTitles = ArrayList<String>(); private val nextKeys = ArrayList<String>()
    private var pendingSeek: Long? = null
    private var seekJob: Job? = null
    private var nextBox: View? = null
    private var nextJob: Job? = null
    private val d by lazy { resources.displayMetrics.density }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        url = intent.getStringExtra("url") ?: run { finish(); return }
        title = intent.getStringExtra("title") ?: ""; key = intent.getStringExtra("key") ?: url; poster = intent.getStringExtra("poster") ?: ""
        intent.getStringArrayListExtra("nextUrls")?.let { nextUrls.addAll(it) }
        intent.getStringArrayListExtra("nextTitles")?.let { nextTitles.addAll(it) }
        intent.getStringArrayListExtra("nextKeys")?.let { nextKeys.addAll(it) }
        view = PlayerView(this)
        seekLabel = TextView(this).apply {
            textSize = 26f; setTypeface(typeface, android.graphics.Typeface.BOLD); setBackgroundResource(R.drawable.panel_bg)
            setPadding((26 * d).toInt(), (14 * d).toInt(), (26 * d).toInt(), (14 * d).toInt()); visibility = View.GONE
        }
        setContentView(FrameLayout(this).apply {
            setBackgroundColor(0xFF000000.toInt()); addView(view)
            addView(seekLabel, FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.CENTER))
        })
        player = Players.make(this, live = false)
        view.player = player
        view.setShowNextButton(nextUrls.isNotEmpty()); view.setShowPreviousButton(false)
        view.resizeMode = App.prefs.getInt("resize", 0)
        load(url, intent.getLongExtra("from", Resume.get(key)))
        player.addListener(object : Player.Listener {
            override fun onPlayerError(error: PlaybackException) {
                android.widget.Toast.makeText(this@PlayerActivity, "Could not play this (${error.errorCodeName})", android.widget.Toast.LENGTH_LONG).show()
            }
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_ENDED) { save(); if (nextUrls.isNotEmpty()) askNext() else finish() }
            }
        })
        lifecycleScope.launch { while (isActive) { delay(15_000); save() } }
    }

    private fun load(u: String, from: Long) {
        player.setMediaItem(MediaItem.fromUri(u))
        if (from > 0) player.seekTo(from)
        player.prepare(); player.playWhenReady = true
    }

    private fun save() {
        if (player.duration > 0) Resume.set(key, player.currentPosition, player.duration, title, poster, url)
    }

    // ---------------- next episode ----------------

    private fun playNext() {
        closeNext()
        if (nextUrls.isEmpty()) { finish(); return }
        save()
        url = nextUrls.removeAt(0); title = nextTitles.removeAt(0); key = nextKeys.removeAt(0)
        view.setShowNextButton(nextUrls.isNotEmpty())
        load(url, Resume.get(key))
        android.widget.Toast.makeText(this, title, android.widget.Toast.LENGTH_SHORT).show()
    }

    /** the episode ended: the next one starts in 10 s (Play now / Cancel) */
    private fun askNext() {
        closeNext()
        val count = TextView(this).apply { textSize = 16f; setTextColor(getColor(R.color.text2)) }
        fun btn(t: String, primary: Boolean, go: () -> Unit) = TextView(this).apply {
            text = t; textSize = 17f; gravity = Gravity.CENTER; isFocusable = true; isClickable = true
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setBackgroundResource(if (primary) R.drawable.tile_bg else R.drawable.item_bg); setTextColor(getColorStateList(R.color.on_focus))
            setPadding((22 * d).toInt(), (12 * d).toInt(), (22 * d).toInt(), (12 * d).toInt()); setOnClickListener { go() }
        }
        val playB = btn("▶  Play now", true) { playNext() }
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setBackgroundResource(R.drawable.panel_bg)
            setPadding((26 * d).toInt(), (22 * d).toInt(), (26 * d).toInt(), (22 * d).toInt())
            addView(TextView(this@PlayerActivity).apply { text = "Next episode"; textSize = 15f; setTextColor(getColor(R.color.accent)) })
            addView(TextView(this@PlayerActivity).apply { text = nextTitles[0]; textSize = 22f; setTypeface(typeface, android.graphics.Typeface.BOLD) })
            addView(count)
            addView(LinearLayout(this@PlayerActivity).apply {
                orientation = LinearLayout.HORIZONTAL; setPadding(0, (14 * d).toInt(), 0, 0)
                addView(playB); addView(View(this@PlayerActivity), LinearLayout.LayoutParams((14 * d).toInt(), 1))
                addView(btn("Cancel", false) { closeNext(); finish() })
            })
        }
        val root = window.decorView as ViewGroup
        root.addView(panel, FrameLayout.LayoutParams((520 * d).toInt(), ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM or Gravity.END).apply {
            setMargins(0, 0, (48 * d).toInt(), (48 * d).toInt())
        })
        nextBox = panel
        applyDim()
        playB.requestFocus()
        nextJob = lifecycleScope.launch {
            for (left in 10 downTo 1) { count.text = "Starts in $left s"; delay(1000) }
            playNext()
        }
    }

    private fun closeNext() {
        nextJob?.cancel(); nextBox?.let { (window.decorView as ViewGroup).removeView(it) }; nextBox = null
    }

    // ---------------- keys ----------------

    /** ◀ ▶ held: 10 s, then 30 s, 1 min, 2 min, 5 min steps; the picture jumps when the key is let go */
    private fun seekStep(repeat: Int) = when {
        repeat < 4 -> 10_000L; repeat < 12 -> 30_000L; repeat < 24 -> 60_000L; repeat < 40 -> 120_000L; else -> 300_000L
    }

    private fun fmt(ms: Long): String { val t = ms / 1000; return if (t >= 3600) "%d:%02d:%02d".format(t / 3600, t / 60 % 60, t % 60) else "%d:%02d".format(t / 60, t % 60) }

    private fun showSeek(target: Long) {
        val diff = target - player.currentPosition
        seekLabel.text = (if (diff >= 0) "⏩  +" else "⏪  −") + fmt(kotlin.math.abs(diff)) + "     " + fmt(target) +
            (if (player.duration > 0) "  /  " + fmt(player.duration) else "")
        seekLabel.visibility = View.VISIBLE; seekLabel.bringToFront()
        seekJob?.cancel()
    }

    private fun commitSeek() {
        val t = pendingSeek ?: return
        pendingSeek = null
        player.seekTo(t)
        seekJob?.cancel(); seekJob = lifecycleScope.launch { delay(900); seekLabel.visibility = View.GONE }
    }

    override fun dispatchKeyEvent(e: KeyEvent): Boolean {
        if (nextBox != null && e.keyCode == KeyEvent.KEYCODE_BACK) { if (e.action == KeyEvent.ACTION_UP) { closeNext(); finish() }; return true }
        if (!overlayOpen && nextBox == null) {
            val down = e.action == KeyEvent.ACTION_DOWN
            when (e.keyCode) {
                KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT -> if (!view.isControllerFullyVisible || pendingSeek != null) {
                    if (down) {
                        val dir = if (e.keyCode == KeyEvent.KEYCODE_DPAD_RIGHT) 1 else -1
                        val base = pendingSeek ?: player.currentPosition
                        val max = if (player.duration > 0) player.duration - 1000 else Long.MAX_VALUE
                        pendingSeek = (base + dir * seekStep(e.repeatCount)).coerceIn(0, max)
                        showSeek(pendingSeek!!)
                    } else commitSeek()
                    return true
                }
                KeyEvent.KEYCODE_MEDIA_FAST_FORWARD -> { if (down) { player.seekTo(player.currentPosition + 60_000); view.showController() }; return true }
                KeyEvent.KEYCODE_MEDIA_REWIND -> { if (down) { player.seekTo((player.currentPosition - 60_000).coerceAtLeast(0)); view.showController() }; return true }
                KeyEvent.KEYCODE_MEDIA_NEXT -> { if (down && nextUrls.isNotEmpty()) playNext(); return true }
                KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER -> if (down && e.repeatCount == 1) { options(); return true }
                KeyEvent.KEYCODE_MENU -> { if (down) options(); return true }
            }
        }
        return super.dispatchKeyEvent(e)
    }

    private fun options() {
        val items = arrayListOf("Audio", "Subtitles", "Picture size", "Night mode")
        if (nextUrls.isNotEmpty()) items.add("Next episode")
        AlertDialog.Builder(this).setTitle(title).setItems(items.toTypedArray()) { _, w ->
            when (w) {
                0 -> tracks(C.TRACK_TYPE_AUDIO)
                1 -> tracks(C.TRACK_TYPE_TEXT)
                2 -> {
                    val modes = intArrayOf(0, 3, 4)
                    AlertDialog.Builder(this).setItems(arrayOf("Fit", "Stretch", "Zoom")) { _, m -> view.resizeMode = modes[m] }.show()
                }
                3 -> nightDialog()
                4 -> playNext()
            }
        }.show()
    }

    private fun tracks(type: Int) {
        val groups = player.currentTracks.groups.filter { it.type == type }
        val names = ArrayList<String>(); val picks = ArrayList<Pair<Int, Int>>()
        if (type == C.TRACK_TYPE_TEXT) { names.add("Off"); picks.add(-1 to -1) }
        groups.forEachIndexed { gi, g ->
            for (t in 0 until g.length) {
                if (!g.isTrackSupported(t)) continue
                val f = g.getTrackFormat(t)
                names.add(listOfNotNull(f.language?.let { Locale(it).displayLanguage }, f.label, if (f.channelCount > 0) "${f.channelCount}ch" else null)
                    .distinct().joinToString(" · ").ifEmpty { "Track ${names.size + 1}" })
                picks.add(gi to t)
            }
        }
        if (names.size < 2 && type == C.TRACK_TYPE_AUDIO || names.isEmpty()) {
            android.widget.Toast.makeText(this, if (type == C.TRACK_TYPE_AUDIO) "One audio only" else "No subtitles", android.widget.Toast.LENGTH_SHORT).show(); return
        }
        AlertDialog.Builder(this).setItems(names.toTypedArray()) { _, w ->
            val (gi, t) = picks[w]
            val b = player.trackSelectionParameters.buildUpon()
            if (gi < 0) b.setTrackTypeDisabled(C.TRACK_TYPE_TEXT, true)
            else b.setTrackTypeDisabled(type, false).setOverrideForType(TrackSelectionOverride(groups[gi].mediaTrackGroup, t))
            player.trackSelectionParameters = b.build()
        }.show()
    }

    override fun onPause() { super.onPause(); save(); player.pause() }
    override fun onDestroy() { super.onDestroy(); player.release() }
}
