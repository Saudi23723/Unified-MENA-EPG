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
    private val allCache = HashMap<Boolean, Pair<Long, List<VodItem>>>()
    private val stamps = HashMap<Boolean, HashMap<Int, Long>>()

    fun clear() { catCache.clear(); listCache.clear(); allCache.clear(); stamps.clear() }

    // ---- kept on the device, per playlist: a group opens at once from here, and is checked with the provider behind it
    private fun dir(): java.io.File {
        val d = java.io.File(App.app.cacheDir, "vod/" + Integer.toHexString((Prefs.server + "|" + Prefs.user).hashCode()))
        if (!d.isDirectory) d.mkdirs()
        return d
    }
    private fun safe(s: String) = s.replace(Regex("[^A-Za-z0-9_-]"), "_")
    private fun file(series: Boolean, cat: String) = java.io.File(dir(), (if (series) "s_" else "v_") + safe(cat) + ".tsv")
    private fun clean(s: String) = s.replace('\t', ' ').replace('\n', ' ').replace('\r', ' ')
    private fun write(f: java.io.File, l: List<VodItem>) {
        try {
            val t = java.io.File(f.path + ".tmp")
            t.bufferedWriter().use { w ->
                for (i in l) { w.write("${i.id}\t${clean(i.name)}\t${clean(i.poster)}\t${clean(i.ext)}\t${clean(i.rating)}\t${clean(i.year)}\t${i.added}\n") }
            }
            t.renameTo(f)
        } catch (e: Exception) { }
    }
    private fun read(f: java.io.File): List<VodItem>? = try {
        if (!f.isFile) null else {
            val out = ArrayList<VodItem>()
            f.bufferedReader().useLines { ls ->
                for (ln in ls) { val p = ln.split('\t'); if (p.size >= 7) out.add(VodItem(p[0].toIntOrNull() ?: 0, p[1], p[2], p[3], p[4], p[5], p[6].toLongOrNull() ?: 0)) }
            }
            out
        }
    } catch (e: Exception) { null }

    /** the groups: from the device at once when they are there (fresh = ask the provider) */
    fun cats(series: Boolean, fresh: Boolean = false): List<VodCat> {
        val k = if (series) "s" else "v"
        val f = java.io.File(dir(), "cats_$k.tsv")
        if (!fresh) {
            catCache[k]?.let { return it }
            try {
                if (f.isFile) {
                    val l = f.readLines().mapNotNull { val p = it.split('\t'); if (p.size >= 2) VodCat(p[0], tidyName(p[1])) else null }
                    if (l.isNotEmpty()) { catCache[k] = l; return l }
                }
            } catch (e: Exception) { }
        }
        val a = JSONArray(text(api(if (series) "get_series_categories" else "get_vod_categories")))
        val l = (0 until a.length()).map { a.getJSONObject(it) }.map { VodCat(it.optString("category_id"), tidyName(it.optString("category_name"))) }
        if (l.isNotEmpty()) try { f.writeText(l.joinToString("\n") { it.id + "\t" + clean(it.name) }) } catch (e: Exception) { }
        catCache[k] = l
        return l
    }
    private val rTitlePrefix = Regex("^\\s*([A-Za-z]{2,3}(-[A-Za-z0-9]{1,6}){0,3}|4K|UHD)\\s*[-:|]\\s*")
    private val rTitleTail = Regex("[\\(\\[]\\s*(19|20)\\d{2}\\s*[\\)\\]]|\\b(19|20)\\d{2}\\b\\s*$|\\b(4K|UHD|FHD|HD|HEVC|MULTI|DUAL|AR|SUBS?)\\b", RegexOption.IGNORE_CASE)
    private val rShown = Regex("^\\s*[A-Za-z0-9]{2,3}(-[A-Za-z0-9]{1,6}){0,3}\\s+[-:|]\\s+")
    /** the title the viewer reads: the provider's sorting prefix ("AR-TR-S - ", "4K-AR - ") is not part of it */
    fun shown(n: String): String = n.replace(rShown, "").ifBlank { n }

    /** a title as the world writes it: no provider prefix ("AR-SUBS - "), no year, no quality words */
    fun titleKey(n: String): String = java.text.Normalizer.normalize(n.replace(rShown, "").replace(rTitlePrefix, "").replace(rTitleTail, " ").lowercase().replace('ı', 'i'), java.text.Normalizer.Form.NFD)
        .replace(Regex("[\\u0300-\\u036f\\u064b-\\u0655\\u0640]"), "")          // accents (Uzak Şehir = uzak sehir), Arabic marks
        .replace(Regex("[أإآ]"), "ا").replace('ى', 'ي').replace('ة', 'ه')
        .replace(Regex("[^a-z0-9\\u0600-\\u06ff]+"), "")

    /** group names some providers send glued together ("أفلامأجنبية2025/2026"): words and years apart */
    fun tidyName(n: String): String = n.trim()
        .replace(Regex("(أفلام|افلام|مسلسلات|برامج)(?=[\\u0621-\\u064A])"), "$1 ")
        .replace(Regex("([\\u0621-\\u064A])(?=\\d)"), "$1 ").replace(Regex("(\\d)(?=[\\u0621-\\u064A])"), "$1 ")
        .replace(Regex("\\s{2,}"), " ")

    fun catsAge(series: Boolean): Long = System.currentTimeMillis() - java.io.File(dir(), "cats_" + (if (series) "s" else "v") + ".tsv").lastModified()

    /** what the device already has of a group (null = nothing yet) and how old it is (ms) */
    fun cached(series: Boolean, cat: String): Pair<Long, List<VodItem>>? {
        val k = (if (series) "s" else "v") + cat
        listCache[k]?.let { return (System.currentTimeMillis() - it.first) to it.second }
        val f = file(series, cat)
        val l = read(f) ?: return null
        listCache[k] = f.lastModified() to l
        return (System.currentTimeMillis() - f.lastModified()) to l
    }

    /** a group from the provider (and kept on the device) */
    fun list(series: Boolean, cat: String): List<VodItem> {
        val k = (if (series) "s" else "v") + cat
        val l = App.http.newCall(Request.Builder().url(api(if (series) "get_series" else "get_vod_streams", "&category_id=" + enc(cat))).build()).execute().use { r ->
            if (!r.isSuccessful) throw java.io.IOException("HTTP ${r.code}")
            parse(r.body!!.charStream(), null)
        }
        listCache[k] = System.currentTimeMillis() to l
        write(file(series, cat), l)
        return l
    }

    private fun parse(rd: java.io.Reader, byCat: HashMap<String, ArrayList<VodItem>>?): ArrayList<VodItem> {
        val out = ArrayList<VodItem>(2000)
        val j = android.util.JsonReader(rd)
        j.isLenient = true
        if (j.peek() != android.util.JsonToken.BEGIN_ARRAY) { j.skipValue(); return out }
        j.beginArray()
        while (j.hasNext()) {
            var id = 0; var name = ""; var poster = ""; var ext = "mp4"; var rating = ""; var added = 0L; var year = ""; var cat = ""
            j.beginObject()
            while (j.hasNext()) {
                val k = j.nextName()
                val t = j.peek()
                if (t == android.util.JsonToken.NULL) { j.nextNull(); continue }
                if (t == android.util.JsonToken.BOOLEAN) { j.nextBoolean(); continue }
                if (t == android.util.JsonToken.BEGIN_ARRAY || t == android.util.JsonToken.BEGIN_OBJECT) { j.skipValue(); continue }
                when (k) {
                    "stream_id", "series_id" -> id = j.nextString().toIntOrNull() ?: 0
                    "name" -> name = j.nextString().trim()
                    "stream_icon", "cover" -> poster = j.nextString()
                    "container_extension" -> ext = j.nextString().ifEmpty { "mp4" }
                    "rating" -> rating = j.nextString().takeIf { it.isNotEmpty() && it != "0" && it != "null" } ?: ""
                    "added", "last_modified" -> added = j.nextString().toLongOrNull() ?: 0
                    "releaseDate", "year" -> { val v = j.nextString().take(4); if (year.isEmpty()) year = v }
                    "category_id" -> cat = j.nextString()
                    else -> j.skipValue()
                }
            }
            j.endObject()
            if (id > 0) {
                val it = VodItem(id, name, poster, ext, rating, year, added)
                out.add(it)
                if (byCat != null && cat.isNotEmpty()) byCat.getOrPut(cat) { ArrayList() }.add(it)
            }
        }
        return out
    }

    /** every movie or series of the playlist in one read (for search), read as a stream: little memory.
     *  The same read fills every group on the device, so each group then opens at once. */
    fun all(series: Boolean): List<VodItem> {
        allCache[series]?.let { if (System.currentTimeMillis() - it.first < 60 * 60_000) return it.second }
        val byCat = HashMap<String, ArrayList<VodItem>>()
        val out = App.http.newCall(Request.Builder().url(api(if (series) "get_series" else "get_vod_streams")).build()).execute().use { r ->
            if (!r.isSuccessful) throw java.io.IOException("HTTP ${r.code}")
            parse(r.body!!.charStream(), byCat)
        }
        allCache[series] = System.currentTimeMillis() to out
        if (out.isNotEmpty()) {
            for ((c, l) in byCat) {
                val f = file(series, c)
                // a group read on its own (the provider's own answer) in the last 6 hours stays as it is
                if (!f.isFile || System.currentTimeMillis() - f.lastModified() > 6 * 3600_000L) {
                    write(f, l); listCache[(if (series) "s" else "v") + c] = System.currentTimeMillis() to l
                }
            }
            val m = HashMap<Int, Long>(out.size * 2); for (i in out) m[i.id] = i.added
            stamps[series] = m
            try { java.io.File(dir(), "stamp_" + (if (series) "s" else "v") + ".tsv").bufferedWriter().use { w -> for (i in out) if (i.added > 0) w.write("${i.id}\t${i.added}\n") } } catch (e: Exception) { }
            App.prefs.edit().putLong(warmKey(series), System.currentTimeMillis()).apply()
        }
        return out
    }

    private fun warmKey(series: Boolean) = "vod_warm_" + (if (series) "s" else "v") + Integer.toHexString((Prefs.server + "|" + Prefs.user).hashCode())
    /** true when the whole catalogue should be read again in the background (first time, or older than 8 hours) */
    fun needsWarm(series: Boolean) = System.currentTimeMillis() - App.prefs.getLong(warmKey(series), 0) > 8 * 3600_000L

    /** when each one was last changed by the provider (a new episode moves a series up) */
    fun stamps(series: Boolean): Map<Int, Long> {
        stamps[series]?.let { return it }
        val m = HashMap<Int, Long>()
        try {
            val f = java.io.File(dir(), "stamp_" + (if (series) "s" else "v") + ".tsv")
            if (f.isFile) f.bufferedReader().useLines { ls -> for (ln in ls) { val i = ln.indexOf('\t'); if (i > 0) m[ln.substring(0, i).toIntOrNull() ?: 0] = ln.substring(i + 1).toLongOrNull() ?: 0 } }
        } catch (e: Exception) { }
        if (m.isNotEmpty()) stamps[series] = m
        return m
    }

    /** the Home showcase: the newest and the best rated of the playlist (a small list kept on the device, made new
     *  every 8 hours from the whole catalogue). Each: label to item. */
    fun showcase(series: Boolean): List<Pair<String, VodItem>> {
        val f = java.io.File(dir(), "show_" + (if (series) "s" else "v") + ".tsv")
        if (f.isFile && System.currentTimeMillis() - f.lastModified() < 3 * 3600_000L) {
            val l = try { f.readLines().mapNotNull { ln -> val p = ln.split('\t'); if (p.size >= 8) p[0] to VodItem(p[1].toIntOrNull() ?: 0, p[2], p[3], p[4], p[5], p[6], p[7].toLongOrNull() ?: 0) else null } } catch (e: Exception) { emptyList() }
            if (l.isNotEmpty()) return l
        }
        val all = all(series).filter { it.poster.startsWith("http") }
        val kind = if (series) "series" else "movies"
        val newest = all.sortedByDescending { it.added }.take(600)
        val out = ArrayList<Pair<String, VodItem>>()
        // what the world is watching (the repo's trending.json, from TMDB): the titles this playlist really has
        try {
            val byName = HashMap<String, VodItem>(all.size * 2)
            for (i in all) { val k = titleKey(i.name); if (k.length >= 2 && k !in byName) byName[k] = i }
            val t = JSONObject(text("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/trending.json"))
            val lists = t.optJSONArray("lists") ?: JSONArray()
            for (li in 0 until lists.length()) {
                val l = lists.getJSONObject(li); val items = l.optJSONArray("items") ?: continue
                var n = 0
                for (k in 0 until items.length()) {
                    val x = items.getJSONObject(k)
                    if ((x.optString("kind") == "series") != series) continue
                    val hit = byName[titleKey(x.optString("title"))] ?: byName[titleKey(x.optString("original"))] ?: byName[titleKey(x.optString("ar"))] ?: continue
                    if (out.any { it.second.id == hit.id }) continue
                    val r = x.optDouble("rating", 0.0)
                    out.add(l.optString("name") to VodItem(hit.id, hit.name, hit.poster, hit.ext, hit.rating.ifEmpty { if (r > 0) r.toString() else "" }, hit.year.ifEmpty { x.optString("year") }, hit.added))
                    if (++n >= 14) break
                }
            }
        } catch (e: Exception) { }
        newest.take(14).forEach { out.add("New in $kind" to it) }
        // the best rated among what came lately (not the same old classics every day)
        newest.filter { (it.rating.toDoubleOrNull() ?: 0.0) >= 7.5 }.sortedByDescending { it.rating.toDoubleOrNull() ?: 0.0 }.filter { x -> out.none { it.second.id == x.id } }.take(10)
            .forEach { out.add("Top rated $kind" to it) }
        try { f.writeText(out.joinToString("\n") { (l, i) -> "$l\t${i.id}\t${clean(i.name)}\t${clean(i.poster)}\t${clean(i.ext)}\t${clean(i.rating)}\t${clean(i.year)}\t${i.added}" }) } catch (e: Exception) { }
        return out
    }

    /** when the series' newest episode came out on the provider (each episode's "added"), kept 3 hours on the device:
     *  Favorites put the series with the newest episode first (owner, 11 Nov 2026: Mehmed, Yeralti, Tulsa King on top) */
    fun latestEpisodeAt(id: Int): Long {
        val k = "lep_" + Resume.pl() + "_" + id
        val c = App.prefs.getString(k, null)?.split(':')
        if (c != null && c.size == 2 && System.currentTimeMillis() - (c[0].toLongOrNull() ?: 0) < 3 * 3600_000L) return c[1].toLongOrNull() ?: 0
        val v = try {
            val info = seriesInfo(id)
            var m = info.optJSONObject("info")?.optString("last_modified")?.toLongOrNull() ?: 0L
            val eps = info.optJSONObject("episodes")
            if (eps != null) for (s in eps.keys()) { val a = eps.optJSONArray(s) ?: continue
                for (i in 0 until a.length()) m = maxOf(m, a.optJSONObject(i)?.optString("added")?.toLongOrNull() ?: 0L) }
            m
        } catch (e: Exception) { return c?.getOrNull(1)?.toLongOrNull() ?: 0 }
        App.prefs.edit().putString(k, "${System.currentTimeMillis()}:$v").apply()
        return v
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

/** where each movie / episode was left (continue watching), kept for each playlist on its own (owner, 11 Nov 2026:
 *  "all the playlists"): the same number is another title on another provider. What was kept before, for every
 *  playlist together, goes to the first playlist that opens. */
object Resume {
    fun pl() = Prefs.playlist.ifEmpty { Integer.toHexString(Prefs.server.hashCode()) }
    private fun lk() = "resume_" + pl()
    private fun pk(key: String) = "pos_" + pl() + "_" + key
    private fun dk(key: String) = "done_" + pl() + "_" + key
    fun get(key: String): Long = App.prefs.getLong(pk(key), App.prefs.getLong("pos_$key", 0))
    fun done(key: String): Boolean = App.prefs.getBoolean(dk(key), App.prefs.getBoolean("done_$key", false))
    fun dur(key: String): Long = list().firstOrNull { it.optString("k") == key }?.optLong("dur") ?: 0
    fun set(key: String, pos: Long, dur: Long, title: String, poster: String, url: String) {
        val e = App.prefs.edit()
        if (dur > 0 && pos > dur - 90_000) { e.remove(pk(key)).remove("pos_$key").putBoolean(dk(key), true); e.apply(); drop(key); return }  // finished
        else if (pos > 60_000) {
            e.putLong(pk(key), pos)
            val a = list().filterNot { it.optString("k") == key }.toMutableList()
            a.add(0, JSONObject().put("k", key).put("t", title).put("p", poster).put("u", url).put("pos", pos).put("dur", dur))
            e.putString(lk(), JSONArray(a.take(30)).toString())
        }
        e.apply()
    }
    fun list(): List<JSONObject> = try {
        if (!App.prefs.contains(lk()) && App.prefs.contains("resume"))
            App.prefs.edit().putString(lk(), App.prefs.getString("resume", "[]")).remove("resume").apply()
        val a = JSONArray(App.prefs.getString(lk(), "[]")); (0 until a.length()).map { a.getJSONObject(it) }
    } catch (e: Exception) { emptyList() }
    /** take it off Continue watching (and forget where it was left) */
    fun remove(key: String) { App.prefs.edit().remove(pk(key)).remove("pos_$key").apply(); drop(key) }
    private fun drop(key: String) {
        App.prefs.edit().putString(lk(), JSONArray(list().filterNot { it.optString("k") == key }).toString()).apply()
    }
}

/** ★ Favorites of movies / series (the same list the Favorites group shows) */
object VodFav {
    /** each playlist its own Favorites (what was kept before for all together goes to the first playlist that opens) */
    fun key(series: Boolean): String {
        val k = (if (series) "vfav_s_" else "vfav_m_") + Resume.pl(); val old = if (series) "vfav_s" else "vfav_m"
        if (!App.prefs.contains(k) && App.prefs.contains(old)) App.prefs.edit().putString(k, App.prefs.getString(old, "[]")).remove(old).apply()
        return k
    }
    fun list(series: Boolean): List<JSONObject> = try {
        val a = JSONArray(App.prefs.getString(key(series), "[]")); (0 until a.length()).map { a.getJSONObject(it) }
    } catch (e: Exception) { emptyList() }
    fun has(series: Boolean, id: Int) = list(series).any { it.optInt("id") == id }
    /** true = added */
    fun toggle(series: Boolean, id: Int, name: String, poster: String, ext: String, rating: String): Boolean {
        val l = list(series).toMutableList()
        val on = l.none { it.optInt("id") == id }
        if (on) l.add(0, JSONObject().put("id", id).put("n", name).put("p", poster).put("e", ext).put("r", rating))
        else l.removeAll { it.optInt("id") == id }
        App.prefs.edit().putString(key(series), JSONArray(l).toString()).apply()
        return on
    }
}
