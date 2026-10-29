package com.saudi.privatevault

import android.content.Intent
import android.os.Bundle
import android.view.WindowManager
import androidx.appcompat.app.AppCompatActivity

/** Every vault screen: no screenshots, blank in the recent-apps list, PIN on return. */
open class BaseActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
    }

    override fun onResume() {
        super.onResume()
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
