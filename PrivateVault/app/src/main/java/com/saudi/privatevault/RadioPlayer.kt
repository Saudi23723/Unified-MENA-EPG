package com.saudi.privatevault

import android.app.Activity
import android.content.Intent
import android.net.Uri
import com.google.android.material.dialog.MaterialAlertDialogBuilder

/**
 * Live air traffic control. LiveATC's feeds are theirs to play: its terms allow listening in its own
 * app or site, not inside other apps. So the 🎧 opens the LiveATC app (installed from the Play Store
 * once, then one tap away) at the chosen field; KBVU has no public feed at all.
 */
object RadioPlayer {
    private const val PKG = "net.liveatc.android"

    fun choose(act: Activity) {
        val home = VaultLock.prefs(act).getString("efb_home", "KBVU") ?: "KBVU"
        val fields = listOf(home, "KHND", "KLAS", "KVGT").distinct()
        MaterialAlertDialogBuilder(act).setTitle(R.string.atc_title)
            .setMessage(act.getString(R.string.atc_how))
            .setItems(fields.map { "🎧  $it" }.toTypedArray()) { _, i -> open(act, fields[i]) }
            .setNegativeButton(R.string.cancel, null).show()
    }

    fun open(act: Activity, icao: String) {
        if (icao.equals("KBVU", true)) {
            MaterialAlertDialogBuilder(act).setTitle("🎧 KBVU").setMessage(act.getString(R.string.atc_none, "KBVU"))
                .setPositiveButton("KHND") { _, _ -> open(act, "KHND") }.setNegativeButton(R.string.cancel, null).show()
            return
        }
        val app = act.packageManager.getLaunchIntentForPackage(PKG)
        if (app != null) {
            // The LiveATC app, at its search for this field.
            val deep = Intent(Intent.ACTION_VIEW, Uri.parse("https://www.liveatc.net/search/?icao=" + icao.lowercase())).setPackage(PKG)
            try { act.startActivity(deep) } catch (e: Exception) { act.startActivity(app) }
        } else {
            MaterialAlertDialogBuilder(act).setTitle(R.string.atc_title).setMessage(R.string.atc_install)
                .setPositiveButton(R.string.atc_install_go) { _, _ ->
                    try { act.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=$PKG"))) }
                    catch (e: Exception) { act.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/store/apps/details?id=$PKG"))) }
                }.setNegativeButton(R.string.cancel, null).show()
        }
    }
}
