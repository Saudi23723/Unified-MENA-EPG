package com.saudi1.tv

import android.os.Bundle
import android.view.KeyEvent
import android.widget.FrameLayout
import androidx.appcompat.app.AlertDialog
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.TrackSelectionOverride
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.ui.PlayerView
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.util.Locale

/** Movies / episodes: seek bar, ◀ ▶ = 10 s, ⏪ ⏩ = 1 min, hold OK = audio / subtitles; the place is remembered. */
class PlayerActivity : BaseActivity() {
    private lateinit var player: ExoPlayer
    private lateinit var view: PlayerView
    private var key = ""; private var title = ""; private var url = ""; private var poster = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        url = intent.getStringExtra("url") ?: run { finish(); return }
        title = intent.getStringExtra("title") ?: ""; key = intent.getStringExtra("key") ?: url; poster = intent.getStringExtra("poster") ?: ""
        view = PlayerView(this)
        setContentView(FrameLayout(this).apply { setBackgroundColor(0xFF000000.toInt()); addView(view) })
        player = ExoPlayer.Builder(this).setMediaSourceFactory(DefaultMediaSourceFactory(androidx.media3.datasource.DefaultDataSource.Factory(this, OkHttpDataSource.Factory(App.http))))
            .setSeekBackIncrementMs(10_000).setSeekForwardIncrementMs(10_000).build()
        view.player = player
        view.setShowNextButton(false); view.setShowPreviousButton(false)
        view.resizeMode = App.prefs.getInt("resize", 0)
        player.setMediaItem(MediaItem.fromUri(url))
        val from = intent.getLongExtra("from", Resume.get(key))
        if (from > 0) player.seekTo(from)
        player.prepare(); player.playWhenReady = true
        player.addListener(object : Player.Listener {
            override fun onPlayerError(error: PlaybackException) {
                android.widget.Toast.makeText(this@PlayerActivity, "Could not play this (${error.errorCodeName})", android.widget.Toast.LENGTH_LONG).show()
            }
            override fun onPlaybackStateChanged(state: Int) { if (state == Player.STATE_ENDED) { save(); finish() } }
        })
        lifecycleScope.launch { while (isActive) { delay(15_000); save() } }
    }

    private fun save() {
        if (player.duration > 0) Resume.set(key, player.currentPosition, player.duration, title, poster, url)
    }

    override fun dispatchKeyEvent(e: KeyEvent): Boolean {
        if (!overlayOpen && e.action == KeyEvent.ACTION_DOWN) {
            when (e.keyCode) {
                KeyEvent.KEYCODE_MEDIA_FAST_FORWARD -> { player.seekTo(player.currentPosition + 60_000); view.showController(); return true }
                KeyEvent.KEYCODE_MEDIA_REWIND -> { player.seekTo((player.currentPosition - 60_000).coerceAtLeast(0)); view.showController(); return true }
                KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER -> if (e.repeatCount == 1) { options(); return true }
                KeyEvent.KEYCODE_MENU -> { options(); return true }
                KeyEvent.KEYCODE_DPAD_LEFT -> if (!view.isControllerFullyVisible) { player.seekBack(); view.showController(); return true }
                KeyEvent.KEYCODE_DPAD_RIGHT -> if (!view.isControllerFullyVisible) { player.seekForward(); view.showController(); return true }
            }
        }
        return super.dispatchKeyEvent(e)
    }

    private fun options() {
        AlertDialog.Builder(this).setTitle(title).setItems(arrayOf("Audio", "Subtitles", "Picture size")) { _, w ->
            when (w) {
                0 -> tracks(C.TRACK_TYPE_AUDIO)
                1 -> tracks(C.TRACK_TYPE_TEXT)
                2 -> {
                    val modes = intArrayOf(0, 3, 4)
                    AlertDialog.Builder(this).setItems(arrayOf("Fit", "Stretch", "Zoom")) { _, m -> view.resizeMode = modes[m] }.show()
                }
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
                names.add(listOfNotNull(f.language?.let { Locale(it).displayLanguage }, f.label).distinct().joinToString(" · ").ifEmpty { "Track ${names.size + 1}" })
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
