package com.saudi.privatevault

import android.app.UiModeManager
import android.content.Context
import android.content.res.Configuration

/** Running on a television (Chromecast with Google TV, Android TV): a remote, no touch. */
object Tv {
    fun isTv(ctx: Context): Boolean {
        val ui = ctx.getSystemService(Context.UI_MODE_SERVICE) as? UiModeManager
        return ui?.currentModeType == Configuration.UI_MODE_TYPE_TELEVISION ||
            !ctx.packageManager.hasSystemFeature("android.hardware.touchscreen")
    }
}
