package com.saudi1.tv

import android.content.Intent
import android.graphics.Typeface
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.core.content.FileProvider
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.Request
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Settings: account, picture, night dimming, clock, update, about. */
class SettingsActivity : BaseActivity() {
    private lateinit var list: LinearLayout
    private val d by lazy { resources.displayMetrics.density }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val scroll = ScrollView(this)
        list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding((60 * d).toInt(), (34 * d).toInt(), (60 * d).toInt(), (60 * d).toInt()) }
        scroll.addView(list)
        setContentView(scroll)
        build()
    }

    override fun onResume() { super.onResume(); build() }

    private fun build() {
        list.removeAllViews()
        list.addView(TextView(this).apply { text = "Settings"; textSize = 30f; setTypeface(typeface, Typeface.BOLD) })
        section("Account")
        val exp = if (Device.expires > 0) SimpleDateFormat("d MMM yyyy", Locale.ENGLISH).format(Date(Device.expires)) else "—"
        row("Device code", Device.pretty, null)
        row("Customer", Device.name.ifEmpty { "—" }, null)
        row("Playlist", Prefs.server.substringAfter("://").substringBefore('.').ifEmpty { "—" }, null)
        row("Subscription ends", exp, null)
        row("Change playlist / login", "Device code or Xtream login") { startActivity(Intent(this, SetupActivity::class.java)) }
        row("Reload channels", "Get the newest lists now") { reload() }

        section("Picture")
        val sizes = arrayOf("Fit", "Stretch", "Zoom"); val modes = intArrayOf(0, 3, 4)  // AspectRatioFrameLayout modes
        row("Picture size", sizes[modes.indexOf(App.prefs.getInt("resize", 0)).coerceAtLeast(0)]) {
            AlertDialog.Builder(this).setTitle("Picture size").setItems(sizes) { _, w -> App.prefs.edit().putInt("resize", modes[w]).apply(); build() }.show()
        }
        row("Night dimming", if (Dim.level == 0) "Off" else "${Dim.level} %") {
            AlertDialog.Builder(this).setTitle("Night dimming")
                .setSingleChoiceItems(Dim.levels.map { if (it == 0) "Off" else "$it %" }.toTypedArray(), Dim.levels.indexOf(Dim.level).coerceAtLeast(0)) { dlg, w ->
                    Dim.level = Dim.levels[w]; applyDim(); dlg.dismiss(); build()
                }.show()
        }
        val clock = App.prefs.getBoolean("clock", true)
        row("Clock on the picture", if (clock) "On" else "Off") { App.prefs.edit().putBoolean("clock", !clock).apply(); build() }
        val zapInvert = App.prefs.getBoolean("zap_invert", false)
        row("Channel change with ▲ / ▼", if (zapInvert) "▲ previous · ▼ next" else "▲ next · ▼ previous") {
            App.prefs.edit().putBoolean("zap_invert", !zapInvert).apply(); build()
        }

        section("Reminders")
        val rs = Reminders.all()
        row("Reminders", if (rs.isEmpty()) "None" else "${rs.size} set") {
            if (rs.isEmpty()) return@row
            val f = SimpleDateFormat("EEE h:mm a", Locale.ENGLISH)
            AlertDialog.Builder(this).setTitle("Tap to remove").setItems(rs.map { f.format(Date(it.start * 1000)) + "  " + it.title + "  ·  " + it.channelName }.toTypedArray()) { _, w ->
                Reminders.remove(rs[w]); build()
            }.show()
        }

        section("App")
        row("Version", BuildConfig.VERSION_NAME + "   ·   Check for update") { update() }
        row("Download link", "saudi1.1saifsaudi.workers.dev/apk", null)
    }

    private fun section(t: String) {
        list.addView(TextView(this).apply {
            text = t; textSize = 15f; setTextColor(getColor(R.color.accent)); setTypeface(typeface, Typeface.BOLD)
            setPadding((6 * d).toInt(), (24 * d).toInt(), 0, (8 * d).toInt())
        })
    }

    private fun row(title: String, value: String, go: (() -> Unit)?) {
        val r = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setBackgroundResource(R.drawable.item_bg); isFocusable = go != null; isClickable = go != null
            setPadding((18 * d).toInt(), 0, (18 * d).toInt(), 0)
            if (go != null) setOnClickListener { go() }
        }
        val a = TextView(this).apply { text = title; textSize = 17f; setTypeface(typeface, Typeface.BOLD); setTextColor(getColorStateList(R.color.on_focus)); isDuplicateParentStateEnabled = true }
        val b = TextView(this).apply { text = value; textSize = 15f; setTextColor(getColorStateList(R.color.on_focus2)); isDuplicateParentStateEnabled = true; gravity = Gravity.END }
        r.addView(a, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        r.addView(b, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1.3f))
        list.addView(r, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, (58 * d).toInt()).apply { bottomMargin = (6 * d).toInt() })
        if (list.findFocus() == null && go != null) r.post { if (list.findFocus() == null) r.requestFocus() }
    }

    private fun reload() {
        android.widget.Toast.makeText(this, "Loading…", android.widget.Toast.LENGTH_SHORT).show()
        lifecycleScope.launch {
            val ok = withContext(Dispatchers.IO) {
                if (!Device.manual) Device.check()
                try { Prefs.ready && Api.load(cached = false) } catch (e: Exception) { false }
            }
            val n = Api.groups.firstOrNull { it.id == Api.ALL }?.channels?.size ?: 0
            android.widget.Toast.makeText(this@SettingsActivity, if (ok) "Updated · $n channels" else "Could not reach the server", android.widget.Toast.LENGTH_LONG).show()
        }
    }

    /** newest build from the release (same link as Downloader); Android asks once to allow installing it */
    private fun update() {
        lifecycleScope.launch {
            val toast = { s: String -> android.widget.Toast.makeText(this@SettingsActivity, s, android.widget.Toast.LENGTH_LONG).show() }
            val newest = withContext(Dispatchers.IO) {
                try {
                    App.http.newCall(Request.Builder().url("https://github.com/Saudi23723/Unified-MENA-EPG/releases/download/saudi1/version.txt").build()).execute()
                        .use { it.body!!.string().trim().substringAfter("build ").toIntOrNull() ?: 0 }
                } catch (e: Exception) { -1 }
            }
            if (newest < 0) { toast("Could not check for updates"); return@launch }
            if (newest <= BuildConfig.VERSION_CODE) { toast("You have the newest version"); return@launch }
            toast("Downloading version 1.0.$newest…")
            val f = File(cacheDir, "update.apk")
            val ok = withContext(Dispatchers.IO) {
                try {
                    App.http.newCall(Request.Builder().url("https://github.com/Saudi23723/Unified-MENA-EPG/releases/download/saudi1/SAUDI1.apk").build()).execute()
                        .use { r -> if (!r.isSuccessful) false else { f.outputStream().use { o -> r.body!!.byteStream().copyTo(o) }; true } }
                } catch (e: Exception) { false }
            }
            if (!ok) { toast("Download failed"); return@launch }
            val uri = FileProvider.getUriForFile(this@SettingsActivity, "$packageName.files", f)
            startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK))
        }
    }
}
