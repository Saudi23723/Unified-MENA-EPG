package com.saudi1.tv

import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject

class VodCat(val id: String, val name: String)
class VodItem(val id: Int, val name: String, val poster: String, val ext: String, val rating: String, val year: String, val added: Long = 0)
class Episode(val id: String, val num: Int, val title: String, val ext: String, val plot: String, val image: String, val duration: String)

/** Movies and series through the same relay (Xtream API), group by group. */
object Vod {
    private fun enc(s: String) = java.net.URLEncoder.encode(s, "UTF-8")
    private fun api(action: String, extra: String = "") =
        "${Prefs.server}/player_api.php?username=${enc(Prefs.user)}&password=${enc(Prefs.pass)}&action=$action$extra"

    private fun text(u: String): String = App.http.newCall(Request.Builder().url(u).build()).execute().use { r ->
        if (!r.isSuccessful) throw java.io.IOException("HTTP ${r.code}")
        r.body!!.string()
    }

    private val catCache = HashMap<String, List<VodCat>>()
    private val listCache = HashMap<String, Pair<Long, List<VodItem>>>()

    fun clear() { catCache.clear(); listCache.clear() }

    fun cats(series: Boolean): List<VodCat> {
        val k = if (series) "s" else "v"
        catCache[k]?.let { return it }
        val a = JSONArray(text(api(if (series) "get_series_categories" else "get_vod_categories")))
        val l = (0 until a.length()).map { a.getJSONObject(it) }.map { VodCat(it.optString("category_id"), it.optString("category_name").trim()) }
        catCache[k] = l
        return l
    }

    fun list(series: Boolean, cat: String): List<VodItem> {
        val k = (if (series) "s" else "v") + cat
        listCache[k]?.let { if (System.currentTimeMillis() - it.first < 30 * 60_000) return it.second }
        val a = JSONArray(text(api(if (series) "get_series" else "get_vod_streams", "&category_id=" + enc(cat))))
        val l = (0 until a.length()).map { a.getJSONObject(it) }.map {
            VodItem(
                if (series) it.optInt("series_id") else it.optInt("stream_id"),
                it.optString("name").trim(),
                if (series) it.optString("cover") else it.optString("stream_icon"),
                it.optString("container_extension", "mp4").ifEmpty { "mp4" },
                it.optString("rating").takeIf { r -> r.isNotEmpty() && r != "0" && r != "null" } ?: "",
                (it.optString("releaseDate").ifEmpty { it.optString("year") }).take(4),
                (if (series) it.optString("last_modified") else it.optString("added")).toLongOrNull() ?: 0,
            )
        }
        listCache[k] = System.currentTimeMillis() to l
        return l
    }

    private val allCache = HashMap<Boolean, Pair<Long, List<VodItem>>>()

    /** every movie or series of the playlist in one read (for search), read as a stream: little memory */
    fun all(series: Boolean): List<VodItem> {
        allCache[series]?.let { if (System.currentTimeMillis() - it.first < 60 * 60_000) return it.second }
        val out = ArrayList<VodItem>(20000)
        App.http.newCall(Request.Builder().url(api(if (series) "get_series" else "get_vod_streams")).build()).execute().use { r ->
            if (!r.isSuccessful) throw java.io.IOException("HTTP ${r.code}")
            val j = android.util.JsonReader(r.body!!.charStream())
            j.beginArray()
            while (j.hasNext()) {
                var id = 0; var name = ""; var poster = ""; var ext = "mp4"; var rating = ""; var added = 0L
                j.beginObject()
                while (j.hasNext()) {
                    val k = j.nextName()
                    if (j.peek() == android.util.JsonToken.NULL) { j.nextNull(); continue }
                    if (j.peek() == android.util.JsonToken.BOOLEAN) { j.nextBoolean(); continue }
                    if (j.peek() == android.util.JsonToken.BEGIN_ARRAY || j.peek() == android.util.JsonToken.BEGIN_OBJECT) { j.skipValue(); continue }
                    when (k) {
                        "stream_id", "series_id" -> id = j.nextString().toIntOrNull() ?: 0
                        "name" -> name = j.nextString().trim()
                        "stream_icon", "cover" -> poster = j.nextString()
                        "container_extension" -> ext = j.nextString().ifEmpty { "mp4" }
                        "rating" -> rating = j.nextString().takeIf { it.isNotEmpty() && it != "0" } ?: ""
                        "added", "last_modified" -> added = j.nextString().toLongOrNull() ?: 0
                        else -> j.skipValue()
                    }
                }
                j.endObject()
                if (id > 0) out.add(VodItem(id, name, poster, ext, rating, "", added))
            }
        }
        allCache[series] = System.currentTimeMillis() to out
        return out
    }

    fun movieInfo(id: Int): JSONObject = JSONObject(text(api("get_vod_info", "&vod_id=$id")))
    fun seriesInfo(id: Int): JSONObject = JSONObject(text(api("get_series_info", "&series_id=$id")))

    fun movieUrl(id: Int, ext: String) = "${Prefs.server}/movie/${enc(Prefs.user)}/${enc(Prefs.pass)}/$id.$ext"
    fun episodeUrl(id: String, ext: String) = "${Prefs.server}/series/${enc(Prefs.user)}/${enc(Prefs.pass)}/$id.$ext"

    /** seasons -> episodes from get_series_info */
    fun episodes(info: JSONObject): Map<String, List<Episode>> {
        val out = LinkedHashMap<String, List<Episode>>()
        val eps = info.optJSONObject("episodes") ?: return out
        val keys = eps.keys().asSequence().toList().sortedBy { it.toIntOrNull() ?: 999 }
        for (s in keys) {
            val a = eps.optJSONArray(s) ?: continue
            out[s] = (0 until a.length()).map { a.getJSONObject(it) }.map { e ->
                val i = e.optJSONObject("info") ?: JSONObject()
                Episode(e.optString("id"), e.optInt("episode_num"), e.optString("title").trim(), e.optString("container_extension", "mp4").ifEmpty { "mp4" },
                    i.optString("plot"), i.optString("movie_image"), i.optString("duration"))
            }
        }
        return out
    }
}

/** where each movie / episode was left (continue watching) */
object Resume {
    fun get(key: String): Long = App.prefs.getLong("pos_$key", 0)
    fun done(key: String): Boolean = App.prefs.getBoolean("done_$key", false)
    fun dur(key: String): Long = list().firstOrNull { it.optString("k") == key }?.optLong("dur") ?: 0
    fun set(key: String, pos: Long, dur: Long, title: String, poster: String, url: String) {
        val e = App.prefs.edit()
        if (dur > 0 && pos > dur - 90_000) { e.remove("pos_$key").putBoolean("done_$key", true); drop(key) }  // finished
        else if (pos > 60_000) {
            e.putLong("pos_$key", pos)
            val a = list().filterNot { it.optString("k") == key }.toMutableList()
            a.add(0, JSONObject().put("k", key).put("t", title).put("p", poster).put("u", url).put("pos", pos).put("dur", dur))
            e.putString("resume", JSONArray(a.take(30)).toString())
        }
        e.apply()
    }
    fun list(): List<JSONObject> = try {
        val a = JSONArray(App.prefs.getString("resume", "[]")); (0 until a.length()).map { a.getJSONObject(it) }
    } catch (e: Exception) { emptyList() }
    private fun drop(key: String) {
        App.prefs.edit().putString("resume", JSONArray(list().filterNot { it.optString("k") == key }).toString()).apply()
    }
}
