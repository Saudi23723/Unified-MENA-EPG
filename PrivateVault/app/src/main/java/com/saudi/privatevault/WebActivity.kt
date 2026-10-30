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
            root.addView(web, LinearLayout.LayoutParams(-1, 0, 1f))
            web.settings.javaScriptEnabled = true
            web.settings.domStorageEnabled = true
            web.settings.builtInZoomControls = true
            web.settings.displayZoomControls = false
            val js = intent.getStringExtra("js")
            web.webChromeClient = object : WebChromeClient() {
                override fun onProgressChanged(v: WebView, p: Int) { bar.progress = p; bar.visibility = if (p >= 100) View.GONE else View.VISIBLE }
            }
            web.webViewClient = object : WebViewClient() {
                override fun onPageFinished(v: WebView, url: String) {
                    if (js != null) v.postDelayed({ v.evaluateJavascript(js, null) }, 1500)
                }
            }
            web.loadUrl(intent.getStringExtra("url") ?: "about:blank")
        }
    }

    companion object {
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
