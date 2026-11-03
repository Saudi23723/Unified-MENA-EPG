package com.saudi1.tv

import android.annotation.SuppressLint
import android.os.Bundle
import android.view.KeyEvent
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.DefaultLoadControl
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.ui.PlayerView
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import coil.load
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@SuppressLint("SetTextI18n", "NotifyDataSetChanged")
class LiveActivity : AppCompatActivity() {
    private lateinit var playerView: PlayerView
    private lateinit var player: ExoPlayer
    private lateinit var groupsRv: RecyclerView
    private lateinit var channelsRv: RecyclerView
    private lateinit var groupsPanel: View
    private lateinit var browse: View
    private lateinit var previewBox: View
    private lateinit var banner: View
    private lateinit var toastV: TextView

    private var group: Group? = null
    private var playing: Channel? = null
    private var focused: Channel? = null
    private var full = false
    private var infoJob: Job? = null
    private var bannerJob: Job? = null
    private var toastJob: Job? = null
    private var retried = false
    private val time = SimpleDateFormat("h:mm", Locale.ENGLISH)
    private val clockF = SimpleDateFormat("h:mm a", Locale.ENGLISH)

    private val groupAdapter = GroupAdapter()
    private val channelAdapter = ChannelAdapter()
    private val programAdapter = ProgramAdapter()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_live)
        playerView = findViewById(R.id.player)
        groupsRv = findViewById(R.id.groups)
        channelsRv = findViewById(R.id.channels)
        groupsPanel = findViewById(R.id.groupsPanel)
        browse = findViewById(R.id.browse)
        previewBox = findViewById(R.id.previewBox)
        banner = findViewById(R.id.banner)
        toastV = findViewById(R.id.toast)

        groupsRv.layoutManager = LinearLayoutManager(this)
        groupsRv.adapter = groupAdapter
        channelsRv.layoutManager = LinearLayoutManager(this)
        channelsRv.adapter = channelAdapter
        channelsRv.setItemViewCacheSize(20)
        findViewById<RecyclerView>(R.id.programs).apply {
            layoutManager = LinearLayoutManager(this@LiveActivity); adapter = programAdapter; isFocusable = false
        }

        // fast start for live TV: small buffers, play as soon as there is a second of video
        val load = DefaultLoadControl.Builder().setBufferDurationsMs(8_000, 30_000, 1_000, 2_000).build()
        val data = OkHttpDataSource.Factory(App.http)
        player = ExoPlayer.Builder(this).setLoadControl(load)
            .setMediaSourceFactory(DefaultMediaSourceFactory(data)).build()
        playerView.player = player
        player.addListener(object : Player.Listener {
            override fun onPlayerError(error: PlaybackException) {
                val c = playing ?: return
                if (!retried) { retried = true; lifecycleScope.launch { delay(1500); if (playing === c) start(c) } }
                else toast("This channel is not available right now")
            }
            override fun onPlaybackStateChanged(state: Int) { if (state == Player.STATE_READY) retried = false }
        })

        // preview box: 16:9 of the right column; the player is laid over it
        previewBox.post { val w = previewBox.width; previewBox.layoutParams.height = w * 9 / 16; previewBox.requestLayout(); previewBox.post { place() } }

        lifecycleScope.launch {
            val clock = findViewById<TextView>(R.id.clock); val bClock = findViewById<TextView>(R.id.bClock)
            while (isActive) { val t = clockF.format(Date()); clock.text = t; bClock.text = t; delay(10_000) }
        }
        lifecycleScope.launch { start() }
    }

    private suspend fun start() {
        if (Api.groups.isEmpty()) withContext(Dispatchers.IO) {
            try { Api.load(cached = true) } catch (_: Exception) { }
            if (Api.groups.isEmpty()) try { Api.load(cached = false) } catch (_: Exception) { }
        }
        if (Api.groups.isEmpty()) { toast("Could not load the channels"); return }
        groupAdapter.notifyDataSetChanged()
        val last = Api.byId[Prefs.lastChannel]
        val g = Api.groups.firstOrNull { it.id == Prefs.lastGroup && it.channels.isNotEmpty() }
            ?: Api.groups.firstOrNull { it.id != Api.FAV && it.id != Api.ALL } ?: Api.groups[0]
        showGroup(g, last)
        last?.let { play(it) }
        // today's event names (NBA, PPV...) change: fresh lists every 15 minutes while the screen is open
        while (true) {
            delay(15 * 60_000)
            val ok = withContext(Dispatchers.IO) { try { Api.load(cached = false) } catch (e: Exception) { false } }
            if (ok) refreshLists()
        }
    }

    private fun refreshLists() {
        val gid = group?.id; val fid = focused?.id
        groupAdapter.notifyDataSetChanged()
        val g = Api.groups.firstOrNull { it.id == gid } ?: return
        group = g
        channelAdapter.items = g.channels
        channelAdapter.notifyDataSetChanged()
        if (fid != null) focused = Api.byId[fid]
    }

    private fun showGroup(g: Group, select: Channel? = null) {
        group = g
        Prefs.lastGroup = g.id
        findViewById<TextView>(R.id.groupName).text = g.name
        findViewById<TextView>(R.id.groupCount).text = g.channels.size.toString()
        channelAdapter.items = g.channels
        channelAdapter.notifyDataSetChanged()
        val pos = select?.let { s -> g.channels.indexOfFirst { it.id == s.id } }?.takeIf { it >= 0 } ?: 0
        (channelsRv.layoutManager as LinearLayoutManager).scrollToPositionWithOffset(pos, 120)
        channelsRv.post { channelsRv.findViewHolderForAdapterPosition(pos)?.itemView?.requestFocus() ?: channelsRv.requestFocus() }
        groupAdapter.notifyDataSetChanged()
    }

    private fun place() {
        val lp = playerView.layoutParams as FrameLayout.LayoutParams
        if (full) {
            lp.width = ViewGroup.LayoutParams.MATCH_PARENT; lp.height = ViewGroup.LayoutParams.MATCH_PARENT
            lp.leftMargin = 0; lp.topMargin = 0
        } else {
            val loc = IntArray(2); previewBox.getLocationInWindow(loc)
            val root = IntArray(2); findViewById<View>(R.id.root).getLocationInWindow(root)
            lp.width = previewBox.width; lp.height = previewBox.height
            lp.leftMargin = loc[0] - root[0]; lp.topMargin = loc[1] - root[1]
        }
        playerView.layoutParams = lp
    }

    private fun play(c: Channel) {
        if (playing?.id == c.id && player.isPlaying) return
        playing = c
        Prefs.lastChannel = c.id
        retried = false
        start(c)
        channelAdapter.notifyDataSetChanged()
    }

    private fun start(c: Channel) {
        player.setMediaItem(MediaItem.fromUri(Api.streamUrl(c)))
        player.prepare()
        player.playWhenReady = true
    }

    private fun setFull(on: Boolean) {
        full = on
        browse.visibility = if (on) View.GONE else View.VISIBLE
        place()
        if (on) showBanner() else {
            banner.visibility = View.GONE
            val pos = channelAdapter.items.indexOfFirst { it.id == playing?.id }
            if (pos >= 0) {
                (channelsRv.layoutManager as LinearLayoutManager).scrollToPositionWithOffset(pos, 120)
                channelsRv.post { channelsRv.findViewHolderForAdapterPosition(pos)?.itemView?.requestFocus() }
            }
        }
    }

    private fun zap(step: Int) {
        val list = group?.channels ?: return
        if (list.isEmpty()) return
        val i = list.indexOfFirst { it.id == playing?.id }
        val n = list[((if (i < 0) 0 else i + step) % list.size + list.size) % list.size]
        play(n); focused = n
        showBanner()
    }

    private fun showBanner() {
        val c = playing ?: return
        findViewById<TextView>(R.id.bNum).text = c.num.toString()
        findViewById<TextView>(R.id.bName).text = c.name
        findViewById<ImageView>(R.id.bLogo).load(c.logo.ifEmpty { null })
        banner.visibility = View.VISIBLE
        fillNow(c, findViewById(R.id.bNow), findViewById(R.id.bProgress), null, findViewById(R.id.bNext))
        bannerJob?.cancel()
        bannerJob = lifecycleScope.launch { delay(5000); banner.visibility = View.GONE }
    }

    /** now / next of a channel into the given views (guide read in the background, cached for 30 minutes) */
    private fun fillNow(c: Channel, now: TextView, bar: ProgressBar, desc: TextView?, next: TextView?) {
        now.text = ""; bar.progress = 0; desc?.text = ""; next?.text = ""
        lifecycleScope.launch {
            val list = withContext(Dispatchers.IO) { Api.guide(c) }
            if (focused?.id != c.id && playing?.id != c.id) return@launch
            val t = System.currentTimeMillis() / 1000
            val cur = list.firstOrNull { it.now(t) }
            val nx = list.firstOrNull { it.start >= (cur?.stop ?: t) }
            if (cur != null) {
                now.text = "${time.format(Date(cur.start * 1000))} – ${time.format(Date(cur.stop * 1000))}   ${cur.title}"
                bar.progress = (((t - cur.start) * 1000) / (cur.stop - cur.start).coerceAtLeast(1)).toInt()
                desc?.text = cur.desc
            } else now.text = "No guide"
            next?.text = nx?.let { "Next  ${time.format(Date(it.start * 1000))}   ${it.title}" } ?: ""
            if (desc != null) { programAdapter.items = list.filter { it.stop > t }.take(12); programAdapter.notifyDataSetChanged() }
        }
    }

    private fun onFocusChannel(c: Channel) {
        focused = c
        infoJob?.cancel()
        infoJob = lifecycleScope.launch {
            delay(200)  // scrolling fast through the list does not load every guide
            findViewById<TextView>(R.id.chName).text = "${c.num}   ${c.name}"
            fillNow(c, findViewById(R.id.nowTitle), findViewById(R.id.nowProgress), findViewById(R.id.nowDesc), null)
        }
    }

    private fun toast(s: String) {
        toastV.text = s; toastV.visibility = View.VISIBLE
        toastJob?.cancel(); toastJob = lifecycleScope.launch { delay(3000); toastV.visibility = View.GONE }
    }

    override fun dispatchKeyEvent(e: KeyEvent): Boolean {
        if (e.action == KeyEvent.ACTION_DOWN && full) {
            when (e.keyCode) {
                KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_CHANNEL_UP -> { zap(-1); return true }
                KeyEvent.KEYCODE_DPAD_DOWN, KeyEvent.KEYCODE_CHANNEL_DOWN -> { zap(1); return true }
                KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER -> { setFull(false); return true }
                KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_INFO -> { showBanner(); return true }
                KeyEvent.KEYCODE_BACK -> { setFull(false); return true }
            }
        }
        if (e.action == KeyEvent.ACTION_DOWN && !full) {
            when (e.keyCode) {
                KeyEvent.KEYCODE_CHANNEL_UP -> { zap(-1); return true }
                KeyEvent.KEYCODE_CHANNEL_DOWN -> { zap(1); return true }
                KeyEvent.KEYCODE_BACK -> if (groupsPanel.visibility == View.VISIBLE) { closeGroups(); return true }
                KeyEvent.KEYCODE_MENU -> { focused?.let { fav(it) }; return true }
            }
        }
        return super.dispatchKeyEvent(e)
    }

    private fun openGroups() {
        groupsPanel.visibility = View.VISIBLE
        val pos = Api.groups.indexOfFirst { it.id == group?.id }.coerceAtLeast(0)
        (groupsRv.layoutManager as LinearLayoutManager).scrollToPositionWithOffset(pos, 120)
        groupsRv.post { groupsRv.findViewHolderForAdapterPosition(pos)?.itemView?.requestFocus(); place() }
    }

    private fun closeGroups() {
        groupsPanel.visibility = View.GONE
        channelsRv.post { place(); showGroup(group ?: return@post, focused) }
    }

    private fun fav(c: Channel) {
        val on = Api.toggleFavorite(c)
        toast(if (on) "★ Added to Favorites" else "Removed from Favorites")
        channelAdapter.notifyDataSetChanged(); groupAdapter.notifyDataSetChanged()
    }

    override fun onStop() { super.onStop(); player.pause() }
    override fun onStart() { super.onStart(); if (playing != null) player.play() }
    override fun onDestroy() { super.onDestroy(); player.release() }

    // ---------------- adapters ----------------

    inner class GroupAdapter : RecyclerView.Adapter<GroupAdapter.H>() {
        inner class H(v: View) : RecyclerView.ViewHolder(v) {
            val name: TextView = v.findViewById(R.id.name); val count: TextView = v.findViewById(R.id.count)
        }
        override fun getItemCount() = Api.groups.size
        override fun onCreateViewHolder(p: ViewGroup, t: Int) = H(LayoutInflater.from(p.context).inflate(R.layout.item_group, p, false))
        override fun onBindViewHolder(h: H, i: Int) {
            val g = Api.groups[i]
            h.name.text = g.name; h.count.text = g.channels.size.toString()
            h.itemView.isActivated = g.id == group?.id
            h.itemView.setOnClickListener { if (g.channels.isNotEmpty()) { groupsPanel.visibility = View.GONE; channelsRv.post { place(); showGroup(g) } } }
            h.itemView.setOnKeyListener { _, k, e ->
                if (e.action == KeyEvent.ACTION_DOWN && k == KeyEvent.KEYCODE_DPAD_RIGHT) { closeGroups(); true } else false
            }
        }
    }

    inner class ChannelAdapter : RecyclerView.Adapter<ChannelAdapter.H>() {
        var items: List<Channel> = emptyList()
        inner class H(v: View) : RecyclerView.ViewHolder(v) {
            val num: TextView = v.findViewById(R.id.num); val logo: ImageView = v.findViewById(R.id.logo)
            val name: TextView = v.findViewById(R.id.name); val now: TextView = v.findViewById(R.id.now)
            val fav: View = v.findViewById(R.id.fav)
        }
        override fun getItemCount() = items.size
        override fun onCreateViewHolder(p: ViewGroup, t: Int): H {
            val h = H(LayoutInflater.from(p.context).inflate(R.layout.item_channel, p, false))
            h.itemView.setOnFocusChangeListener { _, f -> if (f) items.getOrNull(h.bindingAdapterPosition)?.let { onFocusChannel(it) } }
            h.itemView.setOnClickListener {
                val c = items.getOrNull(h.bindingAdapterPosition) ?: return@setOnClickListener
                if (playing?.id == c.id) setFull(true) else play(c)
            }
            h.itemView.setOnLongClickListener { items.getOrNull(h.bindingAdapterPosition)?.let { fav(it) }; true }
            h.itemView.setOnKeyListener { _, k, e ->
                if (e.action == KeyEvent.ACTION_DOWN && k == KeyEvent.KEYCODE_DPAD_LEFT) { openGroups(); true } else false
            }
            return h
        }
        override fun onBindViewHolder(h: H, i: Int) {
            val c = items[i]
            h.num.text = c.num.toString()
            h.name.text = c.name
            h.now.text = if (playing?.id == c.id) "▶ Playing" else ""
            h.itemView.isActivated = playing?.id == c.id
            h.fav.visibility = if (c.id.toString() in Prefs.favorites) View.VISIBLE else View.GONE
            if (c.logo.isEmpty()) h.logo.setImageDrawable(null) else h.logo.load(c.logo) { size(124, 80) }
        }
    }

    inner class ProgramAdapter : RecyclerView.Adapter<ProgramAdapter.H>() {
        var items: List<Program> = emptyList()
        inner class H(v: View) : RecyclerView.ViewHolder(v) {
            val time: TextView = v.findViewById(R.id.time); val title: TextView = v.findViewById(R.id.title)
        }
        override fun getItemCount() = items.size
        override fun onCreateViewHolder(p: ViewGroup, t: Int) = H(LayoutInflater.from(p.context).inflate(R.layout.item_program, p, false))
        override fun onBindViewHolder(h: H, i: Int) {
            val p = items[i]
            h.time.text = time.format(Date(p.start * 1000)) + " – " + time.format(Date(p.stop * 1000))
            h.title.text = p.title
            h.title.setTextColor(getColor(if (p.now()) R.color.accent else R.color.text))
        }
    }
}
