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

        val p = ExoPlayer.Builder(this).build()
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
    }

    private fun mediaItem(id: String, name: String, uri: Uri): MediaItem =
        MediaItem.Builder()
            .setMediaId(id)
            .setUri(uri)
            .setMediaMetadata(MediaMetadata.Builder().setTitle(name).build())
            .build()

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
