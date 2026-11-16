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
    private class Match(val start: Long, val stop: Long, val title: String, val channels: MutableList<Channel>) { var live = false; var names = "" }
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

    /** the day's real broadcast listings (livefootballtv + live-footballontv, gathered by the repo every few minutes):
     *  live matches only, each with the channels that carry it. The file prints its times in US Pacific;
     *  they are turned into world time here, then shown in this device's clock. */
    private fun listings(): List<Triple<Long, String, String>> {
        val xml = App.http.newCall(okhttp3.Request.Builder()
            .url("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/main/today_matches_epg.xml?t=" + System.currentTimeMillis() / 300_000).build())
            .execute().use { it.body!!.string() }
        val zone = java.time.ZoneId.of("America/Los_Angeles")
        val bidi = Regex("[\u2066-\u2069\u200E\u200F\u202A-\u202E]")
        val head = Regex("(\\d{2})/(\\d{2})")
        val row = Regex("^\\s*\\S*\\s*(\\d{1,2}):(\\d{2})\\s+(.+)$")
        // the desc of each day's first block lists the whole day
        val days = LinkedHashMap<String, String>(); val years = HashMap<String, Int>()
        val parser = android.util.Xml.newPullParser()
        parser.setInput(java.io.StringReader(xml))
        var start = ""; var inDesc = false
        while (parser.next() != org.xmlpull.v1.XmlPullParser.END_DOCUMENT) {
            when (parser.eventType) {
                org.xmlpull.v1.XmlPullParser.START_TAG -> {
                    if (parser.name == "programme") start = parser.getAttributeValue(null, "start") ?: ""
                    inDesc = parser.name == "desc"
                }
                org.xmlpull.v1.XmlPullParser.TEXT -> if (inDesc) {
                    val d = parser.text.replace(bidi, "")
                    val h = d.lineSequence().firstOrNull() ?: ""
                    if ((days[h]?.length ?: 0) < d.length) { days[h] = d; years[h] = start.take(4).toIntOrNull() ?: 2026 }
                }
                org.xmlpull.v1.XmlPullParser.END_TAG -> inDesc = false
            }
        }
        val out = ArrayList<Triple<Long, String, String>>()
        for ((h, d) in days) {
            val m = head.find(h) ?: continue
            val day = m.groupValues[1].toInt(); val month = m.groupValues[2].toInt(); val year = years[h] ?: 2026
            val lines = d.lines()
            var k = 1
            while (k < lines.size) {
                val r = row.find(lines[k])
                if (r != null) {
                    val t = java.time.ZonedDateTime.of(year, month, day, r.groupValues[1].toInt(), r.groupValues[2].toInt(), 0, 0, zone).toEpochSecond()
                    val chans = lines.getOrNull(k + 1)?.takeIf { row.find(it) == null }?.trim() ?: ""
                    out.add(Triple(t, r.groupValues[3].trim(), chans))
                }
                k++
            }
        }
        return out
    }

    /** "beIN 5", "TNT 2", "Alwan 3", "Sky Sports Football" -> the playlist's channels with that name (every quality) */
    private fun channelsFor(names: String, all: Map<String, List<Channel>>): MutableList<Channel> {
        val out = ArrayList<Channel>()
        for (n in names.split("·", "+").map { it.trim() }.filter { it.length > 1 }) {
            val k = key(n)
            if (k.length < 3) continue
            all[k]?.forEach { c -> if (out.none { it.id == c.id }) out.add(c) }
        }
        // owner, 4 Nov 2026: Alwan and Fajer first, then beIN, TNT, Sky, TSN, Fox, CBS; inside each: HEVC / RAW, 4K, FHD, HD, SD
        return out.sortedWith(compareBy({ brand(it.name) }, { tier(it.name) })).toMutableList()
    }

    private val brands = listOf(Regex("(?i)alwan|ألوان"), Regex("(?i)fajer|fajr|الفجر"), Regex("(?i)\\bbe ?in\\b"),
        Regex("(?i)\\btnt\\b"), Regex("(?i)\\bsky\\b"), Regex("(?i)\\btsn"), Regex("(?i)\\bfox\\b"), Regex("(?i)\\bcbs\\b"))
    private fun brand(n: String) = brands.indexOfFirst { it.containsMatchIn(n) }.let { if (it < 0) brands.size else it }
    private fun tier(n: String): Int {
        val u = java.text.Normalizer.normalize(n, java.text.Normalizer.Form.NFKC).uppercase()
        return when {
            Regex("\\b(HEVC|H265|RAW)\\b").containsMatchIn(u) -> 0
            Regex("\\b(4K|UHD|8K|2160P?|3840P?)\\b").containsMatchIn(u) -> 1
            Regex("\\b(FHD|1080P?)\\b").containsMatchIn(u) -> 2
            Regex("\\b(SD|LQ|LOW|LITE)\\b").containsMatchIn(u) -> 4
            else -> 3
        }
    }

    private fun key(n: String) = Api.baseName(n).replace("SPORT", "").replace("ENGLISH", "EN").replace("الكأس", "ALKASS").replace("ALKAS", "ALKASS")

    private fun load() = lifecycleScope.launch {
        val found = withContext(Dispatchers.IO) {
            if (Api.groups.isEmpty()) try { Api.load(cached = true) } catch (_: Exception) { }
            val rows = try { listings() } catch (e: Exception) { emptyList() }
            val all = (Api.groups.firstOrNull { it.id == Api.ALL }?.channels ?: emptyList()).filter { it.id > 0 }.groupBy { key(it.name) }
            val now = System.currentTimeMillis() / 1000
            rows.filter { it.first + 2 * 3600 > now }.distinctBy { it.first.toString() + it.second.lowercase() }.sortedBy { it.first }.map { (t, title, names) ->
                Match(t, t + 2 * 3600, title, channelsFor(names, all)).also { it.names = names }
            }
        }
        items = found; adapter.notifyDataSetChanged()
        info.text = (if (found.isEmpty()) "No live matches listed right now" else "${found.size} live matches") +
            "   ·   times in your clock (" + java.util.TimeZone.getDefault().id + ")   ·   OK watch · hold OK remind me"
    }

    private fun watch(m: Match) {
        if (m.channels.isEmpty()) {
            android.widget.Toast.makeText(this, "On ${m.names.ifEmpty { "—" }} · not found in your playlist", android.widget.Toast.LENGTH_LONG).show(); return
        }
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
                val c = m.channels.firstOrNull() ?: return@setOnLongClickListener true
                val on = Reminders.toggle(Reminder(c.id, m.start, m.title, c.name))
                android.widget.Toast.makeText(this@SportsActivity, if (on) "⏰ I'll switch to it a minute before" else "Reminder removed", android.widget.Toast.LENGTH_SHORT).show()
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
            h.title.text = m.title
            h.desc.text = m.names + if (m.channels.isEmpty()) "   ·   not in your playlist" else "   ·   ${m.channels.size} in your playlist"
            val nowS = System.currentTimeMillis() / 1000
            val live = nowS in m.start until m.stop
            h.mark.text = when { live -> "LIVE"; m.channels.isNotEmpty() && Reminders.has(m.channels.first().id, m.start) -> "⏰"; else -> "" }
            h.mark.setTextColor(getColor(if (live) R.color.live else R.color.accent))
            if (i == 0 && !h.row.hasFocus()) h.row.post { if (currentFocus == null) h.row.requestFocus() }
        }
    }
}
