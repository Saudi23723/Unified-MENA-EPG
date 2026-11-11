package com.saudi.privatevault

import android.content.Context
import android.os.Handler
import android.os.Looper
import androidx.media3.common.MediaItem
import androidx.media3.exoplayer.ExoPlayer

/**
 * Live air traffic control, played right in the app: LiveATC's public feeds, found from the
 * airport's code and opened from the playlist LiveATC offers for any audio player. It keeps
 * playing while the pilot moves between screens (map, notes, checklist), until stopped.
 */
object RadioPlayer {
    class Feed(val mount: String, val name: String)

    private var player: ExoPlayer? = null
    @Volatile var playing: Feed? = null
        private set
    var onChange: (() -> Unit)? = null

    private val NAMES = mapOf("twr" to "Tower", "gnd" to "Ground", "app" to "Approach", "dep" to "Departure", "del" to "Clearance",
        "ctaf" to "CTAF", "atis" to "ATIS", "ctr" to "Center", "ramp" to "Ramp", "zla" to "LA Center", "zlc" to "Salt Lake Center")

    private fun nameOf(mount: String): String {
        val parts = mount.lowercase().split('_')
        val apt = parts.first().uppercase()
        val rest = parts.drop(1).joinToString(" ") { p -> NAMES[p] ?: NAMES.entries.firstOrNull { p.startsWith(it.key) }?.value ?: p.uppercase() }
        return if (rest.isEmpty()) apt else "$apt $rest"
    }

    /** The feeds LiveATC has for an airport (off the main thread); empty when it has none. */
    fun feeds(icao: String): List<Feed> {
        val html = try { AviationData.get("https://www.liveatc.net/search/?icao=" + icao.lowercase(), 12000) } catch (e: Exception) { return emptyList() }
        val mounts = Regex("mount=([a-z0-9_]+)", RegexOption.IGNORE_CASE).findAll(html).map { it.groupValues[1].lowercase() }.distinct().toList()
        // The name LiveATC shows for each feed, when it can be read; else one made from the mount.
        return mounts.map { m ->
            val shown = Regex("<strong>([^<]{3,60})</strong>[\\s\\S]{0,1500}?mount=$m", RegexOption.IGNORE_CASE).find(html)?.groupValues?.get(1)?.trim()
            Feed(m, shown?.takeIf { it.isNotBlank() } ?: nameOf(m))
        }
    }

    /** The stream behind a feed, from LiveATC's playlist for audio players. */
    private fun streamOf(mount: String): String? = try {
        val pls = AviationData.get("https://www.liveatc.net/play/$mount.pls", 10000)
        Regex("File\\d+=(\\S+)").find(pls)?.groupValues?.get(1)
    } catch (e: Exception) { null }

    /** Plays a feed; [done] says whether it started. */
    fun play(ctx: Context, feed: Feed, done: (Boolean) -> Unit) {
        val app = ctx.applicationContext
        Thread {
            val url = streamOf(feed.mount)
            Handler(Looper.getMainLooper()).post {
                if (url == null) { done(false); return@post }
                stop()
                val p = ExoPlayer.Builder(app).build()
                p.setMediaItem(MediaItem.fromUri(url))
                p.prepare(); p.playWhenReady = true
                player = p
                playing = feed
                onChange?.invoke()
                done(true)
            }
        }.start()
    }

    /** From anywhere (the map's 🎧): pick a field, then its feed; it plays at once, no pages in between. */
    fun choose(act: android.app.Activity) {
        val home = VaultLock.prefs(act).getString("efb_home", "KBVU") ?: "KBVU"
        val fields = listOf(home, "KLAS", "KHND", "KVGT").distinct()
        val items = (if (playing != null) listOf("■  " + act.getString(R.string.atc_stop) + " · " + playing!!.name) else emptyList()) + fields.map { "🎧  $it" }
        com.google.android.material.dialog.MaterialAlertDialogBuilder(act).setTitle(R.string.atc_title)
            .setItems(items.toTypedArray()) { _, i ->
                if (playing != null && i == 0) { stop(); return@setItems }
                val icao = fields[i - if (playing != null) 1 else 0]
                android.widget.Toast.makeText(act, "🎧 $icao…", android.widget.Toast.LENGTH_SHORT).show()
                Thread {
                    val list = feeds(icao)
                    act.runOnUiThread {
                        if (list.isEmpty()) {
                            com.google.android.material.dialog.MaterialAlertDialogBuilder(act).setTitle("🎧 $icao")
                                .setMessage(act.getString(R.string.atc_none, icao)).setPositiveButton(android.R.string.ok, null).show()
                        } else com.google.android.material.dialog.MaterialAlertDialogBuilder(act).setTitle("🎧 $icao")
                            .setItems(list.map { it.name }.toTypedArray()) { _, k ->
                                play(act, list[k]) { ok -> android.widget.Toast.makeText(act, if (ok) "▶ " + list[k].name else act.getString(R.string.atc_fail), android.widget.Toast.LENGTH_SHORT).show() }
                            }.show()
                    }
                }.start()
            }.show()
    }

    fun stop() {
        player?.release(); player = null
        playing = null
        onChange?.invoke()
    }
}
