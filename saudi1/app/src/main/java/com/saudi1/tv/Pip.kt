package com.saudi1.tv

import android.app.Activity
import android.app.PictureInPictureParams
import android.content.pm.PackageManager
import android.os.Build
import android.util.Rational
import java.lang.ref.WeakReference

/** The small floating window on phones and tablets (owner, 25 Nov 2026: "fix the PiP and make it an option in the
 *  list"). It opens only from the options menu, never by itself on Home, and there is only ever one: opening a
 *  channel or a film while the small window plays closes that window first (it used to stay and play on top of
 *  the new screen, two pictures and two connections at once). */
object Pip {
    private var cur: WeakReference<Activity>? = null

    fun can(a: Activity) = a.isTouch && Build.VERSION.SDK_INT >= 26 &&
        a.packageManager.hasSystemFeature(PackageManager.FEATURE_PICTURE_IN_PICTURE)

    fun enter(a: Activity): Boolean {
        if (!can(a)) return false
        return try {
            a.enterPictureInPictureMode(PictureInPictureParams.Builder().setAspectRatio(Rational(16, 9)).build())
            cur = WeakReference(a); true
        } catch (e: Exception) { false }
    }

    /** a new player screen opens: the small window (if another screen has it) is closed */
    fun closeOther(a: Activity) {
        cur?.get()?.takeIf { it !== a && !it.isFinishing }?.finish()
        cur = null
    }

    fun left(a: Activity) { if (cur?.get() === a) cur = null }
}
