package com.saudi1.tv

import android.content.Context
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.datasource.DefaultDataSource
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.DefaultLoadControl
import androidx.media3.exoplayer.DefaultRenderersFactory
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory

/** One way to make a player everywhere: the TV's own decoders first, and the built-in FFmpeg sound decoders
 *  (AC3, E-AC3, MP2, DTS...) when the TV has none, so channels with that sound are not silent. */
object Players {
    fun make(ctx: Context, live: Boolean, seekMs: Long = 10_000): ExoPlayer {
        val renderers = DefaultRenderersFactory(ctx)
            .setExtensionRendererMode(DefaultRenderersFactory.EXTENSION_RENDERER_MODE_ON)
            .setEnableDecoderFallback(true)
        val b = ExoPlayer.Builder(ctx, renderers)
            .setMediaSourceFactory(DefaultMediaSourceFactory(DefaultDataSource.Factory(ctx, OkHttpDataSource.Factory(App.http))))
            .setAudioAttributes(AudioAttributes.Builder().setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_MOVIE).build(), true)
            .setSeekBackIncrementMs(seekMs).setSeekForwardIncrementMs(seekMs)
        // fast start for live TV: small buffers, play as soon as there is a second of video
        if (live) b.setLoadControl(DefaultLoadControl.Builder().setBufferDurationsMs(8_000, 30_000, 1_000, 2_000).build())
        return b.build()
    }
}
