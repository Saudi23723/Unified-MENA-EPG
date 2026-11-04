package com.saudi1.tv

import android.annotation.SuppressLint
import android.content.Intent
import android.os.Bundle
import android.view.KeyEvent
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.ImageView
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.GridLayoutManager
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import coil.load
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Movies or Series: groups on the left, posters on the right (one group loaded at a time: fast, little memory). */
@SuppressLint("NotifyDataSetChanged", "SetTextI18n")
class VodActivity : BaseActivity() {
    private var series = false
    private var cats: List<VodCat> = emptyList()
    private var items: List<VodItem> = emptyList()
    private var current = ""
    private var loadJob: Job? = null
    private lateinit var catsRv: RecyclerView
    private lateinit var grid: RecyclerView
    private val catAdapter = CatAdapter()
    private val gridAdapter = GridAdapter()

    companion object { const val RESUME = "__resume"; const val SEARCH = "__search"; const val FAV = "__fav"; const val COLS = 4 }

    /** newest added by the provider first (like the provider's "last modified"), or A–Z, or by rating */
    private val sortNames = arrayOf("Latest added", "A – Z", "Top rated")
    private var sort: Int
        get() = App.prefs.getInt("vod_sort", 0)
        set(v) = App.prefs.edit().putInt("vod_sort", v).apply()

    private fun sorted(l: List<VodItem>): List<VodItem> = when (sort) {
        0 -> if (l.any { it.added > 0 }) l.sortedByDescending { it.added } else l
        1 -> l.sortedBy { it.name.lowercase() }
        else -> l.sortedByDescending { it.rating.toDoubleOrNull() ?: 0.0 }
    }

    private fun sortDialog() {
        AlertDialog.Builder(this).setTitle("Sort").setSingleChoiceItems(sortNames, sort) { d, w ->
            sort = w; d.dismiss(); findViewById<TextView>(R.id.vodSort).text = "⇅  " + sortNames[w]
            if (current != RESUME && current != SEARCH) cats.firstOrNull { it.id == current }?.let { open(it) }
        }.show()
    }

