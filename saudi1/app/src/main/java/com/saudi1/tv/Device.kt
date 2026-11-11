package com.saudi1.tv

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

/** Activation through the owner's admin site: the TV shows its code, the owner adds the login there,
 *  Reload picks it up. A login typed by hand on the TV (Settings) is kept as it is. */
object Device {
    const val SITE = "https://saudi1.1saifsaudi.workers.dev"
    private const val API = "$SITE/api/device"

    val code: String
        get() {
            var c = App.prefs.getString("device_code", "") ?: ""
            if (c.length != 8) {
                val r = java.security.SecureRandom()
                c = (1..8).map { if (it == 1) 1 + r.nextInt(9) else r.nextInt(10) }.joinToString("")
                App.prefs.edit().putString("device_code", c).apply()
            }
            return c
        }

    val pretty get() = code.substring(0, 4) + " " + code.substring(4)

    var manual: Boolean
        // closed (owner, 11 Nov 2026): no TV keeps working on a login typed into it; only the admin page opens a device
        get() = false
        set(v) = App.prefs.edit().putBoolean("manual_login", v).apply()

    var name: String
        get() = App.prefs.getString("customer", "") ?: ""
        private set(v) = App.prefs.edit().putString("customer", v).apply()

    var expires: Long
        get() = App.prefs.getLong("expires", 0)
        private set(v) = App.prefs.edit().putLong("expires", v).apply()

    var active: String
        get() = App.prefs.getString("active_pl", "") ?: ""
        set(v) = App.prefs.edit().putString("active_pl", v).apply()

    /** the playlists this device may use (from the admin site): name, server, user, pass */
    fun playlists(): List<JSONObject> = try {
        val a = org.json.JSONArray(App.prefs.getString("playlists", "[]")); (0 until a.length()).map { a.getJSONObject(it) }
    } catch (e: Exception) { emptyList() }

    /** switch to another of this device's playlists */
    fun use(p: JSONObject) {
        active = p.optString("name")
        Prefs.server = p.optString("server"); Prefs.user = p.optString("user"); Prefs.pass = p.optString("pass")
        Api.groups = emptyList()
        java.io.File(App.app.filesDir, "live_categories.json").delete(); java.io.File(App.app.filesDir, "live_streams.json").delete()
        Vod.clear()
    }

    // ---- what this device is watching: the owner sees it on the admin site (playlist + channel / movie / episode) ----
    private var lastNow = ""; private var lastNowAt = 0L
    fun now(kind: String, title: String) {
        val pl = active.ifEmpty { Prefs.playlist }
        val sig = "$kind|$title|$pl"; val t = System.currentTimeMillis()
        if (sig == lastNow && t - lastNowAt < 100_000) return   // the same thing: said again every 100 s, so "now" stays true
        lastNow = sig; lastNowAt = t
        val body = JSONObject().put("code", code).put("playlist", pl).put("kind", kind).put("title", title.take(140)).toString()
        Thread {
            try { App.http.newCall(Request.Builder().url(SITE + "/api/now").post(body.toRequestBody("application/json".toMediaType())).build()).execute().close() } catch (e: Exception) { }
        }.start()
    }

    /** payment for access, when the owner turned it on: {price, url}; else null (blocking) */
    fun payInfo(): JSONObject? = try {
        App.http.newCall(Request.Builder().url("$SITE/api/pay?code=$code").build()).execute().use { r ->
            val o = JSONObject(r.body!!.string()); if (r.isSuccessful && o.optBoolean("on") && o.optString("url").isNotEmpty()) o else null
        }
    } catch (e: Exception) { null }

    /** spends a promo code on this device. "" = accepted, else what to tell the viewer (blocking) */
    fun promo(p: String): String = try {
        val body = JSONObject().put("code", code).put("promo", p.trim()).toString()
        App.http.newCall(Request.Builder().url(SITE + "/api/promo").post(body.toRequestBody("application/json".toMediaType())).build()).execute().use { r ->
            val o = try { JSONObject(r.body!!.string()) } catch (e: Exception) { JSONObject() }
            if (r.isSuccessful && o.optBoolean("ok")) { App.prefs.edit().putBoolean("promo_ok", true).apply(); "" }
            else o.optString("error").ifEmpty { "Could not check the code. Try again." }
        }
    } catch (e: Exception) { "No internet connection" }

    /** "active" | "pending" | "stopped" | "expired" | "offline" */
    /** the zone of the place the internet is in (ipwho.is, free, no key), asked at most every 3 hours */
    private fun netZone(): String? {
        val now = System.currentTimeMillis()
        if (now - App.prefs.getLong("net_tz_at", 0) < 3 * 3600_000L) return App.prefs.getString("net_tz", null)
        return try {
            App.http.newCall(okhttp3.Request.Builder().url("https://ipwho.is/?fields=timezone").build()).execute().use { r ->
                val id = org.json.JSONObject(r.body!!.string()).optJSONObject("timezone")?.optString("id").orEmpty()
                App.prefs.edit().putLong("net_tz_at", now).apply()
                id.takeIf { it.contains('/') }
            }
        } catch (e: Exception) { null }
    }

    fun check(): String = try {
        val u = "$API?code=$code&model=" + java.net.URLEncoder.encode(android.os.Build.MODEL, "UTF-8")
        App.http.newCall(Request.Builder().url(u).build()).execute().use { r ->
            val o = JSONObject(r.body!!.string())
            val st = o.optString("status")
            if (st == "active") {
                // the playlists the owner gave this device; the one picked on the Playlists screen stays picked
                val arr = o.optJSONArray("playlists")
                val lists = if (arr != null && arr.length() > 0) (0 until arr.length()).map { arr.getJSONObject(it) }
                    else listOf(JSONObject().put("name", "").put("server", o.optString("server")).put("user", o.optString("user")).put("pass", o.optString("pass")))
                App.prefs.edit().putString("playlists", org.json.JSONArray(lists).toString()).apply()
                val pick = lists.firstOrNull { it.optString("name") == active } ?: lists[0]
                val changed = Prefs.server != pick.optString("server") || Prefs.user != pick.optString("user") || Prefs.pass != pick.optString("pass")
                Prefs.server = pick.optString("server"); Prefs.user = pick.optString("user"); Prefs.pass = pick.optString("pass")
                active = pick.optString("name")
                name = o.optString("name"); expires = o.optLong("expires")
                // the time zone of the place the device is in now (a Chromecast on Wi-Fi does not find it by itself):
                // the guide, the matches, the clock in the app follow it (owner, 11 Nov 2026: a pilot's TV)
                (o.optString("tz").takeIf { it.contains('/') } ?: netZone())?.let { tz ->
                    if (App.prefs.getString("net_tz", "") != tz) App.prefs.edit().putString("net_tz", tz).apply()
                    App.useZone(tz)
                }
                // the VPN the owner put on the admin site (an empty one there keeps a file imported on the phone)
                o.optString("vpn").takeIf { it.isNotBlank() }?.let { if (it != Vpn.conf) { Vpn.conf = it; Vpn.wanted = true } }
                manual = false
                if (changed) Api.groups = emptyList()
            } else if (!manual && (st == "stopped" || st == "expired")) {
                Prefs.pass = ""  // the owner stopped this device: no more channels until he turns it on again
                Api.groups = emptyList()
            }
            st
        }
    } catch (e: Exception) { "offline" }
}
