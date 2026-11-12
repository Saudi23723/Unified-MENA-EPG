package com.saudi.privatevault

import android.content.Context
import android.content.Intent
import android.location.Location
import org.json.JSONObject

/**
 * The flight followed live from the ground: a private link (the cloud vault's /track page) for the
 * instructor or the family, the aircraft on a sectional with its altitude, speed, track and the path
 * flown, updated every ten seconds while tracking is on — also in the background, with the GPS service.
 */
object LiveTrack {
    private const val ON = "track_on"
    private const val LINK = "track_link"
    @Volatile private var lastSent = 0L
    @Volatile private var sending = false

    fun on(ctx: Context) = VaultLock.prefs(ctx).getBoolean(ON, false)
    fun link(ctx: Context): String? = VaultLock.prefs(ctx).getString(LINK, null)

    /** Starts: the first position makes the link (off the main thread); null with the reason when it cannot. */
    fun start(ctx: Context, where: Location?, name: String): String? {
        val body = JSONObject().put("name", name)
        where?.let { body.put("p", point(it)) }
        val link = LaptopClient.trackPost(ctx, body) ?: return null
        VaultLock.prefs(ctx).edit().putBoolean(ON, true).putString(LINK, link).apply()
        return link
    }

    fun stop(ctx: Context) {
        val link = link(ctx)
        VaultLock.prefs(ctx).edit().putBoolean(ON, false).apply()
        if (link != null) Thread { try { LaptopClient.trackPost(ctx, JSONObject().put("token", link.substringAfterLast('/')).put("ended", true)) } catch (e: Exception) {} }.start()
    }

    private fun point(l: Location) = org.json.JSONArray().put(l.latitude).put(l.longitude)
        .put(if (l.hasAltitude()) l.altitude * 3.28084 else 0.0).put(if (l.hasSpeed()) l.speed * 1.943844 else 0.0).put(if (l.hasBearing()) l.bearing.toDouble() else 0.0)

    /** Each GPS fix: one position every 10 s while tracking is on. */
    fun onFix(ctx: Context, l: Location) {
        if (!on(ctx) || sending) return
        val now = System.currentTimeMillis()
        if (now - lastSent < 10_000) return
        val link = link(ctx) ?: return
        lastSent = now; sending = true
        val app = ctx.applicationContext
        Thread {
            try { LaptopClient.trackPost(app, JSONObject().put("token", link.substringAfterLast('/')).put("p", point(l))) } catch (e: Exception) {}
            sending = false
        }.start()
    }

    fun share(ctx: Context, link: String) {
        ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, "✈ Follow my flight live: $link")
        }, "Share live tracking"))
    }
}
