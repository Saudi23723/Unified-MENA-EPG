package com.saudi1.tv

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject

/** The viewer's own things (favorites, continue watching, reminders, sort, night mode, locks...) kept safe with the
 *  device code on the owner's site: small text only, once a day by itself, and by hand from Settings.
 *  Logins, the VPN file and downloads are never part of it. */
object Backup {
    private val skip = setOf("server", "user", "pass", "playlists", "device_code", "customer", "expires", "active_pl", "vpn_conf", "vpn_on",
        "tidy_at", "manual_login", "backup_at", "downloads", "hls_ids", "warm_v2")
    private fun kept(k: String) = k !in skip && !k.startsWith("vod_warm_")

    var at: Long
        get() = App.prefs.getLong("backup_at", 0)
        private set(v) = App.prefs.edit().putLong("backup_at", v).apply()

    private fun dump(): JSONObject {
        val o = JSONObject()
        for ((k, v) in App.prefs.all) {
            if (!kept(k) || v == null) continue
            when (v) {
                is String -> o.put(k, JSONObject().put("t", "s").put("v", v))
                is Int -> o.put(k, JSONObject().put("t", "i").put("v", v))
                is Long -> o.put(k, JSONObject().put("t", "l").put("v", v))
                is Boolean -> o.put(k, JSONObject().put("t", "b").put("v", v))
                is Float -> o.put(k, JSONObject().put("t", "f").put("v", v.toDouble()))
                is Set<*> -> o.put(k, JSONObject().put("t", "ss").put("v", JSONArray(v.map { it.toString() })))
            }
        }
        return o
    }

    /** blocking: call off the main thread. true = saved */
    fun save(): Boolean = try {
        val body = JSONObject().put("code", Device.code).put("data", dump().toString()).toString()
        App.http.newCall(Request.Builder().url(Device.SITE + "/api/backup").post(body.toRequestBody("application/json".toMediaType())).build()).execute().use { r ->
            if (r.isSuccessful) at = System.currentTimeMillis()
            r.isSuccessful
        }
    } catch (e: Exception) { false }

    /** blocking. null = nothing saved for this device / no connection; else the time of the backup that was put back */
    fun restore(): Long? = try {
        App.http.newCall(Request.Builder().url(Device.SITE + "/api/backup?code=" + Device.code).build()).execute().use { r ->
            if (!r.isSuccessful) return@use null
            val o = JSONObject(r.body!!.string())
            val data = o.optString("data"); if (data.isEmpty()) return@use null
            val d = JSONObject(data); val e = App.prefs.edit()
            for (k in d.keys()) {
                if (!kept(k)) continue
                val x = d.getJSONObject(k)
                when (x.optString("t")) {
                    "s" -> e.putString(k, x.optString("v"))
                    "i" -> e.putInt(k, x.optInt("v"))
                    "l" -> e.putLong(k, x.optLong("v"))
                    "b" -> e.putBoolean(k, x.optBoolean("v"))
                    "f" -> e.putFloat(k, x.optDouble("v").toFloat())
                    "ss" -> { val a = x.optJSONArray("v") ?: JSONArray(); e.putStringSet(k, (0 until a.length()).map { a.getString(it) }.toHashSet()) }
                }
            }
            e.commit()
            o.optLong("t")
        }
    } catch (e: Exception) { null }

    /** once a day, by itself */
    fun auto() {
        if (!Prefs.ready || System.currentTimeMillis() - at < 24 * 3600_000L) return
        Thread { save() }.start()
    }
}
