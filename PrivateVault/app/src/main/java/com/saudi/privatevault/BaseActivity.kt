package com.saudi.privatevault

import android.content.Intent
import android.os.Bundle
import android.view.WindowManager
import androidx.appcompat.app.AppCompatActivity

/** Every vault screen: no screenshots, blank in the recent-apps list, PIN on return. */
open class BaseActivity : AppCompatActivity() {
    companion object {
        /** Keep the screen on: always, never, or as each screen chooses (the map, the diagram). */
        fun keepScreen(act: android.app.Activity) {
            val f = WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
            when (VaultLock.prefs(act).getString("screen_on", "auto")) {
                "on" -> act.window.addFlags(f)
                "off" -> act.window.clearFlags(f)
            }
        }
    }

    /** Screens over a chart or a photo stay dark whatever the app's look. */
    protected open val alwaysDark = false

    private fun look() { if (alwaysDark) EfbUi.light = false else EfbUi.sync(this) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        look()
        VaultLock.applySecure(this)
    }

    override fun onResume() {
        super.onResume()
        look()
        keepScreen(this)
        EyeComfort.apply(this)
        VaultLock.applySecure(this)
        VaultLock.checkTimeout(this)
        if (!VaultLock.unlocked) {
            startActivity(
                Intent(this, LockActivity::class.java)
                    .addFlags(Intent.FLAG_ACTIVITY_NO_ANIMATION)
            )
        } else {
            // Back from the picker or another app: the one-time pass is spent either way.
            VaultLock.keepUnlockedOnce = false
            onUnlockedResume()
        }
    }

    /** The floating tools button (note, neon); off on screens where it would be in the way. */
    protected open val quickTools = true

    override fun onPostCreate(savedInstanceState: Bundle?) {
        super.onPostCreate(savedInstanceState)
        // No pens or notes on a television.
        if (quickTools && !Tv.isTv(this)) QuickTools.attach(this)
        // The flight bag's tab bar, as ForeFlight's, along the bottom.
        ForeTabs.attach(this)
    }

    /** onResume, but only once the vault is open. */
    open fun onUnlockedResume() {}
}
