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
    }

    // small memory cache: the Chromecast has 2 GB for everything (Dream froze from memory pressure)
    override fun newImageLoader(): ImageLoader = ImageLoader.Builder(this)
        .okHttpClient(http)
        .memoryCache { MemoryCache.Builder(this).maxSizeBytes(24 * 1024 * 1024).build() }
        .diskCache { DiskCache.Builder().directory(cacheDir.resolve("logos")).maxSizeBytes(64L * 1024 * 1024).build() }
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
                .addInterceptor { c -> c.proceed(c.request().newBuilder().header("User-Agent", "SAUDI.1/" + BuildConfig.VERSION_NAME).build()) }
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