    private fun favKey() = if (series) "vfav_s" else "vfav_m"
    private fun favs(): List<org.json.JSONObject> = try {
        val a = org.json.JSONArray(App.prefs.getString(favKey(), "[]")); (0 until a.length()).map { a.getJSONObject(it) }
    } catch (e: Exception) { emptyList() }
    private fun isFav(id: Int) = favs().any { it.optInt("id") == id }
    private fun toggleFav(it: VodItem) {
        val l = favs().toMutableList()
        val on = l.none { f -> f.optInt("id") == it.id }
        if (on) l.add(0, org.json.JSONObject().put("id", it.id).put("n", it.name).put("p", it.poster).put("e", it.ext).put("r", it.rating))
        else l.removeAll { f -> f.optInt("id") == it.id }
        App.prefs.edit().putString(favKey(), org.json.JSONArray(l).toString()).apply()
        android.widget.Toast.makeText(this, if (on) "★ Added to Favorites" else "Removed from Favorites", android.widget.Toast.LENGTH_SHORT).show()
        if (current == FAV) open(cats.first { c -> c.id == FAV }) else gridAdapter.notifyItemChanged(items.indexOf(it))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_vod)
        series = intent.getBooleanExtra("series", false)
        findViewById<TextView>(R.id.title).text = if (series) "Series" else "Movies"
        catsRv = findViewById(R.id.cats); grid = findViewById(R.id.grid)
        catsRv.layoutManager = LinearLayoutManager(this); catsRv.adapter = catAdapter
        grid.layoutManager = GridLayoutManager(this, COLS); grid.adapter = gridAdapter
        findViewById<TextView>(R.id.vodSort).apply {
            setTextColor(getColorStateList(R.color.on_focus)); setOnClickListener { sortDialog() }; text = "⇅  " + sortNames[sort]
        }
        grid.setItemViewCacheSize(24)
        lifecycleScope.launch {
            val c = withContext(Dispatchers.IO) { try { Vod.cats(series) } catch (e: Exception) { null } }
            if (c == null) { android.widget.Toast.makeText(this@VodActivity, "Could not load the groups", android.widget.Toast.LENGTH_LONG).show(); return@launch }
            cats = listOf(VodCat(SEARCH, "🔍  Search"), VodCat(RESUME, "▶  Continue watching"), VodCat(FAV, "★  Favorites")) + c
            catAdapter.notifyDataSetChanged()
            val first = cats.indexOfFirst { it.id == App.prefs.getString("vod_cat_$series", "") }.takeIf { it >= 3 } ?: 3.coerceAtMost(cats.size - 1)
            open(cats[first])
            (catsRv.layoutManager as LinearLayoutManager).scrollToPositionWithOffset(first, 120)
            catsRv.post { catsRv.findViewHolderForAdapterPosition(first)?.itemView?.requestFocus() }
        }
    }

    override fun onResume() { super.onResume(); if (current == RESUME) open(cats.first { it.id == RESUME }) else gridAdapter.notifyDataSetChanged() }

    private fun open(c: VodCat) {
        if (c.id == SEARCH) { search(); return }
        current = c.id
        if (c.id != RESUME && c.id != FAV) App.prefs.edit().putString("vod_cat_$series", c.id).apply()
        findViewById<TextView>(R.id.catName).text = c.name.removePrefix("▶  ")
        catAdapter.notifyDataSetChanged()
        loadJob?.cancel()
        if (c.id == RESUME) {
            items = Resume.list().filter { it.optString("k").startsWith(if (series) "e" else "m") }.map {
                VodItem(it.optString("k").drop(1).toIntOrNull() ?: 0, it.optString("t"), it.optString("p"), it.optString("u"), "", "")
            }
            show(); return
        }
        if (c.id == FAV) {
            items = favs().map { VodItem(it.optInt("id"), it.optString("n"), it.optString("p"), it.optString("e"), it.optString("r"), "") }
            show(); return
        }
        items = emptyList(); show()
        loadJob = lifecycleScope.launch {
            val l = withContext(Dispatchers.IO) { try { Vod.list(series, c.id) } catch (e: Exception) { null } }
            if (current != c.id) return@launch
            items = sorted(l ?: emptyList()); show()
            if (l == null) android.widget.Toast.makeText(this@VodActivity, "Could not load this group", android.widget.Toast.LENGTH_SHORT).show()
        }
    }

    private fun show() {
        findViewById<TextView>(R.id.vodCount).text = items.size.toString()
        gridAdapter.notifyDataSetChanged(); grid.scrollToPosition(0)
    }

    private fun search() {
        startActivity(Intent(this, SearchActivity::class.java).putExtra("mode", if (series) "s" else "m"))
    }

    private fun play(it: VodItem) {
        if (current == RESUME) {
            startActivity(Intent(this, PlayerActivity::class.java).putExtra("url", it.ext).putExtra("title", it.name)
                .putExtra("key", (if (series) "e" else "m") + it.id).putExtra("poster", it.poster))
            return
        }
        startActivity(Intent(this, VodDetailActivity::class.java).putExtra("series", series).putExtra("id", it.id)
            .putExtra("name", it.name).putExtra("poster", it.poster).putExtra("ext", it.ext))
    }

    private fun moveTo(pos: Int) {
        val v = grid.layoutManager?.findViewByPosition(pos)
        if (v != null) { v.requestFocus(); return }
        grid.scrollToPosition(pos)
        grid.post { grid.layoutManager?.findViewByPosition(pos)?.requestFocus() }
    }

    private fun focusCats() {
        val i = cats.indexOfFirst { it.id == current }.coerceAtLeast(0)
        catsRv.layoutManager?.findViewByPosition(i)?.requestFocus() ?: run {
            catsRv.scrollToPosition(i); catsRv.post { catsRv.layoutManager?.findViewByPosition(i)?.requestFocus() }
        }
    }

    inner class CatAdapter : RecyclerView.Adapter<CatAdapter.H>() {
        inner class H(v: View) : RecyclerView.ViewHolder(v) { val name: TextView = v.findViewById(R.id.name); val count: TextView = v.findViewById(R.id.count) }
        override fun getItemCount() = cats.size
        override fun onCreateViewHolder(p: ViewGroup, t: Int) = H(LayoutInflater.from(p.context).inflate(R.layout.item_group, p, false))
        override fun onBindViewHolder(h: H, i: Int) {
            val c = cats[i]
            h.name.text = c.name; h.count.text = ""
            h.itemView.isActivated = c.id == current
            h.itemView.setOnClickListener { open(c) }
            h.itemView.setOnKeyListener { _, k, e ->
                if (e.action == KeyEvent.ACTION_DOWN && k == KeyEvent.KEYCODE_DPAD_RIGHT && items.isNotEmpty()) {
                    grid.findViewHolderForAdapterPosition(0)?.itemView?.requestFocus(); true
                } else false
            }
        }
    }

    inner class GridAdapter : RecyclerView.Adapter<GridAdapter.H>() {
        inner class H(v: View) : RecyclerView.ViewHolder(v) {
            val poster: ImageView = v.findViewById(R.id.poster); val name: TextView = v.findViewById(R.id.name)
            val rating: TextView = v.findViewById(R.id.rating); val progress: ProgressBar = v.findViewById(R.id.progress)
        }
        override fun getItemCount() = items.size
        override fun onCreateViewHolder(p: ViewGroup, t: Int): H {
            val h = H(LayoutInflater.from(p.context).inflate(R.layout.item_poster, p, false))
            h.itemView.setOnClickListener { items.getOrNull(h.bindingAdapterPosition)?.let { play(it) } }
            // hold OK: add to / remove from Favorites
            h.itemView.setOnLongClickListener { items.getOrNull(h.bindingAdapterPosition)?.let { toggleFav(it) }; true }
            // the whole name scrolls on the focused poster
            h.itemView.setOnFocusChangeListener { _, f -> h.name.isSelected = f }
            // the focus stays in the posters: ▼ goes to the poster below (loading it first if needed), never back to the groups
            h.itemView.setOnKeyListener { _, k, e ->
                if (e.action != KeyEvent.ACTION_DOWN) return@setOnKeyListener false
                val p = h.bindingAdapterPosition; if (p < 0) return@setOnKeyListener false
                when (k) {
                    KeyEvent.KEYCODE_DPAD_DOWN -> { if (p + COLS < items.size) moveTo(p + COLS) else if (p / COLS < (items.size - 1) / COLS) moveTo(items.size - 1); true }
                    KeyEvent.KEYCODE_DPAD_UP -> { if (p - COLS >= 0) moveTo(p - COLS) else findViewById<View>(R.id.vodSort).requestFocus(); true }
                    KeyEvent.KEYCODE_DPAD_RIGHT -> { if (p % COLS < COLS - 1 && p + 1 < items.size) moveTo(p + 1); true }
                    KeyEvent.KEYCODE_DPAD_LEFT -> { if (p % COLS > 0) moveTo(p - 1) else focusCats(); true }
                    KeyEvent.KEYCODE_MENU -> { sortDialog(); true }
                    else -> false
                }
            }
            return h
        }
        override fun onBindViewHolder(h: H, i: Int) {
            val it = items[i]
            h.name.text = (if (isFav(it.id)) "★ " else "") + it.name
            h.rating.text = it.rating.toDoubleOrNull()?.let { r -> "★ " + "%.1f".format(r) } ?: ""
            h.rating.visibility = if (h.rating.text.isEmpty()) View.GONE else View.VISIBLE
            if (it.poster.isEmpty()) h.poster.setImageResource(R.drawable.banner) else h.poster.load(it.poster) { size(240, 360); error(R.drawable.banner) }
            val key = (if (series) "e" else "m") + it.id
            val pos = Resume.get(key); val dur = Resume.dur(key)
            h.progress.visibility = if (pos > 0 && !series || current == RESUME) View.VISIBLE else View.GONE
            h.progress.progress = if (dur > 0) (pos * 1000 / dur).toInt() else 0
        }
    }
}
