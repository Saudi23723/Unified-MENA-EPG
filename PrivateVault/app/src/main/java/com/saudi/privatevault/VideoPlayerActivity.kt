package com.saudi.privatevault

import android.net.Uri
import android.os.Bundle
import android.widget.Toast
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import com.saudi.privatevault.databinding.ActivityVideoBinding

class VideoPlayerActivity : BaseActivity() {

    companion object {
        const val EXTRA_IDS = "item_ids"
        const val EXTRA_URLS = "item_urls"
        const val EXTRA_NAMES = "item_names"
    }

    private lateinit var b: ActivityVideoBinding
    private var player: ExoPlayer? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityVideoBinding.inflate(layoutInflater)
        setContentView(b.root)
        val startId = intent.getStringExtra(Viewers.EXTRA_ID) ?: return finish()
        val ids = intent.getStringArrayExtra(EXTRA_IDS)?.toList()?.takeIf { startId in it } ?: listOf(startId)
        val urls = intent.getStringArrayExtra(EXTRA_URLS)
        val names = intent.getStringArrayExtra(EXTRA_NAMES)
        val media = if (urls != null && names != null && urls.size == ids.size && names.size == ids.size) {
            // Streaming from the laptop: nothing of these is stored on the phone.
            ids.indices.map { i -> mediaItem(ids[i], names[i], Uri.parse(urls[i])) }
        } else {
            ids.mapNotNull { VaultStore.item(it) }.map { item ->
                mediaItem(item.id, item.name, item.url?.let { Uri.parse(it) } ?: Uri.fromFile(VaultStore.fileOf(item)))
            }
        }
        val startIndex = media.indexOfFirst { it.mediaId == startId }
        if (startIndex < 0) return finish()

        WindowCompat.getInsetsController(window, window.decorView).apply {
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            hide(WindowInsetsCompat.Type.systemBars())
        }

        val p = ExoPlayer.Builder(this).setSeekBackIncrementMs(15000).setSeekForwardIncrementMs(30000).build()
        player = p
        b.player.player = p
        // Pick up where the chosen video was left last time, then carry on
        // through the rest of the folder.
        val saved = VaultLock.prefs(this).getLong("pos_$startId", 0L)
        p.setMediaItems(media, startIndex, saved)
        p.addListener(object : Player.Listener {
            override fun onMediaItemTransition(mediaItem: MediaItem?, reason: Int) {
                if (reason == Player.MEDIA_ITEM_TRANSITION_REASON_AUTO) {
                    // The previous video played to the end; next time it starts from the beginning.
                    val prev = p.previousMediaItemIndex
                    if (prev >= 0) forget(p.getMediaItemAt(prev).mediaId)
                }
                mediaItem?.mediaMetadata?.title?.let {
                    Toast.makeText(this@VideoPlayerActivity, it, Toast.LENGTH_SHORT).show()
                }
            }

            // The screen stays on while a video plays, so it does not dim and lock mid-lesson.
            override fun onIsPlayingChanged(isPlaying: Boolean) {
                if (isPlaying) window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                else window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            }

            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_ENDED) p.currentMediaItem?.let { forget(it.mediaId) }
            }

