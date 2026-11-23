package com.saudi1.tv

import android.util.JsonReader
import android.util.JsonToken
import okhttp3.Request
import org.json.JSONObject
import java.io.InputStreamReader

/** Another playlist of this device (from the admin site), read only for Multiview: each screen can use its own
 *  playlist, so each has its own connection and the provider does not cut one of them. */
class OtherList(p: JSONObject) {
    val name: String = p.optString("name")
    private val server = p.optString("server"); private val user = p.optString("user"); private val pass = p.optString("pass")
    @Volatile var groups: List<Group> = emptyList()

    private fun enc(s: String) = java.net.URLEncoder.encode(s, "UTF-8")
    private fun api(a: String) = "$server/player_api.php?username=${enc(user)}&password=${enc(pass)}&action=$a"
    private fun str(j: JsonReader): String = when (j.peek()) {
        JsonToken.NULL -> { j.nextNull(); "" }
        JsonToken.BOOLEAN -> j.nextBoolean().toString()
        JsonToken.BEGIN_ARRAY, JsonToken.BEGIN_OBJECT -> { j.skipValue(); "" }
        else -> j.nextString()
    }

    /** blocking: run off the main thread */
    fun load(): Boolean {
        if (groups.isNotEmpty()) return true
        val order = ArrayList<Group>(); val map = HashMap<String, Group>()
        App.http.newCall(Request.Builder().url(api("get_live_categories")).build()).execute().use { r ->
            if (!r.isSuccessful) return false
            JsonReader(InputStreamReader(r.body!!.byteStream(), Charsets.UTF_8)).use { j ->
                j.beginArray()
                while (j.hasNext()) {
                    var id = ""; var n = ""
                    j.beginObject()
                    while (j.hasNext()) when (j.nextName()) { "category_id" -> id = str(j); "category_name" -> n = str(j); else -> j.skipValue() }
                    j.endObject()
                    if (id.isNotEmpty() && id !in map) Group(id, n.trim()).also { map[id] = it; order.add(it) }
                }
                j.endArray()
            }
        }
        App.http.newCall(Request.Builder().url(api("get_live_streams")).build()).execute().use { r ->
            if (!r.isSuccessful) return false
            JsonReader(InputStreamReader(r.body!!.byteStream(), Charsets.UTF_8)).use { j ->
                j.beginArray()
                var k = 0
                while (j.hasNext()) {
                    var id = 0; var num = 0; var n = ""; var logo = ""; var cat = ""
                    j.beginObject()
                    while (j.hasNext()) when (j.nextName()) {
                        "stream_id" -> id = str(j).toIntOrNull() ?: 0
                        "num" -> num = str(j).toIntOrNull() ?: 0
                        "name" -> n = str(j); "stream_icon" -> logo = str(j); "category_id" -> cat = str(j)
                        else -> j.skipValue()
                    }
                    j.endObject()
                    if (id == 0) continue
                    k++
                    val c = Channel(id, if (num > 0) num else k, n.trim(), logo, "", cat, "$server/live/${enc(user)}/${enc(pass)}/$id.ts")
                    (map[cat] ?: map.getOrPut(cat) { Group(cat, "Other").also { order.add(it) } }).channels.add(c)
                }
                j.endArray()
            }
        }
        groups = order.filter { it.channels.isNotEmpty() }
        return groups.isNotEmpty()
    }

    /** the same channel as [c] (same name without quality marks) in this playlist */
    fun same(c: Channel): Channel? {
        val b = Api.baseName(c.name)
        return groups.asSequence().flatMap { it.channels.asSequence() }.firstOrNull { Api.baseName(it.name) == b }
    }
}
