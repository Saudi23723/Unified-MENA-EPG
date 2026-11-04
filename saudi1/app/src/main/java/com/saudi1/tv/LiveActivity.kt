package com.saudi1.tv

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.drawable.ColorDrawable
import android.os.Bundle
import android.view.KeyEvent
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.TrackSelectionOverride
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.DefaultLoadControl
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.ui.AspectRatioFrameLayout
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
class LiveActivity : BaseActivity() {
    private lateinit var playerView: PlayerView
    private lateinit var player: ExoPlayer
    private lateinit var groupsRv: RecyclerView
    private lateinit var channelsRv: RecyclerView
    private lateinit var groupsPanel: View
    private lateinit var browse: View
    private lateinit var rightCol: View
    private lateinit var channelCol: View
    private lateinit var previewBox: View
    private lateinit var banner: View
    private lateinit var fullClock: TextView
    private lateinit var epgPanel: View
    private lateinit var epgList: RecyclerView
    private lateinit var toastV: TextView

    private var group: Group? = null
    private var playing: Channel? = null
    private var previous: Channel? = null
    private var focused: Channel? = null
    private var full = false
    private var overlay = false      // full screen with the channel list over the picture (OK)
    private var infoJob: Job? = null
    private var bannerJob: Job? = null
    private var toastJob: Job? = null
    private var overlayJob: Job? = null
    private var retried = false
    private val time = SimpleDateFormat("h:mm", Locale.ENGLISH)
    private val clockF = SimpleDateFormat("h:mm a", Locale.ENGLISH)
    private val dayF = SimpleDateFormat("EEEE d MMMM", Locale.ENGLISH)

