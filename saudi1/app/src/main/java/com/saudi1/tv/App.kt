package com.saudi1.tv

import android.app.Application
import android.content.Context
import android.content.SharedPreferences
import coil.ImageLoader
import coil.ImageLoaderFactory
import coil.disk.DiskCache
import coil.memory.MemoryCache
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

class App : Application(), ImageLoaderFactory {
    override fun onCreate() {
        super.onCreate()
        app = this
        prefs = getSharedPreferences("saudi1", Context.MODE_PRIVATE)
        // when the app stops by an error, what happened is kept (Settings › App › Last error) so it can be fixed
        val before = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { t, e ->
            try {
                val sw = java.io.StringWriter(); e.printStackTrace(java.io.PrintWriter(sw))
                java.io.File(filesDir, "last_error.txt").writeText(java.text.SimpleDateFormat("d MMM HH:mm", java.util.Locale.ENGLISH).format(java.util.Date()) +
                    "  ·  " + BuildConfig.VERSION_NAME + "\n" + sw.toString().take(6000))
            } catch (x: Throwable) { }
            before?.uncaughtException(t, e)
        }
        tidy()
        Backup.auto()
    }

    /** the cache is cleared by itself (owner, 10 Nov 2026), once a day: pictures not seen for 3 days, temp files, an old
     *  update file, lists of playlists no longer used; and everything of the pictures when they pass 350 MB.
     *  Favorites, Continue watching, settings, downloads and recordings are never touched. */
    fun tidy(force: Boolean = false, done: ((Long) -> Unit)? = null) {
        if (!force && System.currentTimeMillis() - prefs.getLong("tidy_at", 0) < 86400_000L) return
        prefs.edit().putLong("tidy_at", System.currentTimeMillis()).apply()
        Thread {
            var freed = 0L
            fun del(f: java.io.File) { val n = f.length(); if (f.delete()) freed += n }
            try {
                val now = System.currentTimeMillis()
                java.io.File(cacheDir, "update.apk").takeIf { it.isFile }?.let { del(it) }
                // the pictures: old ones always; all of them when they grew too big (or when asked by hand)
                val img = listOf(java.io.File(cacheDir, "img"), java.io.File(cacheDir, "logos"))
                val size = img.sumOf { d -> d.walkBottomUp().filter { it.isFile }.sumOf { it.length() } }
                for (d in img) d.walkBottomUp().forEach { if (it.isFile && (force || size > 350L * 1024 * 1024 || now - it.lastModified() > 3 * 86400_000L)) del(it) }
                if (force || size > 350L * 1024 * 1024) try { imageLoader.diskCache?.clear() } catch (e: Exception) { }
                java.io.File(cacheDir, "vod").walkBottomUp().forEach { if (it.isFile && now - it.lastModified() > 14 * 86400_000L) del(it) else if (it.isDirectory && it.list()?.isEmpty() == true) it.delete() }
                cacheDir.listFiles()?.forEach { if (it.isFile && (force || now - it.lastModified() > 3 * 86400_000L)) del(it) }
                if (force) try { imageLoader.memoryCache?.clear() } catch (e: Exception) { }
            } catch (e: Exception) { }
            done?.invoke(freed)
        }.start()
    }
    private val imageLoader by lazy { coil.Coil.imageLoader(this) }

    // small memory cache: the Chromecast has 2 GB for everything (Dream froze from memory pressure)
    override fun newImageLoader(): ImageLoader = ImageLoader.Builder(this)
        .okHttpClient(http)
        // posters kept decoded for the rows around (RGB 565: half the memory, the same look for pictures);
        // kept on disk too, so a group opened again shows its posters at once
        .memoryCache { MemoryCache.Builder(this).maxSizeBytes(48 * 1024 * 1024).build() }
        .allowRgb565(true)
        .diskCache { DiskCache.Builder().directory(cacheDir.resolve("img")).maxSizeBytes(250L * 1024 * 1024).build() }
        .crossfade(false)
        .respectCacheHeaders(false)
        .build()

    companion object {
        lateinit var app: App
        lateinit var prefs: SharedPreferences
        val http: OkHttpClient by lazy {
            OkHttpClient.Builder()
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(60, TimeUnit.SECONDS)
                .followRedirects(true).followSslRedirects(true)
                .addInterceptor { c -> c.proceed(c.request().newBuilder().header("User-Agent", "SAUDI.TV/" + BuildConfig.VERSION_NAME).build()) }
                .build()
        }
    }
}

object Prefs {
    var server: String
        get() = App.prefs.getString("server", "") ?: ""
        set(v) = App.prefs.edit().putString("server", v.trim().trimEnd('/')).apply()
    var user: String
        get() = App.prefs.getString("user", "") ?: ""
        set(v) = App.prefs.edit().putString("user", v.trim()).apply()
    var pass: String
        get() = App.prefs.getString("pass", "") ?: ""
        set(v) = App.prefs.edit().putString("pass", v.trim()).apply()
    var lastChannel: Int
        get() = App.prefs.getInt("last_channel", -1)
        set(v) = App.prefs.edit().putInt("last_channel", v).apply()
    var lastGroup: String
        get() = App.prefs.getString("last_group", "") ?: ""
        set(v) = App.prefs.edit().putString("last_group", v).apply()
    var favorites: Set<String>
        get() = App.prefs.getStringSet("favorites", emptySet()) ?: emptySet()
        set(v) = App.prefs.edit().putStringSet("favorites", HashSet(v)).apply()
    val ready get() = server.isNotEmpty() && user.isNotEmpty() && pass.isNotEmpty()

    /** "strong" for https://strong.1saifsaudi.workers.dev: the repo's guide files are read straight from GitHub */
    val playlist: String
        get() {
            val h = android.net.Uri.parse(server).host ?: return ""
            return if (h.endsWith(".1saifsaudi.workers.dev")) h.substringBefore('.') else ""
        }
}
