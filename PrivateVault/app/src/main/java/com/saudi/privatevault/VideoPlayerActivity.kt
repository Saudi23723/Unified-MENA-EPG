package com.saudi.privatevault

import android.net.Uri
import android.os.Bundle
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import com.saudi.privatevault.databinding.ActivityVideoBinding

class VideoPlayerActivity : BaseActivity() {

    private lateinit var b: ActivityVideoBinding
    private var player: ExoPlayer? = null
    private var itemId = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityVideoBinding.inflate(layoutInflater)
        setContentView(b.root)
        val item = VaultStore.item(intent.getStringExtra(Viewers.EXTRA_ID)) ?: return finish()
        itemId = item.id
        WindowCompat.getInsetsController(window, window.decorView).apply {
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            hide(WindowInsetsCompat.Type.systemBars())
        }

        val p = ExoPlayer.Builder(this).build()
        player = p
        b.player.player = p
        p.setMediaItem(MediaItem.fromUri(Uri.fromFile(VaultStore.fileOf(item))))
        // Pick up where the video was left last time, unless it had finished.
        val saved = VaultLock.prefs(this).getLong("pos_$itemId", 0L)
        if (saved > 0) p.seekTo(saved)
        p.addListener(object : Player.Listener {
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_ENDED) {
                    VaultLock.prefs(this@VideoPlayerActivity).edit().remove("pos_$itemId").apply()
                }
            }
        })
        p.prepare()
        p.playWhenReady = true
    }

    override fun onPause() {
        super.onPause()
        val p = player ?: return
        p.pause()
        if (p.playbackState != Player.STATE_ENDED) {
            VaultLock.prefs(this).edit().putLong("pos_$itemId", p.currentPosition).apply()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        player?.release()
        player = null
    }
}
