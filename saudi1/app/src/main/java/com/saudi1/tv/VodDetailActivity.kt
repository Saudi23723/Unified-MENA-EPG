package com.saudi1.tv

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Typeface
import android.os.Bundle
import android.text.TextUtils
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.HorizontalScrollView
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.lifecycle.lifecycleScope
import coil.load
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

/** A movie (plot, Play / Resume) or a series (seasons, episodes). */
@SuppressLint("SetTextI18n")
class VodDetailActivity : BaseActivity() {
    private val d by lazy { resources.displayMetrics.density }
    private lateinit var right: LinearLayout
    private lateinit var episodesBox: LinearLayout
    private lateinit var seasonsBox: LinearLayout
    private var seasons: Map<String, List<Episode>> = emptyMap()
    private var series = false
    private var id = 0
    private var name = ""
    private var poster = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        series = intent.getBooleanExtra("series", false)
        id = intent.getIntExtra("id", 0); name = intent.getStringExtra("name") ?: ""; poster = intent.getStringExtra("poster") ?: ""
        val root = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding((40 * d).toInt(), (34 * d).toInt(), (40 * d).toInt(), 0) }
        val img = ImageView(this).apply { scaleType = ImageView.ScaleType.CENTER_CROP }
        if (poster.isNotEmpty()) img.load(poster) { size(480, 720) }
        root.addView(img, LinearLayout.LayoutParams((240 * d).toInt(), (360 * d).toInt()))
        val scroll = ScrollView(this)
        right = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding((34 * d).toInt(), 0, 0, (60 * d).toInt()) }
        scroll.addView(right)
        root.addView(scroll, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f))
        setContentView(root)
        right.addView(TextView(this).apply { text = name; textSize = 30f; setTypeface(typeface, Typeface.BOLD) })
        lifecycleScope.launch {
            val info = withContext(Dispatchers.IO) { try { if (series) Vod.seriesInfo(id) else Vod.movieInfo(id) } catch (e: Exception) { null } }
            if (info == null) { line("Could not load the details. Press OK to try playing anyway.", 16f, R.color.text2); if (!series) buttons(null); return@launch }
            val i = info.optJSONObject("info") ?: JSONObject()
            val meta = listOf(i.optString("releasedate").ifEmpty { i.optString("releaseDate") }.take(4), i.optString("genre"),
                i.optString("duration"), i.optString("rating").takeIf { it.isNotEmpty() && it != "0" }?.let { "★ $it" } ?: "")
                .filter { it.isNotBlank() }.joinToString("   ·   ")
            if (meta.isNotEmpty()) line(meta, 16f, R.color.text2)
            val plot = i.optString("plot").ifEmpty { i.optString("description") }
            if (plot.isNotEmpty()) line(plot, 16f, R.color.text, 5)
            val cast = i.optString("cast").ifEmpty { i.optString("actors") }
            if (cast.isNotEmpty()) line("Cast: $cast", 14f, R.color.text2, 2)
            if (!series) buttons(info.optJSONObject("movie_data")) else seriesUi(info)
        }
    }

    private fun line(t: String, size: Float, color: Int, max: Int = 1) {
        right.addView(TextView(this).apply {
            text = t; textSize = size; setTextColor(getColor(color)); maxLines = max; ellipsize = TextUtils.TruncateAt.END
            setPadding(0, (10 * d).toInt(), 0, 0)
        })
    }

    private fun button(t: String, primary: Boolean, resume: Boolean = false, go: () -> Unit) = TextView(this).apply {
        text = t; textSize = 17f; gravity = Gravity.CENTER; isFocusable = true; isClickable = true
        setTypeface(typeface, Typeface.BOLD)
        setBackgroundResource(if (resume) R.drawable.resume_bg else if (primary) R.drawable.tile_bg else R.drawable.item_bg)
        setTextColor(getColorStateList(R.color.on_focus))
        setPadding((26 * d).toInt(), (12 * d).toInt(), (26 * d).toInt(), (12 * d).toInt())
        setOnClickListener { go() }
    }

    private fun buttons(data: JSONObject?) {
        val ext = data?.optString("container_extension")?.ifEmpty { null } ?: intent.getStringExtra("ext") ?: "mp4"
        val url = Vod.movieUrl(id, ext)
        val key = "m$id"
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, (24 * d).toInt(), 0, 0) }
        val pos = Resume.get(key)
        val play = button(if (pos > 0) "▶  Resume from " + hms(pos) else "▶  Play", true, resume = pos > 0) { watch(url, name, key, if (pos > 0) pos else 0) }
        row.addView(play)
        if (pos > 0) { row.addView(View(this), LinearLayout.LayoutParams((14 * d).toInt(), 1)); row.addView(button("⟲  From the start", false) { watch(url, name, key, 0) }) }
        row.addView(View(this), LinearLayout.LayoutParams((14 * d).toInt(), 1))
        lateinit var dl: TextView
        fun dlText() = Downloads.get(key)?.let { if (it.done) "✓  Downloaded" else "⬇  Downloading…" } ?: "⬇  Download"
        dl = button(dlText(), false) {
            val it = Downloads.get(key)
            if (it == null) { askNotify(); Downloads.add(this, key, name, poster, url); toastS("Downloading — watch it later without internet") }
            else androidx.appcompat.app.AlertDialog.Builder(this).setTitle(name).setItems(arrayOf("🗑  Delete the download")) { _, _ -> Downloads.remove(this, key); dl.text = dlText() }.show()
            dl.text = dlText()
        }
        row.addView(dl)
        right.addView(HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; addView(row) })
        play.requestFocus()
    }

    private fun seriesUi(info: JSONObject) {
        seasons = Vod.episodes(info)
        if (seasons.isEmpty()) { line("No episodes", 16f, R.color.text2); return }
        seasonsBox = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, (22 * d).toInt(), 0, (10 * d).toInt()) }
        val hs = HorizontalScrollView(this).apply { addView(seasonsBox) }
        right.addView(hs)
        episodesBox = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        var firstBtn: View? = null
        seasons.keys.forEach { s ->
            val b = button("Season $s", false) { showSeason(s) }
            seasonsBox.addView(b, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { marginEnd = (10 * d).toInt() })
            if (firstBtn == null) firstBtn = b
        }
        // the season of the episode watched last, else the first
        right.addView(button("⬇  Download this season", false) {
            val s = App.prefs.getString("last_season_$id", null) ?: seasons.keys.first()
            askNotify()
            seasons[s]?.forEach { e -> Downloads.add(this, "e${e.id}", "$name · S$s E${e.num}", poster, Vod.episodeUrl(e.id, e.ext)) }
            toastS("Season $s: downloading ${seasons[s]?.size ?: 0} episodes"); showSeason(s)
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = (10 * d).toInt() })
        val last = App.prefs.getString("last_season_$id", null)?.takeIf { it in seasons } ?: seasons.keys.first()
        right.addView(episodesBox)
        showSeason(last)
        firstBtn?.requestFocus()
    }

    private fun showSeason(s: String) {
        App.prefs.edit().putString("last_season_$id", s).apply()
        episodesBox.removeAllViews()
        var resumeRow: View? = null
        for (e in seasons[s] ?: emptyList()) {
            val key = "e${e.id}"
            val pos = Resume.get(key)
            val done = Resume.done(key)
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
                setBackgroundResource(if (pos > 0) R.drawable.resume_row_bg else R.drawable.item_bg); isFocusable = true; isClickable = true
                setPadding((16 * d).toInt(), (8 * d).toInt(), (16 * d).toInt(), (8 * d).toInt())
                setOnClickListener { watch(Vod.episodeUrl(e.id, e.ext), "$name · S$s E${e.num}", key, Resume.get(key), nextAfter(s, e)) }
                // hold OK / long press: download this episode (or delete the download)
                setOnLongClickListener {
                    if (Downloads.get(key) == null) { askNotify(); Downloads.add(this@VodDetailActivity, key, "$name · S$s E${e.num}", poster, Vod.episodeUrl(e.id, e.ext)); toastS("⬇ Downloading E${e.num}") }
                    else { Downloads.remove(this@VodDetailActivity, key); toastS("Download deleted") }
                    showSeason(s); true
                }
            }
            if (pos > 0 && resumeRow == null) resumeRow = row
            row.addView(TextView(this).apply { text = "E${e.num}"; textSize = 16f; setTypeface(typeface, Typeface.BOLD); setTextColor(getColorStateList(R.color.on_focus)); isDuplicateParentStateEnabled = true },
                LinearLayout.LayoutParams((70 * d).toInt(), ViewGroup.LayoutParams.WRAP_CONTENT))
            row.addView(TextView(this).apply {
                text = (if (done) "✓  " else "") + (Downloads.get(key)?.let { if (it.done) "⬇✓ " else "⬇… " } ?: "") + e.title + (if (pos > 0) "   ▶ Resume " + hms(pos) else "") + (if (e.duration.isNotEmpty()) "   ·   ${e.duration}" else "")
                textSize = 15f; maxLines = 2; ellipsize = TextUtils.TruncateAt.END; setTextColor(getColorStateList(R.color.on_focus)); isDuplicateParentStateEnabled = true
            }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            episodesBox.addView(row, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = (6 * d).toInt() })
        }
    }

    private fun toastS(t: String) = android.widget.Toast.makeText(this, t, android.widget.Toast.LENGTH_SHORT).show()

    private fun askNotify() {
        if (android.os.Build.VERSION.SDK_INT >= 33 && checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED)
            requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 3)
    }

    private fun watch(url0: String, title: String, key: String, from: Long, next: List<Triple<String, String, String>> = emptyList()) {
        // a downloaded copy plays from the device (no internet needed)
        val url = Downloads.localFile(key)?.let { android.net.Uri.fromFile(it).toString() } ?: url0
        startActivity(Intent(this, PlayerActivity::class.java).putExtra("url", url).putExtra("title", title)
            .putExtra("key", key).putExtra("poster", poster).putExtra("from", from)
            .putExtra("nextUrls", ArrayList(next.map { it.first })).putExtra("nextTitles", ArrayList(next.map { it.second }))
            .putExtra("nextKeys", ArrayList(next.map { it.third })))
    }

    /** the episodes after this one (rest of the season, then the next seasons): the player goes on by itself */
    private fun nextAfter(season: String, ep: Episode): List<Triple<String, String, String>> {
        val out = ArrayList<Triple<String, String, String>>()
        var on = false
        for ((s, list) in seasons) for (e in list) {
            if (on) out.add(Triple(Vod.episodeUrl(e.id, e.ext), "$name · S$s E${e.num}", "e${e.id}"))
            if (s == season && e.id == ep.id) on = true
            if (out.size >= 40) return out
        }
        return out
    }

    private fun hms(ms: Long): String { val t = ms / 1000; return if (t >= 3600) "%d:%02d:%02d".format(t / 3600, t / 60 % 60, t % 60) else "%d:%02d".format(t / 60, t % 60) }

    override fun onResume() {
        super.onResume()
        if (series && seasons.isNotEmpty()) App.prefs.getString("last_season_$id", null)?.let { showSeason(it) }
    }
}
