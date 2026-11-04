package com.saudi1.tv

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Typeface
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Sports today: the matches of the coming 2 days from the guide of the playlist's sports channels.
 *  Every time is shown in the device's own clock (the guide is kept in world time), so it is right in
 *  Amman, Dubai, London or Chicago alike. OK = watch (choose the channel), hold OK = remind me. */
@SuppressLint("NotifyDataSetChanged", "SetTextI18n")
class SportsActivity : BaseActivity() {
    private class Match(val start: Long, val stop: Long, val title: String, val channels: MutableList<Channel>) { var live = false }
    private var items: List<Match> = emptyList()
    private lateinit var info: TextView
    private val d by lazy { resources.displayMetrics.density }
    private val timeF = SimpleDateFormat("h:mm a", Locale.ENGLISH)
    private val dayF = SimpleDateFormat("EEEE d MMMM", Locale.ENGLISH)
    private val adapter = A()

    /** only the sports channels the owner chose (by channel or group name) */
    private val sportChan = Regex("(?i)tnt\\s*sports?|sky\\s*sports?|\\btsn\\b|sportsnet|bein|ʙᴇɪɴ|thmanyah|thamanya|ثمانية|alwan|ألوان|الوان|fajer|فجر|shasha|شاشا|tabii|trt\\s*spor")
    /** the guide's own countdown blocks before a match ("⏰ Next: …"): the match itself comes after them */
    private val filler = Regex("(?i)^\\s*⏰|التالي\\s*:|المباراة القادمة|\\bnext\\s*:|\\bup next\\b|\\bcoming up\\b|program 24/7")
    private val liveMark = Regex("(?i)\\blive\\b|مباشر|🔴|\\(l\\)|\\[l\\]|canlı|en vivo|en direct")
    private val replayMark = Regex("(?i)\\breplay\\b|\\brepeat\\b|\\bdelayed\\b|\\(r\\)|\\[r\\]|إعادة|اعادة|مسجل|tekrar|\\bbant\\b|\\bretro\\b|\\bclassics?\\b|best of|rewind|rediffusion|\\bencore\\b")
    /** a match: two sides (Team A vs / v / × / x / ضد / - Team B) */
    private val matchTitle = Regex("(?i)\\S.*\\s(vs\\.?|v|×|x|ضد|–|-)\\s.*\\S")
    private val notMatch = Regex("(?i)\\b(news|highlights|magazine|review|preview|replay|classic|studio|show|talk|podcast|weekly|countdown)\\b|ملخص|إعادة|اعادة|استوديو|برنامج|أخبار|اخبار")

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding((40 * d).toInt(), (26 * d).toInt(), (40 * d).toInt(), 0) }
        val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = android.view.Gravity.CENTER_VERTICAL }
        top.addView(TextView(this).apply { text = "⚽  Sports today"; textSize = 28f; setTypeface(typeface, Typeface.BOLD) },
            LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        top.addView(TextView(this).apply {
            text = "📺  Guide screens"; textSize = 15f; setTypeface(typeface, Typeface.BOLD); isFocusable = true; isClickable = true
            setBackgroundResource(R.drawable.tile_bg); setTextColor(getColorStateList(R.color.on_focus))
            setPadding((18 * d).toInt(), (10 * d).toInt(), (18 * d).toInt(), (10 * d).toInt())
            setOnClickListener { startActivity(Intent(this@SportsActivity, LiveActivity::class.java).putExtra("group", Api.DASH)) }
        })
        col.addView(top)
        info = TextView(this).apply {
            textSize = 14f; setTextColor(getColor(R.color.text2)); setPadding(0, (6 * d).toInt(), 0, (8 * d).toInt())
            text = "Loading the matches…  ·  times in your clock (" + java.util.TimeZone.getDefault().id + ")"
        }
        col.addView(info)
        val rv = RecyclerView(this).apply {
            layoutManager = LinearLayoutManager(this@SportsActivity); adapter = this@SportsActivity.adapter
            clipToPadding = false; setPadding(0, 0, 0, (120 * d).toInt())
        }
        col.addView(rv, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        setContentView(col)
        load()
    }

    private fun load() = lifecycleScope.launch {
        val found = withContext(Dispatchers.IO) {
            if (Api.groups.isEmpty()) try { Api.load(cached = true) } catch (_: Exception) { }
            val chans = Api.groups.filter { it.id != Api.FAV && it.id != Api.SEARCH }
                .flatMap { g -> g.channels.filter { c -> sportChan.containsMatchIn(c.name) || (g.id != Api.ALL && sportChan.containsMatchIn(g.name)) } }
                .filter { it.id > 0 }.distinctBy { it.id }
            // one channel per quality family is enough to read the guide (4K / FHD / HD share it)
            val readers = chans.groupBy { Api.baseName(it.name) }.values.map { it.first() }.take(220)
            val now = System.currentTimeMillis() / 1000
            val until = now + 48 * 3600
            val byKey = LinkedHashMap<String, Match>()
            readers.chunked(10).forEach { part ->
                part.map { c -> async { c to Api.guide(c) } }.map { it.await() }.forEach { (c, list) ->
                    for (p in list) {
                        if (p.stop <= now || p.start > until || !matchTitle.containsMatchIn(p.title) || notMatch.containsMatchIn(p.title) ||
                            replayMark.containsMatchIn(p.title) || replayMark.containsMatchIn(p.desc) ||
                            filler.containsMatchIn(p.title)) continue  // recorded / replays / "next match" countdown blocks are left out
                        val t = p.title.replace(Regex("(?i)^\\s*(live|مباشر)\\s*[:|-]?\\s*"), "").trim()
                        val k = (p.start / 300).toString() + "|" + t.lowercase().replace(Regex("[^\\p{L}\\p{N}]"), "")
                        val m = byKey.getOrPut(k) { Match(p.start, p.stop, t, ArrayList()) }
                        if (liveMark.containsMatchIn(p.title) || liveMark.containsMatchIn(p.desc)) m.live = true
                        // every quality of that channel can play it
                        Api.qualities(c).forEach { q -> if (m.channels.none { it.id == q.id }) m.channels.add(q) }
                    }
                }
                val snap = byKey.values.sortedBy { it.start }
                withContext(Dispatchers.Main) { items = snap; adapter.notifyDataSetChanged(); info.text = "${snap.size} matches so far…" }
            }
            byKey.values.sortedBy { it.start }
        }
        items = found; adapter.notifyDataSetChanged()
        info.text = (if (found.isEmpty()) "No matches found in the guide right now" else "${found.size} matches") +
            "   ·   times in your clock (" + java.util.TimeZone.getDefault().id + ")   ·   OK watch · hold OK remind me"
    }

    private fun watch(m: Match) {
        if (m.channels.size == 1) { tune(m.channels[0]); return }
        AlertDialog.Builder(this).setTitle(m.title)
            .setItems(m.channels.map { "${it.num}   ${it.name}   ·   " + (Api.group(it.group)?.name ?: "") }.toTypedArray()) { _, w -> tune(m.channels[w]) }.show()
    }

    private fun tune(c: Channel) = startActivity(Intent(this, LiveActivity::class.java).putExtra("channel", c.id))

    inner class A : RecyclerView.Adapter<A.H>() {
        inner class H(v: View) : RecyclerView.ViewHolder(v) {
            val day: TextView = v.findViewById(R.id.day); val row: View = v.findViewById(R.id.row)
            val time: TextView = v.findViewById(R.id.time); val title: TextView = v.findViewById(R.id.title)
            val desc: TextView = v.findViewById(R.id.desc); val mark: TextView = v.findViewById(R.id.mark)
        }
        override fun getItemCount() = items.size
        override fun onCreateViewHolder(p: ViewGroup, t: Int): H {
            val h = H(LayoutInflater.from(p.context).inflate(R.layout.item_guide, p, false))
            h.row.setOnClickListener { items.getOrNull(h.bindingAdapterPosition)?.let { watch(it) } }
            h.row.setOnLongClickListener {
                val m = items.getOrNull(h.bindingAdapterPosition) ?: return@setOnLongClickListener true
                val c = m.channels.first()
                val on = Reminders.toggle(Reminder(c.id, m.start, m.title, c.name))
                android.widget.Toast.makeText(this@SportsActivity, if (on) "⏰ I'll remind you 10 s before" else "Reminder removed", android.widget.Toast.LENGTH_SHORT).show()
                notifyItemChanged(h.bindingAdapterPosition); true
            }
            return h
        }
        override fun onBindViewHolder(h: H, i: Int) {
            val m = items[i]
            val dd = dayF.format(Date(m.start * 1000))
            val prev = items.getOrNull(i - 1)?.let { dayF.format(Date(it.start * 1000)) }
            h.day.visibility = if (dd != prev) View.VISIBLE else View.GONE
            val today = dayF.format(Date()); val tomorrow = dayF.format(Date(System.currentTimeMillis() + 86_400_000))
            h.day.text = when (dd) { today -> "Today · $dd"; tomorrow -> "Tomorrow · $dd"; else -> dd }
            h.time.text = timeF.format(Date(m.start * 1000))
            h.title.text = (if (m.live) "🔴 " else "") + m.title
            h.desc.text = m.channels.take(4).joinToString("  ·  ") { it.name } + if (m.channels.size > 4) "  +${m.channels.size - 4}" else ""
            val nowS = System.currentTimeMillis() / 1000
            val live = nowS in m.start until m.stop
            h.mark.text = when { live -> "LIVE"; Reminders.has(m.channels.first().id, m.start) -> "⏰"; else -> "" }
            h.mark.setTextColor(getColor(if (live) R.color.live else R.color.accent))
            if (i == 0 && !h.row.hasFocus()) h.row.post { if (currentFocus == null) h.row.requestFocus() }
        }
    }
}
