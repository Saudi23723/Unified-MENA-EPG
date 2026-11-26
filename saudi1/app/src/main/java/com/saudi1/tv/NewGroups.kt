package com.saudi1.tv

import android.util.JsonReader
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.InputStreamReader

/** The provider's groups the playlist does not carry, picked up the way TiviMate does it (owner, 26 Nov 2026): the
 *  device asks the provider itself for its whole live list now and then, and every group the app does not have yet
 *  comes in at the END of the hidden groups, with a clean name and a flag; Settings -> Arrange shows any of them.
 *  The relay is only asked where the provider is (one redirect, no video opened). */
object NewGroups {
    private const val EVERY = 6 * 3600_000L
    private fun pl() = Prefs.playlist.ifEmpty { Integer.toHexString(Prefs.server.hashCode()) }
    fun file() = File(App.app.filesDir, "new_groups_" + pl() + ".json")

    /** true when the provider was asked and something changed (the lists are then rebuilt) */
    fun check(known: Set<Int>, probe: Int, events: Set<Int> = emptySet(), force: Boolean = false): Boolean {
        val k = "ng_t_" + pl()
        val noEv = App.prefs.getString("ng_ev_" + pl(), null) == null && events.isNotEmpty()
        if (!force && !noEv && System.currentTimeMillis() - App.prefs.getLong(k, 0) < EVERY) return false
        if (known.size < 20) return false
        App.prefs.edit().putLong(k, System.currentTimeMillis()).apply()
        val origin = origin(probe) ?: return false
        App.prefs.edit().putString("ng_origin_" + pl(), origin).putString("ng_origin_for_" + pl(), Prefs.server).apply()
        val base = "$origin/player_api.php?username=${enc(Prefs.user)}&password=${enc(Prefs.pass)}&action="
        val names = HashMap<String, String>()
        val ca = App.http.newCall(Request.Builder().url(base + "get_live_categories").build()).execute().use { r ->
            if (!r.isSuccessful) return false
            JSONArray(r.body!!.string())
        }
        for (i in 0 until ca.length()) ca.optJSONObject(i)?.let { names[it.optString("category_id")] = it.optString("category_name") }
        // the channels the app does not have, by the provider's group (read as a stream: the list can be 30,000 long)
        val byCat = LinkedHashMap<String, MutableList<JSONObject>>(); val knownCats = HashSet<String>(); val evCats = LinkedHashSet<String>()
        App.http.newCall(Request.Builder().url(base + "get_live_streams").build()).execute().use { r ->
            if (!r.isSuccessful) return false
            JsonReader(InputStreamReader(r.body!!.byteStream(), Charsets.UTF_8)).use { j ->
                j.beginArray()
                while (j.hasNext()) {
                    var id = 0; var name = ""; var logo = ""; var cat = ""
                    j.beginObject()
                    while (j.hasNext()) when (j.nextName()) {
                        "stream_id" -> id = s(j).toIntOrNull() ?: 0
                        "name" -> name = s(j); "stream_icon" -> logo = s(j); "category_id" -> cat = s(j)
                        else -> j.skipValue()
                    }
                    j.endObject()
                    if (id == 0) continue
                    if (id in events) evCats.add(cat)
                    if (id in known) { knownCats.add(cat); continue }
                    if (name.isBlank() || SEPARATOR.containsMatchIn(name)) continue
                    byCat.getOrPut(cat) { ArrayList() }.add(JSONObject().put("stream_id", id).put("name", chan(name)).put("stream_icon", logo))
                }
                j.endArray()
            }
        }
        if (byCat.isEmpty() && knownCats.isEmpty()) return false        // an empty answer is trouble, not "nothing new"
        // the provider's groups that hold our event / PPV channels: their names are asked again every 10 minutes
        App.prefs.edit().putString("ng_ev_" + pl(), JSONArray(evCats.toList()).toString()).apply()
        // a provider group the app already shows part of is not new (the owner picked from it)
        val fresh = byCat.filterKeys { it !in knownCats && !ADULT.containsMatchIn(names[it] ?: "") }
        // the groups keep the places they had; one the provider adds goes to the end
        val ok = "ng_o_" + pl()
        val before = try { JSONArray(App.prefs.getString(ok, "[]")).let { a -> (0 until a.length()).map { a.getString(it) } } } catch (e: Exception) { emptyList() }
        val order = before.filter { it in fresh } + fresh.keys.filter { it !in before }
        App.prefs.edit().putString(ok, JSONArray(before + fresh.keys.filter { it !in before }).toString()).apply()
        val cats = JSONArray(); val streams = JSONArray()
        for (c in order) {
            val gid = "pv$c"
            cats.put(JSONObject().put("category_id", gid).put("category_name", groupName(names[c] ?: "Other")))
            for (x in fresh[c]!!) streams.put(x.put("category_id", gid))
        }
        val out = JSONObject().put("cats", cats).put("streams", streams).toString()
        val f = file()
        if (f.isFile && f.readText() == out) return false
        f.writeText(out)
        return true
    }

