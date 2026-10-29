package com.saudi.privatevault

import android.content.Context
import android.net.Uri
import android.os.Build
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.SocketTimeoutException
import java.net.URL

/** Talks to خزنتي on the laptop (PrivateVault/laptop/khazanti.py). Every call blocks: run it off the main thread. */
object LaptopClient {
    private const val DISCOVERY_PORT = 47802

    class Found(val url: String, val name: String)

    sealed class LoginResult {
        object Ok : LoginResult()
        object Wrong : LoginResult()
        class Wait(val seconds: Int) : LoginResult()
        object Unreachable : LoginResult()
    }

    class Index(val name: String, val folders: List<Folder>, val items: List<VaultItem>)

    class NotAuthorized : IOException("not authorized")

    fun url(ctx: Context): String? = VaultLock.prefs(ctx).getString("laptop_url", null)
    private fun token(ctx: Context): String? = VaultLock.prefs(ctx).getString("laptop_token", null)
    fun isLinked(ctx: Context) = url(ctx) != null && token(ctx) != null

    fun unlink(ctx: Context) {
        VaultLock.prefs(ctx).edit().remove("laptop_token").apply()
    }

    /** Typed addresses may lack the scheme or the port. */
    fun normalize(input: String): String {
        var s = input.trim().trimEnd('/')
        if (!s.startsWith("http://") && !s.startsWith("https://")) s = "http://$s"
        val uri = Uri.parse(s)
        if (uri.port == -1) s = "${uri.scheme}://${uri.host}:47801"
        return s
    }

    /** Asks the home network where the laptop is. */
    fun discover(): List<Found> {
        val found = mutableListOf<Found>()
        DatagramSocket().use { s ->
            s.broadcast = true
            s.soTimeout = 2500
            val msg = "KHAZNATI_DISCOVER".toByteArray()
            s.send(DatagramPacket(msg, msg.size, InetAddress.getByName("255.255.255.255"), DISCOVERY_PORT))
            val buf = ByteArray(256)
            val deadline = System.currentTimeMillis() + 2500
            while (System.currentTimeMillis() < deadline) {
                val p = DatagramPacket(buf, buf.size)
                try {
                    s.receive(p)
                } catch (e: SocketTimeoutException) {
                    break
                }
                val parts = String(p.data, 0, p.length, Charsets.UTF_8).split(" ", limit = 3)
                if (parts.size >= 2 && parts[0] == "KHAZNATI") {
                    val url = "http://${p.address.hostAddress}:${parts[1]}"
                    if (found.none { it.url == url }) found.add(Found(url, parts.getOrElse(2) { "" }))
                }
            }
        }
        return found
    }

    fun login(ctx: Context, url: String, password: String): LoginResult {
        val body = JSONObject().put("password", password).put("device", "${Build.MANUFACTURER} ${Build.MODEL}")
        val conn = open("$url/api/login", null)
        return try {
            conn.requestMethod = "POST"
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json")
            conn.outputStream.use { it.write(body.toString().toByteArray()) }
            when (conn.responseCode) {
                200 -> {
                    val token = JSONObject(conn.inputStream.bufferedReader().readText()).getString("token")
                    VaultLock.prefs(ctx).edit().putString("laptop_url", url).putString("laptop_token", token).apply()
                    LoginResult.Ok
                }
                403, 429 -> {
                    val wait = try {
                        JSONObject(conn.errorStream.bufferedReader().readText()).optInt("wait", 0)
                    } catch (e: Exception) {
                        0
                    }
                    if (wait > 0) LoginResult.Wait(wait) else LoginResult.Wrong
                }
                else -> LoginResult.Unreachable
            }
        } catch (e: IOException) {
            LoginResult.Unreachable
        } finally {
            conn.disconnect()
        }
    }

    fun index(ctx: Context): Index {
        val base = url(ctx) ?: throw NotAuthorized()
        val status = getJson(ctx, "$base/api/status")
        val json = getJson(ctx, "$base/api/index")
        val folders = mutableListOf<Folder>()
        val fa = json.getJSONArray("folders")
        for (i in 0 until fa.length()) {
            val o = fa.getJSONObject(i)
            folders.add(Folder(o.getString("id"), o.getString("name"), o.nullableString("parent"), o.optLong("created")))
        }
        val items = mutableListOf<VaultItem>()
        val ia = json.getJSONArray("items")
        for (i in 0 until ia.length()) {
            val o = ia.getJSONObject(i)
            items.add(
                VaultItem(
                    o.getString("id"), o.getString("name"), "", o.optString("mime"), o.optLong("size"),
                    o.optLong("added"), o.nullableString("folder"),
                )
            )
        }
        return Index(status.optString("name"), folders, items)
    }

    /** Address the player streams from; the token rides along because players cannot add headers. */
    fun fileUrl(ctx: Context, id: String): String =
        "${url(ctx)}/api/file/${Uri.encode(id)}?t=${Uri.encode(token(ctx) ?: "")}"

    /** Copies one laptop file to [target], reporting progress from 0 to 100. */
    fun download(ctx: Context, id: String, target: File, progress: (Int) -> Unit) {
        val conn = open(fileUrl(ctx, id), null)
        try {
            if (conn.responseCode == 401) throw NotAuthorized()
            if (conn.responseCode != 200) throw IOException("HTTP ${conn.responseCode}")
            val total = conn.contentLengthLong
            val tmp = File(target.path + ".part")
            conn.inputStream.use { inp ->
                tmp.outputStream().use { out ->
                    val buf = ByteArray(256 * 1024)
                    var done = 0L
                    var last = -1
                    while (true) {
                        val n = inp.read(buf)
                        if (n < 0) break
                        out.write(buf, 0, n)
                        done += n
                        val pct = if (total > 0) (done * 100 / total).toInt() else 0
                        if (pct != last) {
                            last = pct
                            progress(pct)
                        }
                    }
                }
            }
            if (!tmp.renameTo(target)) {
                tmp.delete()
                throw IOException("could not save")
            }
        } finally {
            conn.disconnect()
        }
    }

    private fun getJson(ctx: Context, url: String): JSONObject {
        val conn = open(url, token(ctx))
        try {
            if (conn.responseCode == 401) throw NotAuthorized()
            if (conn.responseCode != 200) throw IOException("HTTP ${conn.responseCode}")
            return JSONObject(conn.inputStream.bufferedReader().readText())
        } finally {
            conn.disconnect()
        }
    }

    private fun open(url: String, token: String?): HttpURLConnection {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 5000
        conn.readTimeout = 30000
        if (token != null) conn.setRequestProperty("Authorization", "Bearer $token")
        return conn
    }

    private fun JSONObject.nullableString(key: String): String? =
        if (isNull(key)) null else optString(key, "").ifEmpty { null }
}
