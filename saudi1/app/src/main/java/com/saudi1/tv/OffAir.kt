package com.saudi1.tv

import okhttp3.Interceptor
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import org.json.JSONObject

/** A channel the provider has switched off sends, instead of the live stream, one fixed video file (owner, 18 Nov 2026:
 *  STARZPLAY SPORTS (STC) and BBC PARLIAMENT were black: Strong sent the same black file from Aug 2023 for both).
 *  A live stream never has a size and a date; that file has both. When it comes:
 *   - the channel plays from another stream of the SAME channel (same guide id, or the same name without HD / 4K...),
 *     in any playlist, by itself, in about a second;
 *   - the switch is kept for 24 h (then the channel's own stream is tried again: providers bring channels back);
 *   - the admin site is told (Dashboard › صحة التطبيق), so a channel with no other stream is seen the same day.
 *  Only the live screen uses it; nothing here touches the picture or the keys. */
object OffAir {
    private const val DAY = 86_400_000L

    /** the check, on the live player's own connection only */
    val interceptor = Interceptor { chain ->
        val t0 = android.os.SystemClock.elapsedRealtime()
        val r = chain.proceed(chain.request())
        android.util.Log.d("SAUDI", "live answer ${r.code} in ${android.os.SystemClock.elapsedRealtime() - t0}ms (redirects ${generateSequence(r.priorResponse) { it.priorResponse }.count()})")
        val path = chain.request().url.encodedPath
        if (r.code == 200 && path.contains("/live/") && path.endsWith(".ts")) {
            val size = r.header("Content-Length")?.toLongOrNull() ?: -1L
            val date = r.headers.getDate("Last-Modified")?.time ?: 0L
            // a fixed file made more than a day ago: never a live channel
            if (size > 0 && date > 0 && System.currentTimeMillis() - date > DAY) {
                r.close()
                return@Interceptor Response.Builder().request(r.request).protocol(r.protocol).code(404).message("off air")
                    .header("X-Off-Air", "1").body("".toResponseBody(null)).build()
            }
        }
        r
    }

    /** this error is the provider's off-air file */
    fun isOffAir(e: Throwable?): Boolean = generateSequence(e) { it.cause }.take(8)
        .filterIsInstance<androidx.media3.datasource.HttpDataSource.InvalidResponseCodeException>()
        .any { x -> x.headerFields.keys.any { it != null && it.equals("X-Off-Air", true) } }

    // ---- the switches kept (channel id -> the stream that plays it, with when) ----
    private val lock = Any()
    private fun load(): JSONObject = try { JSONObject(App.prefs.getString("off_air", "{}") ?: "{}") } catch (e: Exception) { JSONObject() }

    /** the stream that plays this channel now (its own unless switched in the last 24 h) */
    fun streamFor(id: Int): Int = synchronized(lock) {
        val o = load().optJSONObject(id.toString()) ?: return id
        if (System.currentTimeMillis() - o.optLong("t") > DAY) id else o.optInt("to", id)
    }

    private fun keep(id: Int, to: Int, dead: Set<Int>) = synchronized(lock) {
        val all = load(); val now = System.currentTimeMillis()
        // old entries go
        all.keys().asSequence().toList().forEach { k -> if (now - (all.optJSONObject(k)?.optLong("t") ?: 0) > DAY) all.remove(k) }
        all.put(id.toString(), JSONObject().put("to", to).put("t", now).put("dead", dead.joinToString(",")))
        App.prefs.edit().putString("off_air", all.toString()).apply()
    }

    private fun deadFor(id: Int): MutableSet<Int> = synchronized(lock) {
        val o = load().optJSONObject(id.toString())
        if (o == null || System.currentTimeMillis() - o.optLong("t") > DAY) mutableSetOf()
        else o.optString("dead").split(",").mapNotNull { it.toIntOrNull() }.toMutableSet()
    }

    private val TAGS = Regex("""\b(UHD|FHD|HD|SD|LQ|HQ|HEVC|H265|4K|8K|RAW|60FPS|50FPS|BACKUP|VIP)\b""")
    private val SUP = Regex("[ᴬ-ᵛ⁰-⁹ʰᵉᵛᶜᴴᴰᴿᴬᵂ◉●★]+")
    private val PREFIX = Regex("""^\s*(\|?[A-Z]{2,4}\|?\s*[:|]\s*)+""")
    private val OTHER = Regex("[^A-Z0-9\\u0600-\\u06FF]+")
    private val LOW = Regex("""\b(SD|LQ)\b""")
    private val BIG = Regex("""\b(4K|8K|UHD)\b""")
    private val HDQ = Regex("""\b(HD|FHD)\b|ᴴᴰ""")
    private fun plain(n: String) = OTHER.replace(TAGS.replace(PREFIX.replace(SUP.replace(n.uppercase(), " "), ""), " "), "")

    private fun rank(n: String): Int {
        val u = n.uppercase()
        return when { LOW.containsMatchIn(u) -> 3; BIG.containsMatchIn(u) -> 2; HDQ.containsMatchIn(u) -> 0; else -> 1 }
    }

    /** the stream just played (id) of channel c was the off-air file: the next stream of the same channel, or null.
     *  Called off the main thread (it looks through every channel of the playlist). */
    fun next(c: Channel, played: Int): Int? {
        val dead = deadFor(c.id); dead.add(played)
        val pool = Api.byId.values.filter { it.id != c.id && it.id !in dead && it.url.isEmpty() }
        // the same guide first (a plain comparison, instant); the same name only when the channel has no guide match
        var alts = if (c.epgId.isEmpty()) emptyList() else pool.filter { it.epgId.equals(c.epgId, true) }
        if (alts.isEmpty()) { val p = plain(c.name); if (p.length >= 3) { val first = p.take(3); alts = pool.filter { it.name.uppercase().contains(first) && plain(it.name) == p } } }
        alts = alts.sortedBy { rank(it.name) }
        val to = alts.firstOrNull()?.id
        if (to != null) keep(c.id, to, dead)
        Health.report("off-air", "${c.name} [${c.id}] stream $played is the provider's off-air file" +
            (if (to != null) " -> plays from ${Api.byId[to]?.name} [$to]" else " -> no other stream of this channel"))
        return to
    }
}
