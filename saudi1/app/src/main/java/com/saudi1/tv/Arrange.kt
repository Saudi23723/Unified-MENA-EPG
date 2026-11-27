package com.saudi1.tv

import org.json.JSONArray

/** The viewer's own arrangement of a playlist, kept on the device (and in the backup): the order of the groups,
 *  groups not shown, channels not shown. Nothing is removed from the playlist: "Show" brings anything back. */
object Arrange {
    private fun pl() = Prefs.playlist.ifEmpty { Integer.toHexString(Prefs.server.hashCode()) }

    /** The owner's own arrangement of the live groups (owner, 27 Nov 2026: "make them like mine for everyone, unless
     *  someone changes it himself"): xtream/<playlist>/owner_arrange.json, read from his backup. Every part the viewer
     *  never touched (order, hidden, shown, hidden channels, channel order, names) comes from it; a part he changes is
     *  his from then on, and Reset brings the owner's back. Movies, series and favorites are not part of it. */
    private class Def(val order: List<String>, val hidden: Set<String>, val shown: Set<String>, val chans: Set<String>,
                      val chanOrder: Map<String, List<String>>, val names: Map<String, String>)
    private var defFor = ""; private var defAt = 0L; private var defCache: Def? = null
    fun defFile(pl: String = Prefs.playlist) = java.io.File(App.app.filesDir, "owner_arrange_$pl.json")
    private fun def(): Def? {
        val f = defFile(); if (Prefs.playlist.isEmpty() || !f.isFile) return null
        if (defFor == Prefs.playlist && defAt == f.lastModified()) return defCache
        defCache = try {
            val o = org.json.JSONObject(f.readText())
            fun list(k: String) = o.optJSONArray(k)?.let { a -> (0 until a.length()).map { a.getString(it) } } ?: emptyList()
            val co = o.optJSONObject("channel_order"); val nm = o.optJSONObject("names")
            Def(list("order"), list("hidden").toSet(), list("shown").toSet(), list("hidden_channels").toSet(),
                co?.keys()?.asSequence()?.associateWith { k -> co.getJSONArray(k).let { a -> (0 until a.length()).map { a.getString(it) } } } ?: emptyMap(),
                nm?.keys()?.asSequence()?.associateWith { nm.getString(it) } ?: emptyMap())
        } catch (e: Exception) { null }
        defFor = Prefs.playlist; defAt = f.lastModified()
        return defCache
    }
    private fun has(k: String) = App.prefs.contains(k)

