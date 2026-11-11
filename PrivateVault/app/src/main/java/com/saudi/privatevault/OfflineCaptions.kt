package com.saudi.privatevault

import android.content.Context
import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.net.Uri
import com.google.mlkit.common.model.DownloadConditions
import com.google.mlkit.nl.translate.TranslateLanguage
import com.google.mlkit.nl.translate.Translation
import com.google.mlkit.nl.translate.TranslatorOptions
import org.json.JSONArray
import org.json.JSONObject
import org.vosk.Model
import org.vosk.Recognizer
import java.io.File
import java.net.URL
import java.util.zip.ZipInputStream

/**
 * Closed captions made on the device itself, no cloud AI: the video's sound is decoded as it plays,
 * Vosk (offline speech recognition) writes down the words with their times, Google's on-device
 * translator puts each caption into Arabic, and the app's aviation dictionary keeps the terms right.
 * Captions are kept per video, so a video watched again has them at once.
 */
class OfflineCaptions(private val ctx: Context, private val id: String, private val source: Uri) {
    class Cue(val start: Long, val end: Long, val en: String, var ar: String = "")

    val cues = java.util.concurrent.CopyOnWriteArrayList<Cue>()
    @Volatile private var stop = false
    @Volatile private var worker: Thread? = null
    @Volatile var status = ""
    /** Up to where (ms) the sound has been written down, from [from]. */
    @Volatile var startedAt = -1L
    @Volatile var upTo = -1L

    private val cache = File(File(ctx.filesDir, "cc").apply { mkdirs() }, id.replace(Regex("[^A-Za-z0-9_-]"), "_") + ".cues.json")

    init { load() }

    /** The caption to show at [ms], or null. */
    fun at(ms: Long): Cue? = cues.firstOrNull { ms >= it.start && ms <= it.end + 700 }

    /** Writes down the sound from [ms] on, unless that part is already done. */
    fun from(ms: Long) {
        val done = cues.isNotEmpty() && ms >= (cues.first().start - 2000) && ms <= (cues.last().end + 3000) && complete
        if (done) return
        if (worker != null && ms >= startedAt && ms <= upTo + 15000) return
        stop = true
        worker?.join(300)
        stop = false
        startedAt = ms; upTo = ms
        worker = Thread { try { run(ms) } catch (e: Throwable) { status = "⚠ " + (e.message ?: e.javaClass.simpleName) } finally { worker = null } }.apply { priority = Thread.MIN_PRIORITY; start() }
    }

    fun close() { stop = true; save() }

    @Volatile private var complete = false

    // ---- the speech model, downloaded once (about 40 MB) ----

    private fun model(): Model {
        val dir = File(ctx.filesDir, "vosk")
        val ready = File(dir, "vosk-model-small-en-us-0.15")
        if (!File(ready, "am").exists()) {
            status = "⬇ CC model…"
            dir.mkdirs()
            URL("https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip").openStream().use { input ->
                ZipInputStream(input.buffered()).use { z ->
                    var e = z.nextEntry
                    while (e != null) {
                        val f = File(dir, e.name)
                        if (!f.canonicalPath.startsWith(dir.canonicalPath)) throw SecurityException("bad zip")
                        if (e.isDirectory) f.mkdirs() else { f.parentFile?.mkdirs(); f.outputStream().use { z.copyTo(it) } }
                        e = z.nextEntry
                    }
                }
            }
        }
        return Model(ready.path)
    }

    // ---- the work: sound → 16 kHz mono → words with times → captions ----

