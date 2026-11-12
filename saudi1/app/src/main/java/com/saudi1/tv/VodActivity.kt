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
    private lateinit var grid: androidx.leanback.widget.VerticalGridView
    private val catAdapter = CatAdapter()
    private val gridAdapter = GridAdapter()

    companion object { const val RESUME = "__resume"; const val SEARCH = "__search"; const val FAV = "__fav"; const val DL = "__dl"; const val COLS = 4 }

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

    private fun favKey() = VodFav.key(series)
    private fun favs(): List<org.json.JSONObject> = try {
        val a = org.json.JSONArray(App.prefs.getString(favKey(), "[]")); (0 until a.length()).map { a.getJSONObject(it) }
    } catch (e: Exception) { emptyList() }
    // read once, not for every poster drawn (reading the saved lists for each poster made the lists slow)
    private var favIds = HashSet<Int>()
    private var resumeOf = HashMap<String, LongArray>()
    private fun refreshMarks() {
        favIds = favs().mapTo(HashSet()) { it.optInt("id") }
        val m = HashMap<String, LongArray>()
        for (r in Resume.list()) m[r.optString("k")] = longArrayOf(r.optLong("pos"), r.optLong("dur"))
        resumeOf = m
    }
    private fun isFav(id: Int) = id in favIds
    private fun toggleFav(it: VodItem) {
        val l = favs().toMutableList()
        val on = l.none { f -> f.optInt("id") == it.id }
        if (on) l.add(0, org.json.JSONObject().put("id", it.id).put("n", it.name).put("p", it.poster).put("e", it.ext).put("r", it.rating))
        else l.removeAll { f -> f.optInt("id") == it.id }
        App.prefs.edit().putString(favKey(), org.json.JSONArray(l).toString()).apply()
        refreshMarks()
        android.widget.Toast.makeText(this, if (on) "★ Added to Favorites" else "Removed from Favorites", android.widget.Toast.LENGTH_SHORT).show()
        if (current == FAV) open(cats.first { c -> c.id == FAV }) else gridAdapter.notifyItemChanged(items.indexOf(it))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_vod)
        series = intent.getBooleanExtra("series", false)
        findViewById<TextView>(R.id.title).text = if (series) "Series" else "Movies"
        catsRv = findViewById(R.id.cats); grid = findViewById(R.id.grid)
        // smooth ▲▼: the rows just off screen are always laid out, so the focus moves one row and the list glides
        // there (no jump to a far position); no change animations that make the focus hop while a list updates
        catsRv.layoutManager = object : LinearLayoutManager(this) {
            override fun calculateExtraLayoutSpace(st: RecyclerView.State, extra: IntArray) { val h = height; extra[0] = h / 2; extra[1] = h / 2 }
        }
        catsRv.adapter = catAdapter; catsRv.itemAnimator = null
        // Google TV's own grid: ▲▼ move the focus one row and the list glides so the focused row stays in view
        // at the same height; held keys move steadily (no jumps, no stalls)
        grid.setNumColumns(COLS)
        grid.windowAlignment = androidx.leanback.widget.BaseGridView.WINDOW_ALIGN_BOTH_EDGE
        grid.windowAlignmentOffsetPercent = 30f
        grid.itemAlignmentOffsetPercent = 0f
        grid.focusScrollStrategy = androidx.leanback.widget.BaseGridView.FOCUS_SCROLL_ALIGNED
        grid.adapter = gridAdapter; grid.itemAnimator = null
        findViewById<TextView>(R.id.vodSort).apply {
            setTextColor(getColorStateList(R.color.on_focus)); setOnClickListener { sortDialog() }; text = "⇅  " + sortNames[sort]
            // ▼ from the sort button goes straight back to the posters (it stayed up there before)
            setOnKeyListener { _, k, e ->
                if (e.action == KeyEvent.ACTION_DOWN && k == KeyEvent.KEYCODE_DPAD_DOWN && items.isNotEmpty()) {
                    val pos = sortCol.coerceAtMost(items.size - 1)
                    grid.scrollToPosition(0); grid.post { grid.layoutManager?.findViewByPosition(pos)?.requestFocus() ?: moveTo(pos) }; true
                } else if (e.action == KeyEvent.ACTION_DOWN && k == KeyEvent.KEYCODE_DPAD_LEFT) { focusCats(); true } else false
            }
        }
        grid.setItemViewCacheSize(COLS * 4)
        // posters that leave the screen are kept ready (not built again) while the rows move
        grid.recycledViewPool.setMaxRecycledViews(0, COLS * 8); grid.setHasFixedSize(true)
        refreshMarks()
        val fixed = listOf(VodCat(SEARCH, "🔍  Search"), VodCat(RESUME, "▶  Continue watching"), VodCat(FAV, "★  Favorites"), VodCat(DL, "⬇  Downloads"))
        // the screen is there at once: Continue watching first, the groups from the device, the provider asked behind it
        cats = fixed; catAdapter.notifyDataSetChanged()
        open(cats[1])
        catsRv.post { catsRv.findViewHolderForAdapterPosition(1)?.itemView?.requestFocus() }
        lifecycleScope.launch {
            val c = withContext(Dispatchers.IO) { try { Vod.cats(series) } catch (e: Exception) { null } }
            if (c == null) { android.widget.Toast.makeText(this@VodActivity, "Could not load the groups", android.widget.Toast.LENGTH_LONG).show(); return@launch }
            cats = fixed + Arrange.vod(series, c)
            catAdapter.notifyItemRangeInserted(4, cats.size - 4)
            // nothing to continue: open the group that was open last time
            if (items.isEmpty() && current == RESUME && c.isNotEmpty()) {
                val first = cats.indexOfFirst { it.id == App.prefs.getString("vod_cat_$series", "") }.takeIf { it >= 4 } ?: 4
                open(cats[first])
                (catsRv.layoutManager as LinearLayoutManager).scrollToPositionWithOffset(first, 120)
                catsRv.post { catsRv.findViewHolderForAdapterPosition(first)?.itemView?.requestFocus() }
            }
            // the groups themselves checked with the provider now and then
            if (Vod.catsAge(series) > 3 * 3600_000L) {
                val n = withContext(Dispatchers.IO) { try { Vod.cats(series, true) } catch (e: Exception) { null } }
                if (n != null && n.isNotEmpty() && (n.size != c.size || n.indices.any { n[it].id != c[it].id || n[it].name != c[it].name })) {
                    val focused = catsRv.focusedChild?.let { catsRv.getChildAdapterPosition(it) } ?: -1
                    cats = fixed + Arrange.vod(series, n); catAdapter.notifyDataSetChanged()
                    if (focused >= 0) catsRv.post { catsRv.findViewHolderForAdapterPosition(focused.coerceAtMost(cats.size - 1))?.itemView?.requestFocus() }
                }
            }
            // the whole catalogue read once behind the screen: every group then opens at once, and Favorites know the newest episode
            if (Vod.needsWarm(series)) {
                withContext(Dispatchers.IO) { try { Vod.all(series) } catch (e: Exception) { } }
                if (current == FAV && series && grid.focusedChild == null) open(cats.first { it.id == FAV })
            }
        }
    }

    private var lastPos = -1
    private var sortCol = 0

    override fun onResume() {
        super.onResume()
        refreshMarks()
        if (current == RESUME || current == DL) open(cats.first { it.id == current })
        else if (lastPos >= 0) {
            // back from a movie: the focus stays on the poster that was opened (not the groups)
            val p = lastPos
            gridAdapter.notifyItemRangeChanged(0, items.size)
            grid.post { grid.layoutManager?.findViewByPosition(p)?.requestFocus() ?: moveTo(p) }
        }
    }

    private fun open(c: VodCat) {
        if (c.id == SEARCH) { search(); return }
        if (Parental.isLocked(c.id, c.name)) { Parental.ask(this) { open(c) }; return }
        val old = cats.indexOfFirst { it.id == current }
        current = c.id
        if (c.id != RESUME && c.id != FAV && c.id != DL) App.prefs.edit().putString("vod_cat_$series", c.id).apply()
        findViewById<TextView>(R.id.catName).text = c.name.removePrefix("▶  ") + if (c.id == RESUME) "   ·   hold OK to remove" else ""
        // only the two rows whose mark changes (a full refresh moved the focus while ▲▼)
        if (old >= 0) catAdapter.notifyItemChanged(old)
        cats.indexOfFirst { it.id == c.id }.takeIf { it >= 0 }?.let { catAdapter.notifyItemChanged(it) }
        loadJob?.cancel()
        if (c.id == RESUME) {
            items = Resume.list().filter { it.optString("k").startsWith(if (series) "e" else "m") }.map {
                VodItem(it.optString("k").drop(1).toIntOrNull() ?: 0, it.optString("t"), it.optString("p"), it.optString("u"), "", "")
            }
            show(); return
        }
        if (c.id == DL) {
            items = Downloads.all().filter { it.key.startsWith(if (series) "e" else "m") }.map {
                VodItem(it.key.drop(1).toIntOrNull() ?: 0, (if (it.done) "" else "⬇ ") + it.title, it.poster, it.key, if (it.done) "" else "…", "")
            }
            show(); return
        }
        if (c.id == FAV) {
            val f = favs().map { VodItem(it.optInt("id"), it.optString("n"), it.optString("p"), it.optString("e"), it.optString("r"), "") }
            items = f; show()
            // series: the one with the newest episode comes first (each favourite's own episode list, every 3 hours)
            if (series && f.size > 1) loadJob = lifecycleScope.launch {
                val at = withContext(Dispatchers.IO) {
                    val st = Vod.stamps(true)
                    // four at a time, not to press the provider
                    f.chunked(4).flatMap { ch -> ch.map { x -> kotlinx.coroutines.async { x.id to maxOf(st[x.id] ?: 0L, Vod.latestEpisodeAt(x.id)) } }.map { it.await() } }.toMap()
                }
                if (current != FAV || at.values.all { it == 0L }) return@launch
                val o = f.sortedByDescending { at[it.id] ?: 0L }
                if (o.indices.any { o[it].id != f[it].id } && grid.focusedChild == null) { items = o; show() }
            }
            return
        }
        loadJob = lifecycleScope.launch {
            // what the device has is shown at once; the provider is asked only when that is old (or there is nothing)
            val had = withContext(Dispatchers.IO) { Vod.cached(series, c.id)?.let { it.first to sorted(it.second) } }
            if (current != c.id) return@launch
            if (had != null) { items = had.second; show() } else { items = emptyList(); show() }
            if (had != null && had.first < 30 * 60_000L) return@launch
            val l = withContext(Dispatchers.IO) { try { sorted(Vod.list(series, c.id)) } catch (e: Exception) { null } }
            if (current != c.id) return@launch
            if (l == null) { if (had == null) android.widget.Toast.makeText(this@VodActivity, "Could not load this group", android.widget.Toast.LENGTH_SHORT).show(); return@launch }
            val same = had != null && had.second.size == l.size && l.indices.all { l[it].id == had.second[it].id && l[it].name == had.second[it].name }
            // never under the hand: the new list waits for the next visit when the posters are being browsed
            if (!same && (had == null || grid.focusedChild == null)) { items = l; show() }
        }
    }

    private fun show() {
        fetchedTo = -1
        findViewById<TextView>(R.id.vodCount).text = items.size.toString()
        gridAdapter.notifyDataSetChanged(); grid.scrollToPosition(0)
    }

    private fun search() {
        startActivity(Intent(this, SearchActivity::class.java).putExtra("mode", if (series) "s" else "m"))
    }

    private fun play(it: VodItem) {
        if (current == DL) {
            val d = Downloads.get(it.ext) ?: return
            val f = Downloads.localFile(d.key)
            if (f == null) { android.widget.Toast.makeText(this, "Still downloading", android.widget.Toast.LENGTH_SHORT).show(); return }
            startActivity(Intent(this, PlayerActivity::class.java).putExtra("url", android.net.Uri.fromFile(f).toString()).putExtra("title", d.title)
                .putExtra("key", d.key).putExtra("poster", d.poster))
            return
        }
        if (current == RESUME) {
            startActivity(Intent(this, PlayerActivity::class.java).putExtra("url", it.ext).putExtra("title", it.name)
                .putExtra("key", (if (series) "e" else "m") + it.id).putExtra("poster", it.poster))
            return
        }
        startActivity(Intent(this, VodDetailActivity::class.java).putExtra("series", series).putExtra("id", it.id)
            .putExtra("name", it.name).putExtra("poster", it.poster).putExtra("ext", it.ext))
    }

    /** "★ 7.5" without String.format for every poster drawn */
    private fun ratingText(r: String): String {
        val v = r.toDoubleOrNull() ?: return ""
        val t = Math.round(v * 10).toInt(); return "★ " + (t / 10) + "." + (t % 10)
    }
    // the poster size, worked out once (not for every poster drawn)
    private val ph by lazy { posterH() }
    private val pw by lazy { ph * 2 / 3 }
    /** the posters of the two rows below the one drawn are fetched before they are needed: no grey squares while moving */
    private var fetchedTo = -1
    private fun prefetch(i: Int) {
        val to = (i + COLS * 3).coerceAtMost(items.size - 1)
        if (to <= fetchedTo) return
        val il = coil.Coil.imageLoader(this)
        for (k in maxOf(fetchedTo + 1, i + 1)..to) {
            val u = items[k].poster; if (u.isEmpty()) continue
            il.enqueue(coil.request.ImageRequest.Builder(this).data(u).size(pw, ph).build())
        }
        fetchedTo = to
    }

    /** a real poster shape (2:3) for the width a column has (known before the first layout too) */
    private fun posterH(): Int {
        val d = resources.displayMetrics.density
        val gw = if (grid.width > 0) grid.width else resources.displayMetrics.widthPixels - (258 * d).toInt()
        return (((gw - grid.paddingLeft - grid.paddingRight) / COLS - (16 * d).toInt()) * 6 / 5).coerceAtLeast((90 * d).toInt())
    }

    private var lastStep = 0L
    private val glide = android.view.animation.DecelerateInterpolator(1.4f)
    private fun moveTo(pos: Int) {
        val v = grid.layoutManager?.findViewByPosition(pos)
        if (v != null) v.requestFocus() else grid.setSelectedPositionSmooth(pos)
    }

    /** the end of the list goes round to the first row (same column): the focus is held on the posters
     *  until that row is built, so it never falls to the groups on the left */
    private fun wrapGrid(pos: Int) {
        grid.setSelectedPosition(pos)
        fun tryFocus(n: Int) {
            val v = grid.findViewHolderForAdapterPosition(pos)?.itemView
            if (v != null) { v.requestFocus(); return }
            if (n < 10) grid.postDelayed({ tryFocus(n + 1) }, 25)
        }
        grid.post { tryFocus(0) }
    }

    private fun wrapCats(pos: Int) {
        (catsRv.layoutManager as LinearLayoutManager).scrollToPositionWithOffset(pos, 0)
        catsRv.post { catsRv.findViewHolderForAdapterPosition(pos)?.itemView?.requestFocus() }
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
                if (e.action != KeyEvent.ACTION_DOWN) return@setOnKeyListener false
                val p = h.bindingAdapterPosition
                when {
                    k == KeyEvent.KEYCODE_DPAD_RIGHT && items.isNotEmpty() -> { grid.findViewHolderForAdapterPosition(0)?.itemView?.requestFocus(); true }
                    // the end of the groups goes round to the first one, and ▲ on the first to the last (like Live TV)
                    k == KeyEvent.KEYCODE_DPAD_DOWN && p == cats.size - 1 -> { wrapCats(0); true }
                    k == KeyEvent.KEYCODE_DPAD_UP && p == 0 -> { wrapCats(cats.size - 1); true }
                    else -> false
                }
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
            // a poster a little taller than wide: two whole rows and the start of the third on the screen
            (h.poster.parent as View).layoutParams.height = ph
            h.itemView.setOnClickListener { lastPos = h.bindingAdapterPosition; items.getOrNull(h.bindingAdapterPosition)?.let { play(it) } }
            // hold OK: add to / remove from Favorites
            h.itemView.setOnLongClickListener {
                items.getOrNull(h.bindingAdapterPosition)?.let {
                    if (current == DL) AlertDialog.Builder(this@VodActivity).setTitle(it.name).setItems(arrayOf("🗑  Delete the download")) { _, _ ->
                        Downloads.remove(this@VodActivity, it.ext); open(cats.first { c -> c.id == DL })
                    }.show()
                    else if (current == RESUME) AlertDialog.Builder(this@VodActivity).setTitle(it.name).setItems(arrayOf("✕  Remove from Continue watching", "⟲  Play from the beginning")) { _, w ->
                        val k = (if (series) "e" else "m") + it.id
                        if (w == 0) { Resume.remove(k); open(cats.first { c -> c.id == RESUME }) }
                        else startActivity(Intent(this@VodActivity, PlayerActivity::class.java).putExtra("url", it.ext).putExtra("title", it.name).putExtra("key", k).putExtra("poster", it.poster).putExtra("from", 0L))
                    }.show()
                    else toggleFav(it)
                }; true
            }
            // the whole name scrolls on the focused poster
            h.itemView.setOnFocusChangeListener { _, f -> h.name.isSelected = f }
            // the focus stays in the posters: ▼ goes to the poster below (loading it first if needed), never back to the groups
            h.itemView.setOnKeyListener { _, k, e ->
                if (e.action != KeyEvent.ACTION_DOWN) return@setOnKeyListener false
                val p = h.bindingAdapterPosition; if (p < 0) return@setOnKeyListener false
                when (k) {
                    // the last row goes round to the first one (same column), like the lists
                    // ▼: the next row is the grid's own move; the last row goes round to the first row (same column)
                    KeyEvent.KEYCODE_DPAD_DOWN -> { if (p + COLS < items.size) false else if (p / COLS < (items.size - 1) / COLS) { moveTo(items.size - 1); true } else { wrapGrid(p % COLS); true } }
                    // the first row: ▲ goes up to the sort button only on a new press (holding ▲ stops on the posters)
                    KeyEvent.KEYCODE_DPAD_UP -> { if (p - COLS >= 0) false else { if (e.repeatCount == 0) { sortCol = p % COLS; findViewById<View>(R.id.vodSort).requestFocus() }; true } }
                    KeyEvent.KEYCODE_DPAD_RIGHT -> { if (p % COLS < COLS - 1 && p + 1 < items.size) false else true }
                    KeyEvent.KEYCODE_DPAD_LEFT -> { if (p % COLS > 0) false else { focusCats(); true } }
                    KeyEvent.KEYCODE_MENU -> { sortDialog(); true }
                    else -> false
                }
            }
            return h
        }
        override fun onBindViewHolder(h: H, i: Int) {
            val it = items[i]
            h.name.text = (if (isFav(it.id)) "★ " else "") + Vod.shown(it.name)
            h.rating.text = ratingText(it.rating)
            h.rating.visibility = if (h.rating.text.isEmpty()) View.GONE else View.VISIBLE
            if (it.poster.isEmpty()) h.poster.setImageResource(R.drawable.banner) else h.poster.load(it.poster) { size(pw, ph); error(R.drawable.banner) }
            val key = (if (series) "e" else "m") + it.id
            val r = resumeOf[key]; val pos = r?.get(0) ?: 0L; val dur = r?.get(1) ?: 0L
            h.progress.visibility = if (pos > 0 && !series || current == RESUME) View.VISIBLE else View.GONE
            h.progress.progress = if (dur > 0) (pos * 1000 / dur).toInt() else 0
        }
    }
}
