package com.saudi1.tv

import android.content.Intent
import android.graphics.Color
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject

/** rec = 0: a reminder (the TV changes to the channel); rec > 0: record it by itself until that time (seconds) */
class Reminder(val channel: Int, val start: Long, val title: String, val channelName: String, val rec: Long = 0)

/** Programs the viewer asked to be reminded of (like TiviMate): a minute before the start a 10-second countdown shows, then the channel changes. */
object Reminders {
    fun all(): List<Reminder> = try {
        val a = JSONArray(App.prefs.getString("reminders", "[]"))
        (0 until a.length()).map { a.getJSONObject(it) }.map {
            Reminder(it.getInt("c"), it.getLong("s"), it.optString("t"), it.optString("n"), it.optLong("r"))
        }
    } catch (e: Exception) { emptyList() }

    private fun save(l: List<Reminder>) {
        val a = JSONArray()
        l.forEach { a.put(JSONObject().put("c", it.channel).put("s", it.start).put("t", it.title).put("n", it.channelName).put("r", it.rec)) }
        App.prefs.edit().putString("reminders", a.toString()).apply()
    }

    fun has(c: Int, start: Long) = all().any { it.channel == c && it.start == start }
    /** "⏰ " for a reminder, "⏺ " for a planned recording, "" for none */
    fun mark(c: Int, start: Long) = all().firstOrNull { it.channel == c && it.start == start }?.let { if (it.rec > 0) "⏺ " else "⏰ " } ?: ""

    /** true = now set, false = removed */
    fun toggle(r: Reminder): Boolean {
        val l = all().toMutableList()
        val i = l.indexOfFirst { it.channel == r.channel && it.start == r.start }
        if (i >= 0) { l.removeAt(i); save(l); return false }
        l.add(r); save(l); return true
    }

    fun remove(r: Reminder) = save(all().filterNot { it.channel == r.channel && it.start == r.start })

    /** reminders whose countdown should show now (a minute before the start, not older than 2 minutes) */
    fun due(): Reminder? {
        val t = System.currentTimeMillis() / 1000
        val l = all()
        l.filter { it.start < t - 120 }.forEach { remove(it) }
        return l.firstOrNull { it.start - t in -120..60 }
    }
}

/** Night dimming levels: 0, 20, 40, 60, 80 % */
object Dim {
    val levels = intArrayOf(0, 10, 20, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90)
    /** the level chosen by hand */
    var manual: Int
        get() = App.prefs.getInt("dim", 0)
        set(v) = App.prefs.edit().putInt("dim", v).apply()
    /** the level in use now: the night schedule's inside its hours, else the one chosen by hand */
    var level: Int
        get() = if (nightNow()) App.prefs.getInt("night_dim", 50) else manual
        set(v) { if (nightNow()) App.prefs.edit().putInt("night_dim", v).apply() else manual = v }

