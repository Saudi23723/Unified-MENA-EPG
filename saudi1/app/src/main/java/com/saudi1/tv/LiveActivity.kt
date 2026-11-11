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
    private var tries = 0
    private var usingHls = false
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
        player = Players.make(this, live = true)
        playerView.player = player
        playerView.resizeMode = App.prefs.getInt("resize", AspectRatioFrameLayout.RESIZE_MODE_FIT)
        player.addListener(object : Player.Listener {
            override fun onPlayerError(error: PlaybackException) {
                val c = playing ?: return
                // fell behind the live edge (HLS): jump back to live, no error for the viewer
                if (error.errorCode == PlaybackException.ERROR_CODE_BEHIND_LIVE_WINDOW) { player.seekToDefaultPosition(); player.prepare(); return }
                // 1st: the same link again (a provider "500" is often a busy moment); 2nd: the channel's HLS link
                // (some channels are sent as HLS on the .ts address: "no extractor could read the stream"); then give up
                when (tries++) {
                    0 -> lifecycleScope.launch { delay(1200); if (playing === c) start(c) }
                    1 -> lifecycleScope.launch { delay(500); if (playing === c) start(c, hls = !Hls.has(c.id)) }
                    else -> toast("This channel is not available right now")
                }
            }
            override fun onVideoSizeChanged(videoSize: androidx.media3.common.VideoSize) {
                // the banner opened before the picture: its line gets the real quality as soon as it is known
                val c = playing ?: return
                if (banner.visibility == View.VISIBLE) findViewById<TextView>(R.id.bName).text = c.name + qualityTag()
            }
            override fun onPlaybackStateChanged(state: Int) {
                // every moment spent waiting after the picture started puts the viewer that much behind live
                if (state == Player.STATE_BUFFERING && player.currentPosition > 0) {
                    bufStart = android.os.SystemClock.elapsedRealtime()
                    android.util.Log.w("SAUDI", "wait: ${playing?.name} ahead=${player.bufferedPosition - player.currentPosition}ms speed=${player.playbackParameters.speed}")
                    slowLine()
                }
                if (state == Player.STATE_READY && bufStart > 0) android.util.Log.w("SAUDI", "wait over after ${android.os.SystemClock.elapsedRealtime() - bufStart}ms")
                if (state != Player.STATE_BUFFERING && bufStart > 0) { lag += android.os.SystemClock.elapsedRealtime() - bufStart; bufStart = 0 }
                if (state == Player.STATE_READY) {
                    // remember which link worked for this channel
                    playing?.let { c -> if (usingHls) Hls.add(c.id) else if (tries > 0) Hls.remove(c.id) }
                    tries = 0
                }
            }
        })
        // phones / tablets: a tap on the picture shows the controls, a swipe ▲▼ changes channel, a tap in browse mode goes full screen
        if (isTouch) touchSetup() else playerView.setOnClickListener { if (!full) setFull(true) else if (overlay) hideOverlay() else showOverlay() }
        findViewById<View>(R.id.groupName).setOnClickListener { if (groupsPanel.visibility == View.VISIBLE) closeGroups() else openGroups() }

        // the preview box keeps 16:9 whatever the width (groups open / closed, phone / TV), and the picture follows it
        previewBox.addOnLayoutChangeListener { v, l, t, r, b, ol, ot, or, ob ->
            val want = (r - l) * 9 / 16
            if (want > 0 && v.layoutParams.height != want) { v.layoutParams.height = want; v.post { v.requestLayout() } }
            if (!full && (l != ol || t != ot || r != or || b != ob)) v.post { if (!full) place() }
        }
        findViewById<View>(R.id.root).addOnLayoutChangeListener { _, _, _, _, _, _, _, _, _ -> if (!full) previewBox.post { if (!full) place() } }

        lifecycleScope.launch {
            val clock = findViewById<TextView>(R.id.clock); val bClock = findViewById<TextView>(R.id.bClock)
            while (isActive) { val t = clockF.format(Date()); clock.text = t; bClock.text = t; fullClock.text = t; delay(5_000) }
        }
        lifecycleScope.launch { start() }
        // always close to live (.ts channels): with picture in reserve it plays 1.07x until it is back, the sound
        // keeps its pitch; far behind with nothing in reserve (a long hiccup) = the channel again, straight at live
        lifecycleScope.launch {
            while (isActive) {
                delay(1000)
                if (playing == null || usingHls || player.playbackState != Player.STATE_READY || !player.isPlaying) continue
                val ahead = player.bufferedPosition - player.currentPosition
                val fast = player.playbackParameters.speed > 1f
                if (fast) lag = (lag - 50).coerceAtLeast(0)
                // smooth first (owner, 9 Nov 2026: short freezes): what the provider sends ahead is KEPT as a reserve
                // (up to ~9 s) so its small gaps do not show; only more than that is caught up. Being a few seconds
                // behind live costs nothing, a spinner every few minutes does.
                val want = when { ahead > 14_000 -> 1.05f; fast && ahead > 9_000 -> 1.05f; else -> 1f }
                if (want != player.playbackParameters.speed) player.setPlaybackSpeed(want)
                if (lag > 12_000 && ahead < 2_500) { lag = 0; playing?.let { start(it) } }
            }
        }
        // a picture that stops moving (the provider's stream stalls) starts again by itself
        lifecycleScope.launch {
            var last = -1L; var still = 0
            var frames = -1; var frozen = 0
            while (isActive) {
                delay(3000)
                val c = playing
                if (c == null || !player.playWhenReady || player.playbackState == Player.STATE_IDLE || player.playbackState == Player.STATE_ENDED) { still = 0; last = -1; frames = -1; frozen = 0; continue }
                Device.now("live", c.name)
                val pos = player.currentPosition
                if (pos == last) { if (++still >= 3) { still = 0; last = -1; android.util.Log.w("SAUDI", "stalled: restart ${c.name}"); start(c); continue } } else still = 0
                last = pos
                // the sound goes on but the picture is stuck (the video decoder stopped): the clock still moves, so
                // watch the pictures shown instead — none for 6 s while playing = the channel again
                val n = player.videoDecoderCounters?.let { it.ensureUpdated(); it.renderedOutputBufferCount } ?: -1
                if (player.isPlaying && player.videoFormat != null && n >= 0 && n == frames) {
                    if (++frozen >= 2) { frozen = 0; frames = -1; android.util.Log.w("SAUDI", "picture frozen: restart ${c.name}"); player.setPlaybackSpeed(1f); start(c); continue }
                } else frozen = 0
                frames = n
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        if (intent.hasExtra("channel")) Api.byId[intent.getIntExtra("channel", 0)]?.let { tune(it) }
    }

    /** a reminder: straight to the channel, full screen */
    override fun tuneTo(channel: Int) { Api.byId[channel]?.let { tune(it) } }

    private fun tune(c: Channel) {
        val g = Api.group(c.group) ?: group
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
        fun ok(c: Channel?) = c?.takeIf { ch -> !Parental.isLocked(ch.group, Api.group(ch.group)?.name ?: "") }
        val asked = if (intent.hasExtra("channel")) ok(Api.byId[intent.getIntExtra("channel", 0)]) else null
        // a guide screen (Sports today) is never "the last channel": Live TV opens on the real channels
        val last = asked ?: ok(Api.byId[Prefs.lastChannel])?.takeIf { it.id > 0 && it.group != Api.DASH }
        val wantGroup = intent.getStringExtra("group")
        val g = Api.group(wantGroup ?: asked?.group ?: last?.group ?: Prefs.lastGroup.takeIf { it != Api.DASH })?.takeIf { it.channels.isNotEmpty() && !Parental.isLocked(it.id, it.name) }
            ?: Api.groups.firstOrNull { it.id != Api.FAV && it.id != Api.ALL && it.id != Api.SEARCH && it.channels.isNotEmpty() } ?: Api.groups[0]
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
        val g = Api.group(gid) ?: return
        group = g
        channelAdapter.items = g.channels
        channelAdapter.notifyDataSetChanged()
        if (fid != null) focused = Api.byId[fid]
        playing = playing?.let { Api.byId[it.id] ?: it }
    }

    private fun showGroup(g: Group, select: Channel? = null) {
        group = g
        // the guide screens (Sports today) are not a real group: Live TV opens on the normal channels next time
        if (g.id != Api.DASH) Prefs.lastGroup = g.id
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
            if (previewBox.width == 0 || previewBox.height == 0) { previewBox.post { place() }; return }
            lp.width = previewBox.width; lp.height = previewBox.height
            lp.leftMargin = loc[0] - root[0]; lp.topMargin = loc[1] - root[1]
        }
        playerView.layoutParams = lp
    }

    private fun play(c: Channel) {
        if (playing?.id == c.id && player.playbackState != Player.STATE_IDLE) return
        val old = playing
        if (old != null && old.id != c.id) previous = old
        if (c.id > 0) { History.add(c.id); Prefs.lastChannel = c.id }
        playing = c
        tries = 0; stalls.clear()
        start(c)
        channelAdapter.items.indexOfFirst { it.id == old?.id }.takeIf { it >= 0 }?.let { channelAdapter.notifyItemChanged(it) }
        channelAdapter.items.indexOfFirst { it.id == c.id }.takeIf { it >= 0 }?.let { channelAdapter.notifyItemChanged(it) }
    }

    private var lag = 0L; private var bufStart = 0L

    // ---- the connection cannot carry this quality: after 3 waits in 2 minutes the channel goes to its next lighter
    // copy by itself (4K → FHD → HD → SD), once per channel; MENU › Quality goes back (Settings can turn this off)
    private val stalls = ArrayList<Long>()
    private var loweredFor = -1
    private fun tier(n: String): Int { val u = n.uppercase(); return when {
        Regex("\\b(8K|4K|UHD|2160P?|3840P?|RAW)\\b").containsMatchIn(u) -> 4; Regex("\\b(FHD|1080P?)\\b").containsMatchIn(u) -> 3
        Regex("\\b(SD|LQ|LOW|LITE|480P?|576P?)\\b").containsMatchIn(u) -> 1; else -> 2 } }
    private fun slowLine() {
        val c = playing ?: return
        if (!App.prefs.getBoolean("auto_quality", true) || c.id <= 0 || loweredFor == c.id) return
        val now = android.os.SystemClock.elapsedRealtime()
        stalls.add(now); stalls.removeAll { now - it > 120_000 }
        if (stalls.size < 3) return
        stalls.clear()
        val mine = tier(c.name)
        val lower = Api.qualities(c).filter { it.id != c.id && tier(it.name) < mine }.maxByOrNull { tier(it.name) } ?: return
        loweredFor = lower.id
        toast("Slow connection — now on ${lower.name}   ·   MENU › Quality to change")
        jump(lower)
    }

    private fun start(c: Channel, hls: Boolean = Hls.has(c.id)) {
        val u = Api.streamUrl(c)
        usingHls = hls && u.endsWith(".ts")
        // HLS: the player itself stays 6 s from live, a little faster / slower to keep there
        val liveCfg = MediaItem.LiveConfiguration.Builder().setTargetOffsetMs(6_000).setMinOffsetMs(3_000).setMaxOffsetMs(20_000)
            .setMinPlaybackSpeed(0.97f).setMaxPlaybackSpeed(1.06f).build()
        player.setMediaItem(if (usingHls) MediaItem.Builder().setUri(u.removeSuffix(".ts") + ".m3u8")
            .setMimeType(androidx.media3.common.MimeTypes.APPLICATION_M3U8).setLiveConfiguration(liveCfg).build() else MediaItem.fromUri(u))
        lag = 0; bufStart = 0
        player.setPlaybackSpeed(1f)
        player.prepare()
        player.playWhenReady = true
    }

    // ---------------- full screen ----------------

    private fun setFull(on: Boolean) {
        full = on; overlay = false
        hideTouch()
        epgPanel.visibility = View.GONE
        browse.background = ColorDrawable(getColor(R.color.bg))
        rightCol.visibility = View.VISIBLE
        channelCol.background = null
        browse.visibility = if (on) View.GONE else View.VISIBLE
        fullClock.visibility = if (on && App.prefs.getBoolean("clock", true)) View.VISIBLE else View.GONE
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
        hideTouch()
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
        val p = previous ?: History.ids().drop(1).firstNotNullOfOrNull { Api.byId[it] } ?: run { toast("No previous channel"); return }
        jump(p)
    }

    private fun jump(p: Channel) {
        val g = Api.group(p.group) ?: group
        if (g != null && g !== group) showGroup(g, p)
        play(p); focused = p
        showBanner()
    }

    /** LEFT: the last channels watched (up to 5) — OK on one goes there; LEFT again = the one before */
    private fun recent() {
        val list = History.ids().filter { it != playing?.id }.mapNotNull { Api.byId[it] }.take(5)
        if (list.isEmpty()) { toast("No previous channel"); return }
        val d = AlertDialog.Builder(this).setTitle("Last channels")
            .setItems(list.map { "${it.num}   ${it.name}" }.toTypedArray()) { _, w -> jump(list[w]) }.create()
        d.setOnKeyListener { dd, k, e ->
            if (k == KeyEvent.KEYCODE_DPAD_LEFT && e.action == KeyEvent.ACTION_DOWN && e.repeatCount == 0) { dd.dismiss(); jump(list[0]); true } else false
        }
        d.show()
    }

    /** what the channel really sends (like TiviMate): "  ·  1080p50 HEVC" — empty until the picture is there */
    private fun qualityTag(): String {
        val f = player.videoFormat ?: return ""
        if (f.height <= 0) return ""
        val res = when { f.height >= 2000 -> "4K"; f.height >= 1000 -> "1080p"; f.height >= 700 -> "720p"; else -> "${f.height}p SD" }
        val fps = if (f.frameRate > 1) f.frameRate.toInt().toString() else ""
        val m = f.sampleMimeType ?: ""
        val co = when { m.contains("hevc") -> " HEVC"; m.contains("avc") -> " H.264"; else -> "" }
        return "   ·   $res$fps$co"
    }

    private fun showBanner() {
        val c = playing ?: return
        findViewById<TextView>(R.id.bNum).text = c.num.toString()
        findViewById<TextView>(R.id.bName).text = c.name + qualityTag()
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
        val recording = Recorder.current != null
        // the owner's order (8 Nov 2026): what is used most first
        val items = arrayOf("Search", "Night mode", "Multiview", if (recording) "⏹ Stop recording" else "⏺ Record", "Last channels", "TV Guide",
            "Quality", "Audio", "Subtitles", "Picture size")
        AlertDialog.Builder(this).setTitle(playing?.name ?: "Options").setItems(items) { _, w0 ->
            if (w0 == 6) { quality(); return@setItems }
            if (w0 == 2) { startActivity(Intent(this, MultiviewActivity::class.java).putExtra("channel", playing?.id ?: -1)); return@setItems }
            if (w0 == 0) { startActivity(Intent(this, SearchActivity::class.java)); return@setItems }
            if (w0 == 3) { if (recording) { Recorder.stop(this); toast("Recording stopped") } else record(); return@setItems }
            when (intArrayOf(-1, 3, -1, -1, 4, 5, -1, 0, 1, 2)[w0]) {
                0 -> tracks(C.TRACK_TYPE_AUDIO)
                1 -> tracks(C.TRACK_TYPE_TEXT)
                2 -> {
                    val modes = intArrayOf(AspectRatioFrameLayout.RESIZE_MODE_FIT, AspectRatioFrameLayout.RESIZE_MODE_FILL, AspectRatioFrameLayout.RESIZE_MODE_ZOOM)
                    AlertDialog.Builder(this).setTitle("Picture size").setItems(arrayOf("Fit", "Stretch", "Zoom")) { _, m ->
                        playerView.resizeMode = modes[m]; App.prefs.edit().putInt("resize", modes[m]).apply()
                    }.show()
                }
                3 -> dimDialog()
                4 -> recent()
                5 -> startActivity(Intent(this, GuideActivity::class.java))
            }
        }.show()
    }

    /** record the playing channel: until the program ends, or for a set time */
    private fun record() {
        val c = playing ?: return
        lifecycleScope.launch {
            val t = System.currentTimeMillis() / 1000
            val cur = withContext(Dispatchers.IO) { Api.guide(c) }.firstOrNull { it.now(t) }
            val opts = ArrayList<Pair<String, Long>>()
            if (cur != null) opts.add("Until “${cur.title}” ends (${time.format(Date(cur.stop * 1000))})" to cur.stop * 1000 + 120_000)
            listOf(30, 60, 120, 180).forEach { m -> opts.add("$m minutes" to System.currentTimeMillis() + m * 60_000L) }
            val free = Recordings.free(this@LiveActivity) / (1024 * 1024 * 1024.0)
            AlertDialog.Builder(this@LiveActivity).setTitle("Record ${c.name}  ·  %.1f GB free".format(free))
                .setItems(opts.map { it.first }.toTypedArray()) { _, w ->
                    Recorder.start(this@LiveActivity, c, opts[w].second)
                    toast("⏺ Recording — find it in Settings › Recordings")
                }.show()
        }
    }

    /** the same channel in its other qualities (4K / FHD / HD / SD / HEVC / RAW...) from the whole list */
    private fun quality() {
        val c = playing ?: return
        lifecycleScope.launch {
            val same = withContext(Dispatchers.Default) { Api.qualities(c) }
            if (same.size < 2) { toast("This channel has one quality"); return@launch }
            val labels = same.map { (if (it.id == c.id) "▶  " else "") + it.name + "   ·   " + (Api.group(it.group)?.name ?: "") }
            AlertDialog.Builder(this@LiveActivity).setTitle("Quality").setItems(labels.toTypedArray()) { _, w ->
                if (same[w].id != c.id) jump(same[w])
            }.show()
        }
    }

    private fun dimDialog() {
        nightDialog()
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
                now.text = "\u200E${time.format(Date(cur.start * 1000))} – ${time.format(Date(cur.stop * 1000))}   ${cur.title}"
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
                KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_CHANNEL_UP -> { if (down) zap(if (App.prefs.getBoolean("zap_invert", false)) -1 else 1); return true }
                KeyEvent.KEYCODE_DPAD_DOWN, KeyEvent.KEYCODE_CHANNEL_DOWN -> { if (down) zap(if (App.prefs.getBoolean("zap_invert", false)) 1 else -1); return true }
                KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER -> {
                    // short press: channel list over the picture; hold: options
                    if (down && e.repeatCount == 1) options()
                    else if (!down && !e.isCanceled && e.eventTime - e.downTime < 500) showOverlay()
                    return true
                }
                KeyEvent.KEYCODE_DPAD_LEFT -> { if (down && e.repeatCount == 0) recent(); return true }
                KeyEvent.KEYCODE_LAST_CHANNEL -> { if (down) back(); return true }
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
                KeyEvent.KEYCODE_CHANNEL_UP -> { zap(1); return true }
                KeyEvent.KEYCODE_CHANNEL_DOWN -> { zap(-1); return true }
                KeyEvent.KEYCODE_LAST_CHANNEL -> { back(); return true }
                KeyEvent.KEYCODE_BACK -> if (groupsPanel.visibility == View.VISIBLE) { closeGroups(); return true }
                KeyEvent.KEYCODE_MENU -> { options(); return true }
            }
        }
        return super.dispatchKeyEvent(e)
    }

    private fun jumpTo(rv: RecyclerView, pos: Int) {
        (rv.layoutManager as LinearLayoutManager).scrollToPositionWithOffset(pos, 120)
        rv.post { rv.findViewHolderForAdapterPosition(pos)?.itemView?.requestFocus() }
    }

    private fun openGroups() {
        groupsPanel.visibility = View.VISIBLE
        if (overlay) groupsPanel.setBackgroundResource(R.drawable.panel_bg) else groupsPanel.setBackgroundColor(getColor(R.color.bg))
        // a short slide in, over the channel list: nothing else on the screen moves or resizes
        groupsPanel.alpha = 0f; groupsPanel.translationX = -30 * resources.displayMetrics.density
        groupsPanel.animate().alpha(1f).translationX(0f).setDuration(140).start()
        val pos = Api.groups.indexOfFirst { it.id == group?.id }.coerceAtLeast(0)
        (groupsRv.layoutManager as LinearLayoutManager).scrollToPositionWithOffset(pos, 120)
        groupsRv.post { groupsRv.findViewHolderForAdapterPosition(pos)?.itemView?.requestFocus() }
    }

    private fun closeGroups() {
        groupsPanel.visibility = View.GONE
        channelsRv.post { showGroup(group ?: return@post, focused) }
    }

    private fun fav(c: Channel) {
        val on = Api.toggleFavorite(c)
        toast(if (on) "★ Added to Favorites" else "Removed from Favorites")
        channelAdapter.items.indexOfFirst { it.id == c.id }.takeIf { it >= 0 }?.let { channelAdapter.notifyItemChanged(it) }
        groupAdapter.notifyItemChanged(0)
    }

    override fun onStop() { super.onStop(); player.pause() }
    override fun onStart() {
        super.onStart()
        playerView.resizeMode = App.prefs.getInt("resize", AspectRatioFrameLayout.RESIZE_MODE_FIT)
        if (playing != null) player.play()
    }
    override fun onDestroy() { super.onDestroy(); player.release() }

    // ---------------- phones / tablets ----------------

    private var touchBar: View? = null
    private var touchJob: Job? = null
    private var touchName: TextView? = null

    @SuppressLint("ClickableViewAccessibility")
    private fun touchSetup() {
        val d = resources.displayMetrics.density
        fun btn(t: String, size: Float = 15f, go: () -> Unit) = TextView(this).apply {
            text = t; textSize = size; gravity = android.view.Gravity.CENTER; setTypeface(typeface, android.graphics.Typeface.BOLD)
            setBackgroundResource(R.drawable.touch_btn); isClickable = true
            setPadding((16 * d).toInt(), (10 * d).toInt(), (16 * d).toInt(), (10 * d).toInt())
            setOnClickListener { go(); stayTouch() }
        }
        val bar = FrameLayout(this).apply { setBackgroundResource(R.drawable.touch_scrim); visibility = View.GONE; isClickable = true }
        val top = android.widget.LinearLayout(this).apply { orientation = android.widget.LinearLayout.HORIZONTAL; gravity = android.view.Gravity.CENTER_VERTICAL }
        top.addView(btn("✕", 18f) { setFull(false) })
        touchName = TextView(this).apply { textSize = 18f; setTypeface(typeface, android.graphics.Typeface.BOLD); setPadding((16 * d).toInt(), 0, 0, 0); setSingleLine(true); ellipsize = android.text.TextUtils.TruncateAt.END }
        top.addView(touchName, android.widget.LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        top.addView(btn("⋮", 20f) { options() })
        bar.addView(top, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, android.view.Gravity.TOP).apply { setMargins((16 * d).toInt(), (14 * d).toInt(), (16 * d).toInt(), 0) })
        val side = android.widget.LinearLayout(this).apply { orientation = android.widget.LinearLayout.VERTICAL }
        side.addView(btn("▲", 22f) { zap(1) }); side.addView(View(this), android.widget.LinearLayout.LayoutParams(1, (14 * d).toInt())); side.addView(btn("▼", 22f) { zap(-1) })
        bar.addView(side, FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, android.view.Gravity.END or android.view.Gravity.CENTER_VERTICAL).apply { marginEnd = (18 * d).toInt() })
        val bottom = android.widget.LinearLayout(this).apply { orientation = android.widget.LinearLayout.HORIZONTAL; gravity = android.view.Gravity.CENTER }
        listOf<Pair<String, () -> Unit>>(
            "☰  Channels" to { showOverlay() }, "⟲  Last" to { recent() }, "🗓  Guide" to { showEpgPanel() },
            "HD  Quality" to { quality() }, "🔈  Audio" to { tracks(C.TRACK_TYPE_AUDIO) }, "◐  Night" to { nightDialog() },
        ).forEach { (t, go) ->
            bottom.addView(btn(t) { go() }, android.widget.LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { marginStart = (5 * d).toInt(); marginEnd = (5 * d).toInt() })
        }
        bar.addView(android.widget.HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; addView(bottom) },
            FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, android.view.Gravity.BOTTOM or android.view.Gravity.CENTER_HORIZONTAL).apply { bottomMargin = (18 * d).toInt() })
        bar.setOnClickListener { hideTouch() }
        (findViewById<ViewGroup>(R.id.root)).addView(bar, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        touchBar = bar

        val gd = android.view.GestureDetector(this, object : android.view.GestureDetector.SimpleOnGestureListener() {
            override fun onDown(e: android.view.MotionEvent) = true
            override fun onSingleTapConfirmed(e: android.view.MotionEvent): Boolean {
                when { !full -> setFull(true); overlay -> hideOverlay(); else -> showTouch() }
                return true
            }
            override fun onDoubleTap(e: android.view.MotionEvent): Boolean { if (full) showOverlay(); return true }
            override fun onFling(e1: android.view.MotionEvent?, e2: android.view.MotionEvent, vx: Float, vy: Float): Boolean {
                if (!full || e1 == null) return false
                val dx = e2.x - e1.x; val dy = e2.y - e1.y
                if (kotlin.math.abs(dy) > kotlin.math.abs(dx) && kotlin.math.abs(dy) > 80 * d) zap(if (dy < 0) 1 else -1)   // swipe up = next
                else if (kotlin.math.abs(dx) > 80 * d) { if (dx < 0) showEpgPanel() else recent() }
                return true
            }
        })
        playerView.setOnTouchListener { _, ev -> gd.onTouchEvent(ev) }
    }

    private fun showTouch() {
        val b = touchBar ?: return
        touchName?.text = playing?.let { "${it.num}   ${it.name}" } ?: ""
        b.visibility = View.VISIBLE; b.bringToFront(); toastV.bringToFront()
        showBanner(); b.bringToFront()
        applyDim()
        stayTouch()
    }

    private fun stayTouch() { touchJob?.cancel(); touchJob = lifecycleScope.launch { delay(6000); hideTouch() } }
    private fun hideTouch() { touchJob?.cancel(); touchBar?.visibility = View.GONE }

    // ---------------- adapters ----------------

    inner class GroupAdapter : RecyclerView.Adapter<GroupAdapter.H>() {
        inner class H(v: View) : RecyclerView.ViewHolder(v) {
            val name: TextView = v.findViewById(R.id.name); val count: TextView = v.findViewById(R.id.count)
        }
        override fun getItemCount() = Api.groups.size
        override fun onCreateViewHolder(p: ViewGroup, t: Int) = H(LayoutInflater.from(p.context).inflate(R.layout.item_group, p, false))
        override fun onBindViewHolder(h: H, i: Int) {
            val g = Api.groups[i]
            h.name.text = g.name; h.count.text = if (g.id == Api.SEARCH) "" else g.channels.size.toString()
            h.itemView.isActivated = g.id == group?.id
            h.name.text = (if (Parental.isLocked(g.id, g.name)) "🔒 " else "") + g.name
            h.itemView.setOnClickListener {
                if (g.id == Api.SEARCH) { startActivity(Intent(this@LiveActivity, SearchActivity::class.java).putExtra("mode", "live")); return@setOnClickListener }
                if (g.channels.isEmpty()) return@setOnClickListener
                Parental.ask(this@LiveActivity) { groupsPanel.visibility = View.GONE; channelsRv.post { showGroup(g); groupAdapter.notifyDataSetChanged() } }
            }
            h.itemView.setOnKeyListener { _, k, e ->
                if (e.action != KeyEvent.ACTION_DOWN) return@setOnKeyListener false
                val p = h.bindingAdapterPosition
                when {
                    k == KeyEvent.KEYCODE_DPAD_RIGHT -> { closeGroups(); true }
                    // the end of the list goes round to the other end
                    k == KeyEvent.KEYCODE_DPAD_DOWN && p == itemCount - 1 -> { jumpTo(groupsRv, 0); true }
                    k == KeyEvent.KEYCODE_DPAD_UP && p == 0 -> { jumpTo(groupsRv, itemCount - 1); true }
                    else -> false
                }
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
            // the focused channel's whole name scrolls (a long name was cut with "…")
            h.itemView.setOnFocusChangeListener { v, f ->
                v.findViewById<TextView>(R.id.name)?.isSelected = f
                if (f) items.getOrNull(h.bindingAdapterPosition)?.let { onFocusChannel(it) }
            }
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
                if (e.action != KeyEvent.ACTION_DOWN) return@setOnKeyListener false
                val p = h.bindingAdapterPosition
                when {
                    k == KeyEvent.KEYCODE_DPAD_LEFT -> { openGroups(); true }
                    k == KeyEvent.KEYCODE_DPAD_DOWN && p == itemCount - 1 && itemCount > 1 -> { jumpTo(channelsRv, 0); true }
                    k == KeyEvent.KEYCODE_DPAD_UP && p == 0 && itemCount > 1 && e.repeatCount == 0 -> { jumpTo(channelsRv, itemCount - 1); true }
                    else -> false
                }
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
            h.title.text = Reminders.mark(currentChannelForPrograms(), p.start) + p.title
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
                val pos = h.bindingAdapterPosition
                planDialog(c, pr.start, pr.stop, pr.title) { notifyItemChanged(pos) }
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
