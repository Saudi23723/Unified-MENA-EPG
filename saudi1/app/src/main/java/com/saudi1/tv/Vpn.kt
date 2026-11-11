package com.saudi1.tv

import android.content.Context
import com.wireguard.android.backend.GoBackend
import com.wireguard.android.backend.Tunnel
import com.wireguard.config.Config

/** WireGuard VPN: the config the owner put on the admin site for this device (or a .conf file on a phone).
 *  When it is on, the app starts it by itself. */
object Vpn {
    private var backend: GoBackend? = null
    private val tunnel = object : Tunnel {
        override fun getName() = "saudi"
        override fun onStateChange(newState: Tunnel.State) { up = newState == Tunnel.State.UP }
    }
    @Volatile var up = false

    var conf: String
        get() = App.prefs.getString("vpn_conf", "") ?: ""
        set(v) = App.prefs.edit().putString("vpn_conf", v).apply()
    var wanted: Boolean
        get() = App.prefs.getBoolean("vpn_on", false)
        set(v) = App.prefs.edit().putBoolean("vpn_on", v).apply()

    fun valid(t: String) = Regex("(?i)\\[Interface]").containsMatchIn(t) && Regex("(?i)\\[Peer]").containsMatchIn(t) && Regex("(?i)PrivateKey\\s*=").containsMatchIn(t)

    /** the server name of the VPN (for Settings) */
    fun endpoint(): String = Regex("(?im)^\\s*Endpoint\\s*=\\s*(\\S+)").find(conf)?.groupValues?.get(1)?.substringBeforeLast(':') ?: ""

    private fun b(ctx: Context) = backend ?: GoBackend(ctx.applicationContext).also { backend = it }

    /** MTU 1280: smaller packets get through every network (hotel / airport Wi-Fi too), without them video gets stuck
     *  in the tunnel and keeps loading (owner, 11 Nov 2026: "with the VPN it is very bad") */
    private fun small(c: String): String {
        val noMtu = c.lines().filterNot { Regex("(?i)^\\s*MTU\\s*=").containsMatchIn(it) }.joinToString("\n")
        return noMtu.replaceFirst(Regex("(?i)\\[Interface]"), "[Interface]\nMTU = 1280")
    }

    /** null = connected, else the reason (run off the main thread) */
    fun start(ctx: Context): String? = try {
        if (conf.isBlank()) "No VPN on this device" else {
            b(ctx).setState(tunnel, Tunnel.State.UP, Config.parse(small(conf).byteInputStream()))
            up = true; null
        }
    } catch (e: Exception) { up = false; e.message ?: e.javaClass.simpleName }

    fun stop(ctx: Context) {
        try { b(ctx).setState(tunnel, Tunnel.State.DOWN, null) } catch (_: Exception) { }
        up = false
    }
}
