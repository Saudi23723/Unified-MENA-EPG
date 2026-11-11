package com.saudi.privatevault

import android.app.Activity
import android.app.Dialog
import android.content.Intent
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView

/**
 * The flight maneuvers as the app's own pages, not a scanned book: a list grouped as the ACS
 * groups them, each with its path drawn small, and for each maneuver a short animated clip,
 * the SportStar's numbers, the procedure step by step, the ACS standards and the common errors.
 */
class ManeuversActivity : BaseActivity() {
    companion object {
        const val EXTRA_ID = "maneuver"
        fun open(a: Activity, id: String? = null) = a.startActivity(Intent(a, ManeuversActivity::class.java).apply { if (id != null) putExtra(EXTRA_ID, id) })
    }

    private lateinit var col: LinearLayout
    private fun dp(v: Int) = EfbUi.dp(this, v)
    private fun done(id: String) = VaultLock.prefs(this).getBoolean("man_done_$id", false)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val m = Maneuvers.byId(intent.getStringExtra(EXTRA_ID))
        if (m == null) list() else detail(m)
    }

    override fun onResume() {
        super.onResume()
        if (intent.getStringExtra(EXTRA_ID) == null && ::col.isInitialized && listBuilt) { col.removeAllViews(); fillList() }
    }

    // ---------------------------------------------------------------- the list

    private var listBuilt = false

    private fun list() {
        col = EfbUi.screen(this, getString(R.string.man_title))
        fillList()
        listBuilt = true
        EfbUi.stagger(col)
    }

    private fun fillList() {
        // A hero: the steep turn playing, and what the module holds.
        val hero = FrameLayout(this).apply { background = EfbUi.cardBg(this@ManeuversActivity, 0xFF0E1712.toInt(), 14); clipToOutline = true }
        hero.addView(ManeuverAnimationView(this).apply { anim = Maneuvers.byId("pattern")!!.anim() }, FrameLayout.LayoutParams(-1, dp(230)))
        col.addView(hero, LinearLayout.LayoutParams(-1, dp(230)).apply { topMargin = dp(10) })
        val n = Maneuvers.ALL.size; val k = Maneuvers.ALL.count { done(it.id) }
        col.addView(EfbUi.text(this, getString(R.string.man_intro, n, k), 13f, EfbUi.DIM).apply { setPadding(dp(4), dp(10), dp(4), 0) })

        val book = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            background = EfbUi.cardBg(this@ManeuversActivity, EfbUi.pick(0xFF1C2A3D.toInt(), 0xFFE7F0FF.toInt()), 14)
            setPadding(dp(16), dp(14), dp(14), dp(14)); layoutDirection = View.LAYOUT_DIRECTION_LTR
        }
        book.addView(EfbUi.text(this, "📖", 26f), LinearLayout.LayoutParams(dp(42), -2))
        val bt = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        bt.addView(EfbUi.ltr(EfbUi.text(this, "Jeppesen · Private Pilot Maneuvers", 15.5f, EfbUi.TEXT, bold = true)))
        bt.addView(EfbUi.ltr(EfbUi.text(this, "Your copy, in the app: 33 maneuvers, swipe to turn, pinch to zoom", 12.5f, EfbUi.DIM)))
        book.addView(bt, LinearLayout.LayoutParams(0, -2, 1f))
        book.addView(EfbUi.text(this, "›", 22f, EfbUi.DIM))
        EfbUi.pressable(book) { ManeuverBook.read(this, ManeuverBook.FIRST) }
        col.addView(book, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) })

        for (g in Maneuvers.GROUPS) {
            val items = Maneuvers.ALL.filter { it.group == g }
            if (items.isEmpty()) continue
            col.addView(EfbUi.section(this, g))
            val card = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; background = EfbUi.cardBg(this@ManeuversActivity); layoutDirection = View.LAYOUT_DIRECTION_LTR }
            for ((i, m) in items.withIndex()) {
                if (i > 0) card.addView(View(this).apply { setBackgroundColor(EfbUi.CARD_LINE) }, LinearLayout.LayoutParams(-1, 1).apply { marginStart = dp(104) })
                card.addView(row(m))
            }
            col.addView(card)
        }
        // The book's other maneuvers: its own pages.
        val animated = ManeuverBook.FOR.values.toSet()
        col.addView(EfbUi.section(this, "More from the Jeppesen book"))
        val more = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; background = EfbUi.cardBg(this@ManeuversActivity); layoutDirection = View.LAYOUT_DIRECTION_LTR }
        for ((i, e) in ManeuverBook.ENTRIES.filter { it.no !in animated }.withIndex()) {
            if (i > 0) more.addView(View(this).apply { setBackgroundColor(EfbUi.CARD_LINE) }, LinearLayout.LayoutParams(-1, 1).apply { marginStart = dp(62) })
            val r = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(12), dp(11), dp(12), dp(11)) }
            r.addView(TextView(this).apply {
                text = "${e.no}"; textSize = 13f; typeface = EfbUi.MEDIUM; gravity = Gravity.CENTER; setTextColor(EfbUi.ACCENT)
                background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setStroke(dp(1), EfbUi.ACCENT) }
            }, LinearLayout.LayoutParams(dp(32), dp(32)))
            val t = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(14), 0, dp(6), 0) }
            t.addView(EfbUi.ltr(EfbUi.text(this, e.title, 15f, EfbUi.TEXT, bold = true)))
            t.addView(EfbUi.ltr(EfbUi.text(this, "${e.chapter} · ${e.pages.count()} pages", 12f, EfbUi.DIM)))
            r.addView(t, LinearLayout.LayoutParams(0, -2, 1f))
            r.addView(EfbUi.text(this, "›", 22f, EfbUi.DIM))
            r.setBackgroundResource(R.drawable.item_focus_bg)
            r.setOnClickListener { ManeuverBook.read(this, e.pages.first, e.pages) }
            more.addView(r)
        }
        col.addView(more)
        col.addView(EfbUi.text(this, getString(R.string.man_note), 11.5f, EfbUi.DIM).apply { setPadding(dp(4), dp(18), dp(4), 0) })
    }

    private fun row(m: Maneuvers.M): View {
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(dp(10), dp(10), dp(12), dp(10)) }
        val thumb = FrameLayout(this).apply { background = EfbUi.cardBg(this@ManeuversActivity, 0xFF101A14.toInt(), 8); clipToOutline = true }
        thumb.addView(ManeuverAnimationView(this).apply { this.thumb = true; anim = m.anim() }, FrameLayout.LayoutParams(-1, -1))
        row.addView(thumb, LinearLayout.LayoutParams(dp(82), dp(54)))
        val t = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(12), 0, dp(6), 0) }
        t.addView(EfbUi.ltr(EfbUi.text(this, m.title, 15.5f, EfbUi.TEXT, bold = true)))
        t.addView(EfbUi.ltr(EfbUi.text(this, m.line, 12.5f, EfbUi.DIM)))
        t.addView(EfbUi.ltr(EfbUi.text(this, "ACS ${m.acs}" + if (done(m.id)) "   ✓ practiced" else "", 11f, if (done(m.id)) EfbUi.GOOD else EfbUi.ACCENT, bold = true)).apply { setPadding(0, dp(2), 0, 0) })
        row.addView(t, LinearLayout.LayoutParams(0, -2, 1f))
        row.addView(EfbUi.text(this, "›", 22f, EfbUi.DIM))
        row.setBackgroundResource(R.drawable.item_focus_bg)
        row.setOnClickListener { open(this, m.id) }
        return row
    }

    // ---------------------------------------------------------------- one maneuver

    private fun detail(m: Maneuvers.M) {
        col = EfbUi.screen(this, m.title)
        col.layoutDirection = View.LAYOUT_DIRECTION_LTR
        val anim = m.anim()

        // The clip.
        val frame = FrameLayout(this).apply { background = EfbUi.cardBg(this@ManeuversActivity, 0xFF0E1712.toInt(), 14); clipToOutline = true }
        val view = ManeuverAnimationView(this).apply { this.anim = anim }
        frame.addView(view, FrameLayout.LayoutParams(-1, -1))
        val h = (resources.displayMetrics.widthPixels.coerceAtMost(resources.displayMetrics.heightPixels) * 0.68f).toInt().coerceIn(dp(230), dp(420))
        col.addView(frame, LinearLayout.LayoutParams(-1, h).apply { topMargin = dp(10) })

        // Controls: play/pause, replay, speed, full screen.
        val ctl = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(0, dp(10), 0, 0) }
        val play = chip(if (view.playing) "❚❚  Pause" else "▶  Play", true) { view.playing = !view.playing }
        view.onPlayChanged = { p -> play.text = if (p) "❚❚  Pause" else "▶  Play" }
        ctl.addView(play)
        ctl.addView(chip("↻  Replay") { view.restart() })
        val speeds = listOf(0.5f, 1f, 2f)
        val sChips = ArrayList<TextView>()
        for (s in speeds) {
            val c = chip(if (s == 0.5f) "½×" else "${s.toInt()}×", s == 1f) {
                view.speed = s
                sChips.forEachIndexed { i, tv -> style(tv, speeds[i] == s) }
            }
            sChips += c; ctl.addView(c)
        }
        ctl.addView(View(this), LinearLayout.LayoutParams(0, 1, 1f))
        ctl.addView(chip("⛶") { fullScreen(m) })
        col.addView(android.widget.HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; addView(ctl) })
        col.addView(EfbUi.text(this, getString(R.string.man_hint), 11.5f, EfbUi.DIM).apply { setPadding(dp(4), dp(6), dp(4), 0) })

        // Tags and the one-liner.
        val tags = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(16), 0, 0) }
        tags.addView(tag("ACS ${m.acs}", EfbUi.ACCENT))
        tags.addView(tag(m.group.uppercase(), EfbUi.DIM))
        col.addView(tags)
        col.addView(EfbUi.ltr(EfbUi.text(this, m.line, 19f, EfbUi.TEXT, bold = true)).apply { setPadding(dp(2), dp(8), dp(2), 0) })

        ManeuverBook.entry(ManeuverBook.FOR[m.id])?.let { e ->
            block("📖  Jeppesen · Maneuver ${e.no} · ${e.title}") { c ->
                c.addView(ManeuverBook.strip(this, e))
                c.addView(chip("📖  Read these ${e.pages.count()} pages", true) { ManeuverBook.read(this, e.pages.first, e.pages) }.apply {
                    (layoutParams as LinearLayout.LayoutParams).topMargin = dp(10)
                })
            }
        }

        block("Objective") { it.addView(body(m.objective)) }

        block("SportStar MAX numbers") { c -> pairs(c, m.numbers, EfbUi.TEXT) }

        block("Procedure") { c ->
            for ((i, s) in m.steps.withIndex()) {
                val r = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, if (i == 0) 0 else dp(12), 0, 0) }
                val num = TextView(this).apply {
                    text = "${i + 1}"; textSize = 12.5f; typeface = EfbUi.MEDIUM; gravity = Gravity.CENTER; setTextColor(0xFFFFFFFF.toInt())
                    background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(EfbUi.ACCENT) }
                }
                r.addView(num, LinearLayout.LayoutParams(dp(24), dp(24)))
                r.addView(body(s).apply { setPadding(dp(12), dp(1), 0, 0) }, LinearLayout.LayoutParams(0, -2, 1f))
                c.addView(r)
            }
        }

        block("ACS standards") { c -> pairs(c, m.standards, EfbUi.GOOD) }

        block("Common errors") { c ->
            for (e in m.errors) {
                val r = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(6), 0, dp(2)) }
                r.addView(EfbUi.text(this, "✕", 13f, EfbUi.BAD, bold = true), LinearLayout.LayoutParams(dp(22), -2))
                r.addView(body(e), LinearLayout.LayoutParams(0, -2, 1f))
                c.addView(r)
            }
        }

        // The instructor's tip, set apart.
        val tip = EfbUi.card(this).apply {
            background = EfbUi.cardBg(this@ManeuversActivity, EfbUi.pick(0xFF1C2A3D.toInt(), 0xFFE7F0FF.toInt()), 14)
        }
        tip.addView(EfbUi.text(this, "💡  INSTRUCTOR TIP", 11.5f, EfbUi.ACCENT, bold = true).apply { letterSpacing = 0.06f })
        tip.addView(body(m.tip).apply { setPadding(0, dp(6), 0, 0) })
        col.addView(tip)

        // Practiced, and the neighbours.
        val mark = com.google.android.material.button.MaterialButton(this).apply {
            fun label() { text = if (done(m.id)) "✓  Practiced — tap to clear" else "Mark as practiced" }
            label()
            setOnClickListener { VaultLock.prefs(this@ManeuversActivity).edit().putBoolean("man_done_${m.id}", !done(m.id)).apply(); label() }
        }
        col.addView(mark, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(16) })
        val all = Maneuvers.ALL; val i = all.indexOf(m)
        val nav = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(8), 0, 0) }
        all.getOrNull(i - 1)?.let { p -> nav.addView(navCard("‹  Previous", p.title) { finish(); open(this, p.id) }, LinearLayout.LayoutParams(0, -2, 1f).apply { marginEnd = dp(6) }) }
            ?: nav.addView(View(this), LinearLayout.LayoutParams(0, 1, 1f))
        all.getOrNull(i + 1)?.let { n -> nav.addView(navCard("Next  ›", n.title) { finish(); open(this, n.id) }, LinearLayout.LayoutParams(0, -2, 1f).apply { marginStart = dp(6) }) }
            ?: nav.addView(View(this), LinearLayout.LayoutParams(0, 1, 1f))
        col.addView(nav)
        col.addView(EfbUi.text(this, getString(R.string.man_note), 11.5f, EfbUi.DIM).apply { setPadding(dp(4), dp(16), dp(4), 0) })
    }

    private fun body(s: String) = EfbUi.ltr(EfbUi.text(this, s, 14.5f, EfbUi.TEXT)).apply { setLineSpacing(0f, 1.18f) }

    private fun block(title: String, fill: (LinearLayout) -> Unit) {
        col.addView(EfbUi.section(this, title))
        val c = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; background = EfbUi.cardBg(this@ManeuversActivity)
            setPadding(dp(16), dp(14), dp(16), dp(14))
        }
        fill(c)
        col.addView(c)
    }

    private fun pairs(c: LinearLayout, rows: List<Pair<String, String>>, valueColor: Int) {
        for ((i, p) in rows.withIndex()) {
            if (i > 0) c.addView(View(this).apply { setBackgroundColor(EfbUi.CARD_LINE) }, LinearLayout.LayoutParams(-1, 1).apply { topMargin = dp(9); bottomMargin = dp(9) })
            val r = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
            r.addView(EfbUi.ltr(EfbUi.text(this, p.first, 13.5f, EfbUi.DIM)), LinearLayout.LayoutParams(0, -2, 0.9f))
            r.addView(EfbUi.ltr(EfbUi.text(this, p.second, 14.5f, valueColor, bold = true)).apply { gravity = Gravity.END }, LinearLayout.LayoutParams(0, -2, 1.3f))
            c.addView(r)
        }
    }

    private fun tag(s: String, color: Int) = TextView(this).apply {
        text = s; textSize = 10.5f; typeface = EfbUi.MEDIUM; letterSpacing = 0.05f; setTextColor(color)
        background = GradientDrawable().apply { cornerRadius = dp(10).toFloat(); setStroke(dp(1), color) }
        setPadding(dp(9), dp(3), dp(9), dp(3))
        layoutParams = LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(8) }
    }

    private fun style(tv: TextView, on: Boolean) {
        tv.setTextColor(if (on) 0xFFFFFFFF.toInt() else EfbUi.TEXT)
        tv.background = GradientDrawable().apply { cornerRadius = dp(18).toFloat(); setColor(if (on) EfbUi.ACCENT else EfbUi.CARD); if (!on) setStroke(dp(1), EfbUi.CARD_LINE) }
    }

    private fun chip(s: String, on: Boolean = false, click: () -> Unit) = TextView(this).apply {
        text = s; textSize = 13.5f; typeface = EfbUi.MEDIUM; gravity = Gravity.CENTER
        setPadding(dp(14), dp(8), dp(14), dp(8)); minWidth = dp(44)
        style(this, on)
        layoutParams = LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(8) }
        EfbUi.pressable(this) { click() }
    }

    private fun navCard(head: String, title: String, click: () -> Unit) = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL; background = EfbUi.cardBg(this@ManeuversActivity); setPadding(dp(14), dp(10), dp(14), dp(12))
        addView(EfbUi.text(this@ManeuversActivity, head, 11.5f, EfbUi.ACCENT, bold = true))
        addView(EfbUi.ltr(EfbUi.text(this@ManeuversActivity, title, 13.5f, EfbUi.TEXT)).apply { maxLines = 2 })
        EfbUi.pressable(this) { click() }
    }

    /** The clip alone, the whole screen, landscape or portrait as the device is held. */
    private fun fullScreen(m: Maneuvers.M) {
        val d = Dialog(this, android.R.style.Theme_Black_NoTitleBar_Fullscreen)
        val f = FrameLayout(this).apply { setBackgroundColor(0xFF0E1712.toInt()) }
        val v = ManeuverAnimationView(this).apply { anim = m.anim() }
        f.addView(v, FrameLayout.LayoutParams(-1, -1))
        f.addView(TextView(this).apply {
            text = "✕"; textSize = 20f; setTextColor(0xFFFFFFFF.toInt()); gravity = Gravity.CENTER
            background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(0x99000000.toInt()) }
            setOnClickListener { d.dismiss() }
        }, FrameLayout.LayoutParams(dp(40), dp(40), Gravity.TOP or Gravity.END).apply { setMargins(dp(12), dp(64), dp(12), dp(12)) })
        f.addView(TextView(this).apply {
            text = m.title; textSize = 13f; typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL); setTextColor(0xCCFFFFFF.toInt())
        }, FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM or Gravity.END).apply { setMargins(dp(12), dp(12), dp(14), dp(48)) })
        d.setContentView(f)
        d.show()
    }
}
