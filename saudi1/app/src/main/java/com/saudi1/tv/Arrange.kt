package com.saudi1.tv

import org.json.JSONArray

/** The viewer's own arrangement of a playlist, kept on the device (and in the backup): the order of the groups,
 *  groups not shown, channels not shown. Nothing is removed from the playlist: "Show" brings anything back. */
object Arrange {
    private fun pl() = Prefs.playlist.ifEmpty { Integer.toHexString(Prefs.server.hashCode()) }
    var hiddenGroups: Set<String>
        get() = App.prefs.getStringSet("gh_" + pl(), emptySet()) ?: emptySet()
        set(v) = App.prefs.edit().putStringSet("gh_" + pl(), HashSet(v)).apply()
    var hiddenChannels: Set<String>
        get() = App.prefs.getStringSet("ch_" + pl(), emptySet()) ?: emptySet()
        set(v) = App.prefs.edit().putStringSet("ch_" + pl(), HashSet(v)).apply()
    var order: List<String>
        get() = try { val a = JSONArray(App.prefs.getString("go_" + pl(), "[]")); (0 until a.length()).map { a.getString(it) } } catch (e: Exception) { emptyList() }
        set(v) = App.prefs.edit().putString("go_" + pl(), JSONArray(v).toString()).apply()
    val any get() = hiddenGroups.isNotEmpty() || hiddenChannels.isNotEmpty() || order.isNotEmpty()

    // Movies and Series groups (owner, 11 Nov 2026): hidden and moved the same way, per playlist
    private fun vk(series: Boolean) = (if (series) "s_" else "v_") + pl()
    fun vodHidden(series: Boolean): Set<String> = App.prefs.getStringSet("vh_" + vk(series), emptySet()) ?: emptySet()
    fun setVodHidden(series: Boolean, v: Set<String>) = App.prefs.edit().putStringSet("vh_" + vk(series), HashSet(v)).apply()
    fun vodOrder(series: Boolean): List<String> = try { val a = JSONArray(App.prefs.getString("vo_" + vk(series), "[]")); (0 until a.length()).map { a.getString(it) } } catch (e: Exception) { emptyList() }
    fun setVodOrder(series: Boolean, v: List<String>) = App.prefs.edit().putString("vo_" + vk(series), JSONArray(v).toString()).apply()
    fun vod(series: Boolean, cats: List<VodCat>, all: Boolean = false): List<VodCat> {
        val o = vodOrder(series); val pos = HashMap<String, Int>(); o.forEachIndexed { i, id -> pos[id] = i }
        val sorted = if (o.isEmpty()) cats else {
            val known = cats.filter { it.id in pos }.sortedBy { pos[it.id] }
            val out = ArrayList<VodCat>(); var k = 0
            for (c in cats) { if (c.id in pos) out.add(known[k++]) else out.add(c) }
            out
        }
        if (all) return sorted
        val h = vodHidden(series); return if (h.isEmpty()) sorted else sorted.filter { it.id !in h }
    }
    fun reset() { App.prefs.edit().remove("gh_" + pl()).remove("ch_" + pl()).remove("go_" + pl())
        .remove("vh_" + vk(true)).remove("vh_" + vk(false)).remove("vo_" + vk(true)).remove("vo_" + vk(false)).apply() }

    /** the playlist's groups in the viewer's order (hidden ones left in when all = true, for the arranging screen) */
    fun apply(groups: List<Group>, all: Boolean = false): List<Group> {
        val o = order; val pos = HashMap<String, Int>(); o.forEachIndexed { i, id -> pos[id] = i }
        // groups the viewer never moved keep their place among the others
        val sorted = if (o.isEmpty()) groups else {
            val known = groups.filter { it.id in pos }.sortedBy { pos[it.id] }
            val out = ArrayList<Group>(); var k = 0
            for (g in groups) { if (g.id in pos) out.add(known[k++]) else out.add(g) }
            out
        }
        if (all) return sorted
        val hg = hiddenGroups; val hc = hiddenChannels
        val shown = sorted.filter { it.id !in hg }
        if (hc.isNotEmpty()) shown.forEach { g -> g.channels.removeAll { it.id.toString() in hc } }
        return shown.filter { it.channels.isNotEmpty() }
    }
}
