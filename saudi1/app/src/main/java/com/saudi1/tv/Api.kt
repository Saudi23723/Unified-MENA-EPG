package com.saudi1.tv

import android.util.Base64
import android.util.JsonReader
import android.util.JsonToken
import okhttp3.Request
import org.json.JSONObject
import java.io.File
import java.io.InputStream
import java.io.InputStreamReader
import java.util.concurrent.ConcurrentHashMap

class Group(val id: String, val name: String, val channels: MutableList<Channel> = ArrayList()) {
    override fun toString() = name
}

class Channel(
    val id: Int, val num: Int, val name: String, val logo: String, val epgId: String, val group: String,
)

class Program(val start: Long, val stop: Long, val title: String, val desc: String) {
    fun now(t: Long = System.currentTimeMillis() / 1000) = t in start until stop
}

/** Xtream player_api through the owner's relays, plus the repo's guide files read straight from GitHub. */
object Api {
    const val FAV = "__fav"
    const val ALL = "__all"
    private const val DATA = "https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/xtream-data/"

    @Volatile var groups: List<Group> = emptyList()
    @Volatile var byId: Map<Int, Channel> = emptyMap()

    private fun url(action: String, extra: String = "") =
        "${Prefs.server}/player_api.php?username=${enc(Prefs.user)}&password=${enc(Prefs.pass)}" +
            (if (action.isEmpty()) "" else "&action=$action") + extra

    private fun enc(s: String) = java.net.URLEncoder.encode(s, "UTF-8")

    fun streamUrl(c: Channel) = "${Prefs.server}/live/${enc(Prefs.user)}/${enc(Prefs.pass)}/${c.id}.ts"

    private fun get(u: String): okhttp3.Response {
        val r = App.http.newCall(Request.Builder().url(u).build()).execute()
        if (!r.isSuccessful) { r.close(); throw java.io.IOException("HTTP ${r.code}") }
        return r
    }

    /** true when the login works */
    fun login(): Boolean = get(url("")).use { r ->
        val o = JSONObject(r.body!!.string())
        o.optJSONObject("user_info")?.optInt("auth", 0) == 1
    }

    private fun cache(name: String) = File(App.app.filesDir, name)

    /** Load the lists: from the copy on the TV when [cached] (instant start), else from the server (and save it). */
    fun load(cached: Boolean): Boolean {
        val cf = cache("live_categories.json"); val sf = cache("live_streams.json")
        if (cached) {
            if (!cf.exists() || !sf.exists()) return false
            build(cf.inputStream(), sf.inputStream())
            return true
        }
        val c = get(url("get_live_categories")).use { it.body!!.bytes() }
        val tmp = cache("live_streams.tmp")
        get(url("get_live_streams")).use { r -> tmp.outputStream().use { o -> r.body!!.byteStream().copyTo(o) } }
        build(c.inputStream(), tmp.inputStream())
        cf.writeBytes(c); tmp.renameTo(sf)
        return true
    }

    private fun build(cats: InputStream, streams: InputStream) {
        val order = ArrayList<Group>(); val map = HashMap<String, Group>()
        JsonReader(InputStreamReader(cats, Charsets.UTF_8)).use { j ->
            j.beginArray()
            while (j.hasNext()) {
                var id = ""; var name = ""
                j.beginObject()
                while (j.hasNext()) when (j.nextName()) {
                    "category_id" -> id = str(j)
                    "category_name" -> name = str(j)
                    else -> j.skipValue()
                }
                j.endObject()
                if (id.isNotEmpty() && id !in map) { val g = Group(id, name.trim()); map[id] = g; order.add(g) }
            }
            j.endArray()
        }
        val all = ArrayList<Channel>(8000); val ids = HashMap<Int, Channel>(8000)
        JsonReader(InputStreamReader(streams, Charsets.UTF_8)).use { j ->
            j.beginArray()
            while (j.hasNext()) {
                var id = 0; var num = 0; var name = ""; var logo = ""; var epg = ""; var cat = ""
                j.beginObject()
                while (j.hasNext()) when (j.nextName()) {
                    "stream_id" -> id = str(j).toIntOrNull() ?: 0
                    "num" -> num = str(j).toIntOrNull() ?: 0
                    "name" -> name = str(j)
                    "stream_icon" -> logo = str(j)
                    "epg_channel_id" -> epg = str(j)
                    "category_id" -> cat = str(j)
                    else -> j.skipValue()
                }
                j.endObject()
                if (id == 0 || ids.containsKey(id)) continue
                val ch = Channel(id, if (num > 0) num else all.size + 1, name.trim(), logo, epg, cat)
                ids[id] = ch; all.add(ch)
                (map[cat] ?: map.getOrPut(cat) { Group(cat, "Other").also { order.add(it) } }).channels.add(ch)
            }
            j.endArray()
        }
        val fav = Prefs.favorites
        val out = ArrayList<Group>()
        out.add(Group(FAV, "★ Favorites", all.filter { it.id.toString() in fav }.toMutableList()))
        out.add(Group(ALL, "All channels", all))
        out.addAll(order.filter { it.channels.isNotEmpty() })
        groups = out; byId = ids
    }

