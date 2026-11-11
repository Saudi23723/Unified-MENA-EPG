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
                b.player.post { ensureCaptions(p) }
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
        captions(p)
        p.prepare()
        p.playWhenReady = true
        // Captions the app makes itself, shown as soon as they are ready.
        b.player.post { ensureCaptions(p) }
        if (tv) {
            b.player.resizeMode = sizes[VaultLock.prefs(this).getInt("tv_video_size", 0).coerceIn(0, 2)]
            window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            b.player.post { flash(getString(R.string.tv_video_keys)) }
        }
    }

    /** Captions on whenever the video carries them, in the pilot's chosen colours (Settings → Captions). */
    private fun captions(p: ExoPlayer) {
        val prefs = VaultLock.prefs(this)
        p.trackSelectionParameters = p.trackSelectionParameters.buildUpon()
            .setPreferredTextLanguages("ar", "en")
            .setSelectUndeterminedTextLanguage(true)
            .setIgnoredTextSelectionFlags(0)
            .setTrackTypeDisabled(androidx.media3.common.C.TRACK_TYPE_TEXT, !prefs.getBoolean("cc_on", true))
            .build()
        val fg = prefs.getInt("cc_fg", 0xFFFFFFFF.toInt())
        val alpha = prefs.getInt("cc_bg_alpha", 60).coerceIn(0, 100) * 255 / 100
        val bg = (alpha shl 24) or (prefs.getInt("cc_bg", 0xFF000000.toInt()) and 0xFFFFFF)
        b.player.subtitleView?.apply {
            setStyle(androidx.media3.ui.CaptionStyleCompat(fg, bg, 0, androidx.media3.ui.CaptionStyleCompat.EDGE_TYPE_DROP_SHADOW, 0xFF000000.toInt(), null))
            setFractionalTextSize(androidx.media3.ui.SubtitleView.DEFAULT_TEXT_SIZE_FRACTION * prefs.getFloat("cc_size", 1.15f))
            setApplyEmbeddedStyles(false)
        }
    }

    /** The current video with its app-made captions: attached if ready, else made in the background. */
    private fun ensureCaptions(p: ExoPlayer) {
        val item = p.currentMediaItem ?: return
        val id = item.mediaId
        val prefs = VaultLock.prefs(this)
        if (!prefs.getBoolean("cc_on", true)) return
        if (item.localConfiguration?.subtitleConfigurations?.isNotEmpty() == true) return
        Captions.ready(this, id)?.let { attach(p, it); return }
        if (!prefs.getBoolean("cc_auto", true) || (!Gemini.hasKey(this) && !LaptopClient.isLinked(this))) {
            if (!Gemini.hasKey(this)) flash(getString(R.string.cc_nokey))
            return
        }
        val uri = item.localConfiguration?.uri ?: return
        Thread {
            val ok = Captions.make(applicationContext, id, uri) { st -> runOnUiThread { flash(st) } }
            runOnUiThread {
                val f = Captions.ready(this, id)
                if (ok && f != null && player === p && p.currentMediaItem?.mediaId == id) { attach(p, f); flash("CC ✓") }
                else if (!ok) flash(getString(when (Captions.problem) { "nokey" -> R.string.cc_nokey; "audio" -> R.string.cc_noaudio; else -> R.string.cc_failed }))
            }
        }.start()
    }

    private fun attach(p: ExoPlayer, srt: java.io.File) {
        val i = p.currentMediaItemIndex
        val cur = p.currentMediaItem ?: return
        val pos = p.currentPosition
        val sub = MediaItem.SubtitleConfiguration.Builder(Uri.fromFile(srt))
            .setMimeType(androidx.media3.common.MimeTypes.APPLICATION_SUBRIP)
            .setLanguage(VaultLock.prefs(this).getString("cc_lang", "both")?.let { if (it == "en") "en" else "ar" })
            .setSelectionFlags(androidx.media3.common.C.SELECTION_FLAG_DEFAULT or androidx.media3.common.C.SELECTION_FLAG_FORCED)
            .build()
        p.replaceMediaItem(i, cur.buildUpon().setSubtitleConfigurations(listOf(sub)).build())
        if (Math.abs(p.currentPosition - pos) > 2000) p.seekTo(i, pos)
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
    private var backAt = 0L

    override fun dispatchKeyEvent(event: android.view.KeyEvent): Boolean {
        val p = player
        // Back: once hides the controls; with them hidden, twice (within 2 s) leaves the video.
        if (event.keyCode == android.view.KeyEvent.KEYCODE_BACK) {
            if (event.action == android.view.KeyEvent.ACTION_UP) {
                val now = android.os.SystemClock.elapsedRealtime()
                when {
                    b.player.isControllerFullyVisible -> b.player.hideController()
                    now - backAt < 2000 -> finish()
                    else -> { backAt = now; flash("↩ " + getString(R.string.video_back_again)) }
                }
            }
            return true
        }
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

    /** Played to the end: next time from the start, and marked watched in its folder. */
    private fun forget(id: String) {
        VaultLock.prefs(this).edit().remove("pos_$id").putBoolean("done_$id", true).apply()
    }

    override fun onPause() {
        super.onPause()
        val p = player ?: return
        p.pause()
        val current = p.currentMediaItem ?: return
        if (p.playbackState != Player.STATE_ENDED) {
            val e = VaultLock.prefs(this).edit().putLong("pos_${current.mediaId}", p.currentPosition)
            if (p.duration > 0) e.putLong("dur_${current.mediaId}", p.duration)
            // Nearly all of it seen counts as watched.
            if (p.duration > 0 && p.currentPosition > p.duration * 0.95) e.putBoolean("done_${current.mediaId}", true).remove("pos_${current.mediaId}")
            e.apply()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        player?.release()
        player = null
    }
}