            override fun onPlayerError(error: PlaybackException) {
                Toast.makeText(this@VideoPlayerActivity, R.string.open_failed, Toast.LENGTH_LONG).show()
                if (p.hasNextMediaItem()) {
                    p.seekToNextMediaItem()
                    p.prepare()
                }
            }
        })
        p.prepare()
        p.playWhenReady = true
        if (tv) {
            b.player.resizeMode = sizes[VaultLock.prefs(this).getInt("tv_video_size", 0).coerceIn(0, 2)]
            window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            b.player.post { flash(getString(R.string.tv_video_keys)) }
        }
    }

    private fun mediaItem(id: String, name: String, uri: Uri): MediaItem =
        MediaItem.Builder()
            .setMediaId(id)
            .setUri(uri)
            .setMediaMetadata(MediaMetadata.Builder().setTitle(name).build())
            .build()

    // ---- the remote, on a television ----

    private val tv by lazy { Tv.isTv(this) }
    private var badge: android.widget.TextView? = null
    private val sizes = intArrayOf(
        androidx.media3.ui.AspectRatioFrameLayout.RESIZE_MODE_FIT,
        androidx.media3.ui.AspectRatioFrameLayout.RESIZE_MODE_ZOOM,
        androidx.media3.ui.AspectRatioFrameLayout.RESIZE_MODE_FILL,
    )
    private val sizeNames = arrayOf("Fit", "Zoom", "Stretch")

    /** A big short label in the corner, as a TV player shows what a key did. */
    private fun flash(text: String) {
        val root = window.decorView as? android.widget.FrameLayout ?: return
        val d = resources.displayMetrics.density
        val v = badge ?: android.widget.TextView(this).apply {
            textSize = 22f; setTextColor(0xFFFFFFFF.toInt()); typeface = EfbUi.MEDIUM
            background = android.graphics.drawable.GradientDrawable().apply { cornerRadius = 20 * d; setColor(0xB3000000.toInt()) }
            setPadding((22 * d).toInt(), (10 * d).toInt(), (22 * d).toInt(), (10 * d).toInt())
            root.addView(this, android.widget.FrameLayout.LayoutParams(-2, -2, android.view.Gravity.TOP or android.view.Gravity.END).apply { setMargins(0, (36 * d).toInt(), (40 * d).toInt(), 0) })
        }.also { badge = it }
        v.text = text
        v.animate().cancel(); v.alpha = 1f
        v.animate().alpha(0f).setStartDelay(900).setDuration(400).start()
    }

    /**
     * With the controls hidden: OK plays or pauses, left and right go back 15 s and
     * forward 30 s, up shows the controls, down changes the picture size
     * (fit, zoom, stretch). With them shown, the remote moves through them as usual.
     */
    override fun dispatchKeyEvent(event: android.view.KeyEvent): Boolean {
        val p = player
        if (!tv || p == null || b.player.isControllerFullyVisible) return super.dispatchKeyEvent(event)
        if (event.action != android.view.KeyEvent.ACTION_DOWN) {
            return if (event.keyCode == android.view.KeyEvent.KEYCODE_BACK) super.dispatchKeyEvent(event) else true
        }
        when (event.keyCode) {
            android.view.KeyEvent.KEYCODE_DPAD_CENTER, android.view.KeyEvent.KEYCODE_ENTER, android.view.KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE -> {
                if (p.isPlaying) { p.pause(); flash("⏸") } else { p.play(); flash("▶") }
            }
            android.view.KeyEvent.KEYCODE_DPAD_LEFT, android.view.KeyEvent.KEYCODE_MEDIA_REWIND -> { p.seekBack(); flash("⏪ 15 s") }
            android.view.KeyEvent.KEYCODE_DPAD_RIGHT, android.view.KeyEvent.KEYCODE_MEDIA_FAST_FORWARD -> { p.seekForward(); flash("30 s ⏩") }
            android.view.KeyEvent.KEYCODE_DPAD_DOWN -> {
                val i = (sizes.indexOf(b.player.resizeMode) + 1) % sizes.size
                b.player.resizeMode = sizes[i]
                VaultLock.prefs(this).edit().putInt("tv_video_size", i).apply()
                flash("▣ " + sizeNames[i])
            }
            android.view.KeyEvent.KEYCODE_DPAD_UP, android.view.KeyEvent.KEYCODE_MENU -> b.player.showController()
            android.view.KeyEvent.KEYCODE_MEDIA_NEXT -> if (p.hasNextMediaItem()) p.seekToNextMediaItem()
            android.view.KeyEvent.KEYCODE_MEDIA_PREVIOUS -> if (p.hasPreviousMediaItem()) p.seekToPreviousMediaItem()
            else -> return super.dispatchKeyEvent(event)
        }
        return true
    }

    private fun forget(id: String) {
        VaultLock.prefs(this).edit().remove("pos_$id").apply()
    }

    override fun onPause() {
        super.onPause()
        val p = player ?: return
        p.pause()
        val current = p.currentMediaItem ?: return
        if (p.playbackState != Player.STATE_ENDED) {
            VaultLock.prefs(this).edit().putLong("pos_${current.mediaId}", p.currentPosition).apply()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        player?.release()
        player = null
    }
}
