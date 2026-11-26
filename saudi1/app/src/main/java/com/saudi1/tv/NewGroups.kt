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
    fun check(known: Set<Int>, probe: Int, force: Boolean = false): Boolean {
        val k = "ng_t_" + pl()
        if (!force && System.currentTimeMillis() - App.prefs.getLong(k, 0) < EVERY) return false
        if (known.size < 20) return false
        App.prefs.edit().putLong(k, System.currentTimeMillis()).apply()
        val origin = origin(probe) ?: return false
        val base = "$origin/player_api.php?username=${enc(Prefs.user)}&password=${enc(Prefs.pass)}&action="
        val names = HashMap<String, String>()
        val ca = App.http.newCall(Request.Builder().url(base + "get_live_categories").build()).execute().use { r ->
            if (!r.isSuccessful) return false
            JSONArray(r.body!!.string())
        }
        for (i in 0 until ca.length()) ca.optJSONObject(i)?.let { names[it.optString("category_id")] = it.optString("category_name") }
        // the channels the app does not have, by the provider's group (read as a stream: the list can be 30,000 long)
        val byCat = LinkedHashMap<String, MutableList<JSONObject>>(); val knownCats = HashSet<String>()
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
                    if (id in known) { knownCats.add(cat); continue }
                    if (name.isBlank() || SEPARATOR.containsMatchIn(name)) continue
                    byCat.getOrPut(cat) { ArrayList() }.add(JSONObject().put("stream_id", id).put("name", chan(name)).put("stream_icon", logo))
                }
                j.endArray()
            }
        }
        if (byCat.isEmpty() && knownCats.isEmpty()) return false        // an empty answer is trouble, not "nothing new"
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
        val small = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".zip("ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ".toList()).toMap()
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