    private fun run(startMs: Long) {
        val m = sharedModel ?: model().also { sharedModel = it }
        status = "🎧 CC"
        val rec = Recognizer(m, 16000f).apply { setWords(true) }
        val ex = MediaExtractor()
        if (source.scheme == "http" || source.scheme == "https") ex.setDataSource(source.toString(), emptyMap()) else ex.setDataSource(ctx, source, null)
        val track = (0 until ex.trackCount).firstOrNull { ex.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("audio/") == true }
            ?: run { status = "⚠ CC: no sound"; return }
        ex.selectTrack(track)
        ex.seekTo(startMs * 1000, MediaExtractor.SEEK_TO_PREVIOUS_SYNC)
        val fmt = ex.getTrackFormat(track)
        val codec = MediaCodec.createDecoderByType(fmt.getString(MediaFormat.KEY_MIME)!!)
        codec.configure(fmt, null, null, 0)
        codec.start()
        var rate = fmt.getInteger(MediaFormat.KEY_SAMPLE_RATE)
        var ch = fmt.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
        val info = MediaCodec.BufferInfo()
        var inputDone = false
        var base = -1L          // the time (ms) of the first sound fed to the recognizer
        var frac = 0.0          // resampling position
        val out16 = java.io.ByteArrayOutputStream()
        try {
            while (!stop) {
                if (!inputDone) {
                    val i = codec.dequeueInputBuffer(10000)
                    if (i >= 0) {
                        val buf = codec.getInputBuffer(i)!!
                        val n = ex.readSampleData(buf, 0)
                        if (n < 0) { codec.queueInputBuffer(i, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM); inputDone = true }
                        else { codec.queueInputBuffer(i, 0, n, ex.sampleTime, 0); ex.advance() }
                    }
                }
                val o = codec.dequeueOutputBuffer(info, 10000)
                if (o == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                    rate = codec.outputFormat.getInteger(MediaFormat.KEY_SAMPLE_RATE)
                    ch = codec.outputFormat.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
                } else if (o >= 0) {
                    if (base < 0) base = info.presentationTimeUs / 1000
                    val b = codec.getOutputBuffer(o)!!.order(java.nio.ByteOrder.LITTLE_ENDIAN).asShortBuffer()
                    val frames = b.remaining() / ch
                    val step = rate / 16000.0
                    out16.reset()
                    // Mono, then 16 kHz by stepping through the frames.
                    while (frac < frames) {
                        val f = frac.toInt()
                        var sum = 0
                        for (c in 0 until ch) sum += b.get(f * ch + c)
                        val v = (sum / ch)
                        out16.write(v and 0xFF); out16.write((v shr 8) and 0xFF)
                        frac += step
                    }
                    frac -= frames
                    codec.releaseOutputBuffer(o, false)
                    val bytes = out16.toByteArray()
                    if (rec.acceptWaveForm(bytes, bytes.size)) take(rec.result, base)
                    upTo = info.presentationTimeUs / 1000
                    if ((info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0) { take(rec.finalResult, base); complete = startMs == 0L; break }
                    // No further ahead than two minutes past the picture: the phone stays cool.
                    while (!stop && upTo - (playhead()) > 120000) Thread.sleep(500)
                }
            }
        } finally {
            try { codec.stop(); codec.release() } catch (e: Exception) {}
            ex.release(); rec.close()
            save()
        }
    }

    /** Where the picture is now; set by the player. */
    @Volatile var position = 0L
    private fun playhead() = position

    /** A recognizer result: its words grouped into captions of up to about 7 words or 3.5 s. */
    private fun take(json: String, base: Long) {
        val words = JSONObject(json).optJSONArray("result") ?: return
        var group = ArrayList<JSONObject>()
        fun flush() {
            if (group.isEmpty()) return
            val s = base + (group.first().optDouble("start") * 1000).toLong()
            val e = base + (group.last().optDouble("end") * 1000).toLong()
            val text = group.joinToString(" ") { it.optString("word") }.replaceFirstChar { it.uppercase() }
            val cue = Cue(s, e, text)
            cues.removeAll { it.start in s..e }
            cues.add(cue)
            translate(cue)
            group = ArrayList()
        }
        for (i in 0 until words.length()) {
            val w = words.getJSONObject(i)
            if (group.isNotEmpty() && (group.size >= 7 || w.optDouble("end") - group.first().optDouble("start") > 3.5 ||
                    w.optDouble("start") - group.last().optDouble("end") > 0.8)) flush()
            group.add(w)
        }
        flush()
        // In time order for showing.
        val sorted = cues.sortedBy { it.start }
        cues.clear(); cues.addAll(sorted)
    }

    // ---- Arabic, on the device ----

    private fun translate(c: Cue) {
        val tr = translator ?: return
        val (text, found) = AviationGlossary.protect(c.en)
        tr.translate(text).addOnSuccessListener { ar ->
            c.ar = AviationGlossary.restore(ar, found) ?: ar.replace(Regex("ZQ\\d+"), "")
        }
    }

    private fun load() {
        try {
            val a = JSONArray(cache.readText())
            for (i in 0 until a.length()) a.getJSONObject(i).let { cues.add(Cue(it.getLong("s"), it.getLong("e"), it.getString("en"), it.optString("ar"))) }
            complete = cache.length() > 0 && JSONArray(cache.readText()).length() > 0 && File(cache.path + ".done").exists()
        } catch (e: Exception) {}
        for (c in cues) if (c.ar.isEmpty()) translate(c)
    }

    private fun save() {
        try {
            val a = JSONArray()
            for (c in cues) a.put(JSONObject().put("s", c.start).put("e", c.end).put("en", c.en).put("ar", c.ar))
            cache.writeText(a.toString())
            if (complete) File(cache.path + ".done").writeText("1")
        } catch (e: Exception) {}
    }

    companion object {
        @Volatile private var sharedModel: Model? = null
        @Volatile private var translator: com.google.mlkit.nl.translate.Translator? = null

        /** The English to Arabic model, downloaded once by the device (about 30 MB). */
        fun prepareArabic(ctx: Context) {
            if (translator != null) return
            try {
                val t = Translation.getClient(TranslatorOptions.Builder().setSourceLanguage(TranslateLanguage.ENGLISH).setTargetLanguage(TranslateLanguage.ARABIC).build())
                t.downloadModelIfNeeded(DownloadConditions.Builder().build()).addOnSuccessListener { translator = t }
            } catch (e: Throwable) {}
        }
    }
}
