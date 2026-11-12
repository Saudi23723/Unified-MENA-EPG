package com.saudi.privatevault

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder

/**
 * Keeps the GPS and the flight recording going while the map is in the background or the screen
 * is off: a location service in the foreground, with its notification, as Android requires.
 * The map's own GPS listener goes on receiving fixes while this runs.
 */
class TrackingService : Service() {
    companion object {
        private const val CHANNEL = "tracking"

        /** Who needs the GPS kept alive (the map, an airport page): the service stops when none is left. */
        private val users = HashSet<String>()

        fun start(ctx: Context, who: String = "map") {
            users += who
            try {
                val i = Intent(ctx, TrackingService::class.java)
                if (Build.VERSION.SDK_INT >= 26) ctx.startForegroundService(i) else ctx.startService(i)
            } catch (e: Exception) { }
        }

        fun stop(ctx: Context, who: String = "map") {
            users -= who
            if (users.isNotEmpty()) return
            try { ctx.stopService(Intent(ctx, TrackingService::class.java)) } catch (e: Exception) { }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val nm = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26 && nm.getNotificationChannel(CHANNEL) == null) {
            nm.createNotificationChannel(NotificationChannel(CHANNEL, "Flight tracking", NotificationManager.IMPORTANCE_LOW))
        }
        val open = PendingIntent.getActivity(this, 0, Intent(this, MapActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE)
        val n: Notification = (if (Build.VERSION.SDK_INT >= 26) Notification.Builder(this, CHANNEL) else @Suppress("DEPRECATION") Notification.Builder(this))
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle("Pilot Companion")
            .setContentText("GPS tracking and flight recording are on")
            .setContentIntent(open)
            .setOngoing(true)
            .build()
        try {
            if (Build.VERSION.SDK_INT >= 29) startForeground(7, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION)
            else startForeground(7, n)
        } catch (e: Exception) {
            stopSelf()
        }
        return START_NOT_STICKY
    }
}
