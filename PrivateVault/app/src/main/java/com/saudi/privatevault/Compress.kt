package com.saudi.privatevault

import android.content.Context
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.os.Handler
import android.os.Looper
import androidx.annotation.OptIn
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.util.UnstableApi
import androidx.media3.effect.Presentation
import androidx.media3.transformer.Composition
import androidx.media3.transformer.EditedMediaItem
import androidx.media3.transformer.Effects
import androidx.media3.transformer.ExportException
import androidx.media3.transformer.ExportResult
import androidx.media3.transformer.Transformer
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** Videos go to the cloud at 720p (H.264, AAC): the phone's own encoder, in a temporary file. */
object Compress {
    /** The 720p copy, or null when it is not needed (already 720p or less) or could not be made. Off the main thread. */
    @OptIn(UnstableApi::class)
    fun to720(ctx: Context, input: File): File? {
        // The picture as shown (rotation applied): its short side is what "720p" means.
        var w = 0; var h = 0
        try {
            MediaMetadataRetriever().run {
                setDataSource(input.path)
                w = extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH)?.toIntOrNull() ?: 0
                h = extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT)?.toIntOrNull() ?: 0
                val rot = extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_ROTATION)?.toIntOrNull() ?: 0
                if (rot % 180 != 0) { val x = w; w = h; h = x }
                release()
            }
        } catch (e: Exception) {}
        if (w <= 0 || h <= 0 || minOf(w, h) <= 720) return null
        val size = if (h <= w) Presentation.createForHeight(720)
            else Presentation.createForWidthAndHeight(720, (720L * h / w).toInt() / 2 * 2, Presentation.LAYOUT_SCALE_TO_FIT)
        val out = File(File(ctx.cacheDir, "compress").apply { mkdirs() }, input.nameWithoutExtension + ".720.mp4")
        out.delete()
        val done = CountDownLatch(1)
        var ok = false
        val main = Handler(Looper.getMainLooper())
        var transformer: Transformer? = null
        main.post {
            try {
                val t = Transformer.Builder(ctx)
                    .setVideoMimeType(MimeTypes.VIDEO_H264)
                    .setAudioMimeType(MimeTypes.AUDIO_AAC)
                    .addListener(object : Transformer.Listener {
                        override fun onCompleted(composition: Composition, result: ExportResult) { ok = true; done.countDown() }
                        override fun onError(composition: Composition, result: ExportResult, exception: ExportException) { done.countDown() }
                    })
                    .build()
                transformer = t
                val item = EditedMediaItem.Builder(MediaItem.fromUri(Uri.fromFile(input)))
                    .setEffects(Effects(listOf(), listOf(size)))
                    .build()
                t.start(item, out.path)
            } catch (e: Exception) { done.countDown() }
        }
        if (!done.await(3, TimeUnit.HOURS)) main.post { try { transformer?.cancel() } catch (e: Exception) {} }
        return if (ok && out.length() > 0 && out.length() < input.length()) out else { out.delete(); null }
    }
}