    // ---- night mode by the clock: between two times every day it turns on by itself, and off after
    var scheduled: Boolean
        get() = App.prefs.getBoolean("night_on", false)
        set(v) = App.prefs.edit().putBoolean("night_on", v).apply()
    /** minutes after midnight */
    var from: Int
        get() = App.prefs.getInt("night_from", 22 * 60)
        set(v) = App.prefs.edit().putInt("night_from", v).apply()
    var to: Int
        get() = App.prefs.getInt("night_to", 6 * 60)
        set(v) = App.prefs.edit().putInt("night_to", v).apply()
    fun nightNow(): Boolean {
        if (!scheduled) return false
        val c = java.util.Calendar.getInstance(); val m = c.get(java.util.Calendar.HOUR_OF_DAY) * 60 + c.get(java.util.Calendar.MINUTE)
        val a = from; val b = to
        return if (a == b) false else if (a < b) m in a until b else m >= a || m < b
    }
    fun clock(m: Int): String { val h = m / 60; return "%d:%02d %s".format(if (h % 12 == 0) 12 else h % 12, m % 60, if (h < 12) "AM" else "PM") }
    /** Eye comfort (warm screen, like Samsung's Eye Comfort Shield): 0 off, 1 low, 2 medium, 3 high */
    val warmNames = arrayOf("Off", "10 %", "15 %", "20 %", "25 %", "30 %", "35 %", "40 %", "45 %", "50 %", "55 %")
    val warmAlpha = floatArrayOf(0f, 0.06f, 0.09f, 0.12f, 0.15f, 0.18f, 0.21f, 0.24f, 0.27f, 0.30f, 0.33f)
    private fun warmManual(): Int {
        // the old three levels (Low / Medium / High) carried over to the new scale once
        if (!App.prefs.getBoolean("warm_v2", false)) {
            val o = App.prefs.getInt("warm", 0)
            App.prefs.edit().putInt("warm", intArrayOf(0, 2, 5, 7).getOrElse(o) { 0 }).putBoolean("warm_v2", true).apply()
        }
        return App.prefs.getInt("warm", 0).coerceIn(0, warmNames.size - 1)
    }
    var warm: Int
        get() { val m = warmManual(); return if (nightNow()) App.prefs.getInt("night_warm", 4).coerceIn(0, warmNames.size - 1) else m }
        set(v) { warmManual(); if (nightNow()) App.prefs.edit().putInt("night_warm", v).apply() else App.prefs.edit().putInt("warm", v).apply() }
}

/** Parental lock: a 4-digit PIN guards the adult groups (found by name) and any group the owner of the TV locks. */
object Parental {
    private val adult = Regex("(?i)\\b(xxx|adult|adults|18\\+|\\+18|for adults|porn|erotic)\\b|للكبار")
    var pin: String
        get() = App.prefs.getString("pin", "") ?: ""
        set(v) = App.prefs.edit().putString("pin", v).apply()
    val on get() = pin.length == 4
    var locked: Set<String>
        get() = App.prefs.getStringSet("locked_groups", emptySet()) ?: emptySet()
        set(v) = App.prefs.edit().putStringSet("locked_groups", v).apply()
    @Volatile var unlocked = false      // until the app is closed
    fun isLocked(groupId: String, groupName: String) = on && !unlocked && (groupId in locked || adult.containsMatchIn(groupName))

    /** asks for the PIN, then runs ok() */
    fun ask(a: android.app.Activity, ok: () -> Unit) {
        if (!on || unlocked) { ok(); return }
        val e = android.widget.EditText(a).apply {
            inputType = android.text.InputType.TYPE_CLASS_NUMBER or android.text.InputType.TYPE_NUMBER_VARIATION_PASSWORD
            filters = arrayOf(android.text.InputFilter.LengthFilter(4)); hint = "PIN"; gravity = Gravity.CENTER; textSize = 26f
        }
        val d = androidx.appcompat.app.AlertDialog.Builder(a).setTitle("🔒  Locked — enter the PIN").setView(e)
            .setPositiveButton("OK") { _, _ ->
                if (e.text.toString() == pin) { unlocked = true; ok() }
                else android.widget.Toast.makeText(a, "Wrong PIN", android.widget.Toast.LENGTH_SHORT).show()
            }.setNegativeButton("Cancel", null).create()
        d.show(); e.requestFocus()
    }
}

/** phone / tablet (touch screen, no remote) instead of a TV */
val android.content.Context.isTouch: Boolean
    get() = !packageManager.hasSystemFeature("android.software.leanback") &&
        packageManager.hasSystemFeature("android.hardware.touchscreen")

/** Every screen: night dimming on top, and the reminder countdown. */
open class BaseActivity : AppCompatActivity() {
    companion object {
        private var started = 0
        /** the app was in the background (HOME, another app, TV off) and is coming back */
        @Volatile var cameBack = false
        private var wasHidden = false
    }
    override fun onStart() { super.onStart(); if (started++ == 0 && wasHidden) cameBack = true; wasHidden = false }
    override fun onStop() { super.onStop(); if (--started == 0) wasHidden = true }