    /** The provider puts the game in the channel's name ("Hawks vs Rockets") and changes it for every game: the names
     *  in the new event / PPV groups are asked again every 10 minutes, one small request per group (owner, 26 Nov 2026:
     *  "the names the provider puts must always be updated"). true when a name changed. */
    fun names(ours: Map<Int, String>): Boolean {
        val k = "ng_n_" + pl()
        if (System.currentTimeMillis() - App.prefs.getLong(k, 0) < 10 * 60_000L) return false
        App.prefs.edit().putLong(k, System.currentTimeMillis()).apply()
        val f = file()
        val o = try { if (f.isFile) JSONObject(f.readText()) else null } catch (e: Exception) { null }
        val cats = o?.optJSONArray("cats"); val streams = o?.optJSONArray("streams")
        val pv = if (cats == null) emptyList() else (0 until cats.length()).map { cats.getJSONObject(it) }
            .filter { EVENT.containsMatchIn(it.optString("category_name")) }.map { it.optString("category_id").removePrefix("pv") }
        val mine = try { JSONArray(App.prefs.getString("ng_ev_" + pl(), "[]")).let { a -> (0 until a.length()).map { a.getString(it) } } } catch (e: Exception) { emptyList() }
        val ask = (mine + pv).distinct().take(30)
        if (ask.isEmpty()) return false
        val origin = origin() ?: return false
        val base = "$origin/player_api.php?username=${enc(Prefs.user)}&password=${enc(Prefs.pass)}&action=get_live_streams&category_id="
        val now = HashMap<Int, String>()
        for (g in ask) try {
            App.http.newCall(Request.Builder().url(base + enc(g)).build()).execute().use { r ->
                if (!r.isSuccessful) return@use
                val a = JSONArray(r.body!!.string())
                for (i in 0 until a.length()) a.optJSONObject(i)?.let { x -> val n = x.optString("name"); if (n.isNotBlank()) now[x.optInt("stream_id")] = chan(n) }
            }
        } catch (e: Exception) { }
        if (now.isEmpty()) return false
        var changed = false
        if (o != null && streams != null) {
            for (i in 0 until streams.length()) {
                val x = streams.getJSONObject(i); val n = now[x.optInt("stream_id")] ?: continue
                if (n != x.optString("name")) { x.put("name", n); changed = true }
            }
            if (changed) f.writeText(o.toString())
        }
        // our own event channels: today's game where the provider's name is not the same channel name as ours (the
        // owner's names stay when only a country mark / quality / spacing differs, like the relay does)
        val ov = JSONObject()
        for ((id, n) in ours) { val p = now[id] ?: continue; if (p.isNotBlank() && key(p) != key(n)) ov.put(id.toString(), p) }
        val nf = namesFile(); val txt = ov.toString()
        if (!(nf.isFile && nf.readText() == txt)) { nf.writeText(txt); changed = true } else nf.setLastModified(System.currentTimeMillis())
        return changed
    }
    fun namesFile() = File(App.app.filesDir, "live_names_" + pl() + ".json")
    /** today's names of our event channels (stream id -> name), read when the lists are built */
    fun overrides(): Map<Int, String> = try {
        val f = namesFile()
        // older than 6 hours: no longer trusted (the relay names come back)
        if (!f.isFile || System.currentTimeMillis() - f.lastModified() > 6 * 3600_000L) emptyMap()
        else JSONObject(f.readText()).let { o -> o.keys().asSequence().mapNotNull { k -> k.toIntOrNull()?.let { it to o.getString(k) } }.toMap() }
    } catch (e: Exception) { emptyMap() }
    private fun key(t: String) = java.text.Normalizer.normalize(t, java.text.Normalizer.Form.NFKC).uppercase()
        .replace(Regex("^\\|?[A-Z]{2,3}\\s*[:|]\\s*"), "").replace(Regex("\\b(UHD|FHD|HD|SD|4K|8K|HEVC|RAW|\\d{3,4}P)\\b"), "")
        .replace(Regex("[^A-Z0-9\\u0600-\\u06FF]"), "")
    /** the owner's event / PPV groups (the relay's EVENT_GROUP) */
    val OUR_EVENT = Regex("^(?!.*24/7).*(PPV|PAY PER VIEW|EVENT|PACKAGE|ESPN\\+|TSN\\+|SN\\+|PEACOCK|PARAMOUNT|CUP GAMES|NFL SPORTS|ᴘᴘᴠ|ᴇᴠᴇɴᴛ|ᴱᵛᵉⁿᵗ|NBA PASS|DAZN|STAN\\b|SOCCER|\\bNBA\\b|\\bNFL\\b|\\bNHL\\b|\\bMLB\\b|\\bNCAA|MAX ESPN|\\bFLO\\b|FLOSPORT)", RegexOption.IGNORE_CASE)
    private val EVENT = Regex("PPV|ᴘᴘᴠ|EVENT|ᴇᴠᴇɴᴛ|UFC|BOXING|ʙᴏxɪɴɢ|FIGHT|ꜰɪɢʜᴛ|WWE|MMA|NBA|NFL|NHL|MLB|NCAA|MLS|LEAGUE|ʟᴇᴀɢᴜᴇ|SPORT|ꜱᴘᴏʀᴛ|LIVE|ʟɪᴠᴇ|MATCH|GAME", RegexOption.IGNORE_CASE)

