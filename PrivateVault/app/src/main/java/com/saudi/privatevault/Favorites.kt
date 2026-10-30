package com.saudi.privatevault

import android.content.Context

/** The pilot's own airports, first in the search. */
object Favorites {
    private fun set(ctx: Context): MutableSet<String> = VaultLock.prefs(ctx).getStringSet("fav_airports", emptySet())!!.toMutableSet()

    fun has(ctx: Context, ident: String) = ident in set(ctx)

    fun all(ctx: Context): Set<String> = set(ctx)

    /** Adds or removes; true when it is now a favourite. */
    fun toggle(ctx: Context, ident: String): Boolean {
        val s = set(ctx)
        val on = if (ident in s) { s.remove(ident); false } else { s.add(ident); true }
        VaultLock.prefs(ctx).edit().putStringSet("fav_airports", s).apply()
        return on
    }
}
