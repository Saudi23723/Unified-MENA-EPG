package com.saudi.privatevault

import android.app.Application
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner

class VaultApp : Application() {
    override fun onCreate() {
        super.onCreate()
        VaultStore.init(this)
        // The whole app counts as one session: leaving it starts the lock's
        // countdown, and coming back after it ran out asks for the PIN.
        ProcessLifecycleOwner.get().lifecycle.addObserver(object : DefaultLifecycleObserver {
            override fun onStop(owner: LifecycleOwner) {
                if (VaultLock.keepUnlockedOnce) {
                    VaultLock.keepUnlockedOnce = false
                } else {
                    VaultLock.leftAt = System.currentTimeMillis()
                }
            }
        })
    }
}