    /** the provider's address found by the last check (for the guide of the new channels), or one asked now */
    fun origin(): String? {
        val o = App.prefs.getString("ng_origin_" + pl(), null)
        if (o != null && App.prefs.getString("ng_origin_for_" + pl(), "") == Prefs.server) return o
        val probe = Api.byId.keys.firstOrNull { it > 0 } ?: return null
        return origin(probe)?.also { App.prefs.edit().putString("ng_origin_" + pl(), it).putString("ng_origin_for_" + pl(), Prefs.server).apply() }
    }

    /** where the provider is: the relay answers a channel link with a redirect to it */
    private fun origin(id: Int): String? = try {
        App.http.newBuilder().followRedirects(false).followSslRedirects(false).build()
            .newCall(Request.Builder().url("${Prefs.server}/live/${enc(Prefs.user)}/${enc(Prefs.pass)}/$id.ts").build()).execute().use { r ->
                val loc = r.header("Location")
                if (r.isRedirect && loc != null) { val u = java.net.URL(java.net.URL(Prefs.server), loc); "${u.protocol}://${u.authority}" }
                else Prefs.server            // no relay: the server is the provider
            }
    } catch (e: Exception) { null }

    private val SEPARATOR = Regex("✶|⋆|^\\s*#{3,}|#{3,}\\s*$|^\\s*[-=_]{4,}")
    private val ADULT = Regex("XXX|ADULT|\\+18|18\\+|FOR ADULTS", RegexOption.IGNORE_CASE)
    private fun s(j: JsonReader): String = if (j.peek() == android.util.JsonToken.NULL) { j.nextNull(); "" } else j.nextString()
    private fun enc(s: String) = java.net.URLEncoder.encode(s, "UTF-8")