    private val groupAdapter = GroupAdapter()
    private val channelAdapter = ChannelAdapter()
    private val programAdapter = ProgramAdapter()
    private val guideAdapter = GuideAdapter()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_live)
        playerView = findViewById(R.id.player)
        groupsRv = findViewById(R.id.groups)
        channelsRv = findViewById(R.id.channels)
        groupsPanel = findViewById(R.id.groupsPanel)
        browse = findViewById(R.id.browse)
        rightCol = findViewById(R.id.rightCol)
        channelCol = findViewById(R.id.channelCol)
        previewBox = findViewById(R.id.previewBox)
        banner = findViewById(R.id.banner)
        fullClock = findViewById(R.id.fullClock)
        epgPanel = findViewById(R.id.epgPanel)
        epgList = findViewById(R.id.epgList)
        toastV = findViewById(R.id.toast)

        groupsRv.layoutManager = LinearLayoutManager(this)
        groupsRv.adapter = groupAdapter
        channelsRv.layoutManager = LinearLayoutManager(this)
        channelsRv.adapter = channelAdapter
        channelsRv.setItemViewCacheSize(20)
        epgList.layoutManager = LinearLayoutManager(this)
        epgList.adapter = guideAdapter
        findViewById<RecyclerView>(R.id.programs).apply {
            layoutManager = LinearLayoutManager(this@LiveActivity); adapter = programAdapter; isFocusable = false
        }

        // fast start for live TV: small buffers, play as soon as there is a second of video
        val load = DefaultLoadControl.Builder().setBufferDurationsMs(8_000, 30_000, 1_000, 2_000).build()
        player = ExoPlayer.Builder(this).setLoadControl(load)
            .setMediaSourceFactory(DefaultMediaSourceFactory(OkHttpDataSource.Factory(App.http))).build()
        playerView.player = player
        playerView.resizeMode = App.prefs.getInt("resize", AspectRatioFrameLayout.RESIZE_MODE_FIT)
        player.addListener(object : Player.Listener {
            override fun onPlayerError(error: PlaybackException) {
                val c = playing ?: return
                if (!retried) { retried = true; lifecycleScope.launch { delay(1500); if (playing === c) start(c) } }
                else toast("This channel is not available right now")
            }
            override fun onPlaybackStateChanged(state: Int) { if (state == Player.STATE_READY) retried = false }
        })
        // phones / tablets: a tap on the picture shows the channel list, a tap in browse mode goes full screen
        playerView.setOnClickListener { if (!full) setFull(true) else if (overlay) hideOverlay() else showOverlay() }

        previewBox.post { previewBox.layoutParams.height = previewBox.width * 9 / 16; previewBox.requestLayout(); previewBox.post { place() } }

        lifecycleScope.launch {
            val clock = findViewById<TextView>(R.id.clock); val bClock = findViewById<TextView>(R.id.bClock)
            while (isActive) { val t = clockF.format(Date()); clock.text = t; bClock.text = t; fullClock.text = t; delay(5_000) }
        }
        lifecycleScope.launch { start() }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        val id = intent.getIntExtra("channel", -1)
        if (id > 0) Api.byId[id]?.let { tune(it) }
    }

    /** a reminder: straight to the channel, full screen */
    override fun tuneTo(channel: Int) { Api.byId[channel]?.let { tune(it) } }

    private fun tune(c: Channel) {
        val g = Api.groups.firstOrNull { it.id == c.group } ?: group
        if (g != null && g !== group) showGroup(g, c)
        play(c); focused = c
        setFull(true)
    }

    private suspend fun start() {
        if (Api.groups.isEmpty()) withContext(Dispatchers.IO) {
            try { Api.load(cached = true) } catch (_: Exception) { }
            if (Api.groups.isEmpty()) try { Api.load(cached = false) } catch (_: Exception) { }
        }
        if (Api.groups.isEmpty()) { toast("Could not load the channels"); return }
        groupAdapter.notifyDataSetChanged()
        val asked = Api.byId[intent.getIntExtra("channel", -1)]
        val last = asked ?: Api.byId[Prefs.lastChannel]
        val g = Api.groups.firstOrNull { it.id == (asked?.group ?: Prefs.lastGroup) && it.channels.isNotEmpty() }
            ?: Api.groups.firstOrNull { it.id != Api.FAV && it.id != Api.ALL } ?: Api.groups[0]
        showGroup(g, last)
        last?.let { play(it) }
        if (asked != null) setFull(true)
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
        playing = playing?.let { Api.byId[it.id] ?: it }
    }

    private fun showGroup(g: Group, select: Channel? = null) {
        group = g
        Prefs.lastGroup = g.id
        findViewById<TextView>(R.id.groupName).text = g.name
        findViewById<TextView>(R.id.groupCount).text = g.channels.size.toString()
        channelAdapter.items = g.channels
        channelAdapter.notifyDataSetChanged()
        focusChannel(select)
        groupAdapter.notifyDataSetChanged()
    }

    private fun focusChannel(c: Channel?) {
        val pos = c?.let { s -> channelAdapter.items.indexOfFirst { it.id == s.id } }?.takeIf { it >= 0 } ?: 0
        (channelsRv.layoutManager as LinearLayoutManager).scrollToPositionWithOffset(pos, 120)
        channelsRv.post { channelsRv.findViewHolderForAdapterPosition(pos)?.itemView?.requestFocus() ?: channelsRv.requestFocus() }
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
        if (playing?.id == c.id && player.playbackState != Player.STATE_IDLE) return
        if (playing != null && playing?.id != c.id) previous = playing
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

    // ---------------- full screen ----------------

    private fun setFull(on: Boolean) {
        full = on; overlay = false
        epgPanel.visibility = View.GONE
        browse.background = ColorDrawable(getColor(R.color.bg))
        rightCol.visibility = View.VISIBLE
        channelCol.background = null
        browse.visibility = if (on) View.GONE else View.VISIBLE
        fullClock.visibility = if (on) View.VISIBLE else View.GONE
        place()
        if (on) showBanner() else {
            banner.visibility = View.GONE
            focusChannel(playing)
        }
        playerView.bringToFront()
        if (on) { banner.bringToFront(); fullClock.bringToFront() }
        toastV.bringToFront()
        applyDim()
    }

    /** OK in full screen: the channel list over the picture, the picture keeps playing (like TiviMate) */
    private fun showOverlay() {
        overlay = true
        banner.visibility = View.GONE; epgPanel.visibility = View.GONE
        browse.background = null
        rightCol.visibility = View.INVISIBLE
        channelCol.setBackgroundResource(R.drawable.panel_bg)
        browse.visibility = View.VISIBLE
        browse.bringToFront(); fullClock.bringToFront(); toastV.bringToFront()
        focusChannel(playing)
        applyDim()
        stayOverlay()
    }

    private fun stayOverlay() {
        overlayJob?.cancel()
        overlayJob = lifecycleScope.launch { delay(12_000); if (overlay) hideOverlay() }
    }

    private fun hideOverlay() {
        overlay = false; overlayJob?.cancel()
        groupsPanel.visibility = View.GONE
        browse.visibility = View.GONE
        browse.background = ColorDrawable(getColor(R.color.bg))
        rightCol.visibility = View.VISIBLE
        channelCol.background = null
    }

    private fun showEpgPanel() {
        val c = playing ?: return
        banner.visibility = View.GONE
        epgPanel.visibility = View.VISIBLE
        epgPanel.bringToFront(); toastV.bringToFront()
        findViewById<TextView>(R.id.epgTitle).text = "${c.num}   ${c.name}"
        guideAdapter.channel = c; guideAdapter.items = emptyList(); guideAdapter.notifyDataSetChanged()
        lifecycleScope.launch {
            val list = withContext(Dispatchers.IO) { Api.guide(c) }
            val t = System.currentTimeMillis() / 1000
            guideAdapter.items = list.filter { it.stop > t }
            guideAdapter.notifyDataSetChanged()
            if (list.isEmpty()) toast("No guide for this channel")
            epgList.scrollToPosition(0)
            epgList.post { epgList.findViewHolderForAdapterPosition(0)?.itemView?.findViewById<View>(R.id.row)?.requestFocus() }
        }
        applyDim()
    }

    private fun zap(step: Int) {
        val list = group?.channels ?: return
        if (list.isEmpty()) return
        val i = list.indexOfFirst { it.id == playing?.id }
        val n = list[((if (i < 0) 0 else i + step) % list.size + list.size) % list.size]
        play(n); focused = n
        showBanner()
    }

    private fun back() {
        val p = previous ?: run { toast("No previous channel"); return }
        val g = Api.groups.firstOrNull { gr -> gr.id == p.group } ?: group
        if (g != null && g !== group) showGroup(g, p)
        play(p); focused = p
        showBanner()
    }

    private fun showBanner() {
        val c = playing ?: return
        findViewById<TextView>(R.id.bNum).text = c.num.toString()
        findViewById<TextView>(R.id.bName).text = c.name
        findViewById<ImageView>(R.id.bLogo).load(c.logo.ifEmpty { null })
        banner.visibility = View.VISIBLE
        banner.bringToFront(); fullClock.bringToFront()
        fillNow(c, findViewById(R.id.bNow), findViewById(R.id.bProgress), null, findViewById(R.id.bNext))
        bannerJob?.cancel()
        bannerJob = lifecycleScope.launch { delay(5000); banner.visibility = View.GONE }
        applyDim()
    }

    /** audio / subtitles / picture size / night dimming (MENU, or hold OK in full screen) */
    private fun options() {
        val items = arrayOf("Audio", "Subtitles", "Picture size", "Night dimming", "Previous channel", "TV Guide")
        AlertDialog.Builder(this).setTitle(playing?.name ?: "Options").setItems(items) { _, w ->
            when (w) {
                0 -> tracks(C.TRACK_TYPE_AUDIO)
                1 -> tracks(C.TRACK_TYPE_TEXT)
                2 -> {
                    val modes = intArrayOf(AspectRatioFrameLayout.RESIZE_MODE_FIT, AspectRatioFrameLayout.RESIZE_MODE_FILL, AspectRatioFrameLayout.RESIZE_MODE_ZOOM)
                    AlertDialog.Builder(this).setTitle("Picture size").setItems(arrayOf("Fit", "Stretch", "Zoom")) { _, m ->
                        playerView.resizeMode = modes[m]; App.prefs.edit().putInt("resize", modes[m]).apply()
                    }.show()
                }
                3 -> dimDialog()
                4 -> back()
                5 -> startActivity(Intent(this, GuideActivity::class.java))
            }
        }.show()
    }

    private fun dimDialog() {
        AlertDialog.Builder(this).setTitle("Night dimming")
            .setSingleChoiceItems(Dim.levels.map { if (it == 0) "Off" else "$it %" }.toTypedArray(), Dim.levels.indexOf(Dim.level).coerceAtLeast(0)) { d, w ->
                Dim.level = Dim.levels[w]; applyDim(); d.dismiss()
            }.show()
    }

    private fun tracks(type: Int) {
        val groups = player.currentTracks.groups.filter { it.type == type }
        val names = ArrayList<String>(); val picks = ArrayList<Pair<Int, Int>>()
        if (type == C.TRACK_TYPE_TEXT) { names.add("Off"); picks.add(-1 to -1) }
        groups.forEachIndexed { gi, g ->
            for (t in 0 until g.length) {
                if (!g.isTrackSupported(t)) continue
                val f = g.getTrackFormat(t)
                val lang = f.language?.let { Locale(it).displayLanguage }?.takeIf { it.isNotBlank() } ?: "Track ${names.size + 1}"
                names.add(listOfNotNull(lang, f.label, if (f.channelCount > 0) "${f.channelCount}ch" else null).distinct().joinToString(" · "))
                picks.add(gi to t)
            }
        }
        if (names.isEmpty() || (type == C.TRACK_TYPE_AUDIO && names.size < 2)) { toast(if (type == C.TRACK_TYPE_AUDIO) "This channel has one audio" else "No subtitles on this channel"); return }
        AlertDialog.Builder(this).setTitle(if (type == C.TRACK_TYPE_AUDIO) "Audio" else "Subtitles").setItems(names.toTypedArray()) { _, w ->
            val (gi, t) = picks[w]
            val b = player.trackSelectionParameters.buildUpon()
            if (gi < 0) b.setTrackTypeDisabled(C.TRACK_TYPE_TEXT, true)
            else b.setTrackTypeDisabled(type, false).setOverrideForType(TrackSelectionOverride(groups[gi].mediaTrackGroup, t))
            player.trackSelectionParameters = b.build()
        }.show()
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
        if (overlay) stayOverlay()
        infoJob?.cancel()
        infoJob = lifecycleScope.launch {
            delay(200)  // scrolling fast through the list does not load every guide
            findViewById<TextView>(R.id.chName).text = "${c.num}   ${c.name}"
            fillNow(c, findViewById(R.id.nowTitle), findViewById(R.id.nowProgress), findViewById(R.id.nowDesc), null)
        }
    }

    private fun toast(s: String) {
        toastV.text = s; toastV.visibility = View.VISIBLE; toastV.bringToFront()
        toastJob?.cancel(); toastJob = lifecycleScope.launch { delay(3000); toastV.visibility = View.GONE }
    }

    override fun dispatchKeyEvent(e: KeyEvent): Boolean {
        if (overlayOpen) return super.dispatchKeyEvent(e)
        val down = e.action == KeyEvent.ACTION_DOWN
        if (full && !overlay && epgPanel.visibility != View.VISIBLE) {
            when (e.keyCode) {
                KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_CHANNEL_UP -> { if (down) zap(-1); return true }
                KeyEvent.KEYCODE_DPAD_DOWN, KeyEvent.KEYCODE_CHANNEL_DOWN -> { if (down) zap(1); return true }
                KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER -> {
                    // short press: channel list over the picture; hold: options
                    if (down && e.repeatCount == 1) options()
                    else if (!down && !e.isCanceled && e.eventTime - e.downTime < 500) showOverlay()
                    return true
                }
                KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_LAST_CHANNEL -> { if (down) back(); return true }
                KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_GUIDE -> { if (down) showEpgPanel(); return true }
                KeyEvent.KEYCODE_INFO -> { if (down) showBanner(); return true }
                KeyEvent.KEYCODE_MENU -> { if (down) options(); return true }
                KeyEvent.KEYCODE_BACK -> { if (!down) setFull(false); return true }
            }
        }
        if (full && epgPanel.visibility == View.VISIBLE && e.keyCode == KeyEvent.KEYCODE_BACK) {
            if (!down) epgPanel.visibility = View.GONE; return true
        }
        if (full && overlay) {
            if (down) stayOverlay()
            if (e.keyCode == KeyEvent.KEYCODE_BACK) {
                if (!down) { if (groupsPanel.visibility == View.VISIBLE) closeGroups() else hideOverlay() }
                return true
            }
        }
        if (down && !full) {
            when (e.keyCode) {
                KeyEvent.KEYCODE_CHANNEL_UP -> { zap(-1); return true }
                KeyEvent.KEYCODE_CHANNEL_DOWN -> { zap(1); return true }
                KeyEvent.KEYCODE_LAST_CHANNEL -> { back(); return true }
                KeyEvent.KEYCODE_BACK -> if (groupsPanel.visibility == View.VISIBLE) { closeGroups(); return true }
                KeyEvent.KEYCODE_MENU -> { options(); return true }
            }
        }
        return super.dispatchKeyEvent(e)
    }

    private fun openGroups() {
        groupsPanel.visibility = View.VISIBLE
        if (overlay) groupsPanel.setBackgroundResource(R.drawable.panel_bg) else groupsPanel.background = null
        val pos = Api.groups.indexOfFirst { it.id == group?.id }.coerceAtLeast(0)
        (groupsRv.layoutManager as LinearLayoutManager).scrollToPositionWithOffset(pos, 120)
        groupsRv.post { groupsRv.findViewHolderForAdapterPosition(pos)?.itemView?.requestFocus(); if (!full) place() }
    }

    private fun closeGroups() {
        groupsPanel.visibility = View.GONE
        channelsRv.post { if (!full) place(); showGroup(group ?: return@post, focused) }
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
            h.itemView.setOnClickListener { if (g.channels.isNotEmpty()) { groupsPanel.visibility = View.GONE; channelsRv.post { if (!full) place(); showGroup(g) } } }
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
                when {
                    overlay -> { play(c); hideOverlay(); showBanner() }
                    playing?.id == c.id -> setFull(true)
                    else -> play(c)
                }
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
            h.title.text = (if (Reminders.has(currentChannelForPrograms(), p.start)) "⏰ " else "") + p.title
            h.title.setTextColor(getColor(if (p.now()) R.color.accent else R.color.text))
        }
    }

    private fun currentChannelForPrograms() = focused?.id ?: -1

    /** the channel's guide for the coming days; OK on a coming program sets / removes a reminder */
    inner class GuideAdapter : RecyclerView.Adapter<GuideAdapter.H>() {
        var items: List<Program> = emptyList()
        var channel: Channel? = null
        inner class H(v: View) : RecyclerView.ViewHolder(v) {
            val day: TextView = v.findViewById(R.id.day); val row: View = v.findViewById(R.id.row)
            val time: TextView = v.findViewById(R.id.time); val title: TextView = v.findViewById(R.id.title)
            val desc: TextView = v.findViewById(R.id.desc); val mark: TextView = v.findViewById(R.id.mark)
        }
        override fun getItemCount() = items.size
        override fun onCreateViewHolder(p: ViewGroup, t: Int): H {
            val h = H(LayoutInflater.from(p.context).inflate(R.layout.item_guide, p, false))
            h.row.setOnClickListener {
                val pr = items.getOrNull(h.bindingAdapterPosition) ?: return@setOnClickListener
                val c = channel ?: return@setOnClickListener
                if (pr.now()) { epgPanel.visibility = View.GONE; return@setOnClickListener }
                val on = Reminders.toggle(Reminder(c.id, pr.start, pr.title, c.name))
                toast(if (on) "⏰ Reminder set: ${time.format(Date(pr.start * 1000))} ${pr.title}" else "Reminder removed")
                notifyItemChanged(h.bindingAdapterPosition)
            }
            return h
        }
        override fun onBindViewHolder(h: H, i: Int) {
            val p = items[i]
            val d = dayF.format(Date(p.start * 1000))
            val prev = items.getOrNull(i - 1)?.let { dayF.format(Date(it.start * 1000)) }
            h.day.visibility = if (d != prev) View.VISIBLE else View.GONE
            h.day.text = if (d == dayF.format(Date())) "Today" else d
            h.time.text = time.format(Date(p.start * 1000))
            h.title.text = p.title
            h.desc.text = p.desc
            val c = channel
            h.mark.text = when {
                p.now() -> "LIVE"
                c != null && Reminders.has(c.id, p.start) -> "⏰"
                else -> ""
            }
            h.mark.setTextColor(getColor(if (p.now()) R.color.live else R.color.accent))
        }
    }
}
