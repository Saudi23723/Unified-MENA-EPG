package com.saudi.privatevault

import android.annotation.SuppressLint
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONObject
import java.io.File
import kotlin.coroutines.resume

/**
 * NOTAMs with no key: the FAA NOTAM Search page is opened, unseen, in a
 * web view, and the search is asked from inside the page itself, the way
 * the page asks it when a pilot types an airport, so the FAA answers as it
 * answers its own site. The list is kept on the phone for reading offline.
 */
object NotamWeb {
    private const val PAGE = "https://notams.aim.faa.gov/notamSearch/nsapp.html#/"

    private class Bridge(val done: (String?) -> Unit) {
        @JavascriptInterface fun result(text: String?) = done(text)
    }

    /** Fetches and saves the NOTAMs of an airport; true when a list was saved. Call from the main thread. */
    @SuppressLint("SetJavaScriptEnabled")
    suspend fun fetch(ctx: Context, ident: String): Boolean {
        val text = withTimeoutOrNull(35000) {
            suspendCancellableCoroutine<String?> { cont ->
                val web = WebView(ctx.applicationContext)
                var finished = false
                fun finish(t: String?) {
                    if (finished) return
                    finished = true
                    Handler(Looper.getMainLooper()).post { web.destroy() }
                    if (cont.isActive) cont.resume(t)
                }
                web.settings.javaScriptEnabled = true
                web.settings.domStorageEnabled = true
                web.addJavascriptInterface(Bridge { finish(it) }, "SSEFB")
                web.webViewClient = object : WebViewClient() {
                    override fun onPageFinished(v: WebView, url: String) {
                        v.evaluateJavascript(
                            """
                            (function(){
                              var body='searchType=0&designatorsForLocation=$ident&designatorForAccountable=&latDegrees=&latMinutes=0&latSeconds=0&longDegrees=&longMinutes=0&longSeconds=0&radius=10&sortColumns=5+false&sortDirection=true&designatorForNotamNumberSearch=&notamNumber=&radiusSearchOnDesignator=false&radiusSearchDesignator=&latitudeDirection=N&longitudeDirection=W&freeFormText=&flightPathText=&flightPathDivertAirfields=&flightPathBuffer=4&flightPathIncludeNavaids=true&flightPathIncludeArtcc=false&flightPathIncludeTfr=true&flightPathIncludeRegulatory=false&flightPathResultsType=All+NOTAMs&archiveDate=&archiveDesignator=&offset=0&notamsOnly=false&filters=&minRunwayLength=&minRunwayWidth=&runwaySurfaceTypes=&predefinedAbbreviations=&flightPathAddlBuffer=&recaptchaToken=';
                              fetch('/notamSearch/search', {method:'POST', credentials:'include',
                                headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8','X-Requested-With':'XMLHttpRequest','Accept':'application/json, text/plain, */*'},
                                body: body})
                              .then(function(r){ return r.text(); })
                              .then(function(t){ SSEFB.result(t); })
                              .catch(function(e){ SSEFB.result(null); });
                            })();
                            """.trimIndent(), null)
                    }
                }
                cont.invokeOnCancellation { Handler(Looper.getMainLooper()).post { web.destroy() } }
                web.loadUrl(PAGE)
            }
        } ?: return false
        return try {
            val list = JSONObject(text).optJSONArray("notamList") ?: return false
            val file = File(ctx.filesDir, "aviation/notams/${ident.replace(Regex("[^A-Z0-9]"), "")}.json")
            file.parentFile?.mkdirs()
            file.writeText(JSONObject().put("notamList", list).toString())
            true
        } catch (e: Exception) {
            false
        }
    }
}
