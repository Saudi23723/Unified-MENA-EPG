package com.saudi.privatevault

import android.content.Context
import android.net.Uri
import android.os.Handler
import android.os.Looper
import androidx.annotation.OptIn
import androidx.media3.common.MediaItem
import androidx.media3.common.MimeTypes
import androidx.media3.common.util.UnstableApi
import androidx.media3.transformer.Composition
import androidx.media3.transformer.EditedMediaItem
import androidx.media3.transformer.ExportException
import androidx.media3.transformer.ExportResult
import androidx.media3.transformer.Transformer
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * Closed captions made by the app for any video: its sound is taken out (AAC), Gemini writes it down
 * as timed captions (SRT), then into Arabic with the aviation terms kept; kept on the device, so each
 * video is done once. English, Arabic, or both lines together.
 */
object Captions {
    private val busy = HashSet<String>()

    private fun safe(id: String) = id.replace(Regex("[^A-Za-z0-9_-]"), "_")
    fun file(ctx: Context, id: String, lang: String) = File(File(ctx.filesDir, "cc").apply { mkdirs() }, "${safe(id)}.$lang.srt")

    /** The captions to show for this video in the chosen language ("ar", "en", "both"), if made. */
    fun ready(ctx: Context, id: String): File? {
        val lang = VaultLock.prefs(ctx).getString("cc_lang", "both") ?: "both"
        val f = file(ctx, id, lang)
        if (f.exists() && f.length() > 0) return f
        if (lang == "both") {
            val en = file(ctx, id, "en"); val ar = file(ctx, id, "ar")
            if (en.exists() && ar.exists()) { f.writeText(merge(en.readText(), ar.readText())); return f }
        }
        return null
    }

    /** Makes the captions (off the main thread); [status] reports each step. True when ready. */
    @OptIn(UnstableApi::class)
    fun make(ctx: Context, id: String, source: Uri, status: (String) -> Unit): Boolean {
        synchronized(busy) { if (!busy.add(id)) return false }
        try {
            val key = Gemini.key(ctx)
            if (key.isEmpty()) return false
            if (!file(ctx, id, "en").exists()) {
                status("🎧 CC · 1/3")
                val audio = audioOf(ctx, source) ?: return false
                try {
                    status("☁ CC · 2/3")
                    val uri = upload(key, audio) ?: return false
                    status("✍ CC · 3/3")
                    val srt = ask(key, listOf(JSONObject().put("file_data", JSONObject().put("mime_type", "audio/mp4").put("file_uri", uri)),
                        JSONObject().put("text", TRANSCRIBE))) ?: return false
                    file(ctx, id, "en").writeText(clean(srt))
                } finally { audio.delete() }
            }
            if (!file(ctx, id, "ar").exists()) {
                status("🌐 CC · العربي")
                val ar = ask(key, listOf(JSONObject().put("text", TRANSLATE + "\n\n" + file(ctx, id, "en").readText()))) ?: return false
                file(ctx, id, "ar").writeText(clean(ar))
            }
            return ready(ctx, id) != null
        } catch (e: Exception) {
            return false
        } finally { synchronized(busy) { busy.remove(id) } }
    }

    private const val TRANSCRIBE = "Transcribe this audio as SubRip (SRT) closed captions in the language spoken. " +
        "Exact timestamps HH:MM:SS,mmm measured from the start of the audio, cues of 1 to 6 seconds, at most 2 lines of " +
        "42 characters each, numbered from 1. Write aviation terms, call signs, numbers and frequencies exactly as said. " +
        "Mark long music or silence with no cue. Output only the SRT, nothing else."
    private const val TRANSLATE = "Translate these SRT captions into clear Modern Standard Arabic for a student pilot. Keep every " +
        "cue number and timestamp exactly as it is; translate only the text lines. Keep call signs, frequencies, numbers, " +
        "abbreviations and aviation terms in English (e.g. ATC, VOR, flaps) inside the Arabic sentence. Output only the SRT."

    /** The video's sound as AAC in a temporary file, from the phone or streamed from the vault. */
    @OptIn(UnstableApi::class)
    private fun audioOf(ctx: Context, source: Uri): File? {
        val out = File(File(ctx.cacheDir, "cc").apply { mkdirs() }, "a${System.currentTimeMillis()}.m4a")
        val done = CountDownLatch(1)
        var ok = false
        val main = Handler(Looper.getMainLooper())
        var t: Transformer? = null
        main.post {
            try {
                t = Transformer.Builder(ctx).setAudioMimeType(MimeTypes.AUDIO_AAC)
                    .addListener(object : Transformer.Listener {
                        override fun onCompleted(composition: Composition, result: ExportResult) { ok = true; done.countDown() }
                        override fun onError(composition: Composition, result: ExportResult, exception: ExportException) { done.countDown() }
                    }).build()
                t!!.start(EditedMediaItem.Builder(MediaItem.fromUri(source)).setRemoveVideo(true).build(), out.path)
            } catch (e: Exception) { done.countDown() }
        }
        if (!done.await(2, TimeUnit.HOURS)) main.post { try { t?.cancel() } catch (e: Exception) {} }
        return if (ok && out.length() > 0) out else { out.delete(); null }
    }

