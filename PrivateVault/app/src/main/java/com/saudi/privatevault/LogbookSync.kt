package com.saudi.privatevault

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * The logbook the same on every device linked to the vault (the cloud):
 * each flight, endorsement and signature travels on its own with the time
 * it last changed, the newer copy wins, and a deletion travels too. The
 * vault merges it like a document's notes, one entry per "page".
 */
object LogbookSync {
    private const val NAME = "logbook"

    /** What the last sync did, for the pilot: sent, taken, or why it could not. */
    @Volatile var lastSent = 0
    @Volatile var lastError: String? = null

    private fun stampsFile(ctx: Context) = File(ctx.filesDir, "logbook_stamps.json")

    /** key ("f:id", "e:id") → [time, deleted?]. */
    private fun stamps(ctx: Context): JSONObject = try { JSONObject(stampsFile(ctx).readText()) } catch (e: Exception) { JSONObject() }

    private fun saveStamps(ctx: Context, o: JSONObject) = stampsFile(ctx).writeText(o.toString())

    /** Called on every save: what changed or went since the last save gets the time now. */
    @Synchronized
    fun noteChange(ctx: Context, prefix: String, before: Map<String, String>, after: Map<String, String>) {
        val now = System.currentTimeMillis()
        val st = stamps(ctx)
        for ((id, json) in after) if (before[id] != json) st.put("$prefix:$id", JSONArray().put(now).put(false))
        for (id in before.keys - after.keys) st.put("$prefix:$id", JSONArray().put(now).put(true))
        saveStamps(ctx, st)
    }

    private fun time(st: JSONObject, key: String, fallback: Long) = st.optJSONArray(key)?.optLong(0) ?: fallback

    /** Sends what this device has and takes what is newer elsewhere; the number of entries taken. Off the main thread. */
    @Synchronized
    fun sync(ctx: Context): Int {
        if (!LaptopClient.isLinked(ctx)) { lastError = "not linked"; return -1 }
        val st = stamps(ctx)
        val pages = JSONObject()
        val t = JSONObject()
        val flights = Logbook.all(ctx)
        for (e in flights) {
            val k = "f:${e.id}"
            pages.put(k, JSONArray().put(e.toJson())); t.put(k, time(st, k, e.updated))
        }
        val ends = Logbook.endorsements(ctx)
        for (e in ends) {
            val k = "e:${e.id}"
            pages.put(k, JSONArray().put(e.toJson())); t.put(k, time(st, k, 1L))
        }
        val ground = Logbook.ground(ctx)
        for (g in ground) {
            val k = "g:${g.id}"
            pages.put(k, JSONArray().put(g.toJson())); t.put(k, time(st, k, 1L))
        }
        PilotDocs.all(ctx).let { d -> if (d.length() > 0) { pages.put("d:docs", JSONArray().put(d)); t.put("d:docs", d.optLong("_t", 1L)) } }
        // Deleted here: an empty entry with the time of the deletion.
        for (k in st.keys()) {
            val a = st.getJSONArray(k)
            if (a.optBoolean(1)) { pages.put(k, JSONArray()); t.put(k, a.optLong(0)) }
        }
        val sigs = Logbook.signatures(ctx)
        sigs.listFiles()?.forEach { f ->
            val k = "s:${f.name}"
            pages.put(k, JSONArray().put(android.util.Base64.encodeToString(f.readBytes(), android.util.Base64.NO_WRAP))); t.put(k, f.lastModified())
        }
        lastSent = pages.length()
        val merged = LaptopClient.syncKv(ctx, NAME, JSONObject().put("v", 2).put("pages", pages).put("t", t).toString())
        if (merged == null) { lastError = "vault unreachable"; return -1 }
        lastError = null

        // Take what is newer on the vault.
        val rp = merged.optJSONObject("pages") ?: return 0
        val rt = merged.optJSONObject("t") ?: JSONObject()
        val fl = flights.associateBy { it.id }.toMutableMap()
        val en = ends.associateBy { it.id }.toMutableMap()
        var taken = 0
        var flightsChanged = false
        var endsChanged = false
        val gr = ground.associateBy { it.id }.toMutableMap()
        var groundChanged = false
        for (k in rp.keys()) {
            val remoteT = rt.optLong(k, 0)
            val localT = t.optLong(k, -1)
            if (remoteT <= localT) continue
            val v = rp.optJSONArray(k) ?: continue
            val id = k.substringAfter(':')
            when {
                k.startsWith("f:") -> {
                    if (v.length() == 0) { if (fl.remove(id) != null) flightsChanged = true }
                    else { fl[id] = LogEntry.fromJson(v.getJSONObject(0)); flightsChanged = true }
                    st.put(k, JSONArray().put(remoteT).put(v.length() == 0)); taken++
                }
                k.startsWith("e:") -> {
                    if (v.length() == 0) { if (en.remove(id) != null) endsChanged = true }
                    else { en[id] = Endorsement.fromJson(v.getJSONObject(0)); endsChanged = true }
                    st.put(k, JSONArray().put(remoteT).put(v.length() == 0)); taken++
                }
                k.startsWith("g:") -> {
                    if (v.length() == 0) { if (gr.remove(id) != null) groundChanged = true }
                    else { gr[id] = GroundLesson.fromJson(v.getJSONObject(0)); groundChanged = true }
                    st.put(k, JSONArray().put(remoteT).put(v.length() == 0)); taken++
                }
                k == "d:docs" && v.length() > 0 -> { PilotDocs.replace(ctx, v.getJSONObject(0)); taken++ }
                k.startsWith("s:") && v.length() > 0 -> {
                    val f = File(sigs, id.replace(Regex("[^A-Za-z0-9_.-]"), ""))
                    f.writeBytes(android.util.Base64.decode(v.getString(0), android.util.Base64.DEFAULT))
                    f.setLastModified(remoteT)
                    taken++
                }
            }
        }
        // Written without stamping them again: they carry the vault's times.
        if (flightsChanged) Logbook.save(ctx, fl.values.toList(), stamp = false)
        if (endsChanged) Logbook.saveEndorsements(ctx, en.values.toList(), stamp = false)
        if (groundChanged) Logbook.saveGround(ctx, gr.values.toList(), stamp = false)
        saveStamps(ctx, st)
        VaultLock.prefs(ctx).edit().putLong("logbook_synced", System.currentTimeMillis()).apply()
        return taken
    }

    /** In the background after a change, when linked. */
    fun soon(ctx: Context) {
        if (!LaptopClient.isLinked(ctx)) return
        val app = ctx.applicationContext
        Thread { try { sync(app) } catch (e: Exception) {} }.start()
    }
}