    var hiddenGroups: Set<String>
        get() = if (has("gh_" + pl())) App.prefs.getStringSet("gh_" + pl(), emptySet()) ?: emptySet() else def()?.hidden ?: emptySet()
        set(v) = App.prefs.edit().putStringSet("gh_" + pl(), HashSet(v)).apply()
    var hiddenChannels: Set<String>
        get() = if (has("ch_" + pl())) App.prefs.getStringSet("ch_" + pl(), emptySet()) ?: emptySet() else def()?.chans ?: emptySet()
        set(v) = App.prefs.edit().putStringSet("ch_" + pl(), HashSet(v)).apply()
    var order: List<String>
        get() = if (!has("go_" + pl())) def()?.order ?: emptyList()
            else try { val a = JSONArray(App.prefs.getString("go_" + pl(), "[]")); (0 until a.length()).map { a.getString(it) } } catch (e: Exception) { emptyList() }
        set(v) = App.prefs.edit().putString("go_" + pl(), JSONArray(v).toString()).apply()
    /** groups that come hidden (the playlist's own hidden groups, built for the app); "Show" keeps them shown */
    @Volatile var defaultHidden: Set<String> = emptySet()
    var shownGroups: Set<String>
        get() = if (has("gs_" + pl())) App.prefs.getStringSet("gs_" + pl(), emptySet()) ?: emptySet() else def()?.shown ?: emptySet()
        set(v) = App.prefs.edit().putStringSet("gs_" + pl(), HashSet(v)).apply()
    fun isHidden(id: String) = id in hiddenGroups || (id in defaultHidden && id !in shownGroups)
    fun setHidden(id: String, hide: Boolean) {
        if (hide) { hiddenGroups = hiddenGroups + id; shownGroups = shownGroups - id }
        else { hiddenGroups = hiddenGroups - id; if (id in defaultHidden) shownGroups = shownGroups + id }
    }
    // the viewer's own names for groups (owner, 26 Nov 2026: a keyboard with emoji for whoever wants to rename);
    // kept by group number per playlist, like the order; an adult group keeps its name (the parental lock reads it)
    private fun rk(kind: Int) = when (kind) { 0 -> "gr_" + pl(); else -> "vr_" + vk(kind == 2) }
    fun names(kind: Int): Map<String, String> = try {
        if (kind == 0 && !has(rk(0))) def()?.names ?: emptyMap()
        else { val o = org.json.JSONObject(App.prefs.getString(rk(kind), "{}")); o.keys().asSequence().associateWith { o.getString(it) } }
    } catch (e: Exception) { emptyMap() }
    fun rename(kind: Int, id: String, name: String?) {
        val m = names(kind).toMutableMap(); if (name.isNullOrBlank()) m.remove(id) else m[id] = name.trim()
        App.prefs.edit().putString(rk(kind), org.json.JSONObject(m as Map<*, *>).toString()).apply()
    }
    private fun named(g: Group, m: Map<String, String>): Group {
        val n = m[g.id] ?: return g
        return if (Parental.isAdult(g.name)) g else Group(g.id, n, g.channels)
    }
    private fun namedVod(c: VodCat, m: Map<String, String>): VodCat = m[c.id]?.let { VodCat(c.id, it) } ?: c
    /** the viewer changed something himself (the owner's arrangement alone is not "his own order") */
    val any get() = listOf("gh_", "ch_", "go_", "gs_", "gr_").any { has(it + pl()) }

