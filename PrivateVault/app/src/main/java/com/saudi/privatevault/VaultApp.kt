package com.saudi.privatevault

import android.app.Application
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner

class VaultApp : Application() {
    override fun onCreate() {
        super.onCreate()
        VaultStore.init(this)
        // The whole app counts as one session: leaving it for the home screen
        // or another app locks it again.
        ProcessLifecycleOwner.get().lifecycle.addObserver(object : DefaultLifecycleObserver {
            override fun onStop(owner: LifecycleOwner) {
                if (VaultLock.keepUnlockedOnce) {
                    VaultLock.keepUnlockedOnce = false
                } else {
                    VaultLock.unlocked = false
                }
            }
        })
    }
}
