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

    /** The LiveATC app, found by its name among the installed apps (whatever its package is called). */
    private fun liveAtc(act: Activity): Intent? {
        act.packageManager.getLaunchIntentForPackage(PKG)?.let { return it }
        val main = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val hit = act.packageManager.queryIntentActivities(main, 0).firstOrNull {
            it.loadLabel(act.packageManager).toString().contains("LiveATC", true) || it.activityInfo.packageName.contains("liveatc", true)
        } ?: return null
        return act.packageManager.getLaunchIntentForPackage(hit.activityInfo.packageName)
    }

    /**
     * As ForeFlight does it: the LiveATC app beside the map in split screen, the map keeping its
     * track and traffic on one side, the tower or approach playing on the other.
     */
    fun open(act: Activity, icao: String) {
        if (icao.equals("KBVU", true)) {
            MaterialAlertDialogBuilder(act).setTitle("🎧 KBVU").setMessage(act.getString(R.string.atc_none, "KBVU"))
                .setPositiveButton("KHND") { _, _ -> open(act, "KHND") }.setNegativeButton(R.string.cancel, null).show()
            return
        }
        val app = liveAtc(act)
        if (app != null) {
            app.addFlags(Intent.FLAG_ACTIVITY_LAUNCH_ADJACENT or Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_MULTIPLE_TASK)
            try { act.startActivity(app) } catch (e: Exception) { app.flags = Intent.FLAG_ACTIVITY_NEW_TASK; act.startActivity(app) }
            android.widget.Toast.makeText(act, act.getString(R.string.atc_split, icao), android.widget.Toast.LENGTH_LONG).show()
        } else {
            MaterialAlertDialogBuilder(act).setTitle(R.string.atc_title).setMessage(R.string.atc_install)
                .setPositiveButton(R.string.atc_install_go) { _, _ ->
                    try { act.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("market://search?q=LiveATC&c=apps"))) }
                    catch (e: Exception) { act.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/store/search?q=LiveATC&c=apps"))) }
                }.setNegativeButton(R.string.cancel, null).show()
        }
    }
}
