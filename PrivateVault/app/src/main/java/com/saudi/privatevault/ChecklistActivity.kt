package com.saudi.privatevault

import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.google.android.material.button.MaterialButton
import com.google.android.material.dialog.MaterialAlertDialogBuilder

/**
 * Checklists as an electronic flight bag keeps them: two panels.
 *
 * On the left the pilot moves about — the three groups across the top (Normal, Abnormal,
 * Emergency), the subgroups under them as grey headings (PREFLIGHT, IN FLIGHT…), and the lists
 * themselves, each with a dot showing how far through it is. On the right are that list's own
 * items: the grey detail lines that name a part of the aeroplane, and under them the check items,
 * each with what to do written on its right. The item in hand is lit; a tick fills it in and the
 * next one lights. Along the bottom: Reset, Speak, Skip, Check.
 *
 * On a narrow screen the two panels take turns: the lists, then the items with a way back.
 */
class ChecklistActivity : BaseActivity() {

    /** One line of a list: a detail (a heading inside the list) or a check item with its action. */
    private class Item(val title: String, val action: String, val detail: Boolean, val note: String? = null)

    /** One list: its name, the subgroup and group it belongs to, and its items. */
    private class Lst(val name: String, val sub: String, val group: Int, val items: List<Item>) {
        val key get() = "$group|$sub|$name"
    }

    private val prefs get() = VaultLock.prefs(this)
    private var aircraft = "SportStar MAX"
    private val done = HashSet<String>()
    private val skipped = HashSet<String>()
    private var group = 0
    private var open: Lst? = null
    private var lists: List<Lst> = emptyList()
    private var speaking = false
    private var tts: android.speech.tts.TextToSpeech? = null

    private lateinit var rootBox: LinearLayout
    private lateinit var leftPanel: LinearLayout
    private lateinit var rightPanel: LinearLayout
    private var wide = false

    private fun dp(v: Int) = EfbUi.dp(this, v)