    /** Sends the sound to Gemini's file store; its uri once it is ready to read. */
    private fun upload(key: String, f: File): String? {
        val start = URL("https://generativelanguage.googleapis.com/upload/v1beta/files").openConnection() as HttpURLConnection
        val at = try {
            start.requestMethod = "POST"; start.doOutput = true
            start.setRequestProperty("x-goog-api-key", key)
            start.setRequestProperty("X-Goog-Upload-Protocol", "resumable")
            start.setRequestProperty("X-Goog-Upload-Command", "start")
            start.setRequestProperty("X-Goog-Upload-Header-Content-Length", f.length().toString())
            start.setRequestProperty("X-Goog-Upload-Header-Content-Type", "audio/mp4")
            start.setRequestProperty("Content-Type", "application/json")
            start.outputStream.use { it.write(JSONObject().put("file", JSONObject().put("display_name", "captions")).toString().toByteArray()) }
            if (start.responseCode != 200) return null
            start.getHeaderField("x-goog-upload-url") ?: return null
        } finally { start.disconnect() }
        val up = URL(at).openConnection() as HttpURLConnection
        val info = try {
            up.requestMethod = "POST"; up.doOutput = true
            up.setFixedLengthStreamingMode(f.length())
            up.setRequestProperty("X-Goog-Upload-Offset", "0")
            up.setRequestProperty("X-Goog-Upload-Command", "upload, finalize")
            up.outputStream.use { o -> f.inputStream().use { it.copyTo(o, 256 * 1024) } }
            if (up.responseCode != 200) return null
            JSONObject(up.inputStream.bufferedReader().readText()).optJSONObject("file") ?: return null
        } finally { up.disconnect() }
        val name = info.optString("name"); var state = info.optString("state"); val uri = info.optString("uri")
        var tries = 0
        while (state == "PROCESSING" && tries++ < 120) {
            Thread.sleep(2000)
            val g = URL("https://generativelanguage.googleapis.com/v1beta/$name").openConnection() as HttpURLConnection
            try {
                g.setRequestProperty("x-goog-api-key", key)
                if (g.responseCode == 200) state = JSONObject(g.inputStream.bufferedReader().readText()).optString("state")
            } finally { g.disconnect() }
        }
        return uri.takeIf { state == "ACTIVE" || state.isEmpty() }
    }

    /** One request to Gemini; the text of its answer. */
    private fun ask(key: String, parts: List<JSONObject>): String? {
        for (model in listOf("gemini-2.5-flash", "gemini-flash-latest")) {
            val c = URL("https://generativelanguage.googleapis.com/v1beta/models/$model:generateContent").openConnection() as HttpURLConnection
            try {
                c.requestMethod = "POST"; c.doOutput = true; c.readTimeout = 600000; c.connectTimeout = 15000
                c.setRequestProperty("x-goog-api-key", key)
                c.setRequestProperty("Content-Type", "application/json")
                val body = JSONObject().put("contents", JSONArray().put(JSONObject().put("role", "user").put("parts", JSONArray(parts))))
                    .put("generationConfig", JSONObject().put("temperature", 0.1).put("maxOutputTokens", 65536))
                c.outputStream.use { it.write(body.toString().toByteArray()) }
                if (c.responseCode != 200) continue
                val o = JSONObject(c.inputStream.bufferedReader().readText())
                val ps = o.optJSONArray("candidates")?.optJSONObject(0)?.optJSONObject("content")?.optJSONArray("parts") ?: continue
                val sb = StringBuilder()
                for (i in 0 until ps.length()) sb.append(ps.getJSONObject(i).optString("text"))
                if (sb.contains("-->")) return sb.toString()
            } catch (e: Exception) {
            } finally { c.disconnect() }
        }
        return null
    }

    /** Only the SRT: code fences and words around it dropped, numbering made whole. */
    private fun clean(s: String): String {
        val t = s.replace("```srt", "").replace("```", "").trim()
        val from = Regex("(?m)^\\s*\\d+\\s*\\n\\s*\\d{2}:\\d{2}:\\d{2}[,.]\\d{3}").find(t)?.range?.first ?: 0
        return t.substring(from).replace(Regex("(\\d{2}:\\d{2}:\\d{2})\\.(\\d{3})"), "$1,$2").trim() + "\n"
    }

    private class Cue(val time: String, val text: String)

    private fun parse(s: String): List<Cue> = s.replace("\r", "").split(Regex("\\n\\s*\\n")).mapNotNull { b ->
        val lines = b.trim().lines()
        val ti = lines.indexOfFirst { it.contains("-->") }
        if (ti < 0) null else Cue(lines[ti].trim(), lines.drop(ti + 1).joinToString("\n").trim())
    }

    /** English above, Arabic under it, cue by cue. */
    private fun merge(en: String, ar: String): String {
        val a = parse(en); val b = parse(ar).associateBy { it.time }
        return a.mapIndexed { i, c -> "${i + 1}\n${c.time}\n${c.text}" + (b[c.time]?.text?.let { "\n$it" } ?: "") }.joinToString("\n\n") + "\n"
    }
}