    private var dimView: View? = null
    private var box: View? = null
    private var watch: Job? = null
    private var counting: Job? = null
    private var current: Reminder? = null
    val overlayOpen get() = box != null

    override fun onResume() {
        super.onResume()
        // the app opened again from the TV's home screen: it starts on the SAUDI.TV home page (owner, 4 Nov 2026),
        // unless "Start on the last channel" is on in Settings
        if (cameBack && this !is HomeActivity) {
            cameBack = false
            if (!App.prefs.getBoolean("open_last", false)) {
                startActivity(Intent(this, HomeActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP))
            }
        }
        applyDim()
        if (isTouch) fullScreen()
        watch = lifecycleScope.launch {
            var night = Dim.nightNow()
            while (isActive) {
                if (box == null) Reminders.due()?.let { r ->
                    if (r.rec <= 0) show(r)
                    else {
                        // a planned recording: it starts by itself, the viewer keeps watching what is on
                        Reminders.remove(r)
                        val c = Api.byId[r.channel]
                        val t = when { c == null -> "Could not record ${r.title}: the channel is not in this playlist"; Recorder.current != null -> "Could not record ${r.title}: another recording is running"
                            else -> { Recorder.start(this@BaseActivity, c, r.rec * 1000 + 120_000); "⏺ Recording ${r.title}" } }
                        android.widget.Toast.makeText(this@BaseActivity, t, android.widget.Toast.LENGTH_LONG).show()
                    }
                }
                // the night schedule starts / ends while a screen is open
                val n = Dim.nightNow(); if (n != night) { night = n; applyDim() }
                delay(2000)
            }
        }
    }

    override fun onPause() { super.onPause(); watch?.cancel() }

    /** phones and tablets: the whole screen (no status bar, no navigation / task bar); a swipe from the edge shows them for a moment */
    private fun fullScreen() {
        try {
            if (android.os.Build.VERSION.SDK_INT >= 28) window.attributes = window.attributes.apply { layoutInDisplayCutoutMode = android.view.WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES }
            androidx.core.view.WindowCompat.setDecorFitsSystemWindows(window, false)
            androidx.core.view.WindowInsetsControllerCompat(window, window.decorView).apply {
                systemBarsBehavior = androidx.core.view.WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
                hide(androidx.core.view.WindowInsetsCompat.Type.systemBars())
            }
        } catch (e: Exception) { }
    }
    override fun onWindowFocusChanged(hasFocus: Boolean) { super.onWindowFocusChanged(hasFocus); if (hasFocus && isTouch) fullScreen() }

    /** night dimming + eye comfort, from any screen */
    fun nightDialog() {
        androidx.appcompat.app.AlertDialog.Builder(this).setTitle("Night mode")
            .setItems(arrayOf("Dimming: " + (if (Dim.level == 0) "Off" else "${Dim.level} %"), "Eye comfort: " + Dim.warmNames[Dim.warm],
                "At a set time: " + if (Dim.scheduled) Dim.clock(Dim.from) + " – " + Dim.clock(Dim.to) else "Off")) { _, w ->
                if (w == 2) { nightSchedule(); return@setItems }
                if (w == 0) androidx.appcompat.app.AlertDialog.Builder(this).setTitle("Dimming")
                    .setSingleChoiceItems(Dim.levels.map { if (it == 0) "Off" else "$it %" }.toTypedArray(), Dim.levels.indexOf(Dim.level).coerceAtLeast(0)) { d, k ->
                        Dim.level = Dim.levels[k]; applyDim(); d.dismiss()
                    }.show()
                else androidx.appcompat.app.AlertDialog.Builder(this).setTitle("Eye comfort (warm screen)")
                    .setSingleChoiceItems(Dim.warmNames, Dim.warm) { d, k -> Dim.warm = k; applyDim(); d.dismiss() }.show()
            }.show()
    }