    private val navy = 0xFF1B2A3A.toInt()
    private val panelBg = 0xFF0E1419.toInt()
    private val rowBg = 0xFF161D25.toInt()
    private val lit = 0xFF0A84FF.toInt()
    private val grey = 0xFF8A94A0.toInt()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = navy
        window.navigationBarColor = panelBg
        if (!prefs.getBoolean("ck_athene_shown", false)) prefs.edit().putBoolean("ck_athene_shown", true).putString("ck_aircraft", ATHENE).apply()
        aircraft = prefs.getString("ck_aircraft", ATHENE)!!.let { if (it == "SportStar") "SportStar MAX" else it }
        load()
        wide = resources.configuration.screenWidthDp >= 680
        rootBox = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setBackgroundColor(panelBg); layoutDirection = View.LAYOUT_DIRECTION_LTR }
        leftPanel = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(0xFF121A22.toInt()) }
        rightPanel = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(panelBg) }
        if (wide) {
            rootBox.addView(leftPanel, LinearLayout.LayoutParams(dp(300), -1))
            rootBox.addView(View(this).apply { setBackgroundColor(0xFF263340.toInt()) }, LinearLayout.LayoutParams(1, -1))
            rootBox.addView(rightPanel, LinearLayout.LayoutParams(0, -1, 1f))
        } else {
            rootBox.addView(leftPanel, LinearLayout.LayoutParams(0, -1, 1f))
            rootBox.addView(rightPanel, LinearLayout.LayoutParams(0, -1, 1f).apply { })
        }
        setContentView(rootBox)
        androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(rootBox) { _, ins ->
            val bars = ins.getInsets(androidx.core.view.WindowInsetsCompat.Type.systemBars())
            rootBox.setPadding(0, bars.top, 0, bars.bottom); ins
        }
        parse()
        if (intent.getBooleanExtra("emergency", false)) {
            group = 2
            open = lists.firstOrNull { it.group == 2 }
        } else open = lists.firstOrNull { it.group == group && !allDone(it) } ?: lists.firstOrNull { it.group == group }
        paint()
    }

    override fun onDestroy() {
        super.onDestroy()
        try { tts?.stop(); tts?.shutdown() } catch (e: Exception) { }
    }

    override fun onBackPressed() {
        if (!wide && rightShown) { rightShown = false; paint() } else @Suppress("DEPRECATION") super.onBackPressed()
    }

    private var rightShown = false

    // ---- the checklist text, turned into groups, subgroups and lists ----

    private fun text(): String = prefs.getString("ck_$aircraft", null) ?: when (aircraft) {
        "C172" -> C172
        ATHENE -> ATHENEAIR
        else -> SPORTSTAR
    }

    /** Which of the three groups a list belongs to, by what its name says. */
    private fun groupOf(name: String): Int {
        val u = name.uppercase()
        return when {
            u.contains("EMERGENC") || u.contains("ENGINE FAILURE") || u.contains("FIRE") || u.contains("SPIN") ||
                u.contains("FORCED") || u.contains("DITCH") || u.contains("EVACUAT") -> 2
            u.contains("ABNORMAL") || u.contains("MALFUNCTION") || u.contains("FAILURE") || u.contains("ICING") ||
                u.contains("ALTERNATOR") || u.contains("VOLTAGE") || u.contains("ROUGH") -> 1
            else -> 0
        }
    }

    /** Which part of the flight a list sits in, so the left panel can gather them under headings. */
    private fun subOf(name: String): String {
        val u = name.uppercase()
        return when {
            u.contains("SPEED") || u.contains("REFERENCE") || u.contains("LIMIT") || u.contains("WEIGHT") -> "REFERENCE"
            u.contains("PREFLIGHT") || u.contains("WALK") || u.contains("BEFORE START") || u.contains("BEFORE ENGINE") ||
                u.contains("START") || u.contains("COCKPIT") -> "PREFLIGHT"
            u.contains("TAXI") || u.contains("RUN-UP") || u.contains("RUNUP") || u.contains("BEFORE TAKEOFF") ||
                u.contains("TAKEOFF") || u.contains("DEPART") -> "TAKEOFF"
            u.contains("CLIMB") || u.contains("CRUISE") || u.contains("ENROUTE") || u.contains("EN ROUTE") -> "IN FLIGHT"
            u.contains("DESCEN") || u.contains("APPROACH") || u.contains("LANDING") || u.contains("PATTERN") -> "ARRIVAL"
            u.contains("AFTER LANDING") || u.contains("SHUT") || u.contains("POST") || u.contains("SECUR") || u.contains("PARK") -> "POST FLIGHT"
            else -> "OTHER"
        }
    }

    /**
     * The text, read into lists. A line beginning with # opens a list; a line beginning with > is a
     * detail heading inside it; "item .. action" is a check item; an indented line is a note on the
     * item above it. Anything written for the older format still reads the same way.
     */
    private fun parse() {
        val out = ArrayList<Lst>()
        var name = ""
        var items = ArrayList<Item>()
        fun flush() {
            if (name.isNotEmpty() && items.isNotEmpty()) out.add(Lst(name, subOf(name), groupOf(name), items))
        }
        for (raw in text().lines()) {
            val line = raw.trimEnd()
            if (line.isBlank()) continue
            val t = line.trim()
            when {
                t.startsWith("#") -> { flush(); name = t.trimStart('#').trim(); items = ArrayList() }
                t.startsWith(">") -> items.add(Item(t.trimStart('>').trim(), "", true))
                t.contains("..") -> {
                    val title = t.substringBefore("..").trim(' ', '·')
                    val action = t.substringAfter("..").trim()
                    items.add(Item(title, action, false))
                }
                raw.startsWith("  ") && items.isNotEmpty() -> {
                    val last = items.removeAt(items.size - 1)
                    items.add(Item(last.title, last.action, last.detail, ((last.note ?: "") + " " + t).trim()))
                }
                else -> items.add(Item(t, "", true))
            }
        }
        flush()
        lists = out
    }

    private fun itemKey(l: Lst, i: Int) = "${l.key}#$i"
    private fun allDone(l: Lst) = l.items.withIndex().filter { !it.value.detail }
        .all { done.contains(itemKey(l, it.index)) || skipped.contains(itemKey(l, it.index)) }

    private fun progress(l: Lst): Pair<Int, Int> {
        val checks = l.items.withIndex().filter { !it.value.detail }
        return checks.count { done.contains(itemKey(l, it.index)) } to checks.size
    }

    private fun load() {
        done.clear(); skipped.clear()
        try {
            val a = org.json.JSONArray(prefs.getString("ck2_done_$aircraft", "[]"))
            for (i in 0 until a.length()) done.add(a.getString(i))
            val b = org.json.JSONArray(prefs.getString("ck2_skip_$aircraft", "[]"))
            for (i in 0 until b.length()) skipped.add(b.getString(i))
        } catch (e: Exception) { }
    }

    private fun keep() = prefs.edit()
        .putString("ck2_done_$aircraft", org.json.JSONArray(done.toList()).toString())
        .putString("ck2_skip_$aircraft", org.json.JSONArray(skipped.toList()).toString()).apply()

    // ---- the panels ----

    private fun paint() {
        paintLeft()
        paintRight()
        if (!wide) {
            (leftPanel.layoutParams as LinearLayout.LayoutParams).weight = if (rightShown) 0f else 1f
            (rightPanel.layoutParams as LinearLayout.LayoutParams).weight = if (rightShown) 1f else 0f
            leftPanel.visibility = if (rightShown) View.GONE else View.VISIBLE
            rightPanel.visibility = if (rightShown) View.VISIBLE else View.GONE
            rootBox.requestLayout()
        }
    }

    private fun barButton(label: String, bg: Int, go: () -> Unit) = TextView(this).apply {
        text = label; textSize = 12.5f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
        typeface = EfbUi.MEDIUM
        background = EfbUi.cardBg(this@ChecklistActivity, bg, 7)
        setPadding(dp(10), dp(7), dp(10), dp(7))
        setOnClickListener { go() }
    }

    private fun paintLeft() {
        leftPanel.removeAllViews()
        // The bar at the top: back, share, edit, and the red button that jumps to the emergencies.
        val top = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(navy); setPadding(dp(6), dp(6), dp(6), dp(6))
        }
        top.addView(barButton("‹ Back", 0xFF2A3B4D.toInt()) { finish() })
        top.addView(View(this), LinearLayout.LayoutParams(0, 1, 1f))
        top.addView(barButton("⤴", 0xFF2A3B4D.toInt()) { share() }, LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(5) })
        top.addView(barButton("Edit", 0xFF2A3B4D.toInt()) { edit() }, LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(5) })
        top.addView(barButton("▲", 0xFFC62828.toInt()) {
            group = 2; open = lists.firstOrNull { it.group == 2 }; rightShown = true; paint()
        })
        leftPanel.addView(top)
        // The aeroplane this checklist is for; a tap changes it.
        leftPanel.addView(TextView(this).apply {
            text = aircraft; textSize = 14f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
            typeface = EfbUi.MEDIUM; setBackgroundColor(navy); setPadding(dp(8), 0, dp(8), dp(8))
            setOnClickListener { pickAircraft() }
        })
        // The three groups.
        val tabs = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; setBackgroundColor(navy); setPadding(dp(8), 0, dp(8), dp(8))
        }
        for ((i, n) in listOf("Normal", "Abnormal", "Emergency").withIndex()) {
            tabs.addView(TextView(this).apply {
                text = n; textSize = 12.5f; gravity = Gravity.CENTER
                setTextColor(if (i == group) 0xFF10161D.toInt() else 0xFFD7DEE6.toInt())
                typeface = EfbUi.MEDIUM
                background = EfbUi.cardBg(this@ChecklistActivity, if (i == group) 0xFFFFFFFF.toInt() else 0xFF2A3B4D.toInt(), 6)
                setPadding(dp(4), dp(6), dp(4), dp(6))
                setOnClickListener {
                    group = i
                    open = lists.firstOrNull { it.group == i }
                    paint()
                }
            }, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = if (i < 2) dp(4) else 0 })
        }
        leftPanel.addView(tabs)
        // The lists, gathered under their subgroups.
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val mine = lists.filter { it.group == group }
        if (mine.isEmpty()) col.addView(EfbUi.text(this, "Nothing in this group.", 14f, grey).apply { setPadding(dp(14), dp(16), dp(14), 0) })
        var sub = ""
        for (l in mine) {
            if (l.sub != sub) {
                sub = l.sub
                col.addView(TextView(this).apply {
                    text = sub; textSize = 10.5f; setTextColor(grey); typeface = EfbUi.MEDIUM
                    letterSpacing = 0.1f
                    setBackgroundColor(0xFF1A232C.toInt()); setPadding(dp(14), dp(7), dp(14), dp(7))
                })
            }
            val (dn, all) = progress(l)
            val here = open?.key == l.key
            col.addView(LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
                setBackgroundColor(if (here) lit else 0x00000000)
                setPadding(dp(14), dp(12), dp(12), dp(12))
                // The dot: empty, part-filled, or full, as the list is worked through.
                addView(TextView(this@ChecklistActivity).apply {
                    text = if (all > 0 && dn >= all) "●" else if (dn > 0) "◐" else "○"
                    textSize = 14f
                    setTextColor(if (all > 0 && dn >= all) 0xFF30D158.toInt() else if (here) 0xFFFFFFFF.toInt() else grey)
                }, LinearLayout.LayoutParams(dp(22), -2))
                addView(EfbUi.text(this@ChecklistActivity, l.name, 14.5f, if (here) 0xFFFFFFFF.toInt() else 0xFFD7DEE6.toInt(), bold = here),
                    LinearLayout.LayoutParams(0, -2, 1f))
                if (all > 0) addView(EfbUi.text(this@ChecklistActivity, "$dn/$all", 11.5f, if (here) 0xFFD9E7F5.toInt() else grey, mono = true))
                setOnClickListener { open = l; rightShown = true; paint() }
            })
            col.addView(View(this).apply { setBackgroundColor(0xFF222C36.toInt()) }, LinearLayout.LayoutParams(-1, 1))
        }
        leftPanel.addView(ScrollView(this).apply { addView(col) }, LinearLayout.LayoutParams(-1, 0, 1f))
        leftPanel.addView(TextView(this).apply {
            text = "Reset All"; textSize = 13f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
            typeface = EfbUi.MEDIUM; setBackgroundColor(navy); setPadding(dp(10), dp(13), dp(10), dp(13))
            setOnClickListener { askReset() }
        })
    }

    /** The first item not yet ticked or skipped: the one in hand. */
    private fun current(l: Lst): Int =
        l.items.indices.firstOrNull { !l.items[it].detail && !done.contains(itemKey(l, it)) && !skipped.contains(itemKey(l, it)) } ?: -1

    private fun paintRight() {
        rightPanel.removeAllViews()
        val l = open
        if (l == null) {
            rightPanel.addView(EfbUi.text(this, "Pick a checklist.", 15f, grey).apply { setPadding(dp(20), dp(24), dp(20), 0) })
            return
        }
        val head = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(navy); setPadding(dp(6), dp(6), dp(8), dp(6))
        }
        if (!wide) head.addView(barButton("‹", 0xFF2A3B4D.toInt()) { rightShown = false; paint() },
            LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(6) })
        head.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER
            addView(EfbUi.text(this@ChecklistActivity, l.name, 15f, 0xFFFFFFFF.toInt(), bold = true).apply { gravity = Gravity.CENTER; maxLines = 1 })
            addView(EfbUi.text(this@ChecklistActivity, aircraft, 11f, 0xFFA9B6C3.toInt()).apply { gravity = Gravity.CENTER })
        }, LinearLayout.LayoutParams(0, -2, 1f))
        head.addView(barButton("Edit", 0xFF2A3B4D.toInt()) { edit() })
        rightPanel.addView(head)

        val cur = current(l)
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        for ((i, it) in l.items.withIndex()) {
            if (it.detail) {
                col.addView(TextView(this).apply {
                    text = it.title.uppercase(); textSize = 10.5f; setTextColor(grey); typeface = EfbUi.MEDIUM
                    letterSpacing = 0.1f; gravity = Gravity.CENTER
                    setBackgroundColor(0xFF1A232C.toInt()); setPadding(dp(14), dp(8), dp(14), dp(8))
                })
                continue
            }
            val k = itemKey(l, i)
            val isDone = done.contains(k)
            val isSkip = skipped.contains(k)
            val isHere = i == cur
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setBackgroundColor(if (isHere) lit else rowBg)
                setPadding(dp(14), dp(11), dp(14), dp(11))
                setOnClickListener { check(l, i) }
            }
            val line = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
            line.addView(TextView(this).apply {
                text = if (isDone) "✓" else if (isSkip) "–" else "○"
                textSize = 15f
                setTextColor(if (isDone) 0xFF30D158.toInt() else if (isHere) 0xFFFFFFFF.toInt() else grey)
            }, LinearLayout.LayoutParams(dp(26), -2))
            val titleCol = if (isHere) 0xFFFFFFFF.toInt() else if (isDone || isSkip) 0xFF7C8794.toInt() else 0xFFE4EAF1.toInt()
            val actCol = if (isHere) 0xFFFFFFFF.toInt() else if (isDone || isSkip) 0xFF7C8794.toInt() else 0xFF9FB4C8.toInt()
            // A short action sits on the same line as what it belongs to, the way a printed
            // checklist prints it. A long one — a whole brief — goes on its own line underneath,
            // because side by side it would squeeze the name into a column one letter wide and
            // stretch the row down the page.
            val stacked = it.action.length > 26 || it.title.length + it.action.length > 46
            line.addView(EfbUi.text(this, it.title, 14.5f, titleCol, bold = isHere),
                LinearLayout.LayoutParams(0, -2, 1f))
            if (it.action.isNotEmpty() && !stacked) line.addView(EfbUi.text(this, it.action.uppercase(), 12.5f, actCol, bold = true))
            row.addView(line)
            if (it.action.isNotEmpty() && stacked) row.addView(
                EfbUi.text(this, it.action.uppercase(), 12.5f, actCol, bold = true)
                    .apply { setPadding(dp(26), dp(3), 0, 0) })
            it.note?.let { n ->
                row.addView(EfbUi.text(this, n, 11.5f, if (isHere) 0xFFDCEAF8.toInt() else grey).apply {
                    setPadding(dp(26), dp(3), 0, 0)
                })
            }
            col.addView(row)
            col.addView(View(this).apply { setBackgroundColor(0xFF222C36.toInt()) }, LinearLayout.LayoutParams(-1, 1))
        }
        val sc = ScrollView(this).apply { addView(col) }
        rightPanel.addView(sc, LinearLayout.LayoutParams(-1, 0, 1f))

        // The bottom bar: reset this list, read it aloud, skip the item, tick it.
        val bar = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setBackgroundColor(0xFF10161D.toInt()) }
        fun wide(label: String, bg: Int, go: () -> Unit) = bar.addView(TextView(this).apply {
            text = label; textSize = 14f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
            typeface = EfbUi.MEDIUM; setBackgroundColor(bg); setPadding(dp(6), dp(15), dp(6), dp(15))
            setOnClickListener { go() }
        }, LinearLayout.LayoutParams(0, -2, if (label == "Reset") 0.7f else 1f))
        wide("Reset", 0xFF39434E.toInt()) { resetList(l) }
        wide(if (speaking) "Speaking" else "Speak", if (speaking) 0xFF0060CC.toInt() else lit) { speak(l) }
        wide("Skip", 0xFFE08A16.toInt()) { skip(l, cur) }
        wide("Check", 0xFF2E9E4F.toInt()) { check(l, cur) }
        rightPanel.addView(bar)
        // The item in hand is brought into view.
        sc.post {
            val idx = current(l)
            if (idx > 0) sc.smoothScrollTo(0, (idx * dp(46) - sc.height / 3).coerceAtLeast(0))
        }
    }

    private fun check(l: Lst, i: Int) {
        if (i < 0 || i >= l.items.size || l.items[i].detail) return
        val k = itemKey(l, i)
        if (done.contains(k)) { done.remove(k); skipped.remove(k) } else { done.add(k); skipped.remove(k) }
        keep()
        paint()
        if (speaking) speakItem(l)
        if (allDone(l)) {
            val next = lists.filter { it.group == l.group }.firstOrNull { !allDone(it) }
            if (next != null) com.google.android.material.snackbar.Snackbar
                .make(rightPanel, "${l.name} complete", 4000)
                .setAction("Next: ${next.name}") { open = next; paint() }.show()
        }
    }

    private fun skip(l: Lst, i: Int) {
        if (i < 0 || i >= l.items.size) return
        skipped.add(itemKey(l, i)); done.remove(itemKey(l, i)); keep(); paint()
        if (speaking) speakItem(l)
    }

    private fun resetList(l: Lst) {
        for (i in l.items.indices) { done.remove(itemKey(l, i)); skipped.remove(itemKey(l, i)) }
        keep(); paint()
    }

    private fun askReset() {
        MaterialAlertDialogBuilder(this).setTitle(getString(R.string.ck_reset))
            .setMessage("Every list in this checklist starts again.")
            .setPositiveButton(R.string.ok) { _, _ -> done.clear(); skipped.clear(); keep(); paint() }
            .setNegativeButton(R.string.cancel, null).show()
    }

    private fun pickAircraft() {
        val names = listOf(ATHENE, "SportStar MAX", "C172")
        MaterialAlertDialogBuilder(this).setTitle(getString(R.string.ck_title))
            .setItems(names.toTypedArray()) { _, i ->
                aircraft = names[i]
                prefs.edit().putString("ck_aircraft", aircraft).apply()
                load(); parse()
                open = lists.firstOrNull { it.group == group }
                paint()
            }.setNegativeButton(R.string.cancel, null).show()
    }

    private fun share() {
        val sb = StringBuilder("$aircraft · ${getString(R.string.ck_title)}\n\n")
        for (l in lists) {
            sb.append("# ${l.name}\n")
            for (it in l.items) sb.append(if (it.detail) "> ${it.title}\n" else "${it.title} .. ${it.action}\n")
            sb.append("\n")
        }
        startActivity(android.content.Intent.createChooser(android.content.Intent(android.content.Intent.ACTION_SEND).apply {
            type = "text/plain"; putExtra(android.content.Intent.EXTRA_TEXT, sb.toString())
        }, null))
    }

    // ---- reading the list aloud ----

    private fun speak(l: Lst) {
        speaking = !speaking
        if (!speaking) { try { tts?.stop() } catch (e: Exception) { }; paint(); return }
        if (tts == null) tts = android.speech.tts.TextToSpeech(this) { st ->
            if (st == android.speech.tts.TextToSpeech.SUCCESS) { tts?.language = java.util.Locale.US; runOnUiThread { speakItem(l) } }
        } else speakItem(l)
        paint()
    }

    private fun speakItem(l: Lst) {
        val i = current(l)
        if (i < 0) { try { tts?.speak("Checklist complete", android.speech.tts.TextToSpeech.QUEUE_FLUSH, null, "ck") } catch (e: Exception) { }; return }
        val it = l.items[i]
        val say = it.title + if (it.action.isNotEmpty()) ", ${it.action}" else ""
        try { tts?.speak(say, android.speech.tts.TextToSpeech.QUEUE_FLUSH, null, "ck") } catch (e: Exception) { }
    }

    // ---- the text behind it all, the pilot's to change ----

    private fun edit() {
        val e = EditText(this).apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
            setText(text()); setTextColor(EfbUi.TEXT)
            typeface = android.graphics.Typeface.MONOSPACE
            textSize = 12.5f; gravity = Gravity.TOP
            layoutDirection = View.LAYOUT_DIRECTION_LTR; textDirection = View.TEXT_DIRECTION_LTR
            setPadding(dp(14), dp(10), dp(14), dp(10))
        }
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        box.addView(EfbUi.text(this, "# opens a list · > is a heading inside it · \"item .. action\" is a check item · an indented line is a note", 11.5f, grey)
            .apply { setPadding(dp(14), dp(10), dp(14), dp(4)) })
        box.addView(ScrollView(this).apply { addView(e) }, LinearLayout.LayoutParams(-1, dp(420)))
        MaterialAlertDialogBuilder(this).setTitle(getString(R.string.ck_edit)).setView(box)
            .setPositiveButton(R.string.log_save) { _, _ ->
                prefs.edit().putString("ck_$aircraft", e.text.toString()).apply()
                done.clear(); skipped.clear(); keep(); parse()
                open = lists.firstOrNull { it.group == group }
                paint()
            }
            .setNeutralButton(R.string.ck_restore) { _, _ ->
                prefs.edit().remove("ck_$aircraft").apply()
                done.clear(); skipped.clear(); keep(); parse()
                open = lists.firstOrNull { it.group == group }
                paint()
            }
            .setNegativeButton(R.string.cancel, null).show()
    }

    companion object {
        /** Evektor SportStar MAX, from its Aircraft Operating Instructions (SSM2008AOIUS), with the AOI page of each part. */
        const val ATHENE = "AtheneAir EVSS"

        private val SPORTSTAR = """
# 📋 SPEEDS · AOI 2-3, 2-4, 3-3, 4-3
VS0 · stall, flaps 50°, max weight .. 37 KIAS
VS1 · stall, flaps 0°, max weight .. 38 KIAS
VX · flaps 15° / flaps 0° .. 54 / 56 KIAS
VY · flaps 15° / flaps 0° .. 57 / 65 KIAS
Climb to 50 ft (flaps 15°) .. 57 KIAS
Rotation / lift-off airspeed .. 57 KIAS
Approach, normal landing (flaps 50°) .. 60 KIAS
Balked landing, flaps 15° .. 56 KIAS
Best glide (flaps 0°) .. 59 KIAS
Glide, flaps 15° .. 55 KIAS
Precautionary / emergency landing (flaps 50°) .. 55 KIAS
VFE · max flap extended .. 70 KIAS
VA · manoeuvring .. 90 KIAS
VNO · max structural cruising .. 115 KIAS
VNE · never exceed .. 146 KIAS
Max demonstrated crosswind (AOI 5-14) .. 16 kts
Max demonstrated tail wind .. 6 kts
Max demonstrated wind .. 24 kts
# 📋 LIMITS · AOI 2-5 TO 2-10
Engine .. ROTAX 912 ULS
RPM max take-off (max 5 min) .. 5800
RPM max continuous .. 5500
RPM idle .. 1400
Oil temp max / optimum .. 266 °F / 190-230 °F
Oil pressure min / optimum / max .. 12 / 29-73 / 102 PSI
Coolant temp max .. 248 °F
Fuel pressure min .. 2.2 PSI
Ignition check at 4000 RPM: max drop .. 300 RPM
Max difference L / R .. 120 RPM
Max take-off / landing weight .. 1320 lbs
Max baggage .. 55 lbs
Min crew weight .. 121 lbs
Operating C.G. range .. 20 to 34 %MAC
Load factors .. +4.0 / -2.0
Fuel: total / usable .. 31.7 / 31.2 US gal
Oil volume min / max .. 0.53 / 0.79 US gal
Approved manoeuvres .. bank up to 60°, no spins
! WARNING: AEROBATICS AS WELL AS INTENTIONAL SPINS ARE PROHIBITED! NOT AUTHORIZED FOR FLIGHT INTO KNOWN OR FORECAST POSSIBLE ICING CONDITIONS. NOT AUTHORIZED FOR FLIGHT WITHIN 25 MILES OF KNOWN LIGHTNING OR THUNDERSTORMS.
# PRE-FLIGHT CHECK · AOI 4-4 TO 4-7
! WARNING: CHECK BEFORE PRE-FLIGHT CHECK THAT IGNITION IS SWITCHED OFF!
1. Left landing gear leg: attachment and condition .. check
1. Left gear: wheel, tire condition and inflation .. check
1. Left gear: wheel covers, ground cable (if installed) .. check
2. Left wing: surface, leading edge, landing light (if installed) .. check
2. Left wing: Pitot tube condition .. check
2. Left wing: drain fuel tank (AOI 8-6) .. drain
2. Left wing: fuel tank cap .. closed
3. Left wing tip: surface, attachment, fuel tank vent cleanness .. check
3. Left wing tip: position lights / beacon (if installed) .. check
4. Left aileron: surface, trim tab (if installed), attachment, free movement .. check
5. Left wing flap: surface, attachment .. check
6. Rear fuselage: surface, antennas (if installed) .. check
7. Tail units: tail skid, surface .. check
7. Tail units: rudder and elevator attachment, freedom of movement .. check
7. Tail units: trim tab and elevator trim tab control .. check
8. Rear fuselage: surface .. check
9. Right wing flap (see 5.) .. check
10. Right aileron (see 4., except the trim tab) .. check
11. Right wing tip (see 3.) .. check
12. Right wing (see 2., except landing light) .. check
12. Alternate pitot tube (IFR) / AOA probe (if installed) .. check
13. Right landing gear leg (see 1.) .. check
14. Front fuselage right: tip-up canopy attachment and condition .. check
14. Nose gear leg, nose wheel, nose wheel control rods .. check
14. External power socket (if installed) .. check
15. Engine, first flight of day (upper cowling off): engine bed, attachment, exhaust, cowlings .. check
15. Fuel and electrical system, visual .. check
15. Coolant in expansion tank (max. 2/3) .. check
15. Every flight: air intakes cleanness .. check
15. Oil level (between marks on dip stick) .. check
15. Coolant in overflow bottle (approx. 0.42 pints) .. check
15. Upper cowling .. properly closed
16. Propeller: attachment, blades, hub and spinner .. check
17. Front fuselage left: tip-up canopy attachment and condition .. check
18. Cockpit: Master switch .. switched on
18. Canopy OPEN/CLOSE indication light (or EFIS message) .. function check
18. All switches .. OFF
18. Instrument equipment .. check condition
18. Safety belts condition and attachment .. check
18. Loose objects in the cockpit .. check
18. Rudder pedals (if adjustable): same position, secured .. check
18. AOI and other required documents .. complete and valid
# BEFORE ENGINE STARTING · AOI 4-8
Pre-flight check, weight and C.G. .. done
External power source (if socket installed) .. connect as necessary
Safety harnesses .. check, fasten
Control stick .. free
Rudder pedals .. free
Wing flaps .. function check
Trim tab .. function check
PARKING BRAKE handle (if installed) .. release brakes
Brakes .. function check
AVIONICS SWITCH .. check OFF
Ignition .. check OFF
Canopy .. close
# ENGINE STARTING · AOI 4-8 TO 4-10
Master switch .. ON
Fuel gauge indicators .. check fuel qty.
FUEL SELECTOR (pull safety button) .. LEFT
Electric fuel pump (if installed) .. ON
THROTTLE lever .. idle
Choke .. as necessary
Space in the propeller area .. free
BEACON (if installed) .. ON as necessary
Brakes .. apply
Ignition .. START, then BOTH
! CAUTION: ACTIVATE STARTER FOR 10 SEC. AS A MAXIMUM, THEN LET IT COOL DOWN FOR 2 MINUTES.
THROTTLE lever .. approx. 2500 RPM
Oil pressure .. rising within 10 s
GEN, AUX GEN (if inst.) switches .. ON
Engine instruments .. check
Choke .. as necessary
Engine warm-up: 2000 RPM approx. 2 min, then 2500 RPM .. until oil 122 °F
FUEL SELECTOR: verify feeding approx. 1 minute .. RIGHT
FUEL SELECTOR .. LEFT
External power source (if used) .. disconnect
AVIONICS SWITCH .. ON
Radiostation / avionics .. ON
Other electrical equipment .. ON as necessary
# BEFORE TAXIING · TAXIING · AOI 4-10
Transponder (if installed) .. SBY
Outside lights (if installed) .. as necessary
THROTTLE lever .. as necessary
Brakes .. check by depressing
Rudder pedals .. function check
# BEFORE TAKE-OFF · AOI 4-11, 4-12
Brakes .. brake
Ignition check at 4000 RPM: L, BOTH, R, BOTH .. max drop 300, diff 120
Engine instruments .. check
Control stick .. free
Wing flaps .. Take-off pos. (15°)
Elevator trim .. NEUTRAL
Aileron trim (if installed) .. NEUTRAL
Fuel gauge indicator .. check fuel quantity
FUEL SELECTOR .. check LEFT
CARB. PREHEATER (if installed) .. check function, then OFF
Engine instruments .. check
Flight instruments .. check
Radiostation / avionics .. check, set
Ignition .. check BOTH
Choke .. close
Master switch .. check ON
Safety harnesses .. tighten up
Canopy .. closed
Transponder (if installed) .. ON or ALT
! WARNING: TAKE-OFF IS PROHIBITED IF ENGINE RUNNING IS IRREGULAR, IF CHOKE IS OPEN, OR IF ENGINE INSTRUMENTS ARE NOT WITHIN THE REQUIRED RANGE.
# TAKE-OFF · CLIMB · AOI 4-12
THROTTLE lever .. max. take-off power
Take-off run: lighten the nose wheel smoothly .. until lift-off
Airspeed .. 57 KIAS
Brakes .. stop main wheel rotation
At 150 ft: flaps .. retracted (0°)
Trim .. as necessary
Climb: THROTTLE lever .. max. continuous power
Airspeed .. VY 65 KIAS or VX 56 KIAS
Engine instruments .. check
Electric fuel pump (if installed) .. OFF
# CRUISE · DESCENT · AOI 4-13, 4-14
THROTTLE lever .. as necessary, max. 5500 RPM
Engine instruments .. check
Fuel quantity (level flight, wait approx. 2 min) .. check
Tanks: switch alternately; not RIGHT if left tank full .. as needed
CARB. PREHEATER (if installed) .. as necessary
Descent: increased idle, watch engine temperatures .. as necessary
# BEFORE LANDING · FINAL · AOI 4-14, 4-15
Fuel quantity .. check
FUEL SELECTOR .. LEFT
Engine instruments .. check
Brakes .. check by depressing pedals
Safety harnesses .. tighten up
Free area of landing .. check
CARB. PREHEATER (if installed) .. ON
Approaching speed .. 60 KIAS
Flaps .. Take-off pos. (15°)
Trim .. as necessary
Parking brake (if installed) .. check lever down
Electric fuel pump (if installed) .. ON
Final: flaps .. landing pos. (30° or 50°)
Maintain airspeed .. 60 KIAS
CARB. PREHEATER (if installed) .. OFF
Landing: THROTTLE lever .. idle
Touch-down on main wheels; brakes after nose wheel .. as necessary
# BALKED LANDING · AOI 4-15
THROTTLE lever .. max. take-off power
Flaps .. take-off pos. (15°)
Airspeed .. 56 KIAS
At 150 ft: flaps .. retracted (0°)
Trim .. as necessary
THROTTLE lever .. max. continuous power
Instruments .. check
Climb at airspeed .. 65 KIAS
# AFTER LANDING · SHUT-OFF · PARKING · AOI 4-16, 4-17
Flaps .. retracted (0°)
Trim .. NEUTRAL
Outside lights (if installed) .. OFF
Transponder (if installed) .. OFF
Electric fuel pump (if installed) .. OFF
THROTTLE lever .. idle
Engine instruments .. check
AVIONICS SWITCH .. OFF
Radiostation / avionics .. OFF
Other electrical equipment .. OFF
Ignition .. OFF
BEACON (if installed) .. OFF
Master switch .. OFF
FUEL SELECTOR (safety button) .. OFF
PARKING BRAKE (if installed) or chocks .. as necessary
Canopy .. close, lock as necessary
# EMERGENCY · ENGINE FAILURE AT TAKE-OFF RUN · AOI 3-3
THROTTLE lever .. idle
Brakes .. as necessary
FUEL SELECTOR .. OFF
Ignition .. OFF
Master switch .. OFF
# EMERGENCY · ENGINE FAILURE AT TAKE-OFF · AOI 3-3, 3-4
Gliding speed: flaps 15° / flaps 0° .. min. 55 / 59 KIAS
Below 150 ft .. land straight ahead
150 - 400 ft .. straight ahead or turn up to 90°
Above 250 ft .. you can try to start engine
Above 400 ft .. turn up to 180° possible
THROTTLE lever .. idle
Flaps .. as needed
FUEL SELECTOR .. OFF
Ignition .. OFF
ATC .. report
Master switch .. OFF
After touch down .. brake as needed
# EMERGENCY · ENGINE FAILURE IN FLIGHT · AOI 3-4
Gliding speed .. 59 KIAS
Altitude .. decide: restart (3.4) or emergency landing (3.8.1)
# EMERGENCY · ENGINE STARTING IN FLIGHT · AOI 3-4, 3-5
! NOTE: If the engine is shut down, altitude loss during engine starting can reach up to 1000 ft.
Gliding speed .. 59 KIAS
Altitude .. check
Master switch .. ON
Electrical fuel pump (if installed) .. ON
Unnecessary electrical equipment .. switch off
FUEL SELECTOR .. LEFT (or RIGHT if left is empty)
Choke .. as needed
THROTTLE lever .. idle (choke open) or increased idle
Propeller rotating: Ignition .. BOTH
Propeller not rotating: Ignition .. START
No start: increase gliding speed up to .. 108 KIAS
Ignition .. BOTH
Unsuccessful .. emergency landing 3.8.1
# EMERGENCY · FIRE ON THE GROUND · AOI 3-5
FUEL SELECTOR .. OFF
Brakes .. brake
THROTTLE lever .. full
HOT AIR knob (if installed) .. push
After engine stops: Ignition .. OFF
Master switch .. OFF
Airplane .. leave
Manual extinguisher (if available) .. use
# EMERGENCY · FIRE DURING TAKE-OFF · AOI 3-5, 3-6
FUEL SELECTOR .. OFF
THROTTLE lever .. full
Airspeed .. 65 KIAS
HOT AIR knob (if installed) .. push
COLD AIR knob (if installed) .. push
After engine stops: gliding speed .. 55 KIAS
Ignition .. OFF
Master switch .. OFF
Land .. land
Airplane .. leave
Manual extinguisher (if available) .. use
# EMERGENCY · FIRE IN FLIGHT · AOI 3-6, 3-7
FUEL SELECTOR .. OFF
THROTTLE lever .. full
HOT AIR knob (if installed) .. push
COLD AIR knob (if installed) .. push
Gliding speed .. 59 KIAS
Ignition .. OFF
ATC .. report if possible
Master switch .. OFF
! NOTE: For extinguishing the engine fire, you can perform slip if altitude and time allow.
! WARNING: AFTER EXTINGUISHING THE ENGINE FIRE START ENGINE ONLY IF IT IS NECESSARY TO SAFE LANDING. FIRE COULD RESTORE AGAIN.
If restarting: all switches OFF, Master ON, only necessary equipment .. as needed
Emergency landing .. per 3.8.1
Airplane .. leave
Manual extinguisher (if available) .. use as needed
# EMERGENCY · FIRE IN THE COCKPIT · AOI 3-7
Fire source .. identify
Master switch (if electrical fire) .. OFF
Manual extinguisher .. use
After extinguishing: aerate cockpit, open eye-ball vents .. as needed
Safety landing .. per 3.8.2
! WARNING: NEVER AGAIN SWITCH THE DEFECTIVE SYSTEM. If an electrical circuit was the source, switch off its circuit breaker and Master switch back ON.
# EMERGENCY · LANDING, ENGINE NOT OPERATING · AOI 3-8
Airspeed .. 59 KIAS
Landing area .. choose, determine wind direction
Safety harness .. tighten up
Flaps .. landing position (50°)
Airspeed .. 60 KIAS
Radiostation .. notify ATC (if possible)
FUEL SELECTOR .. OFF
Ignition .. OFF
Master switch .. OFF before touch down
# EMERGENCY · SAFETY LANDING, ENGINE OPERATING · AOI 3-8
Area for landing: pass over at 59 KIAS, flaps 15° .. choose, wind direction
Radiostation .. notify ATC (if possible)
Safety harness .. tighten up
Flaps .. landing position (50°)
Airspeed .. 60 KIAS
Landing .. carry out
# EMERGENCY · BURST TIRE · DAMAGED GEAR · AOI 3-9
Burst tire: keep that wheel off the ground with ailerons (nose wheel: elevator) .. as long as possible
At running: hold direction with foot control and brakes .. as needed
Nose gear damage: touch down at lowest speed, keep on main wheels .. as long as possible
Main gear damage: touch down at lowest speed, keep direction .. if possible
# EMERGENCY · UNINTENTIONAL SPIN · AOI 3-9, 3-10
THROTTLE lever .. idle
Control stick: ailerons .. neutral
Pedals .. full rudder against rotation
Control stick .. push forward, hold until rotation stops
Pedals, immediately after rotation stops .. neutral
Control stick .. recover the diving
! CAUTION: ALTITUDE LOSS PER ONE TURN AND RECOVERING FROM THE SPIN IS 500 UP TO 1000 FT.
# EMERGENCY · VIBRATION · CARBURETTOR ICING · AOI 3-10
Vibration: engine RPM .. set where vibrations are lowest
Land at nearest airport or safety landing 3.8.2 .. as needed
Carb icing: CARB. PREHEATER (if installed) .. ON
THROTTLE lever .. idle, then cruising power again
Power not recovered .. land at nearest airport or precautionary landing 3.8.2
# EMERGENCY · CANOPY OPENING IN FLIGHT · AOI 3-11
Grasp shaking control stick(s) .. hold
THROTTLE: reduce airspeed to approx. .. 65 KIAS
Pull opened canopy down by its frame and keep holding .. hold
! WARNING: PRIORITY IS TO MAINTAIN AIRPLANE CONTROLLABILITY! ATTEMPTS TO CLOSE THE CANOPY ARE SECONDARY!
Try to close the canopy (possible in dual flight) .. if able
Safety landing .. per 3.8.2
After landing: check canopy, lock system and horizontal tail .. inspect
""".trimIndent()

        /** The school's own checklist: AtheneAir EVSS Operating Checklist, Revision 1.3, 06/2026 (N19EV, N79EV, N19MX), as printed. */
        private val ATHENEAIR = """
# 📋 SPEEDS · AtheneAir EVSS Operating Checklist Rev 1.3, 06/2026
Aircraft .. N19EV / N79EV / N19MX
VR .. 50 KIAS
VX .. 56 KIAS
VY .. 65 KIAS
VA .. 90 KIAS
VG (best glide) .. 55 KIAS (Flaps 15) / 59 KIAS (Flaps 0)
Approach .. 65 – 70 KIAS
Final .. 60 – 65 KIAS
Short Final .. 60 KIAS
VFE .. 70 KIAS
VS0 .. 37 KIAS
VS1 .. 38 KIAS
VNO .. 115 KIAS
VNE .. 146 KIAS
! For Training use only, reference POH in real Emergency/Abnormal Operations
! ATTENTION! FUEL: MOGAS & 100LL. ENGINE OIL: Do NOT Overfill (1 Ounce at a Time)
# PREFLIGHT COCKPIT
Airplane documents .. CHECK
Interior for FOD .. CHECK
Circuit Breakers .. CHECK
Master Switch .. ON
Battery Voltage .. CHECK
Fuel Quantity .. CHECK
External Lights .. ON
Flaps .. LOWERED
Stall Warning .. CHECK
External Lights .. CHECK
Flaps .. CHECK
External Lights .. OFF
Flaps .. RETRACTED
Seatbelt .. REMOVED
Master .. OFF
# PREFLIGHT EXTERIOR · NOSE
Canopy Attachment .. CHECK
Nose Gear, Control Rods .. CHECK
Tire Inflation/Condition .. CHECK
1st Flight of the Day .. REMOVE COWLING
Engine & Coolant Levels .. INSPECT
Oil Level .. CHECK
! BURP IF NECESSARY
Air Intake / Radiator .. CHECK
Prop/Spinner .. CHECK FOR DAMAGE
Exhaust .. CHECK
# PREFLIGHT EXTERIOR · RIGHT WING
Wing Leading Edge .. CHECK
Vortex Generators .. CHECK
Wing Surface Condition .. CHECK
Wingtip / Fuel Vent .. CHECK
Wing Tie Down .. REMOVE
Aileron / Hinge / Pushrod .. CHECK
Main Gear / Brake Lines .. CHECK
Tire Inflation and Condition .. CHECK
Fuel Sump .. CHECK
Fuel Cap .. CHECK FUEL LEVEL / LOCK
# PREFLIGHT EXTERIOR · EMPENNAGE
Antennae .. CHECK
Vertical Stabilizer .. CHECK
RH. Horizontal Stabilizer .. CHECK
Elevator Movement .. CHECK
Elevator Trim Tab .. CHECK
Elevator Pushrod .. CHECK
Surface and Tail Skid .. CHECK
Tail Tie Down .. REMOVE
Rudder Movement .. CHECK
L.H Horizontal Stabilizer .. CHECK
# PREFLIGHT EXTERIOR · LEFT WING
Main Gear / Brake Lines .. CHECK
Fuel Sump .. CHECK
Tire Inflation and Condition .. CHECK
Aileron / Hinge / Pushrod .. CHECK
Wingtip / Fuel Vent .. CHECK
Wing Tie Down .. REMOVE
Pitot Static Tube .. CHECK CLEAR
Wing Leading Edge .. CHECK
Vortex Generators .. CHECK
Wing Surface Condition .. CHECK
Fuel Cap .. CHECK FUEL LEVEL / LOCK
# BEFORE ENGINE STARTING
Passenger Briefing .. SAFETY
Pilot Briefing .. COMPLETE
Circuit Breakers .. IN
Control Stick .. Free & Correct
Rudder Pedals .. Adjusted
Parking Brake .. As Necessary
All Switches .. OFF
Ignition .. OFF
# ENGINE STARTING
Master Switch .. ON Wait for Dynon
Hobbs .. Check & Dispatch
Fuel Gauge Indicator .. Check Fuel Quantity
Fuel Selector .. Lowest Tank
Electric Fuel Pump .. ON Check Fuel Pressure
Throttle .. Idle / 1 Turn if Warm
Choke .. As Necessary
Beacon .. On
Brakes .. Apply
Propeller Area .. Clear
Ignition .. Start
! Starter: Max 10 sec / 2 min cooldown
# AFTER START
Engine Warmup .. 2000RPM
Oil Pressure .. Check in Green
Engine Instruments .. Check
GEN, AUX GEN .. ON
Avionics Switch .. ON
Electric Fuel Pump .. OFF Check Fuel Pressure
# BEFORE TAXI
Transponder .. ON & ALT, Correct Code
Lights .. ON as Necessary
Weather .. ATIS/AWOS/ASOS
Flight Instruments .. SET
Radio/Avionics/GPS .. CHECK / SET
# TAXI
Taxi Clearance/Briefing .. COMPLETE
Parking Brake .. RELEASED
Brakes .. CHECK
# RUNUP
Fuel Pump .. ON Check Fuel Pressure
Fuel Selector .. Change Tank
Oil Temp .. At Least 122°F
Brakes .. HOLD
Throttle (ignition check) .. 4000RPM
Ignition Check .. Left/Both/Right/Both
! DO NOT EXCEED 300RPM DROP OR 120RPM DIFFERENCE
Carb Heat .. On/Check Drop/Off
Throttle .. 2000 RPM
Trim .. Set
Flight Instruments .. Check
Ignition .. Both
Choke .. Closed
# BEFORE TAKEOFF
Fuel Pump .. ON
Lights .. ON
Trim .. SET
Canopy .. Closed "Green Light"
Flaps .. 15° Degrees
! REVIEW EMERGENCY PROCEDURES
# AFTER TAKEOFF
Throttle .. Max Take-off Power
Airspeed .. 65 KIAS
Flaps .. UP / 0° (Above 150ft AGL)
Lights .. ON
# CLIMB
Throttle .. Max Continuous Power
! Above 1000 Ft AGL:
Fuel Pump .. OFF Check Fuel Pressure
Landing Light .. OFF
Engine Instruments .. Check in Green
Flaps .. Verify UP (0°)
Traffic Avoidance .. SCAN
# CRUISE
Throttle .. Max 5400 RPM
Engine Instruments .. CHECK
Fuel Quantity .. CHECK
Trim .. SET
Carb Preheat .. As Necessary
Traffic Avoidance .. SCAN
# DESCENT
Throttle .. As Necessary
Airspeed .. As Necessary
Trim .. As Necessary
Engine Instruments .. Check in Green
Carb Preheat .. As Necessary
Weather .. ATIS, AWOS, ASOS
# BEFORE LANDING
Fuel Pump .. ON
Fuel Selector .. Fullest Tank
Landing Light .. ON
Carb Preheat .. As Necessary
Seatbelts .. On
# AFTER LANDING
Fuel Pump .. OFF
Lights .. As Necessary
Trim .. Neutral
Flaps .. UP (0°)
# SHUTDOWN
All Electrical Switches .. OFF
Dynon MFD .. Engine Page
Ignition .. OFF
Hobbs/Tach .. Recorded
Master Switch .. OFF
Flight Circle .. Check-In
All Air Vents .. CLOSED
Control Stick .. SECURE
Canopy .. LOCKED
Canopy Cover .. SECURED
# 📋 EMERGENCY · ENGINE FAILURE BRIEF
ON Runway .. Throttle idle, apply the brakes smoothly, and bring aircraft to a stop
After Rotation w/Runway Remaining .. 55 KIAS · Land: Runway · Checklist if time permits · Declare emergency 121.5 / NRST freq
After Rotation No Runway .. 59 KIAS · Land: no more than 30° on each side · Checklist if time permits · Declare emergency 121.5 / NRST freq
After Rotation Above 1000 ft AGL .. 59 KIAS · Land: return to runway · Checklist if time permits · Declare emergency 121.5 or NRST freq
# EMERGENCY · ENGINE FAILURE IN FLIGHT
Airspeed .. 59 KIAS
Best Place to Land .. Locate
Checklist .. Troubleshoot Below
Declare Emergency .. Squawk 7700 & 121.5
# EMERGENCY · ENGINE FAILURE · TROUBLESHOOT
Fuel Pump .. ON
Fuel Selector .. Switch Tanks
Air .. Carb Heat ON
! If power is not restored, secure aircraft & land
# EMERGENCY · ENGINE FAILURE · SECURE
Fuel Pump .. OFF
Fuel Selector .. OFF
Air .. Carb Heat OFF
Spark Ignition .. OFF
Master Switch .. OFF (close to land)
# EMERGENCY LANDING
Airspeed .. 59 KIAS
Best Place to Land .. Locate
Safety Harness .. Tight
Flaps .. As Required (50° Recommended)
Declare Emergency .. Squawk 7700 & 121.5
Fuel Selector .. OFF
Ignition .. OFF
Master Switch .. OFF (Close to Land)
# EMERGENCY · ENGINE FIRE DURING START
Start .. Crank
Fuel Selector .. OFF
Throttle .. Full
Fuel Pump .. Off
Aircraft .. Evacuate
# EMERGENCY · ENGINE FIRE IN FLIGHT
Fuel Pump .. OFF
Fuel Selector .. OFF
Cabin Air .. OFF
Throttle .. Full
Ignition .. OFF
Airspeed .. 110 KIAS
ATC .. Distress
Emergency Landing .. Execute
Master Switch .. OFF
Airplane .. Evacuate
# EMERGENCY · ELECTRICAL FIRE
Fire Source .. Identify
Unnecessary Electrical Equipment .. OFF
Fire Extinguisher .. If Necessary
Circuit Breakers .. CHECK
Vents .. OPEN
Master Switch .. OFF
! Land as soon as Practical
# EMERGENCY · ENGINE OVERHEATING (IN CLIMB)
Airspeed .. >75 KIAS
Power .. Reduce if Possible
! Step Climb if Necessary
! If Temps in RED:
Land .. As soon as Practical
Aircraft .. Secure
""".trimIndent()

        private val C172 = """
# PREFLIGHT
Documents (ARROW) .. On board
Fuel quantity .. Checked visually
Fuel sumps (all) .. Drained, no water
Oil .. 5-8 qt
Propeller & spinner .. No nicks, secure
Control surfaces .. Free and correct
Tires & brakes .. Condition
Pitot cover / tie-downs / chocks .. Removed
Stall warning / vents .. Checked
# BEFORE START
Seats & belts .. Adjusted, fastened
Brakes .. Test and set
Circuit breakers .. Check in
Avionics .. OFF
Fuel selector .. BOTH
Fuel shutoff valve .. ON (push full in)
# ENGINE START
Throttle .. Open 1/4 inch
Mixture .. IDLE CUTOFF (fuel injected) / RICH
Master switch .. ON
Beacon .. ON
Auxiliary fuel pump .. ON 3-5 s, OFF
Propeller area .. CLEAR
Ignition .. START
Mixture .. Advance smoothly to RICH
Oil pressure .. Green within 30 s
Avionics .. ON
# BEFORE TAKEOFF
Parking brake .. Set
Flight controls .. Free and correct
Flight instruments .. Set
Fuel quantity .. Check
Mixture .. RICH (below 3000 ft)
Fuel selector .. BOTH
Elevator trim .. Takeoff
Throttle .. 1800 RPM
Magnetos .. Drop max 150, diff max 50
Vacuum / ammeter / engine gauges .. Green
Throttle .. 1000 RPM or less
Doors & windows .. Closed and locked
Transponder .. ALT
Lights .. ON
# TAKEOFF
Wing flaps .. 0-10°
Throttle .. Full
Mixture .. RICH (lean for max RPM above 3000 ft)
Rotate .. 55 KIAS
Climb .. 74 KIAS (Vy)
# CRUISE
Power .. 2100-2700 RPM
Mixture .. Lean
Fuel .. Monitor
# BEFORE LANDING
Seats & belts .. Secure
Fuel selector .. BOTH
Mixture .. RICH
Landing light .. ON
Flaps .. As required (below 110 KIAS for 10°)
Final approach .. 65-75 KIAS flaps up / 60-70 flaps 30°
# AFTER LANDING
Flaps .. UP
Transponder .. Standby
# SHUTDOWN
Parking brake .. Set
Throttle .. Idle
Avionics .. OFF
Mixture .. IDLE CUTOFF
Magnetos .. OFF
Master .. OFF
Hobbs / tach .. Recorded
# EMERGENCY · ENGINE FAILURE IN FLIGHT
Airspeed .. 68 KIAS
Landing site .. Choose
Fuel selector .. BOTH
Fuel pump .. ON
Mixture .. RICH
Fuel shutoff valve .. ON
Magnetos .. BOTH (or START if prop stopped)
Mayday .. 121.5, squawk 7700
""".trimIndent()
    }
}
