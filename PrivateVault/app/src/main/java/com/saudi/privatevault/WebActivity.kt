package com.saudi.privatevault

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.LinearLayout
import android.widget.ProgressBar

/** A page inside the app (the FAA's NOTAM Search), with an optional script to fill its form. */
class WebActivity : BaseActivity() {

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val col = EfbUi.screen(this, intent.getStringExtra("title") ?: "")
        (col.parent as? View)?.let { scroll ->
            // The page scrolls itself: take the scroll view's place.
            val root = scroll.parent as LinearLayout
            root.removeView(scroll)
            val bar = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply { max = 100 }
            root.addView(bar, LinearLayout.LayoutParams(-1, EfbUi.dp(this, 3)))
            val web = WebView(this)
            val frame = android.widget.FrameLayout(this)
            frame.addView(web, android.widget.FrameLayout.LayoutParams(-1, -1))
            root.addView(frame, LinearLayout.LayoutParams(-1, 0, 1f))
            val start = intent.getStringExtra("url")
            // The AWC's graphical forecasts open on where I am, and a 📍 button brings them back there.
            if (start != null && start.contains("aviationweather.gov/gfa")) {
                val pin = android.widget.TextView(this).apply {
                    text = "📍"; textSize = 22f; gravity = android.view.Gravity.CENTER
                    background = android.graphics.drawable.GradientDrawable().apply { shape = android.graphics.drawable.GradientDrawable.OVAL; setColor(0xFF2D8CFF.toInt()) }
                    elevation = EfbUi.dp(this@WebActivity, 6).toFloat()
                    contentDescription = "My position"
                    setOnClickListener { web.loadUrl(gfaHere()) }
                }
                val sz = EfbUi.dp(this, 54)
                frame.addView(pin, android.widget.FrameLayout.LayoutParams(sz, sz, android.view.Gravity.BOTTOM or android.view.Gravity.START).apply {
                    setMargins(EfbUi.dp(this@WebActivity, 16), 0, 0, EfbUi.dp(this@WebActivity, 120))
                })
            }
            web.settings.javaScriptEnabled = true
            web.settings.domStorageEnabled = true
            web.settings.builtInZoomControls = true
            web.settings.displayZoomControls = false
            val js = intent.getStringExtra("js")
            web.webChromeClient = object : WebChromeClient() {
                override fun onProgressChanged(v: WebView, p: Int) { bar.progress = p; bar.visibility = if (p >= 100) View.GONE else View.VISIBLE }
            }
            val csIdent = intent.getStringExtra("cs_ident")
            // A PDF tapped on the page is saved and read in the app, never handed to the browser.
            web.setDownloadListener { url, _, _, mime, _ -> if (url.endsWith(".pdf", true) || mime == "application/pdf") savePdf(url, csIdent) }
            web.webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(v: WebView, req: android.webkit.WebResourceRequest): Boolean {
                    val u = req.url.toString()
                    // AirNav sends its outgoing links through /depart?<url>.
                    val real = if (u.contains("/depart?")) u.substringAfter("/depart?") else u
                    if (real.substringBefore('?').endsWith(".pdf", true)) { savePdf(real, csIdent); return true }
                    return false
                }

                override fun onPageFinished(v: WebView, url: String) {
                    if (js != null) v.postDelayed({ v.evaluateJavascript(js, null) }, 1500)
                }
            }
            // A weather picture: full width on black, pinch to zoom, a loop keeps moving.
            val img = intent.getStringExtra("image")
            if (img != null) {
                web.settings.useWideViewPort = true
                web.settings.loadWithOverviewMode = true
                web.setBackgroundColor(0xFF000000.toInt())
                web.loadDataWithBaseURL(img, "<html><head><meta name='viewport' content='width=device-width, initial-scale=1, maximum-scale=8'></head>" +
                    "<body style='margin:0;background:#000;display:flex;align-items:center;justify-content:center;min-height:100vh'>" +
                    "<img src='" + img + "?t=" + System.currentTimeMillis() / 300000 + "' style='width:100%;height:auto' " +
                    "onerror=\"document.body.innerHTML='<p style=color:#aaa;font-family:sans-serif;padding:20px>Not available right now — try again in a minute.</p>'\"></body></html>",
                    "text/html", "utf-8", null)
            } else web.loadUrl(if (start != null && start.contains("aviationweather.gov/gfa")) gfaHere() else start ?: "about:blank")
        }
    }

    /** Where I am: the newest fix the phone has (GPS, network), else the home field. */
    private fun here(): Pair<Double, Double> {
        try {
            val m = getSystemService(android.location.LocationManager::class.java)
            val fix = listOf(android.location.LocationManager.GPS_PROVIDER, android.location.LocationManager.NETWORK_PROVIDER, android.location.LocationManager.PASSIVE_PROVIDER)
                .mapNotNull { p -> try { m.getLastKnownLocation(p) } catch (e: SecurityException) { null } }
                .maxByOrNull { it.time }
            if (fix != null) return fix.latitude to fix.longitude
        } catch (e: Exception) { }
        val home = VaultLock.prefs(this).getString("efb_home", "KBVU") ?: "KBVU"
        return try {
            AviationData.airports(this).firstOrNull { it.icao == home || it.ident == home || "K" + it.ident == home }?.let { it.lat to it.lon }
        } catch (e: Exception) { null } ?: (35.9475 to -114.8611)
    }

    /** The GFA centred on me, close enough to read the stations around (its own ?center=lat,lon&zoom= link). */
    private fun gfaHere(): String {
        val (lat, lon) = here()
        return "https://aviationweather.gov/gfa/?center=%.3f,%.3f&zoom=8".format(java.util.Locale.US, lat, lon)
    }

    private fun savePdf(url: String, csIdent: String?) {
        android.widget.Toast.makeText(this, R.string.cs_loading, android.widget.Toast.LENGTH_SHORT).show()
        Thread {
            val dir = java.io.File(filesDir, "supplement/web").apply { mkdirs() }
            val f = java.io.File(dir, url.substringAfterLast('/').substringBefore('?').ifEmpty { "page.pdf" })
            val ok = try {
                val c = java.net.URL(url).openConnection() as java.net.HttpURLConnection
                c.connectTimeout = 20000; c.readTimeout = 60000
                c.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36")
                try { if (c.responseCode == 200) { c.inputStream.use { i -> f.outputStream().use { o -> i.copyTo(o) } }; true } else false } finally { c.disconnect() }
            } catch (e: Exception) { false }
            runOnUiThread {
                if (!ok || f.length() == 0L) {
                    android.widget.Toast.makeText(this, R.string.apt_plates_fail, android.widget.Toast.LENGTH_LONG).show()
                    return@runOnUiThread
                }
                val item = if (csIdent != null) SupplementShelf.keep(this, csIdent, listOf(f)) else null
                if (item != null) SupplementShelf.open(this, item) else {
                    val v = VaultItem("web:" + f.name, f.name, f.absolutePath, "application/pdf", f.length(), f.lastModified(), null)
                    VaultStore.viewOnly(v)
                    startActivity(Intent(this, PdfViewerActivity::class.java).putExtra(Viewers.EXTRA_ID, v.id))
                }
            }
        }.start()
    }

    companion object {
        /** A page where a tapped Chart Supplement PDF is kept for [ident]. */
        fun supplement(act: Activity, ident: String, url: String) = act.startActivity(
            Intent(act, WebActivity::class.java).putExtra("title", "$ident · Chart Supplement").putExtra("url", url).putExtra("cs_ident", ident))

        fun open(act: Activity, title: String, url: String, js: String? = null) =
            act.startActivity(Intent(act, WebActivity::class.java).putExtra("title", title).putExtra("url", url).putExtra("js", js))

        /** The FAA NOTAM Search with the airport typed in and the search pressed, as far as the page allows. */
        fun faaNotams(act: Activity, ident: String) = open(act, "NOTAMs · $ident", "https://notams.aim.faa.gov/notamSearch/nsapp.html#/",
            """
            (function(){
              var id='$ident';
              var boxes=[].slice.call(document.querySelectorAll('input[type=text],input:not([type])'));
              var box=boxes.find(function(b){var s=((b.name||'')+(b.id||'')+(b.placeholder||'')+(b.getAttribute('ng-model')||'')).toLowerCase();return s.indexOf('location')>=0||s.indexOf('designator')>=0;})||boxes[0];
              if(!box) return;
              box.focus(); box.value=id;
              box.dispatchEvent(new Event('input',{bubbles:true})); box.dispatchEvent(new Event('change',{bubbles:true}));
              var btn=[].slice.call(document.querySelectorAll('button,input[type=submit],a')).find(function(b){return /^\s*search\s*$/i.test(b.innerText||b.value||'');});
              if(btn) btn.click();
            })();
            """.trimIndent())
    }
}
