package com.saudi1.tv

import android.os.Bundle
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.TrackSelectionOverride
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.util.Locale

/** Movies / episodes: ◀ ▶ = 10 s (hold = faster and faster), ⏪ ⏩ = 1 min, hold OK = options;
 *  the place is remembered, and a series goes on to the next episode by itself. */
class PlayerActivity : BaseActivity() {
    private lateinit var player: ExoPlayer
    private lateinit var view: PlayerView
    private lateinit var seekLabel: TextView
    private lateinit var topTitle: TextView
    private lateinit var topClock: TextView
    private var key = ""; private var title = ""; private var url = ""; private var poster = ""
    private val nextUrls = ArrayList<String>(); private val nextTitles = ArrayList<String>(); private val nextKeys = ArrayList<String>()
    private var pendingSeek: Long? = null
    private var seekJob: Job? = null
    private var nextBox: View? = null
    private var nextJob: Job? = null
    private val d by lazy { resources.displayMetrics.density }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Pip.closeOther(this)
        url = intent.getStringExtra("url") ?: run { finish(); return }
        title = intent.getStringExtra("title") ?: ""; key = intent.getStringExtra("key") ?: url; poster = intent.getStringExtra("poster") ?: ""
        intent.getStringArrayListExtra("nextUrls")?.let { nextUrls.addAll(it) }
        intent.getStringArrayListExtra("nextTitles")?.let { nextTitles.addAll(it) }
        intent.getStringArrayListExtra("nextKeys")?.let { nextKeys.addAll(it) }
        view = PlayerView(this)
        seekLabel = TextView(this).apply {
            textSize = 26f; setTypeface(typeface, android.graphics.Typeface.BOLD); setBackgroundResource(R.drawable.panel_bg)
            setPadding((26 * d).toInt(), (14 * d).toInt(), (26 * d).toInt(), (14 * d).toInt()); visibility = View.GONE
        }
        // the top of the bar, as in TiviMate: the title (the episode, or the movie) and the time now
        val topBar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; alpha = 0f
            background = android.graphics.drawable.GradientDrawable(android.graphics.drawable.GradientDrawable.Orientation.TOP_BOTTOM, intArrayOf(0xCC000000.toInt(), 0x00000000))
            setPadding((40 * d).toInt(), (22 * d).toInt(), (40 * d).toInt(), (46 * d).toInt())
        }
        topTitle = TextView(this).apply { textSize = 22f; setTextColor(0xFFFFFFFF.toInt()); typeface = android.graphics.Typeface.create("sans-serif-medium", android.graphics.Typeface.NORMAL); maxLines = 1; ellipsize = android.text.TextUtils.TruncateAt.END }
        topClock = TextView(this).apply { textSize = 22f; setTextColor(0xFFFFFFFF.toInt()); typeface = android.graphics.Typeface.create("sans-serif-medium", android.graphics.Typeface.NORMAL) }
        topBar.addView(topTitle, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        topBar.addView(topClock)
        setContentView(FrameLayout(this).apply {
            setBackgroundColor(0xFF000000.toInt()); addView(view)
            addView(topBar, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.TOP))
            addView(seekLabel, FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.CENTER))
        })
        view.setControllerVisibilityListener(androidx.media3.ui.PlayerView.ControllerVisibilityListener { v ->
            if (v == View.VISIBLE) {
                topTitle.text = title
                topClock.text = java.text.SimpleDateFormat(if (android.text.format.DateFormat.is24HourFormat(this)) "HH:mm" else "h:mm a", Locale.getDefault()).format(java.util.Date())
            }
            topBar.animate().alpha(if (v == View.VISIBLE) 1f else 0f).setDuration(180).start()
        })
        player = Players.make(this, live = false)
        view.player = player
        view.setShowNextButton(nextUrls.isNotEmpty()); view.setShowPreviousButton(false)
        // the remote: ◀ ▶ always move 10 s (faster when held), OK = pause / play — the bar shows by itself only then
        view.controllerAutoShow = false; view.useController = true; view.controllerShowTimeoutMs = 3500
        // the ⚙ on the player's bar opens this app's options (picture, audio, subtitles, speed...), not the small built-in menu
        view.findViewById<View>(androidx.media3.ui.R.id.exo_settings)?.setOnClickListener { options() }
        // the picture: TiviMate's display modes (owner, 15 Nov 2026), for this title or for all movies and shows
        applyMode()
        load(url, intent.getLongExtra("from", Resume.get(key)))
        player.addListener(object : Player.Listener {
            override fun onPlayerError(error: PlaybackException) {
                // the connection dropped (provider or internet): carry on from the same second by itself, up to 6 times,
                // instead of stopping the film (owner, 21 Nov 2026)
                val net = error.errorCode in 2000..2999
                if (net && reconnects < 6) {
                    reconnects++
                    val at = player.currentPosition
                    android.util.Log.w("SAUDI", "vod reconnect $reconnects at ${at / 1000}s: ${error.errorCodeName}")
                    lifecycleScope.launch { delay(1500L * reconnects); if (!isFinishing) { player.prepare(); if (at > 0) player.seekTo(at); player.playWhenReady = true } }
                    return
                }
                android.widget.Toast.makeText(this@PlayerActivity, "Could not play this (${error.errorCodeName})", android.widget.Toast.LENGTH_LONG).show()
            }
            override fun onIsPlayingChanged(isPlaying: Boolean) { if (isPlaying) reconnects = 0 }
            override fun onVideoSizeChanged(videoSize: androidx.media3.common.VideoSize) { applyMode() }
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_ENDED) { save(); if (nextUrls.isNotEmpty()) askNext() else finish() }
            }
        })
        lifecycleScope.launch { while (isActive) { tellNow(); delay(15_000); save() } }
        lifecycleScope.launch { while (isActive) { delay(500); skipTick() } }
    }

    private var reconnects = 0

    /** Hardware ↔ Software picture decoding, at once, from the same second (for a film the TV's chip shows badly) */
    private fun switchDecoder() {
        Players.softwareVideo = !Players.softwareVideo
        val at = player.currentPosition
        player.stop(); player.prepare(); if (at > 0) player.seekTo(at); player.playWhenReady = true
        android.widget.Toast.makeText(this, "Decoder: " + if (Players.softwareVideo) "Software" else "Hardware", android.widget.Toast.LENGTH_SHORT).show()
    }

    private fun load(u: String, from: Long) {
        player.setMediaItem(MediaItem.fromUri(u))
        if (from > 0) player.seekTo(from)
        player.prepare(); player.playWhenReady = true
    }

    private fun save() {
        if (player.duration > 0) {
            val n = org.json.JSONArray(); for (i in nextUrls.indices.take(60)) n.put(org.json.JSONArray().put(nextUrls[i]).put(nextTitles.getOrElse(i) { "" }).put(nextKeys.getOrElse(i) { "" }))
            Resume.set(key, player.currentPosition, player.duration, title, poster, url, if (nextUrls.isEmpty()) null else n, intent.getIntExtra("sid", 0))
        }
    }

    // ---------------- next episode ----------------

    private fun playNext() {
        learnCredits()
        closeNext()
        if (nextUrls.isEmpty()) { finish(); return }
        save()
        url = nextUrls.removeAt(0); title = nextTitles.removeAt(0); key = nextKeys.removeAt(0)
        view.setShowNextButton(nextUrls.isNotEmpty())
        load(url, Resume.get(key))
        creditsAsked = false; hideSkip()
        android.widget.Toast.makeText(this, title, android.widget.Toast.LENGTH_SHORT).show()
    }

    /** the episode ended: the next one starts in 10 s (Play now / Cancel) */
    private fun askNext() {
        closeNext()
        val count = TextView(this).apply { textSize = 16f; setTextColor(getColor(R.color.text2)) }
        fun btn(t: String, primary: Boolean, go: () -> Unit) = TextView(this).apply {
            text = t; textSize = 17f; gravity = Gravity.CENTER; isFocusable = true; isClickable = true
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setBackgroundResource(if (primary) R.drawable.tile_bg else R.drawable.item_bg); setTextColor(getColorStateList(R.color.on_focus))
            setPadding((22 * d).toInt(), (12 * d).toInt(), (22 * d).toInt(), (12 * d).toInt()); setOnClickListener { go() }
        }
        val playB = btn("▶  Play now", true) { playNext() }
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setBackgroundResource(R.drawable.panel_bg)
            setPadding((26 * d).toInt(), (22 * d).toInt(), (26 * d).toInt(), (22 * d).toInt())
            addView(TextView(this@PlayerActivity).apply { text = "Next episode"; textSize = 15f; setTextColor(getColor(R.color.accent)) })
            addView(TextView(this@PlayerActivity).apply { text = nextTitles[0]; textSize = 22f; setTypeface(typeface, android.graphics.Typeface.BOLD) })
            addView(count)
            addView(LinearLayout(this@PlayerActivity).apply {
                orientation = LinearLayout.HORIZONTAL; setPadding(0, (14 * d).toInt(), 0, 0)
                addView(playB); addView(View(this@PlayerActivity), LinearLayout.LayoutParams((14 * d).toInt(), 1))
                // at the credits (the episode still playing): Cancel = stay and watch them; at the end: close
                addView(btn("Cancel", false) { closeNext(); if (player.playbackState == Player.STATE_ENDED) finish() })
            })
        }
        val root = window.decorView as ViewGroup
        root.addView(panel, FrameLayout.LayoutParams((520 * d).toInt(), ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM or Gravity.END).apply {
            setMargins(0, 0, (48 * d).toInt(), (48 * d).toInt())
        })
        nextBox = panel
        applyDim()
        playB.requestFocus()
        nextJob = lifecycleScope.launch {
            for (left in 10 downTo 1) { count.text = "Starts in $left s"; delay(1000) }
            playNext()
        }
    }

    // ---------------- skip intro / credits (owner, 25 Nov 2026) ----------------
    // Learnt per series, from what the viewer does once: jumping forward in the first minutes of an episode marks the
    // intro (from where to where); going to the next episode before the end marks the credits (how long before the
    // end). The next episodes then show "Skip intro" at that moment, and the next episode is offered when the credits
    // begin. Shared with the customer's other devices (Backup: skip_*). Nothing learnt yet: nothing shown.
    private val sid get() = intent.getIntExtra("sid", 0)
    private var skipBtn: TextView? = null
    private var creditsAsked = false

    private fun marks(): org.json.JSONObject = try { org.json.JSONObject(App.prefs.getString("skip_$sid", "{}") ?: "{}") } catch (e: Exception) { org.json.JSONObject() }
    private fun saveMarks(o: org.json.JSONObject) { if (sid != 0) { App.prefs.edit().putString("skip_$sid", o.toString()).apply(); Backup.syncSoon() } }

    /** a jump forward of 20 s – 4 min that starts in the first 8 minutes = the intro, from where to where */
    private fun learnIntro(from: Long, to: Long) {
        if (sid == 0) return
        val jump = to - from
        if (from > 8 * 60_000L || jump < 20_000L || jump > 4 * 60_000L) return
        // pressing "Skip intro" itself teaches nothing new
        if (skipBtn != null) return
        saveMarks(marks().put("is", from).put("ie", to))
    }

    /** the next episode asked for before the end (from 15 s to 10 min before it) = the credits' length */
    private fun learnCredits() {
        val dur = player.duration; val pos = player.currentPosition
        if (sid == 0 || dur <= 0 || creditsAsked) return
        val left = dur - pos
        if (left in 15_000L..10 * 60_000L) saveMarks(marks().put("cr", left))
    }

    private fun skipTick() {
        if (sid == 0 || !::player.isInitialized) return
        val pos = player.currentPosition; val dur = player.duration
        val m = marks()
        val st = m.optLong("is", -1); val en = m.optLong("ie", -1)
        // the intro: the button from 3 s before it starts until 3 s before it ends
        if (st >= 0 && en > st && pos in (st - 3000).coerceAtLeast(0)..(en - 3000)) showSkip(en) else hideSkip()
        // the credits: the next episode is offered when they begin
        val cr = m.optLong("cr", -1)
        if (cr > 0 && dur > 0 && !creditsAsked && nextUrls.isNotEmpty() && nextBox == null && player.isPlaying && pos >= dur - cr) {
            creditsAsked = true; save(); askNext()
        }
    }

    private fun showSkip(to: Long) {
        if (skipBtn != null || nextBox != null || menus.isNotEmpty()) return
        val b = TextView(this).apply {
            text = "⏭  Skip intro"; textSize = 18f; isFocusable = true; isClickable = true; gravity = Gravity.CENTER
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setBackgroundResource(R.drawable.tile_bg); setTextColor(getColorStateList(R.color.on_focus))
            setPadding((26 * d).toInt(), (14 * d).toInt(), (26 * d).toInt(), (14 * d).toInt())
            setOnClickListener { player.seekTo(to); hideSkip() }
        }
        (window.decorView as ViewGroup).addView(b, FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM or Gravity.END).apply {
            setMargins(0, 0, (48 * d).toInt(), (110 * d).toInt())
        })
        skipBtn = b
        b.requestFocus()
    }

    private fun hideSkip() { skipBtn?.let { (window.decorView as ViewGroup).removeView(it) }; skipBtn = null }

    private fun closeNext() {
        nextJob?.cancel(); nextBox?.let { (window.decorView as ViewGroup).removeView(it) }; nextBox = null
    }

    // ---------------- keys ----------------

    /** ◀ ▶ held: 10 s, then 30 s, 1 min, 2 min, 5 min steps; the picture jumps when the key is let go */
    private fun seekStep(repeat: Int) = when {
        repeat < 4 -> 10_000L; repeat < 12 -> 30_000L; repeat < 24 -> 60_000L; repeat < 40 -> 120_000L; else -> 300_000L
    }

    private fun fmt(ms: Long): String { val t = ms / 1000; return if (t >= 3600) "%d:%02d:%02d".format(t / 3600, t / 60 % 60, t % 60) else "%d:%02d".format(t / 60, t % 60) }

    private fun showSeek(target: Long) {
        val diff = target - player.currentPosition
        seekLabel.text = (if (diff >= 0) "⏩  +" else "⏪  −") + fmt(kotlin.math.abs(diff)) + "     " + fmt(target) +
            (if (player.duration > 0) "  /  " + fmt(player.duration) else "")
        seekLabel.visibility = View.VISIBLE; seekLabel.bringToFront(); view.showController()
        seekJob?.cancel()
    }

    private fun commitSeek() {
        val t = pendingSeek ?: return
        pendingSeek = null
        learnIntro(player.currentPosition, t)
        player.seekTo(t)
        seekJob?.cancel(); seekJob = lifecycleScope.launch { delay(900); seekLabel.visibility = View.GONE }
    }

    override fun dispatchKeyEvent(e: KeyEvent): Boolean {
        // the menus (bottom bar, side panels): Back closes the top one, the other keys move in them
        if (menus.isNotEmpty()) {
            if (e.keyCode == KeyEvent.KEYCODE_BACK) { if (e.action == KeyEvent.ACTION_UP) popMenu(); return true }
            return super.dispatchKeyEvent(e)
        }
        // Back with the bar (seek bar, buttons) showing: only the bar goes, the picture stays (owner, 17 Nov 2026)
        if (e.keyCode == KeyEvent.KEYCODE_BACK && nextBox == null && !overlayOpen && view.isControllerFullyVisible) {
            if (e.action == KeyEvent.ACTION_UP) view.hideController(); return true
        }
        if (nextBox != null && e.keyCode == KeyEvent.KEYCODE_BACK) { if (e.action == KeyEvent.ACTION_UP) { closeNext(); if (player.playbackState == Player.STATE_ENDED) finish() }; return true }
        // "Skip intro" on screen: OK presses it (the other keys work as always)
        skipBtn?.let { sb -> if (!overlayOpen && nextBox == null && (e.keyCode == KeyEvent.KEYCODE_DPAD_CENTER || e.keyCode == KeyEvent.KEYCODE_ENTER)) {
            if (e.action == KeyEvent.ACTION_UP) sb.performClick(); return true } }
        if (!overlayOpen && nextBox == null) {
            val down = e.action == KeyEvent.ACTION_DOWN
            when (e.keyCode) {
                KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT -> {
                    if (down) {
                        val dir = if (e.keyCode == KeyEvent.KEYCODE_DPAD_RIGHT) 1 else -1
                        val base = pendingSeek ?: player.currentPosition
                        val max = if (player.duration > 0) player.duration - 1000 else Long.MAX_VALUE
                        pendingSeek = (base + dir * seekStep(e.repeatCount)).coerceIn(0, max)
                        showSeek(pendingSeek!!)
                    } else commitSeek()
                    return true
                }
                KeyEvent.KEYCODE_MEDIA_FAST_FORWARD -> { if (down) { player.seekTo(player.currentPosition + 60_000); view.showController() }; return true }
                KeyEvent.KEYCODE_MEDIA_REWIND -> { if (down) { player.seekTo((player.currentPosition - 60_000).coerceAtLeast(0)); view.showController() }; return true }
                KeyEvent.KEYCODE_MEDIA_NEXT -> { if (down && nextUrls.isNotEmpty()) playNext(); return true }
                KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE -> {
                    // short press: the first shows the bar (where it is, the time, the title) and keeps playing;
                    // with the bar up it pauses / plays (owner, 17 Nov 2026) · hold: options
                    if (down && e.repeatCount == 1) options()
                    else if (!down && !e.isCanceled && e.eventTime - e.downTime < 500) {
                        if (e.keyCode != KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE && !view.isControllerFullyVisible && player.isPlaying) view.showController()
                        else { if (player.isPlaying) player.pause() else player.play(); view.showController() }
                    }
                    return true
                }
                // ▲ / ▼ show the bar; ▼ again while the bar is up opens the options (remotes with no MENU key, owner 11 Nov 2026)
                KeyEvent.KEYCODE_DPAD_UP -> { if (down) view.showController(); return true }
                KeyEvent.KEYCODE_DPAD_DOWN -> { if (down && e.repeatCount == 0) { if (view.isControllerFullyVisible) options() else view.showController() }; return true }
                KeyEvent.KEYCODE_MENU, KeyEvent.KEYCODE_SETTINGS, KeyEvent.KEYCODE_INFO -> { if (down) options(); return true }
            }
        }
        return super.dispatchKeyEvent(e)
    }

    // ---- display mode, as in TiviMate: Normal, Full, Zoom, Zoom 2.35:1, Reduced, 4:3, 16:9, 2.35:1 ----
    private val MODES = TvUi.MODES
    /** the title's own choice, else the one for all movies and shows (the old "Picture" choice carried over) */
    private fun mode(): Int {
        val own = App.prefs.getInt("dm_$key", -1)
        if (own in MODES.indices) return own
        val all = App.prefs.getInt("dm_all", -1)
        if (all in MODES.indices) return all
        return when (App.prefs.getInt("vod_resize", App.prefs.getInt("resize", 0))) { 3 -> 1; 4 -> 2; else -> 0 }
    }

    private fun applyMode() = TvUi.applyMode(view, player.videoSize, mode())

    private fun displayModes() {
        val all = App.prefs.getInt("dm_$key", -1) !in MODES.indices
        pushMenu(TvUi.side(this, "Display mode", MODES.toList(), mode(), { k ->
            if (all) App.prefs.edit().putInt("dm_all", k).apply() else App.prefs.edit().putInt("dm_$key", k).apply()
            applyMode(); closeMenus()
        }, "Apply to all movies and shows", all, {
            // the switch: this title keeps its own mode, or follows the one for all
            val e = App.prefs.edit()
            if (all) e.putInt("dm_$key", mode()) else { e.putInt("dm_all", mode()); e.remove("dm_$key") }
            e.apply(); popMenu(); displayModes()
        }))
    }

    // ---- the menus, TiviMate's way: a bar of icons at the bottom, the choices in a panel on the right ----
    private val menus = ArrayList<View>()
    private fun pushMenu(v: View) {
        view.hideController()
        (window.decorView as ViewGroup).addView(v, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        menus.add(v); applyDim()
    }
    private fun popMenu() {
        val v = menus.removeLastOrNull() ?: return
        (window.decorView as ViewGroup).removeView(v)
        // back on the bar: the focus returns to it
        menus.lastOrNull()?.let { it.post { it.findFocus() ?: it.requestFocus(View.FOCUS_DOWN) } }
    }
    private fun closeMenus() { while (menus.isNotEmpty()) popMenu() }

    private fun options() {
        if (menus.isNotEmpty()) return
        val speeds = floatArrayOf(0.5f, 0.75f, 1f, 1.25f, 1.5f, 2f)
        val sp = player.playbackParameters.speed
        val tiles = ArrayList<TvUi.Tile>()
        tiles += TvUi.Tile("▭", "Display", MODES[mode()]) { displayModes() }
        tiles += TvUi.Tile("♫", "Audio", trackNow(C.TRACK_TYPE_AUDIO)) { tracks(C.TRACK_TYPE_AUDIO) }
        tiles += TvUi.Tile("CC", "Subtitles", trackNow(C.TRACK_TYPE_TEXT)) { tracks(C.TRACK_TYPE_TEXT) }
        if (Pip.can(this)) tiles += TvUi.Tile("⧉", "Small window", "") { closeMenus(); Pip.enter(this) }
        tiles += TvUi.Tile("»", "Speed", if (sp == 1f) "Normal" else "${sp}x") {
            pushMenu(TvUi.side(this, "Speed", speeds.map { if (it == 1f) "Normal" else "${it}x" }, speeds.indexOfFirst { it == sp }.coerceAtLeast(0), { k ->
                player.setPlaybackSpeed(speeds[k]); closeMenus() }))
        }
        if (nextUrls.isNotEmpty()) tiles += TvUi.Tile("⇥", "Next episode", "") { closeMenus(); playNext() }
        tiles += TvUi.Tile("↺", "From start", "") { closeMenus(); player.seekTo(0); player.play() }
        tiles += TvUi.Tile("◷", "Sleep timer", if (sleepAt > 0) "${((sleepAt - System.currentTimeMillis()) / 60000 + 1)} min" else "Off") {
            val mins = intArrayOf(0, 15, 30, 45, 60, 90, 120)
            val now = if (sleepAt > 0) -1 else 0
            pushMenu(TvUi.side(this, "Stop playing after", mins.map { if (it == 0) "Off" else "$it minutes" }, now, { k ->
                sleepJob?.cancel(); sleepAt = 0
                if (mins[k] > 0) {
                    sleepAt = System.currentTimeMillis() + mins[k] * 60_000L
                    sleepJob = lifecycleScope.launch { delay(mins[k] * 60_000L); save(); finish() }
                }
                closeMenus()
            }))
        }
        tiles += TvUi.Tile("⚙", "Decoder", if (Players.softwareVideo) "Software" else "Hardware") {
            closeMenus(); switchDecoder() }
        tiles += TvUi.Tile("☾", "Night mode", if (Dim.level > 0 || Dim.warm > 0) "On" else "Off") { closeMenus(); nightDialog() }
        tiles += TvUi.Tile("i", "Info", "") {
            val v = player.videoFormat; val a = player.audioFormat
            val lines = listOfNotNull(
                v?.let { "Picture: ${it.width}×${it.height}" + (if (it.frameRate > 0) "  ·  ${it.frameRate.toInt()} fps" else "") + "  ·  " + codec(it.sampleMimeType) },
                a?.let { "Sound: " + codec(it.sampleMimeType) + (if (it.channelCount > 0) "  ·  ${it.channelCount} ch" else "") + (it.language?.let { l -> "  ·  " + Locale(l).displayLanguage } ?: "") },
                if (player.duration > 0) "Length: ${player.duration / 60000} min" else null).ifEmpty { listOf("No details yet") }
            pushMenu(TvUi.side(this, title, listOf("Close"), -1, { closeMenus() }, lines = lines))
        }
        pushMenu(TvUi.bar(this, title, tiles))
    }

    /** what is chosen now, for the bar */
    private fun trackNow(type: Int): String {
        val g = player.currentTracks.groups.firstOrNull { it.type == type && it.isSelected } ?: return if (type == C.TRACK_TYPE_TEXT) "Off" else ""
        val f = (0 until g.length).firstOrNull { g.isTrackSelected(it) }?.let { g.getTrackFormat(it) } ?: return ""
        return listOfNotNull(f.language?.takeIf { it != "und" && it.isNotBlank() }?.let { Locale(it).displayLanguage }, if (f.channelCount > 2) "${f.channelCount}ch" else null).joinToString(" ").ifEmpty { f.label ?: if (type == C.TRACK_TYPE_AUDIO) "Default" else "On" }
    }

    private var sleepAt = 0L
    private var sleepJob: Job? = null
    private fun codec(m: String?) = when {
        m == null -> "?"; m.contains("hevc") -> "HEVC"; m.contains("avc") -> "H.264"; m.contains("av01") -> "AV1"; m.contains("vp9") -> "VP9"
        m.contains("eac3") -> "Dolby Digital+"; m.contains("ac3") -> "Dolby Digital"; m.contains("mp4a") || m.contains("aac") -> "AAC"
        m.contains("dts") -> "DTS"; m.contains("mpeg") -> "MPEG"; else -> m.substringAfter('/')
    }

    private fun tracks(type: Int) {
        val groups = player.currentTracks.groups.filter { it.type == type }
        val names = ArrayList<String>(); val picks = ArrayList<Pair<Int, Int>>()
        if (type == C.TRACK_TYPE_TEXT) { names.add("Off"); picks.add(-1 to -1) }
        groups.forEachIndexed { gi, g ->
            for (t in 0 until g.length) {
                if (!g.isTrackSupported(t)) continue
                val f = g.getTrackFormat(t)
                names.add(listOfNotNull(f.language?.let { Locale(it).displayLanguage }, f.label, if (f.channelCount > 0) "${f.channelCount}ch" else null)
                    .distinct().joinToString(" · ").ifEmpty { "Track ${names.size + 1}" })
                picks.add(gi to t)
            }
        }
        if (names.size < 2 && type == C.TRACK_TYPE_AUDIO || names.isEmpty()) {
            android.widget.Toast.makeText(this, if (type == C.TRACK_TYPE_AUDIO) "One audio only" else "No subtitles", android.widget.Toast.LENGTH_SHORT).show(); return
        }
        val now = picks.indexOfFirst { (gi, t) -> if (gi < 0) player.currentTracks.groups.none { it.type == type && it.isSelected } else groups[gi].isTrackSelected(t) }
        pushMenu(TvUi.side(this, if (type == C.TRACK_TYPE_AUDIO) "Audio" else "Subtitles", names, now, { w ->
            val (gi, t) = picks[w]
            val b = player.trackSelectionParameters.buildUpon()
            if (gi < 0) b.setTrackTypeDisabled(C.TRACK_TYPE_TEXT, true)
            else b.setTrackTypeDisabled(type, false).setOverrideForType(TrackSelectionOverride(groups[gi].mediaTrackGroup, t))
            player.trackSelectionParameters = b.build()
            closeMenus()
        }))
    }

    // the small window (phones and tablets) opens from the options only (Pip.kt); closed with its ✕: this screen ends
    override fun onPictureInPictureModeChanged(pip: Boolean, cfg: android.content.res.Configuration) {
        super.onPictureInPictureModeChanged(pip, cfg)
        view.useController = !pip
        if (pip) view.hideController()
        else { Pip.left(this); if (!lifecycle.currentState.isAtLeast(androidx.lifecycle.Lifecycle.State.STARTED)) { save(); finish() } }
    }
    private val inPip get() = android.os.Build.VERSION.SDK_INT >= 24 && isInPictureInPictureMode
    override fun onPause() { super.onPause(); save(); if (!inPip) player.pause() }
    // the small window closed: stopped (while it is open the screen is only paused, not stopped)
    override fun onStop() { super.onStop(); player.pause() }

    /** the admin site shows what is playing (only while it plays) */
    private fun tellNow() {
        if (!player.isPlaying && player.playbackState != androidx.media3.common.Player.STATE_BUFFERING) return
        Device.now(when { key.startsWith("e") -> "series"; key.startsWith("m") -> "movie"; key.startsWith("r") -> "recording"; else -> "video" }, title)
    }
    override fun onDestroy() { super.onDestroy(); player.release() }
}