    // Movies and Series groups (owner, 11 Nov 2026): hidden and moved the same way, per playlist
    private fun vk(series: Boolean) = (if (series) "s_" else "v_") + pl()
    fun vodHidden(series: Boolean): Set<String> = App.prefs.getStringSet("vh_" + vk(series), emptySet()) ?: emptySet()
    fun setVodHidden(series: Boolean, v: Set<String>) = App.prefs.edit().putStringSet("vh_" + vk(series), HashSet(v)).apply()
    fun vodOrder(series: Boolean): List<String> = try { val a = JSONArray(App.prefs.getString("vo_" + vk(series), "[]")); (0 until a.length()).map { a.getString(it) } } catch (e: Exception) { emptyList() }
    private fun late(series: Boolean): List<String> = try { val a = JSONArray(App.prefs.getString("vl_" + vk(series), "[]")); (0 until a.length()).map { a.getString(it) } } catch (e: Exception) { emptyList() }
    fun setVodOrder(series: Boolean, v: List<String>) = App.prefs.edit().putString("vo_" + vk(series), JSONArray(v).toString()).apply()
    fun vod(series: Boolean, cats: List<VodCat>, all: Boolean = false): List<VodCat> {
        val nm = names(if (series) 2 else 1)
        val l = vodRaw(series, cats, all)
        return if (nm.isEmpty()) l else l.map { namedVod(it, nm) }
    }
    private fun vodRaw(series: Boolean, cats: List<VodCat>, all: Boolean): List<VodCat> {
        var o = vodOrder(series); val pos = HashMap<String, Int>(); o.forEachIndexed { i, id -> pos[id] = i }
        // the groups this device has seen (owner, 26 Nov 2026): one the provider adds later goes to the END, hidden, even
        // when the viewer never arranged the list; the first list seen is taken as it is
        val kk = "vk_" + vk(series)
        val seen = App.prefs.getStringSet(kk, null)
        if (cats.size > 3) {
            if (seen == null) App.prefs.edit().putStringSet(kk, HashSet(cats.map { it.id })).apply()
            else {
                val fresh = cats.map { it.id }.filter { it !in seen && it !in pos }
                if (fresh.isNotEmpty()) {
                    App.prefs.edit().putStringSet(kk, HashSet(seen + fresh)).apply()
                    setVodHidden(series, vodHidden(series) + fresh)
                    // an arranged list takes them at its end (below); an unarranged one keeps the playlist's own order
                    // (the owner's later changes to it still reach this device) with the late groups after it
                    if (o.isEmpty()) App.prefs.edit().putString("vl_" + vk(series), JSONArray(late(series) + fresh).toString()).apply()
                }
            }
        }
        if (o.isEmpty()) { val l = late(series).toSet(); if (l.isNotEmpty()) {
            val (a, b) = cats.partition { it.id !in l }; val at = late(series).withIndex().associate { it.value to it.index }
            val sorted = a + b.sortedBy { at[it.id] }
            if (all) return sorted
            val h = vodHidden(series); return sorted.filter { it.id !in h }
        } }
        // a category the provider added after the viewer arranged this list goes to the END and comes hidden (owner,
        // 21 Nov 2026); the viewer shows it from Arrange like any hidden group
        if (o.isNotEmpty() && cats.size > 3) {
            val fresh = cats.filter { it.id !in pos }.map { it.id }
            if (fresh.isNotEmpty()) {
                o = o + fresh; fresh.forEachIndexed { i, id -> pos[id] = o.size - fresh.size + i }
                setVodOrder(series, o); setVodHidden(series, vodHidden(series) + fresh)
            }
        }
        val sorted = if (o.isEmpty()) cats else {
            val known = cats.filter { it.id in pos }.sortedBy { pos[it.id] }
            val out = ArrayList<VodCat>(); var k = 0
            for (c in cats) { if (c.id in pos) out.add(known[k++]) else out.add(c) }
            out
        }
        if (all) return sorted
        val h = vodHidden(series); return if (h.isEmpty()) sorted else sorted.filter { it.id !in h }
    }
    // the order of the channels inside a group (owner, 11 Nov 2026: "inside the groups I can rearrange, not only hide")
    private fun ck(gid: String) = "co_" + pl() + "_" + gid
    fun chanOrder(gid: String): List<String> = if (!has(ck(gid))) def()?.chanOrder?.get(gid) ?: emptyList()
        else try { val a = JSONArray(App.prefs.getString(ck(gid), "[]")); (0 until a.length()).map { a.getString(it) } } catch (e: Exception) { emptyList() }
    fun setChanOrder(gid: String, v: List<String>) = App.prefs.edit().putString(ck(gid), JSONArray(v).toString()).apply()
    private fun sortChans(g: Group) {
        val o = chanOrder(g.id); if (o.isEmpty() || g.channels.size < 2) return
        val pos = HashMap<String, Int>(); o.forEachIndexed { i, id -> pos[id] = i }
        val known = g.channels.filter { it.id.toString() in pos }.sortedBy { pos[it.id.toString()] }
        if (known.isEmpty()) return
        val out = ArrayList<Channel>(g.channels.size); var k = 0
        for (c in g.channels) { if (c.id.toString() in pos) out.add(known[k++]) else out.add(c) }
        g.channels.clear(); g.channels.addAll(out)
    }

    fun reset() { App.prefs.all.keys.filter { it.startsWith("co_" + pl() + "_") }.let { ks -> val e = App.prefs.edit(); ks.forEach { e.remove(it) }; e.apply() }
        App.prefs.edit().remove("gh_" + pl()).remove("ch_" + pl()).remove("go_" + pl()).remove("gs_" + pl())
        .remove("vh_" + vk(true)).remove("vh_" + vk(false)).remove("vo_" + vk(true)).remove("vo_" + vk(false)).remove("vl_" + vk(true)).remove("vl_" + vk(false))
        .remove("gr_" + pl()).remove("vr_" + vk(true)).remove("vr_" + vk(false)).apply() }

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
        sorted.forEach { sortChans(it) }
        val nm = names(0)
        if (nm.isNotEmpty()) { val r = sorted.map { named(it, nm) }; return applyRest(r, all) }
        return applyRest(sorted, all)
    }
    private fun applyRest(sorted: List<Group>, all: Boolean): List<Group> {
        if (all) return sorted
        val hc = hiddenChannels
        val shown = sorted.filter { !isHidden(it.id) }
        if (hc.isNotEmpty()) shown.forEach { g -> g.channels.removeAll { it.id.toString() in hc } }
        return shown.filter { it.channels.isNotEmpty() }
    }
}
