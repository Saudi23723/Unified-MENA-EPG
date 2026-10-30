package com.saudi.privatevault

import android.content.Context
import android.os.SystemClock
import android.speech.tts.TextToSpeech
import java.util.Locale

/**
 * Spoken callouts, in English as cockpit callouts are: terrain, airspace,
 * the next waypoint, a runway underneath. Each one is said once and then
 * kept quiet for a while, so the voice never nags.
 */
object Voice {
    private var tts: TextToSpeech? = null
    private var ready = false
    private val last = HashMap<String, Long>()

    fun init(ctx: Context) {
        if (tts != null) return
        tts = TextToSpeech(ctx.applicationContext) { status ->
            ready = status == TextToSpeech.SUCCESS
            if (ready) tts?.language = Locale.US
        }
    }

    fun enabled(ctx: Context) = VaultLock.prefs(ctx).getBoolean("voice_on", true)

    /** Says it, unless the same callout was said within [quietSec]. */
    fun say(ctx: Context, key: String, text: String, quietSec: Int = 60) {
        if (!ready || !enabled(ctx)) return
        val now = SystemClock.elapsedRealtime()
        if (now - (last[key] ?: -1_000_000L) < quietSec * 1000L) return
        last[key] = now
        tts?.speak(text, TextToSpeech.QUEUE_ADD, null, key)
    }
}