    private fun str(j: JsonReader): String = when (j.peek()) {
        JsonToken.NULL -> { j.nextNull(); "" }
        JsonToken.BOOLEAN -> j.nextBoolean().toString()
        JsonToken.BEGIN_ARRAY, JsonToken.BEGIN_OBJECT -> { j.skipValue(); "" }
        else -> j.nextString()
    }

    fun toggleFavorite(c: Channel): Boolean {
        val f = Prefs.favorites.toMutableSet()
        val on = f.add(c.id.toString()) || run { f.remove(c.id.toString()); false }
        Prefs.favorites = f
        groups.firstOrNull { it.id == FAV }?.let { g ->
            if (on) g.channels.add(c) else g.channels.removeAll { it.id == c.id }
        }
        return on
    }

    // ---- guide: the repo's per-channel files (xtream-data branch), one small file per channel ----
    private val maps = ConcurrentHashMap<Int, Map<String, String>>()
    private val epg = ConcurrentHashMap<Int, Pair<Long, List<Program>>>()

    fun guide(c: Channel): List<Program> {
        val now = System.currentTimeMillis()
        epg[c.id]?.let { if (now - it.first < 30 * 60_000) return it.second }
        val list = try { fromRepo(c) ?: fromServer(c) } catch (e: Exception) { emptyList() }
        epg[c.id] = now to list
        return list
    }

    private fun fromRepo(c: Channel): List<Program>? {
        val pl = Prefs.playlist
        if (pl.isEmpty()) return null
        val bucket = c.id % 256
        val m = maps[bucket] ?: get("$DATA" + "map/$pl/$bucket.json").use { r ->
            val o = JSONObject(r.body!!.string())
            o.keys().asSequence().associateWith { o.getString(it) }
        }.also { maps[bucket] = it }
        val file = m[c.id.toString()] ?: return emptyList()
        return get("$DATA" + "epg/$file.json").use { r -> parse(r.body!!.byteStream()) }
    }

    private fun fromServer(c: Channel): List<Program> =
        get(url("get_simple_data_table", "&stream_id=${c.id}")).use { r -> parse(r.body!!.byteStream()) }

    private fun parse(ins: InputStream): List<Program> {
        val out = ArrayList<Program>()
        val t = System.currentTimeMillis() / 1000
        JsonReader(InputStreamReader(ins, Charsets.UTF_8)).use { j ->
            j.beginObject()
            while (j.hasNext()) {
                if (j.nextName() != "epg_listings" || j.peek() != JsonToken.BEGIN_ARRAY) { j.skipValue(); continue }
                j.beginArray()
                while (j.hasNext()) {
                    var s = 0L; var e = 0L; var title = ""; var desc = ""
                    j.beginObject()
                    while (j.hasNext()) when (j.nextName()) {
                        "start_timestamp" -> s = str(j).toLongOrNull() ?: 0
                        "stop_timestamp" -> e = str(j).toLongOrNull() ?: 0
                        "title" -> title = b64(str(j))
                        "description" -> desc = b64(str(j))
                        else -> j.skipValue()
                    }
                    j.endObject()
                    if (e > t - 6 * 3600 && s > 0) out.add(Program(s, e, title, desc))
                }
                j.endArray()
            }
            j.endObject()
        }
        out.sortBy { it.start }
        return out
    }

    private fun b64(s: String): String = try {
        String(Base64.decode(s, Base64.DEFAULT), Charsets.UTF_8).trim()
    } catch (e: Exception) { s }
}
