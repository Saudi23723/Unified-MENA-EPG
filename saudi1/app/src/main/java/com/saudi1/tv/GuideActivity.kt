package com.saudi1.tv

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Typeface
import android.os.Bundle
import android.text.TextUtils
import android.view.Gravity
import android.view.KeyEvent
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import coil.load
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** TV Guide grid (like TiviMate): channels down, time across, 4 hours on screen; OK = watch / remind me. */
@SuppressLint("SetTextI18n", "NotifyDataSetChanged")
class GuideActivity : BaseActivity() {
    private val span = 4 * 3600L
    private var from = 0L
    private var group: Group? = null
    private lateinit var rows: RecyclerView
    private lateinit var ruler: LinearLayout
    private lateinit var info: TextView
    private lateinit var titleV: TextView
    private val time = SimpleDateFormat("h:mm", Locale.ENGLISH)
    private val day = SimpleDateFormat("EEE d MMM", Locale.ENGLISH)
    private var pxPerSec = 0f
    private val adapter = RowAdapter()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val d = resources.displayMetrics.density
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding((18 * d).toInt(), (14 * d).toInt(), (18 * d).toInt(), 0) }
        val top = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        val title = TextView(this).apply { textSize = 22f; setTypeface(typeface, Typeface.BOLD) }
        titleV = title
        info = TextView(this).apply { textSize = 15f; setTextColor(getColor(R.color.text2)); maxLines = 2; ellipsize = TextUtils.TruncateAt.END }
        top.addView(title, LinearLayout.LayoutParams((300 * d).toInt(), ViewGroup.LayoutParams.WRAP_CONTENT))
        top.addView(info, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        root.addView(top)
        val rulerRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        rulerRow.addView(View(this), LinearLayout.LayoutParams((230 * d).toInt(), 1))
        ruler = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        rulerRow.addView(ruler, LinearLayout.LayoutParams(0, (34 * d).toInt(), 1f))
        root.addView(rulerRow, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { topMargin = (10 * d).toInt() })
        rows = RecyclerView(this).apply { layoutManager = LinearLayoutManager(this@GuideActivity); adapter = this@GuideActivity.adapter; setItemViewCacheSize(12) }
        root.addView(rows, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        setContentView(root)

        from = (System.currentTimeMillis() / 1000) / 1800 * 1800
        group = Api.groups.firstOrNull { it.id == Prefs.lastGroup && it.channels.isNotEmpty() }
            ?: Api.groups.firstOrNull { it.id != Api.FAV && it.id != Api.ALL }
        title.text = "▾  " + (group?.name ?: "TV Guide")
        title.setPadding((14 * d).toInt(), (6 * d).toInt(), (14 * d).toInt(), (6 * d).toInt())
        title.setBackgroundResource(R.drawable.item_bg); title.isFocusable = true; title.isClickable = true
        title.setTextColor(getColorStateList(R.color.on_focus))
        title.setOnClickListener { pickGroup(title) }
        info.setPadding((18 * d).toInt(), 0, 0, 0)
        rows.post {
            pxPerSec = (rows.width - 230 * d) / span
            drawRuler(); adapter.notifyDataSetChanged()
            // open on the channel that is playing (else the first)
            val pos = group?.channels?.indexOfFirst { it.id == Prefs.lastChannel }?.coerceAtLeast(0) ?: 0
            (rows.layoutManager as LinearLayoutManager).scrollToPositionWithOffset(pos, (140 * d).toInt())
            focusRow(pos)
        }
    }

    private fun focusRow(pos: Int, tries: Int = 0) {
        rows.postDelayed({
            val v = rows.findViewHolderForAdapterPosition(pos)?.itemView?.findViewWithTag<View>("cell")
            if (v != null) v.requestFocus() else if (tries < 10) focusRow(pos, tries + 1)
        }, 150)
    }

    private fun pickGroup(title: TextView) {
        val gs = Api.groups.filter { it.channels.isNotEmpty() }
        AlertDialog.Builder(this).setTitle("Group").setItems(gs.map { it.name }.toTypedArray()) { _, w ->
            group = gs[w]; title.text = "▾  " + gs[w].name; adapter.notifyDataSetChanged(); rows.scrollToPosition(0); focusRow(0)
        }.show()
    }

    private fun drawRuler() {
        ruler.removeAllViews()
        for (i in 0 until 8) {
            val t = from + i * 1800
            ruler.addView(TextView(this).apply {
                text = if (i == 0) day.format(Date(t * 1000)) + "  " + time.format(Date(t * 1000)) else time.format(Date(t * 1000))
                textSize = 14f; setTextColor(getColor(R.color.text2)); gravity = Gravity.CENTER_VERTICAL
            }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f))
        }
    }

    private fun shift(by: Long) {
        val min = (System.currentTimeMillis() / 1000 - 2 * 3600) / 1800 * 1800
        from = (from + by).coerceAtLeast(min)
        drawRuler(); adapter.notifyDataSetChanged()
    }

    override fun dispatchKeyEvent(e: KeyEvent): Boolean {
        if (!overlayOpen && e.action == KeyEvent.ACTION_DOWN) {
            val f = currentFocus
            if (f?.tag == "cell") {
                val row = f.parent as? ViewGroup
                val idx = row?.indexOfChild(f) ?: -1
                if (e.keyCode == KeyEvent.KEYCODE_DPAD_RIGHT && row != null && idx == row.childCount - 1) { shift(2 * 3600); return true }
                if (e.keyCode == KeyEvent.KEYCODE_DPAD_LEFT && idx == 0 && from > System.currentTimeMillis() / 1000 - 2 * 3600) { shift(-2 * 3600); return true }
            }
            if (e.keyCode == KeyEvent.KEYCODE_MENU) { pickGroup(titleV); return true }
            // ⏪ / ⏩ on the remote: a day back / forward
            if (e.keyCode == KeyEvent.KEYCODE_MEDIA_FAST_FORWARD) { shift(24 * 3600); return true }
            if (e.keyCode == KeyEvent.KEYCODE_MEDIA_REWIND) { shift(-24 * 3600); return true }
        }
        return super.dispatchKeyEvent(e)
    }

    inner class RowAdapter : RecyclerView.Adapter<RowAdapter.H>() {
        inner class H(v: View) : RecyclerView.ViewHolder(v) {
            val logo: ImageView = v.findViewById(R.id.logo); val name: TextView = v.findViewById(R.id.name)
            val num: TextView = v.findViewById(R.id.num); val cells: FrameLayout = v.findViewById(R.id.cells)
        }
        override fun getItemCount() = group?.channels?.size ?: 0
        override fun onCreateViewHolder(p: ViewGroup, t: Int) = H(LayoutInflater.from(p.context).inflate(R.layout.item_guide_row, p, false))
        override fun onBindViewHolder(h: H, i: Int) {
            val c = group!!.channels[i]
            h.num.text = c.num.toString(); h.name.text = c.name
            if (c.logo.isEmpty()) h.logo.setImageDrawable(null) else h.logo.load(c.logo) { size(124, 80) }
            h.cells.removeAllViews()
            h.itemView.tag = c.id
            lifecycleScope.launch {
                val list = withContext(Dispatchers.IO) { Api.guide(c) }
                if (h.itemView.tag != c.id) return@launch
                fill(h.cells, c, list)
            }
        }
    }

    private fun fill(box: FrameLayout, c: Channel, list: List<Program>) {
        box.removeAllViews()
        val d = resources.displayMetrics.density
        val to = from + span
        val shown = list.filter { it.stop > from && it.start < to }.ifEmpty { listOf(Program(from, to, if (list.isEmpty()) "No guide" else "", "")) }
        val now = System.currentTimeMillis() / 1000
        for (p in shown) {
            val s = maxOf(p.start, from); val e = minOf(p.stop, to)
            val w = ((e - s) * pxPerSec).toInt().coerceAtLeast((8 * d).toInt())
            val cell = TextView(this).apply {
                tag = "cell"
                text = (if (Reminders.has(c.id, p.start)) "⏰ " else "") + p.title
                textSize = 15f; maxLines = 2; ellipsize = TextUtils.TruncateAt.END; gravity = Gravity.CENTER_VERTICAL
                setPadding((10 * d).toInt(), 0, (8 * d).toInt(), 0)
                isFocusable = true; isClickable = true
                setBackgroundResource(if (p.now(now) && p.title != "No guide") R.drawable.cell_now else R.drawable.item_bg)
                setTextColor(getColorStateList(R.color.on_focus))
                setOnFocusChangeListener { _, f -> if (f) info.text = "${c.name}   ·   ${time.format(Date(p.start * 1000))} – ${time.format(Date(p.stop * 1000))}   ${p.title}\n${p.desc}" }
                setOnClickListener {
                    if (p.now(System.currentTimeMillis() / 1000) || p.title == "No guide" || p.title.isEmpty()) {
                        Prefs.lastGroup = group?.id ?: Prefs.lastGroup
                        startActivity(Intent(this@GuideActivity, LiveActivity::class.java).putExtra("channel", c.id))
                    } else if (p.start > System.currentTimeMillis() / 1000) {
                        val on = Reminders.toggle(Reminder(c.id, p.start, p.title, c.name))
                        text = (if (on) "⏰ " else "") + p.title
                        android.widget.Toast.makeText(this@GuideActivity, if (on) "Reminder set" else "Reminder removed", android.widget.Toast.LENGTH_SHORT).show()
                    }
                }
            }
            val lp = FrameLayout.LayoutParams(w - (3 * d).toInt(), ViewGroup.LayoutParams.MATCH_PARENT)
            lp.leftMargin = ((s - from) * pxPerSec).toInt()
            box.addView(cell, lp)
        }
    }
}