    /** night mode by the clock: on / off, from, until; the dimming and eye comfort chosen during those hours are the night's */
    fun nightSchedule() {
        val times = (0 until 48).map { it * 30 }
        fun pick(title: String, now: Int, done: (Int) -> Unit) = androidx.appcompat.app.AlertDialog.Builder(this).setTitle(title)
            .setSingleChoiceItems(times.map { Dim.clock(it) }.toTypedArray(), times.indexOf(now).coerceAtLeast(0)) { d, k -> done(times[k]); d.dismiss(); applyDim(); nightSchedule() }.show()
        androidx.appcompat.app.AlertDialog.Builder(this).setTitle("Night mode at a set time")
            .setItems(arrayOf(if (Dim.scheduled) "On  (turn off)" else "Off  (turn on)", "From: " + Dim.clock(Dim.from), "Until: " + Dim.clock(Dim.to),
                "Night dimming: " + App.prefs.getInt("night_dim", 50) + " %", "Night eye comfort: " + Dim.warmNames[App.prefs.getInt("night_warm", 4).coerceIn(0, Dim.warmNames.size - 1)])) { _, w ->
                when (w) {
                    0 -> { Dim.scheduled = !Dim.scheduled; applyDim(); nightSchedule() }
                    1 -> pick("From", Dim.from) { Dim.from = it }
                    2 -> pick("Until", Dim.to) { Dim.to = it }
                    3 -> androidx.appcompat.app.AlertDialog.Builder(this).setTitle("Night dimming")
                        .setSingleChoiceItems(Dim.levels.map { if (it == 0) "Off" else "$it %" }.toTypedArray(), Dim.levels.indexOf(App.prefs.getInt("night_dim", 50)).coerceAtLeast(0)) { d, k ->
                            App.prefs.edit().putInt("night_dim", Dim.levels[k]).apply(); d.dismiss(); applyDim(); nightSchedule() }.show()
                    4 -> androidx.appcompat.app.AlertDialog.Builder(this).setTitle("Night eye comfort")
                        .setSingleChoiceItems(Dim.warmNames, App.prefs.getInt("night_warm", 4).coerceIn(0, Dim.warmNames.size - 1)) { d, k ->
                            App.prefs.edit().putInt("night_warm", k).apply(); d.dismiss(); applyDim(); nightSchedule() }.show()
                }
            }.show()
    }

    private var warmView: View? = null

