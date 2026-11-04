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
    fun make(ctx: Context, live: Boolean, seekMs: Long = 10_000, audioFocus: Boolean = true): ExoPlayer {
        val renderers = DefaultRenderersFactory(ctx)
            .setExtensionRendererMode(DefaultRenderersFactory.EXTENSION_RENDERER_MODE_ON)
            .setEnableDecoderFallback(true)
        val b = ExoPlayer.Builder(ctx, renderers)
            .setMediaSourceFactory(DefaultMediaSourceFactory(DefaultDataSource.Factory(ctx, OkHttpDataSource.Factory(App.http))))
            .setAudioAttributes(AudioAttributes.Builder().setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_MOVIE).build(), audioFocus)
            .setSeekBackIncrementMs(seekMs).setSeekForwardIncrementMs(seekMs)
        // live TV: starts after 1.5 s of picture, keeps up to 50 s in reserve so short provider hiccups don't show,
        // and after a hiccup waits for 3 s before playing again (no stop-start-stop). Staying close to live is
        // done by LiveActivity's catch-up (plays 1.07x while it is behind).
        if (live) b.setLoadControl(DefaultLoadControl.Builder().setBufferDurationsMs(15_000, 50_000, 1_500, 3_000)
            .setPrioritizeTimeOverSizeThresholds(true).build())
        return b.build()
    }
}