    /** "USA: LATIN UNIMAS [1080p]" -> "🇺🇸 | LATIN ᴜɴɪᴍᴀꜱ", "USA: FUBO [PPV EVENTS]" -> "🇺🇸 | FUBO ᴘᴘᴠ", like the groups above it */
    fun groupName(raw: String): String {
        var t = raw.replace(Regex("[\\u24e7\\u00a7✪★☆]"), " ").replace(Regex("\\s+"), " ").trim()
        var flag = ""
        Regex("^\\|?\\s*([A-Za-z]{2,3})\\s*[:|]\\s*(.+)$").find(t)?.let { m ->
            val code = m.groupValues[1].uppercase()
            val iso = mapOf("USA" to "US", "UK" to "GB", "EN" to "GB", "UAE" to "AE", "KSA" to "SA", "EG" to "EG").getOrElse(code) { code }
            if (iso.length == 2 && code != "AR") flag = iso.map { String(Character.toChars(0x1F1E6 + (it - 'A'))) }.joinToString("")
            t = m.groupValues[2]
        }
        t = t.replace(Regex("\\[\\s*PPV\\s*EVENTS?\\s*]", RegexOption.IGNORE_CASE), " PPV ")
            .replace(Regex("\\[\\s*(\\d{3,4}p|4K|UHD|FHD|HD|SD|HEVC|RAW|\\d{2}\\s*FPS)\\s*]", RegexOption.IGNORE_CASE), " ")
            .replace(Regex("[\\[\\]]"), " ").replace(Regex("\\s+"), " ").trim()
        if (flag.isEmpty()) flag = hint(t)
        val small = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".toList().zip("ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ".toList()).toMap()
        val words = t.split(' ').mapIndexed { i, w ->
            if (i > 0 && (w.length >= 5 || w.uppercase() == "PPV") && w.all { it in 'A'..'Z' }) w.map { small[it] ?: it }.joinToString("") else w
        }
        return "$flag | " + words.joinToString(" ").replace(Regex("\\bBEIN\\b"), "beIN")
    }

    private fun hint(t: String): String {
        val u = t.uppercase()
        val hints = listOf("JORDAN|ROYA" to "🇯🇴", "LEBAN" to "🇱🇧", "EGYPT" to "🇪🇬", "IRAQ" to "🇮🇶", "SYRIA" to "🇸🇾",
            "QATAR|BEIN|ALKASS" to "🇶🇦", "UAE|EMIRAT|DUBAI|ABU DHABI" to "🇦🇪", "SAUDI|KSA|MBC|SHAHID|\\bSTC\\b|\\bSSC\\b|ROTANA" to "🇸🇦",
            "KUWAIT" to "🇰🇼", "PALESTIN" to "🇵🇸", "MOROC|MAROC" to "🇲🇦", "OSN|NETFLIX|SHOOF|DISNEY|PRIME" to "🔘",
            "NEWS|أخبار|اخبار" to "📰", "KIDS|CARTOON|أطفال" to "🧸", "QURAN|ISLAM|قرآن" to "🕌", "MOVIE|CINEMA|افلام|أفلام" to "🎬",
            "PPV|UFC|BOXING|FIGHT|EVENT" to "🔥", "SPORT|SOCCER|FOOTBALL|LEAGUE|رياض" to "⚽")
        return hints.firstOrNull { Regex(it.first).containsMatchIn(u) }?.second ?: "🌐"
    }

    /** a channel's name without the provider's marks ("ⓧ", "[1080p]") */
    private fun chan(n: String) = n.replace(Regex("[\\u24e7\\u00a7]"), "").replace(Regex("\\s*\\[(\\d{3,4}p|4K|UHD|FHD|HD|SD)]\\s*$", RegexOption.IGNORE_CASE), "")
        .replace(Regex("\\s+"), " ").trim()
}