    fun applyDim() {
        val root = window.decorView as ViewGroup
        if (warmView == null) {
            warmView = View(this).apply { isClickable = false; isFocusable = false; setBackgroundColor(0xFFFF8A1E.toInt()) }
            root.addView(warmView, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        }
        warmView!!.alpha = Dim.warmAlpha[Dim.warm.coerceIn(0, Dim.warmAlpha.size - 1)]
        warmView!!.visibility = if (Dim.warm > 0) View.VISIBLE else View.GONE
        warmView!!.bringToFront()
        if (dimView == null) {
            dimView = View(this).apply { isClickable = false; isFocusable = false; setBackgroundColor(Color.BLACK) }
            root.addView(dimView, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        }
        dimView!!.alpha = Dim.level / 100f
        dimView!!.visibility = if (Dim.level > 0) View.VISIBLE else View.GONE
        dimView!!.bringToFront()
    }

    /** a coming programme: remind me / record it by itself / take the plan off */
    fun planDialog(c: Channel, start: Long, stop: Long, title: String, after: () -> Unit) {
        val had = Reminders.all().firstOrNull { it.channel == c.id && it.start == start }
        val f = java.text.SimpleDateFormat("h:mm a", java.util.Locale.ENGLISH)
        val items = if (had != null) arrayOf(if (had.rec > 0) "✕  Do not record it" else "✕  Remove the reminder")
            else arrayOf("⏰  Remind me (the TV changes to it a minute before)", "⏺  Record it by itself (${f.format(java.util.Date(start * 1000))} – ${f.format(java.util.Date(stop * 1000))})")
        androidx.appcompat.app.AlertDialog.Builder(this).setTitle(title + "   ·   " + c.name).setItems(items) { _, w ->
            if (had != null) { Reminders.remove(had); android.widget.Toast.makeText(this, "Removed", android.widget.Toast.LENGTH_SHORT).show() }
            else {
                Reminders.toggle(Reminder(c.id, start, title, c.name, if (w == 1) stop else 0))
                android.widget.Toast.makeText(this, if (w == 1) "⏺ It will be recorded — keep SAUDI.TV open (Settings › Recordings)" else "⏰ Reminder set", android.widget.Toast.LENGTH_LONG).show()
            }
            after()
        }.show()
    }

    /** the reminder was accepted: the screen that shows TV tunes to the channel */
    open fun tuneTo(channel: Int) {
        startActivity(Intent(this, LiveActivity::class.java).putExtra("channel", channel).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT))
    }

    private fun show(r: Reminder) {
        val root = window.decorView as ViewGroup
        val d = resources.displayMetrics.density
        val title = TextView(this).apply { textSize = 22f; setTypeface(typeface, android.graphics.Typeface.BOLD); text = r.title }
        val sub = TextView(this).apply { textSize = 16f; setTextColor(getColor(R.color.text2)); text = r.channelName }
        val count = TextView(this).apply { textSize = 16f; setPadding(0, (8 * d).toInt(), 0, (12 * d).toInt()) }
        fun button(t: String, primary: Boolean, go: () -> Unit) = TextView(this).apply {
            text = t; textSize = 17f; gravity = Gravity.CENTER; isFocusable = true; isClickable = true
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setBackgroundResource(if (primary) R.drawable.tile_bg else R.drawable.item_bg)
            setTextColor(getColorStateList(R.color.on_focus))
            setPadding((22 * d).toInt(), (12 * d).toInt(), (22 * d).toInt(), (12 * d).toInt())
            setOnClickListener { go() }
        }
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setBackgroundResource(R.drawable.panel_bg)
            setPadding((26 * d).toInt(), (22 * d).toInt(), (26 * d).toInt(), (22 * d).toInt())
        }
        val buttons = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        lateinit var watchB: TextView
        current = r
        fun close() { counting?.cancel(); root.removeView(box); box = null; current = null; Reminders.remove(r) }
        watchB = button("Watch now", true) { close(); tuneTo(r.channel) }
        val cancel = button("Cancel", false) { close() }
        buttons.addView(watchB); buttons.addView(View(this), LinearLayout.LayoutParams((14 * d).toInt(), 1)); buttons.addView(cancel)
        panel.addView(TextView(this).apply { text = "⏰  Reminder"; textSize = 15f; setTextColor(getColor(R.color.accent)) })
        panel.addView(title); panel.addView(sub); panel.addView(count); panel.addView(buttons)
        val wrap = FrameLayout(this).apply { setBackgroundColor(0x88000000.toInt()); isClickable = true }
        wrap.addView(panel, FrameLayout.LayoutParams((560 * d).toInt(), ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.CENTER))
        root.addView(wrap, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        box = wrap
        dimView?.bringToFront()
        watchB.requestFocus()
        counting = lifecycleScope.launch {
            // a minute before the start: ten seconds to say no, then the channel changes (the start is not missed)
            var left = if (r.start > System.currentTimeMillis() / 1000) 10L else 3L
            while (left > 0) { count.text = "Switching in $left s"; delay(1000); left-- }
            close(); tuneTo(r.channel)
        }
    }

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (box != null && event.keyCode == KeyEvent.KEYCODE_BACK) {
            if (event.action == KeyEvent.ACTION_UP) {
                counting?.cancel(); (window.decorView as ViewGroup).removeView(box); box = null
                current?.let { Reminders.remove(it) }; current = null
            }
            return true
        }
        return super.dispatchKeyEvent(event)
    }
}
