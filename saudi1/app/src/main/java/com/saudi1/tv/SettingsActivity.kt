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
        row("Night mode", (if (Dim.level == 0) "Dimming off" else "Dimming ${Dim.level} %") + " · Eye comfort " + Dim.warmNames[Dim.warm]) {
            nightDialog()
        }
        val clock = App.prefs.getBoolean("clock", true)
        row("Clock on the picture", if (clock) "On" else "Off") { App.prefs.edit().putBoolean("clock", !clock).apply(); build() }
        val openLast = App.prefs.getBoolean("open_last", false)
        row("Start on the last channel", if (openLast) "On" else "Off") { App.prefs.edit().putBoolean("open_last", !openLast).apply(); build() }
        val zapInvert = App.prefs.getBoolean("zap_invert", false)
        row("Channel change with ▲ / ▼", if (zapInvert) "▲ previous · ▼ next" else "▲ next · ▼ previous") {
            App.prefs.edit().putBoolean("zap_invert", !zapInvert).apply(); build()
        }

        section("VPN")
        row("VPN (WireGuard)", when {
            Vpn.conf.isBlank() -> "Not set · the owner adds it on the admin site"
            Vpn.up -> "🛡 On · " + Vpn.endpoint()
            else -> "Off · " + Vpn.endpoint()
        }) { vpnToggle() }
        if (isTouch) row("Import a VPN file", "A WireGuard .conf file from your VPN provider") {
            startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*"), 11)
        }

        section("Parental lock")
        row("PIN lock", if (Parental.on) "On · adult groups are locked" else "Off") { pinDialog() }
        if (Parental.on) row("Lock / unlock groups", "${Parental.locked.size} chosen groups") {
            Parental.ask(this) {
                val gs = Api.groups.filter { it.id != Api.FAV && it.id != Api.ALL && it.id != Api.SEARCH }
                val chk = gs.map { it.id in Parental.locked }.toBooleanArray()
                AlertDialog.Builder(this).setTitle("Locked groups").setMultiChoiceItems(gs.map { it.name }.toTypedArray(), chk) { _, w, c -> chk[w] = c }
                    .setPositiveButton("Save") { _, _ -> Parental.locked = gs.filterIndexed { i, _ -> chk[i] }.map { it.id }.toSet(); build() }.show()
            }
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

        section("Recordings")
        val recs = Recordings.all(this)
        row("Recordings", (if (Recorder.current != null) "⏺ recording now · " else "") + if (recs.isEmpty()) "None" else "${recs.size}") {
            if (recs.isEmpty()) return@row
            AlertDialog.Builder(this).setTitle("Recordings").setItems(recs.map { it.nameWithoutExtension + "   ·   %.1f GB".format(it.length() / 1e9) }.toTypedArray()) { _, w ->
                val f = recs[w]
                AlertDialog.Builder(this).setTitle(f.nameWithoutExtension).setItems(arrayOf("▶ Play", "🗑 Delete")) { _, a ->
                    if (a == 0) startActivity(Intent(this, PlayerActivity::class.java).putExtra("url", android.net.Uri.fromFile(f).toString()).putExtra("title", f.nameWithoutExtension).putExtra("key", "r" + f.name))
                    else { f.delete(); build() }
                }.show()
            }.show()
        }
        if (Recorder.current != null) row("Stop recording", Recorder.current ?: "") { Recorder.stop(this); build() }

        section("App")
        row("Version", BuildConfig.VERSION_NAME + "   ·   Check for update") { update() }
        row("Download link", "saudi1.1saifsaudi.workers.dev/apk", null)
    }

    private fun vpnToggle() {
        if (Vpn.conf.isBlank()) { android.widget.Toast.makeText(this, "No VPN yet: the owner adds it to this device on the admin site, then Reload", android.widget.Toast.LENGTH_LONG).show(); return }
        if (Vpn.up) {
            Vpn.wanted = false
            lifecycleScope.launch { withContext(Dispatchers.IO) { Vpn.stop(this@SettingsActivity) }; build() }
            return
        }
        val ask = android.net.VpnService.prepare(this)
        if (ask != null) startActivityForResult(ask, 10) else vpnStart()
    }

    private fun vpnStart() {
        android.widget.Toast.makeText(this, "Connecting the VPN…", android.widget.Toast.LENGTH_SHORT).show()
        lifecycleScope.launch {
            val err = withContext(Dispatchers.IO) { Vpn.start(this@SettingsActivity) }
            Vpn.wanted = err == null
            android.widget.Toast.makeText(this@SettingsActivity, if (err == null) "🛡 VPN on" else "VPN failed: $err", android.widget.Toast.LENGTH_LONG).show()
            build()
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(req: Int, res: Int, data: Intent?) {
        super.onActivityResult(req, res, data)
        if (req == 10 && res == RESULT_OK) vpnStart()
        if (req == 11 && res == RESULT_OK) data?.data?.let { uri ->
            val t = try { contentResolver.openInputStream(uri)?.use { it.readBytes().decodeToString() } ?: "" } catch (e: Exception) { "" }
            if (!Vpn.valid(t)) { android.widget.Toast.makeText(this, "This is not a WireGuard .conf file", android.widget.Toast.LENGTH_LONG).show(); return@let }
            Vpn.conf = t; build(); vpnToggle()
        }
    }

    private fun pinDialog() {
        val e = android.widget.EditText(this).apply {
            inputType = android.text.InputType.TYPE_CLASS_NUMBER or android.text.InputType.TYPE_NUMBER_VARIATION_PASSWORD
            filters = arrayOf(android.text.InputFilter.LengthFilter(4)); hint = "4 digits"; gravity = Gravity.CENTER; textSize = 26f
        }
        val set = { AlertDialog.Builder(this).setTitle("New PIN (4 digits)").setView(e).setPositiveButton("Save") { _, _ ->
            val p = e.text.toString(); if (p.length == 4) { Parental.pin = p; Parental.unlocked = false; build() } }.setNeutralButton("Turn off") { _, _ -> Parental.pin = ""; build() }.show() }
        if (Parental.on) Parental.ask(this) { set() } else set()
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
