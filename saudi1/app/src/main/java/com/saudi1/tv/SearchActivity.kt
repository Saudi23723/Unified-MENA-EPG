package com.saudi1.tv

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Typeface
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.KeyEvent
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import coil.load
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** One search for everything (like HotPlayer): from the 3rd letter the results show while typing —
 *  live channels, movies and series in three rows. */
@SuppressLint("NotifyDataSetChanged", "SetTextI18n")
class SearchActivity : BaseActivity() {
    private val d by lazy { resources.displayMetrics.density }
    private lateinit var box: EditText
    private lateinit var info: TextView
    private var job: Job? = null
    private val live = Row(0); private val movies = Row(1); private val series = Row(2); private val progs = Row(3)
    private var guides: List<Pair<Channel, List<Program>>> = emptyList()
    private var allMovies: List<VodItem>? = null
    private var allSeries: List<VodItem>? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding((40 * d).toInt(), (28 * d).toInt(), (40 * d).toInt(), (40 * d).toInt()) }
        box = EditText(this).apply {
            hint = "Search channels, movies and series…"; setSingleLine(); textSize = 22f
            setBackgroundResource(R.drawable.edit_bg); setPadding((20 * d).toInt(), 0, (20 * d).toInt(), 0)
            imeOptions = EditorInfo.IME_ACTION_SEARCH
            setOnEditorActionListener { _, _, _ -> hideKeyboard(); firstResult()?.requestFocus(); true }
        }
        col.addView(box, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, (60 * d).toInt()))
        info = TextView(this).apply { textSize = 15f; setTextColor(getColor(R.color.text2)); setPadding((6 * d).toInt(), (10 * d).toInt(), 0, 0); text = "Type 3 letters or more" }
        col.addView(info)
        // movies / series lists load in the background while the viewer types
        val mode = intent.getStringExtra("mode") ?: ""
        listOf(live to "Live TV", progs to "TV Guide (programs)", movies to "Movies", series to "Series").let { rows ->
            (if (mode == "s") listOf(rows[3], rows[2], rows[0], rows[1]) else if (mode == "m") listOf(rows[2], rows[3], rows[0], rows[1]) else rows).forEach { (r, t) -> r.attach(col, t) }
        }
        setContentView(ScrollView(this).apply { addView(col); isFillViewport = true })
        box.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            override fun afterTextChanged(s: Editable?) { query(s.toString()) }
        })
        lifecycleScope.launch(Dispatchers.IO) {
            if (Api.groups.isEmpty()) try { Api.load(cached = true) } catch (_: Exception) { }
            // the guide of the channels the viewer uses (favorites, last watched, the group open last): searched by program name
            val chans = (Api.groups.firstOrNull { it.id == Api.FAV }?.channels.orEmpty() + History.ids().mapNotNull { Api.byId[it] } +
                Api.group(Prefs.lastGroup)?.channels.orEmpty()).filter { it.id > 0 }.distinctBy { it.id }.take(80)
            val got = ArrayList<Pair<Channel, List<Program>>>()
            chans.chunked(8).forEach { part ->
                part.map { c -> async { c to Api.guide(c) } }.forEach { got.add(it.await()) }
                guides = got.toList()
            }
            withContext(Dispatchers.Main) { if (box.text.length >= 3) query(box.text.toString()) }
            allMovies = try { Vod.all(false) } catch (e: Exception) { emptyList() }
            allSeries = try { Vod.all(true) } catch (e: Exception) { emptyList() }
            withContext(Dispatchers.Main) { if (box.text.length >= 3) query(box.text.toString()) }
        }
        box.requestFocus()
    }

    private fun hideKeyboard() = (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).hideSoftInputFromWindow(box.windowToken, 0)

    private fun firstResult(): View? = listOf(live, progs, movies, series).sortedBy { it.order }.firstOrNull { it.items.isNotEmpty() }?.rv?.getChildAt(0)

    private fun norm(s: String) = java.text.Normalizer.normalize(s, java.text.Normalizer.Form.NFKD).replace(Regex("\\p{M}"), "").lowercase()

    private fun query(q0: String) {
        val q = norm(q0.trim())
        job?.cancel()
        if (q.length < 3) { listOf(live, progs, movies, series).forEach { it.set(emptyList()) }; info.text = "Type 3 letters or more"; return }
        job = lifecycleScope.launch {
            delay(250)
            val words = q.split(' ').filter { it.isNotEmpty() }
            fun hit(n: String) = norm(n).let { nn -> words.all { nn.contains(it) } }
            val (l, m, s) = withContext(Dispatchers.Default) {
                val ch = (Api.groups.firstOrNull { it.id == Api.ALL }?.channels ?: emptyList()).filter { hit(it.name) }.take(200)
                val mv = (allMovies ?: emptyList()).filter { hit(it.name) }.sortedByDescending { it.added }.take(200)
                val se = (allSeries ?: emptyList()).filter { hit(it.name) }.sortedByDescending { it.added }.take(200)
                Triple(ch.map { Item(it.name, it.logo, it, null, false) }, mv.map { Item(it.name, it.poster, null, it, false) }, se.map { Item(it.name, it.poster, null, it, true) })
            }
            val tf = java.text.SimpleDateFormat("EEE h:mm a", java.util.Locale.ENGLISH)
            val now = System.currentTimeMillis() / 1000
            val pr = withContext(Dispatchers.Default) {
                guides.flatMap { (c, list) -> list.filter { it.stop > now && hit(it.title) }.map { c to it } }.sortedBy { it.second.start }.take(150)
                    .map { (c, p) -> Item(p.title, c.logo, c, null, false, (if (p.now(now)) "● Now  ·  " else tf.format(java.util.Date(p.start * 1000)) + "  ·  ") + c.name) }
            }
            live.set(l); progs.set(pr); movies.set(m); series.set(s)
            val loading = if (allMovies == null) "   ·   movies & series still loading…" else ""
            info.text = "${l.size} channels   ·   ${pr.size} programs   ·   ${m.size} movies   ·   ${s.size} series$loading"
        }
    }

    private class Item(val name: String, val image: String, val channel: Channel?, val vod: VodItem?, val series: Boolean, val sub: String = "")

    private fun open(it: Item) {
        it.channel?.let { c ->
            startActivity(Intent(this, LiveActivity::class.java).putExtra("channel", c.id).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)); return
        }
        val v = it.vod ?: return
        startActivity(Intent(this, VodDetailActivity::class.java).putExtra("series", it.series).putExtra("id", v.id)
            .putExtra("name", v.name).putExtra("poster", v.poster).putExtra("ext", v.ext))
    }

    override fun dispatchKeyEvent(e: KeyEvent): Boolean {
        // ▼ from the search box goes to the first results row
        if (e.action == KeyEvent.ACTION_DOWN && e.keyCode == KeyEvent.KEYCODE_DPAD_DOWN && box.hasFocus()) {
            firstResult()?.let { hideKeyboard(); it.requestFocus(); return true }
        }
        return super.dispatchKeyEvent(e)
    }

    /** one horizontal row of results */
    private inner class Row(val kind: Int) {
        var items: List<Item> = emptyList()
        var order = 0
        lateinit var rv: RecyclerView
        lateinit var title: TextView
        lateinit var name: String
        private val adapter = object : RecyclerView.Adapter<RecyclerView.ViewHolder>() {
            override fun getItemCount() = items.size
            override fun onCreateViewHolder(p: ViewGroup, t: Int): RecyclerView.ViewHolder {
                val v = if (kind == 0 || kind == 3) LayoutInflater.from(p.context).inflate(R.layout.item_channel, p, false).apply {
                    layoutParams = RecyclerView.LayoutParams((330 * d).toInt(), (64 * d).toInt()).apply { marginEnd = (10 * d).toInt() }
                } else LayoutInflater.from(p.context).inflate(R.layout.item_poster, p, false).apply {
                    layoutParams = RecyclerView.LayoutParams((170 * d).toInt(), ViewGroup.LayoutParams.WRAP_CONTENT)
                    findViewById<View>(R.id.poster).parent.let { (it as View).layoutParams.height = (240 * d).toInt() }
                }
                val h = object : RecyclerView.ViewHolder(v) {}
                v.setOnClickListener { items.getOrNull(h.bindingAdapterPosition)?.let { open(it) } }
                v.setOnFocusChangeListener { _, f -> v.findViewById<TextView>(R.id.name)?.isSelected = f }
                return h
            }
            override fun onBindViewHolder(h: RecyclerView.ViewHolder, i: Int) {
                val it = items[i]; val v = h.itemView
                v.findViewById<TextView>(R.id.name).text = it.name
                if (kind == 0 || kind == 3) {
                    v.findViewById<TextView>(R.id.num).text = if (kind == 3) "" else it.channel?.num?.toString() ?: ""
                    v.findViewById<TextView>(R.id.now).text = if (kind == 3) it.sub else Api.group(it.channel?.group)?.name ?: ""
                    v.findViewById<ImageView>(R.id.logo).let { img -> if (it.image.isEmpty()) img.setImageDrawable(null) else img.load(it.image) { size(124, 80) } }
                } else {
                    val img = v.findViewById<ImageView>(R.id.poster)
                    if (it.image.isEmpty()) img.setImageResource(R.drawable.banner) else img.load(it.image) { size(240, 360); error(R.drawable.banner) }
                    v.findViewById<TextView>(R.id.rating).let { r ->
                        r.text = it.vod?.rating?.toDoubleOrNull()?.let { x -> "★ " + "%.1f".format(x) } ?: ""
                        r.visibility = if (r.text.isEmpty()) View.GONE else View.VISIBLE
                    }
                }
            }
        }

        fun attach(col: LinearLayout, t: String) {
            name = t; order = col.childCount
            title = TextView(this@SearchActivity).apply {
                textSize = 18f; setTypeface(typeface, Typeface.BOLD); setTextColor(getColor(R.color.accent))
                setPadding((6 * d).toInt(), (20 * d).toInt(), 0, (8 * d).toInt()); visibility = View.GONE
            }
            rv = RecyclerView(this@SearchActivity).apply {
                layoutManager = LinearLayoutManager(this@SearchActivity, LinearLayoutManager.HORIZONTAL, false)
                adapter = this@Row.adapter; visibility = View.GONE; clipToPadding = false; setPadding(0, 0, (200 * d).toInt(), 0)
            }
            col.addView(title); col.addView(rv, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        }

        fun set(l: List<Item>) {
            items = l; adapter.notifyDataSetChanged(); rv.scrollToPosition(0)
            title.text = "$name   ${l.size}"
            title.visibility = if (l.isEmpty()) View.GONE else View.VISIBLE
            rv.visibility = title.visibility
        }
    }
}
