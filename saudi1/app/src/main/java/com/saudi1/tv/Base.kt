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

class Reminder(val channel: Int, val start: Long, val title: String, val channelName: String)

/** Programs the viewer asked to be reminded of (like TiviMate): 10 seconds before the start a countdown shows. */
object Reminders {
    fun all(): List<Reminder> = try {
        val a = JSONArray(App.prefs.getString("reminders", "[]"))
        (0 until a.length()).map { a.getJSONObject(it) }.map {
            Reminder(it.getInt("c"), it.getLong("s"), it.optString("t"), it.optString("n"))
        }
    } catch (e: Exception) { emptyList() }

    private fun save(l: List<Reminder>) {
        val a = JSONArray()
        l.forEach { a.put(JSONObject().put("c", it.channel).put("s", it.start).put("t", it.title).put("n", it.channelName)) }
        App.prefs.edit().putString("reminders", a.toString()).apply()
    }

    fun has(c: Int, start: Long) = all().any { it.channel == c && it.start == start }

    /** true = now set, false = removed */
    fun toggle(r: Reminder): Boolean {
        val l = all().toMutableList()
        val i = l.indexOfFirst { it.channel == r.channel && it.start == r.start }
        if (i >= 0) { l.removeAt(i); save(l); return false }
        l.add(r); save(l); return true
    }

    fun remove(r: Reminder) = save(all().filterNot { it.channel == r.channel && it.start == r.start })

    /** reminders whose countdown should show now (start in 10 s or less, not older than 2 minutes) */
    fun due(): Reminder? {
        val t = System.currentTimeMillis() / 1000
        val l = all()
        l.filter { it.start < t - 120 }.forEach { remove(it) }
        return l.firstOrNull { it.start - t in -120..10 }
    }
}

/** Night dimming levels: 0, 20, 40, 60, 80 % */
object Dim {
    val levels = intArrayOf(0, 20, 30, 40, 50, 60, 70, 80)
    var level: Int
        get() = App.prefs.getInt("dim", 0)
        set(v) = App.prefs.edit().putInt("dim", v).apply()
    /** Eye comfort (warm screen, like Samsung's Eye Comfort Shield): 0 off, 1 low, 2 medium, 3 high */
    val warmNames = arrayOf("Off", "Low", "Medium", "High")
    val warmAlpha = floatArrayOf(0f, 0.10f, 0.17f, 0.25f)
    var warm: Int
        get() = App.prefs.getInt("warm", 0)
        set(v) = App.prefs.edit().putInt("warm", v).apply()
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
        watch = lifecycleScope.launch {
            while (isActive) {
                if (box == null) Reminders.due()?.let { show(it) }
                delay(2000)
            }
        }
    }

    override fun onPause() { super.onPause(); watch?.cancel() }

    /** night dimming + eye comfort, from any screen */
    fun nightDialog() {
        androidx.appcompat.app.AlertDialog.Builder(this).setTitle("Night mode")
            .setItems(arrayOf("Dimming: " + (if (Dim.level == 0) "Off" else "${Dim.level} %"), "Eye comfort: " + Dim.warmNames[Dim.warm])) { _, w ->
                if (w == 0) androidx.appcompat.app.AlertDialog.Builder(this).setTitle("Dimming")
                    .setSingleChoiceItems(Dim.levels.map { if (it == 0) "Off" else "$it %" }.toTypedArray(), Dim.levels.indexOf(Dim.level).coerceAtLeast(0)) { d, k ->
                        Dim.level = Dim.levels[k]; applyDim(); d.dismiss()
                    }.show()
                else androidx.appcompat.app.AlertDialog.Builder(this).setTitle("Eye comfort (warm screen)")
                    .setSingleChoiceItems(Dim.warmNames, Dim.warm) { d, k -> Dim.warm = k; applyDim(); d.dismiss() }.show()
            }.show()
    }

    private var warmView: View? = null

    fun applyDim() {
        val root = window.decorView as ViewGroup
        if (warmView == null) {
            warmView = View(this).apply { isClickable = false; isFocusable = false; setBackgroundColor(0xFFFF8A1E.toInt()) }
            root.addView(warmView, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        }
        warmView!!.alpha = Dim.warmAlpha[Dim.warm.coerceIn(0, 3)]
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
            var left = (r.start - System.currentTimeMillis() / 1000).coerceIn(0, 10)
            while (left > 0) { count.text = "Starts in $left s — switching automatically"; delay(1000); left-- }
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
