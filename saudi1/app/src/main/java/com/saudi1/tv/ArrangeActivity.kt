package com.saudi1.tv

import android.graphics.Typeface
import android.os.Bundle
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Arrange like TiviMate (owner, 11 Nov 2026): Live TV / Movies / Series on top; the groups on the left
 *  (every group, the hidden ones too, marked ✕); the channels of the group on the right, each one shown or hidden.
 *  OK on a group: its channels. OK on a channel: hide / show.
 *  Hold OK on a group or a channel: "Move" picks it up (it turns green and locked), ▲▼ carry it one place,
 *  ◀▶ ten places, OK drops it there (owner: "instead of pressing 10 times, lock it, put it where I want, release"). */
class ArrangeActivity : BaseActivity() {
    private val d by lazy { resources.displayMetrics.density }
    private var tab = 0                       // 0 Live TV, 1 Movies, 2 Series
    private var groups: List<Pair<String, String>> = emptyList()   // id, name
    private var chans: List<Channel> = emptyList()
    private var open = -1
    /** what is picked up and carried: the group (left) or the channel (right) at this place, -1 = nothing */
    private var gMove = -1
    private var cMove = -1
    private val moveBg by lazy { android.graphics.drawable.GradientDrawable().apply { cornerRadius = 10 * d; setColor(getColor(R.color.accent)) } }
    private lateinit var gRv: RecyclerView
    private lateinit var cRv: RecyclerView
    private lateinit var cTitle: TextView
    private val tabs = ArrayList<TextView>()
    private val gAd = GroupAdapter()
    private val cAd = ChanAdapter()

    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setBackgroundColor(getColor(R.color.bg))
            setPadding(px(24), px(16), px(24), px(8))
        }
        root.addView(TextView(this).apply { text = "Arrange"; textSize = 24f; setTypeface(typeface, Typeface.BOLD); setTextColor(0xFFFFFFFF.toInt()) })
        val tabRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, px(8), 0, px(10)) }
        listOf("📺  Live TV", "🎬  Movies", "🎞  Series").forEachIndexed { i, t ->
            val v = TextView(this).apply {
                text = t; textSize = 17f; isFocusable = true; setBackgroundResource(R.drawable.item_bg)
                setTextColor(getColorStateList(R.color.on_focus)); setPadding(px(18), px(8), px(18), px(8))
                setOnClickListener { pick(i) }
                setOnFocusChangeListener { _, f -> if (f && tab != i) pick(i) }
            }
            tabs.add(v)
            tabRow.addView(v, LinearLayout.LayoutParams(-2, -2).apply { marginEnd = px(10) })
        }
        root.addView(tabRow)
        root.addView(TextView(this).apply {
            text = "OK on a group: its channels  ·  OK on a channel: hide / show  ·  Hold OK: Move — ▲▼ one place, ◀▶ ten places, OK to drop"
            textSize = 13f; setTextColor(0xFF9AA3AF.toInt()); setPadding(0, 0, 0, px(8))
        })
        val cols = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        gRv = RecyclerView(this).apply { layoutManager = LinearLayoutManager(context); adapter = gAd; itemAnimator = null; clipToPadding = false; setPadding(0, 0, 0, px(120)) }
        val right = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(px(16), 0, 0, 0) }
        cTitle = TextView(this).apply { textSize = 16f; setTextColor(getColor(R.color.accent)); setTypeface(typeface, Typeface.BOLD); setPadding(px(6), 0, 0, px(6)) }
        cRv = RecyclerView(this).apply { layoutManager = LinearLayoutManager(context); adapter = cAd; itemAnimator = null; clipToPadding = false; setPadding(0, 0, 0, px(120)) }
        right.addView(cTitle); right.addView(cRv, LinearLayout.LayoutParams(-1, -1))
        cols.addView(gRv, LinearLayout.LayoutParams(0, -1, 1f))
        cols.addView(right, LinearLayout.LayoutParams(0, -1, 1.2f))
        root.addView(cols, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(root)
        pick(0)
        tabs[0].requestFocus()
    }

    private fun px(v: Int) = (v * d).toInt()

    private fun pick(t: Int) {
        tab = t; open = -1; gMove = -1; cMove = -1; chans = emptyList(); cAd.notifyDataSetChanged()
        tabs.forEachIndexed { i, v -> v.isSelected = i == t; v.alpha = if (i == t) 1f else 0.6f }
        cTitle.text = if (t == 0) "Pick a group to see its channels" else "Movies and series: groups can be moved or hidden"
        lifecycleScope.launch {
            groups = withContext(Dispatchers.IO) {
                try {
                    if (t == 0) {
                        if (Api.rawGroups.isEmpty()) Api.load(true)
                        Arrange.apply(Api.rawGroups, all = true).map { it.id to it.name }
                    } else Arrange.vod(t == 2, Vod.cats(t == 2), all = true).map { it.id to it.name }
                } catch (e: Exception) { emptyList() }
            }
            if (tab != t) return@launch
            gAd.notifyDataSetChanged()
            if (groups.isEmpty()) cTitle.text = if (t == 0) "Open Live TV once first" else "Open ${if (t == 1) "Movies" else "Series"} once first"
        }
    }

    private fun isHid(id: String) = if (tab == 0) Arrange.isHidden(id) else id in Arrange.vodHidden(tab == 2)
    private fun changed() { if (tab == 0) Api.groups = emptyList() }

    private fun showChannels(i: Int) {
        if (tab != 0) { groupMenu(i); return }
        open = i
        val g = Api.rawGroups.firstOrNull { it.id == groups[i].first }
        chans = g?.channels ?: emptyList()
        cTitle.text = groups[i].second + "  ·  " + chans.size + " channels"
        cAd.notifyDataSetChanged(); cRv.scrollToPosition(0)
        cRv.post { cRv.findViewHolderForAdapterPosition(0)?.itemView?.requestFocus() }
        gAd.notifyItemChanged(i)
    }

    private fun groupMenu(i: Int) {
        val (id, name) = groups[i]; val hidden = isHid(id)
        AlertDialog.Builder(this).setTitle(name).setItems(arrayOf("✥  Move  (pick it up, ▲▼ to carry, OK to drop)", "⤒  Move to the top", "⤓  Move to the end",
            if (hidden) "👁  Show this group" else "✕  Hide this group")) { _, a ->
            when (a) {
                0 -> pickGroup(i); 1 -> { move(i, 0); saveGroups() }; 2 -> { move(i, groups.size - 1); saveGroups() }
                3 -> {
                    if (tab == 0) Arrange.setHidden(id, !hidden)
                    else { val h = Arrange.vodHidden(tab == 2); Arrange.setVodHidden(tab == 2, if (hidden) h - id else h + id) }
                    changed(); gAd.notifyItemChanged(i)
                }
            }
        }.show()
    }

    /** carry the group from one place to another (the row keeps the focus while it moves) */
    private fun move(from: Int, to0: Int): Int {
        val to = to0.coerceIn(0, groups.size - 1); if (to == from) return from
        val l = groups.toMutableList(); val g = l.removeAt(from); l.add(to, g); groups = l
        if (open == from) open = to else if (open in minOf(from, to)..maxOf(from, to)) open += if (to > from) -1 else 1
        gAd.notifyItemMoved(from, to); gAd.notifyItemChanged(to)
        gRv.scrollToPosition(to); gRv.post { gRv.findViewHolderForAdapterPosition(to)?.itemView?.requestFocus() }
        return to
    }
    private fun saveGroups() {
        val ids = groups.map { it.first }
        if (tab == 0) Arrange.order = ids else Arrange.setVodOrder(tab == 2, ids)
        changed()
    }
    private fun pickGroup(i: Int) { cMove = -1; gMove = i; gAd.notifyItemChanged(i); toast("✥ Picked up — ▲▼ one place · ◀▶ ten places · OK to drop") }
    private fun pickChan(i: Int) { gMove = -1; cMove = i; cAd.notifyItemChanged(i); toast("✥ Picked up — ▲▼ one place · ◀▶ ten places · OK to drop") }
    private fun toast(t: String) = android.widget.Toast.makeText(this, t, android.widget.Toast.LENGTH_SHORT).show()

    private fun moveChan(from: Int, to0: Int): Int {
        val to = to0.coerceIn(0, chans.size - 1); if (to == from) return from
        val l = chans as? MutableList<Channel> ?: return from
        val c = l.removeAt(from); l.add(to, c)
        cAd.notifyItemMoved(from, to); cAd.notifyItemChanged(to)
        cRv.scrollToPosition(to); cRv.post { cRv.findViewHolderForAdapterPosition(to)?.itemView?.requestFocus() }
        return to
    }
    private fun dropChan() {
        val i = cMove; cMove = -1; if (i >= 0) cAd.notifyItemChanged(i)
        if (open >= 0) { Arrange.setChanOrder(groups[open].first, chans.map { it.id.toString() }); Api.groups = emptyList() }
    }
    private fun dropGroup() { val i = gMove; gMove = -1; if (i >= 0) gAd.notifyItemChanged(i); saveGroups() }

    /** while something is picked up, the remote carries it */
    override fun dispatchKeyEvent(e: KeyEvent): Boolean {
        if ((gMove < 0 && cMove < 0) || e.action != KeyEvent.ACTION_DOWN) {
            return if ((gMove >= 0 || cMove >= 0) && e.action == KeyEvent.ACTION_UP && e.keyCode in keys) true else super.dispatchKeyEvent(e)
        }
        val step = when (e.keyCode) {
            KeyEvent.KEYCODE_DPAD_UP -> -1; KeyEvent.KEYCODE_DPAD_DOWN -> 1
            KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_PAGE_UP, KeyEvent.KEYCODE_CHANNEL_UP -> -10
            KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_PAGE_DOWN, KeyEvent.KEYCODE_CHANNEL_DOWN -> 10
            else -> 0
        }
        if (step != 0) {
            if (gMove >= 0) gMove = move(gMove, gMove + step) else cMove = moveChan(cMove, cMove + step)
            return true
        }
        if (e.keyCode in setOf(KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_BACK, KeyEvent.KEYCODE_NUMPAD_ENTER)) {
            if (gMove >= 0) dropGroup() else dropChan()
            toast("✓ Dropped here")
            return true
        }
        return true
    }
    private val keys = setOf(KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_DOWN, KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT,
        KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_BACK, KeyEvent.KEYCODE_NUMPAD_ENTER)

    private fun chanMenu(i: Int) {
        val c = chans[i]; val hidden = c.id.toString() in Arrange.hiddenChannels
        AlertDialog.Builder(this).setTitle(c.name).setItems(arrayOf("✥  Move  (pick it up, ▲▼ to carry, OK to drop)", "⤒  Move to the top", "⤓  Move to the end",
            if (hidden) "✓  Show this channel" else "✕  Hide this channel")) { _, a ->
            when (a) {
                0 -> pickChan(i)
                1 -> { cMove = moveChan(i, 0); dropChan() }
                2 -> { cMove = moveChan(i, chans.size - 1); dropChan() }
                3 -> toggleChan(i)
            }
        }.show()
    }
    private fun toggleChan(i: Int) {
        val id = chans[i].id.toString(); val hc = Arrange.hiddenChannels
        Arrange.hiddenChannels = if (id in hc) hc - id else hc + id
        Api.groups = emptyList(); cAd.notifyItemChanged(i); if (open >= 0) gAd.notifyItemChanged(open)
    }

    private fun row(p: ViewGroup) = TextView(p.context).apply {
        textSize = 17f; isFocusable = true; isClickable = true; setBackgroundResource(R.drawable.item_bg)
        setTextColor(getColorStateList(R.color.on_focus)); setPadding(px(14), px(10), px(14), px(10)); gravity = Gravity.CENTER_VERTICAL
        layoutParams = RecyclerView.LayoutParams(-1, -2).apply { setMargins(0, px(2), 0, px(2)) }
    }

    inner class GroupAdapter : RecyclerView.Adapter<RecyclerView.ViewHolder>() {
        override fun getItemCount() = groups.size
        override fun onCreateViewHolder(p: ViewGroup, t: Int): RecyclerView.ViewHolder {
            val v = row(p); val h = object : RecyclerView.ViewHolder(v) {}
            v.setOnClickListener { val i = h.bindingAdapterPosition; if (i >= 0) showChannels(i) }
            v.setOnLongClickListener { val i = h.bindingAdapterPosition; if (i >= 0) groupMenu(i); true }
            v.setOnKeyListener { _, k, e ->
                val i = h.bindingAdapterPosition
                if (e.action == KeyEvent.ACTION_DOWN && k == KeyEvent.KEYCODE_MENU && i >= 0) { groupMenu(i); true }
                else if (e.action == KeyEvent.ACTION_DOWN && k == KeyEvent.KEYCODE_DPAD_RIGHT && tab == 0 && i >= 0) { showChannels(i); true }
                else if (e.action == KeyEvent.ACTION_DOWN && k == KeyEvent.KEYCODE_DPAD_UP && i == 0) { tabs[tab].requestFocus(); true }
                else false
            }
            return h
        }
        override fun onBindViewHolder(h: RecyclerView.ViewHolder, i: Int) {
            val (id, name) = groups[i]; val hidden = isHid(id)
            val hc = if (tab == 0) Api.rawGroups.firstOrNull { it.id == id }?.channels?.count { it.id.toString() in Arrange.hiddenChannels } ?: 0 else 0
            val mv = i == gMove
            (h.itemView as TextView).text = (if (mv) "⇅   " else if (hidden) "✕   " else "👁   ") + name + (if (hc > 0) "   ($hc hidden)" else "") + (if (i == open) "   ▸" else "")
            h.itemView.alpha = if (hidden && !mv) 0.5f else 1f
            if (mv) { h.itemView.background = moveBg; (h.itemView as TextView).setTextColor(0xFF0B0E14.toInt()) }
            else { h.itemView.setBackgroundResource(R.drawable.item_bg); (h.itemView as TextView).setTextColor(getColorStateList(R.color.on_focus)) }
        }
    }

    inner class ChanAdapter : RecyclerView.Adapter<RecyclerView.ViewHolder>() {
        override fun getItemCount() = chans.size
        override fun onCreateViewHolder(p: ViewGroup, t: Int): RecyclerView.ViewHolder {
            val v = row(p); val h = object : RecyclerView.ViewHolder(v) {}
            v.setOnClickListener { val i = h.bindingAdapterPosition; if (i >= 0) toggleChan(i) }
            v.setOnLongClickListener { val i = h.bindingAdapterPosition; if (i >= 0) chanMenu(i); true }
            v.setOnKeyListener { _, k, e ->
                if (e.action == KeyEvent.ACTION_DOWN && k == KeyEvent.KEYCODE_MENU) { val i = h.bindingAdapterPosition; if (i >= 0) chanMenu(i); true }
                else if (e.action == KeyEvent.ACTION_DOWN && k == KeyEvent.KEYCODE_DPAD_LEFT && open >= 0) {
                    gRv.findViewHolderForAdapterPosition(open)?.itemView?.requestFocus(); true
                } else false
            }
            return h
        }
        override fun onBindViewHolder(h: RecyclerView.ViewHolder, i: Int) {
            val c = chans[i]; val hidden = c.id.toString() in Arrange.hiddenChannels; val mv = i == cMove
            (h.itemView as TextView).text = (if (mv) "⇅   " else if (hidden) "✕   " else "✓   ") + "${i + 1}.  " + c.name
            h.itemView.alpha = if (hidden && !mv) 0.5f else 1f
            if (mv) { h.itemView.background = moveBg; (h.itemView as TextView).setTextColor(0xFF0B0E14.toInt()) }
            else { h.itemView.setBackgroundResource(R.drawable.item_bg); (h.itemView as TextView).setTextColor(getColorStateList(R.color.on_focus)) }
        }
    }
}
