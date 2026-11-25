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
    fun make(ctx: Context, live: Boolean, seekMs: Long = 10_000, audioFocus: Boolean = true, maxHd: Boolean = false,
             offAir: Boolean = false): ExoPlayer {
        // the picture decoder: the TV's chip (Hardware, fast, the default) or the software one, chosen in the player
        // (Options › Decoder) for a channel or film the chip shows badly; the other one stays as the fallback
        val selector = androidx.media3.exoplayer.mediacodec.MediaCodecSelector { mime, secure, tunneling ->
            val list = androidx.media3.exoplayer.mediacodec.MediaCodecUtil.getDecoderInfos(mime, secure, tunneling)
            if (mime.startsWith("video/") && softwareVideo) list.sortedBy { it.hardwareAccelerated } else list
        }
        val renderers = DefaultRenderersFactory(ctx)
            .setExtensionRendererMode(DefaultRenderersFactory.EXTENSION_RENDERER_MODE_ON)
            .setEnableDecoderFallback(true)
            .setMediaCodecSelector(selector)
        val b = ExoPlayer.Builder(ctx, renderers)
            .setMediaSourceFactory(DefaultMediaSourceFactory(DefaultDataSource.Factory(ctx, OkHttpDataSource.Factory(if (offAir) App.http.newBuilder().addInterceptor(OffAir.interceptor).build() else App.http)))
                // the provider's off-air file is not asked for again 3 times (that took 6 s): the switch comes at once
                .apply { if (offAir) setLoadErrorHandlingPolicy(object : androidx.media3.exoplayer.upstream.DefaultLoadErrorHandlingPolicy() {
                    override fun getRetryDelayMsFor(info: androidx.media3.exoplayer.upstream.LoadErrorHandlingPolicy.LoadErrorInfo): Long =
                        if (OffAir.isOffAir(info.exception)) C.TIME_UNSET else super.getRetryDelayMsFor(info)
                }) }
                // films and episodes: a short drop of the provider is asked for again up to 8 times before it shows
                .apply { if (!live) setLoadErrorHandlingPolicy(androidx.media3.exoplayer.upstream.DefaultLoadErrorHandlingPolicy(8)) })
            .setAudioAttributes(AudioAttributes.Builder().setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_MOVIE).build(), audioFocus)
            .setSeekBackIncrementMs(seekMs).setSeekForwardIncrementMs(seekMs)
        // Multiview: never more than full HD per screen (two 4K pictures at once are too much for the TV's chip)
        if (maxHd) b.setTrackSelector(androidx.media3.exoplayer.trackselection.DefaultTrackSelector(ctx).apply {
            setParameters(buildUponParameters().setMaxVideoSize(1920, 1080).setMaxVideoBitrate(12_000_000))
        })
        // live TV: starts after 1 s of picture (was 1.5 s; owner, 25 Nov 2026: channels felt slower), keeps up to 50 s in reserve so short provider hiccups don't show,
        // and after a hiccup waits for 3 s before playing again (no stop-start-stop). Staying close to live is
        // done by LiveActivity's catch-up (plays 1.07x while it is behind).
        if (live) b.setLoadControl(DefaultLoadControl.Builder().setBufferDurationsMs(15_000, 50_000, 1_000, 3_000)
            .setPrioritizeTimeOverSizeThresholds(true).build())
        // films and episodes (owner, 21 Nov 2026: long episodes waited and stopped to load): start after 1.5 s of
        // picture like TiviMate, then keep up to 2 minutes loaded ahead (at most 100 MB, fine for small TVs too), so
        // a slow moment of the provider is covered by what is already loaded
        else b.setLoadControl(DefaultLoadControl.Builder().setBufferDurationsMs(30_000, 120_000, 1_500, 3_000)
            .setTargetBufferBytes(100 * 1024 * 1024).setPrioritizeTimeOverSizeThresholds(false).build())
        return b.build()
    }

    /** Hardware (false, the default) or software (true) picture decoding, for every player; set in the player */
    var softwareVideo: Boolean
        get() = App.prefs.getBoolean("sw_decoder", false)
        set(v) = App.prefs.edit().putBoolean("sw_decoder", v).apply()
}
