package com.saudi.privatevault

import android.content.Intent
import android.os.Bundle
import android.view.WindowManager
import androidx.appcompat.app.AppCompatActivity

/** Every vault screen: no screenshots, blank in the recent-apps list, PIN on return. */
open class BaseActivity : AppCompatActivity() {
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

    /** onResume, but only once the vault is open. */
    open fun onUnlockedResume() {}
}
