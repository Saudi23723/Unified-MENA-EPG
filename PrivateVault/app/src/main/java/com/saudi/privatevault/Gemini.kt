package com.saudi.privatevault

import android.content.Context
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * The phone talks to Gemini itself with the pilot's key: straight to Google,
 * streamed, no laptop or cloud in between. The model and settings that
 * answered last are remembered and asked first, so no time goes on retries.
 */
object Gemini {
    private const val STREAM_FMT = "https://generativelanguage.googleapis.com/v1beta/models/%s:streamGenerateContent?alt=sse"
    // 2.5 Flash first: with thinking off it answers quickest and is seldom busy; the newer Flash after it.
    private val MODELS = listOf("gemini-2.5-flash", "gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.0-flash")

    // Least thinking first: 2.5 takes a budget (0 = none), the newer models a level ("low"), older ones neither.
    private val THINKING = listOf(
        JSONObject().put("thinkingBudget", 0),
        JSONObject().put("thinkingLevel", "low"),
        null,
        // Deep thinking: as much as the model judges the question needs.
        JSONObject().put("thinkingBudget", -1),
    )

    private const val BASE = "You are a patient flight instructor helping a student pilot (PPL, Evektor SportStar MAX, " +
        "Boulder City KBVU) study aviation books. Be accurate, clear and concise, use short bullet points and bold " +
        "for key terms. Start with the answer itself: no greeting, no filler, no closing question. " +
        "If the page does not hold the answer, say so and answer from general aviation knowledge, clearly marked."

    fun system(ctx: Context) = BASE + if (english(ctx)) " Always answer in English."
        else " Answer in Arabic (Levantine-friendly Modern Standard Arabic), keeping technical terms in English in brackets, e.g. قوة الرفع (Lift)."

    fun english(ctx: Context) = VaultLock.prefs(ctx).getString("ai_lang", "ar") == "en"
    fun setEnglish(ctx: Context, on: Boolean) = VaultLock.prefs(ctx).edit().putString("ai_lang", if (on) "en" else "ar").apply()

    fun key(ctx: Context) = VaultLock.prefs(ctx).getString("gemini_key", "") ?: ""
    fun hasKey(ctx: Context) = key(ctx).isNotEmpty()
    fun setKey(ctx: Context, k: String) = VaultLock.prefs(ctx).edit().putString("gemini_key", k.trim()).remove("gemini_combo").apply()

    /** A turn of the conversation: who spoke, what, and (first turn) the page as a picture. */
    class Turn(val user: Boolean, var text: String, val image: ByteArray? = null)

    private fun contents(turns: List<Turn>): JSONArray {
        val a = JSONArray()
        for (t in turns) {
            val parts = JSONArray()
            t.image?.let { parts.put(JSONObject().put("inline_data", JSONObject().put("mime_type", "image/jpeg").put("data", Base64.encodeToString(it, Base64.NO_WRAP)))) }
            parts.put(JSONObject().put("text", t.text))
            a.put(JSONObject().put("role", if (t.user) "user" else "model").put("parts", parts))
        }
        return a
    }

    /** Streams the reply to the conversation; [onText] gets the text so far as it is written. */
    var lastModel = ""

    /** Opens the line to Google while the pilot reads the screen, so the first question does not wait for it. */
    fun warmUp() = Thread {
        try {
            val c = URL("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1").openConnection() as HttpURLConnection
            c.connectTimeout = 8000; c.readTimeout = 8000
            c.responseCode
            (c.errorStream ?: c.inputStream)?.use { it.readBytes() }
        } catch (e: Exception) {
        }
    }.start()

    /**
     * [deep]: for hard questions and calculations, the newest Flash with its full thinking first,
     * then 2.5 Flash thinking as much as it needs; slower by some seconds, more careful.
     */
    fun chat(ctx: Context, turns: List<Turn>, deep: Boolean = false, onStatus: (String) -> Unit = {}, system: String? = null, onText: (String) -> Unit): LaptopClient.AiAnswer {
        val key = key(ctx)
        val body = contents(turns)
        val sys = JSONObject().put("parts", JSONArray().put(JSONObject().put("text", system ?: system(ctx))))
        val prefs = VaultLock.prefs(ctx)
        val combos = if (deep) mutableListOf("gemini-flash-latest" to 2, "gemini-2.5-flash" to 3, "gemini-flash-lite-latest" to 2)
            else MODELS.flatMap { m -> (0..2).map { m to it } }.toMutableList()
        if (!deep) prefs.getString("gemini_combo", null)?.split("|")?.let { s ->
            val c = s.getOrNull(0).orEmpty() to (s.getOrNull(1)?.toIntOrNull() ?: 0)
            if (combos.remove(c)) combos.add(0, c)
        }
        val errors = ArrayList<String>()
        val dead = HashSet<String>()
        var retried = false
        for ((model, ti) in combos) {
            if (model in dead) continue
            onStatus(model)
            for (attempt in 0..1) {
            val cfg = JSONObject().put("temperature", 0.4)
            THINKING[ti]?.let { cfg.put("thinkingConfig", it) }
            val req = JSONObject().put("systemInstruction", sys).put("contents", body).put("generationConfig", cfg)
            val c = URL(STREAM_FMT.format(model)).openConnection() as HttpURLConnection
            try {
                c.connectTimeout = 10000
                // No word for 25 s is a stall (90 s when it thinks first): the next model is asked.
                c.readTimeout = if (deep) 90000 else 25000
                c.requestMethod = "POST"
                c.doOutput = true
                c.setRequestProperty("Content-Type", "application/json")
                c.setRequestProperty("x-goog-api-key", key)
                c.outputStream.use { it.write(req.toString().toByteArray()) }
                val code = c.responseCode
                if (code == 200) {
                    val sb = StringBuilder()
                    c.inputStream.bufferedReader().useLines { lines ->
                        for (line in lines) {
                            if (!line.startsWith("data:")) continue
                            val o = try { JSONObject(line.substring(5).trim()) } catch (e: Exception) { continue }
                            val parts = o.optJSONArray("candidates")?.optJSONObject(0)?.optJSONObject("content")?.optJSONArray("parts") ?: continue
                            for (i in 0 until parts.length()) {
                                val pt = parts.optJSONObject(i) ?: continue
                                if (!pt.optBoolean("thought")) sb.append(pt.optString("text"))
                            }
                            onText(sb.toString())
                        }
                    }
                    val answer = sb.toString().trim()
                    if (answer.isNotEmpty()) {
                        if (!deep) prefs.edit().putString("gemini_combo", "$model|$ti").apply()
                        lastModel = model
                        return LaptopClient.AiAnswer(answer, "gemini", null)
                    }
                    errors.add("$model: empty answer")
                    break
                }
                val msg = try { JSONObject(c.errorStream?.bufferedReader()?.readText() ?: "").optJSONObject("error")?.optString("message") ?: "" } catch (e: Exception) { "" }
                errors.add("$model: HTTP $code ${msg.take(160)}")
                // A wrong key or no quota left is the same for every model.
                if ((code == 400 && msg.contains("API key", true)) || code == 401 || code == 403 || (code == 429 && !deep))
                    return LaptopClient.AiAnswer(null, null, "failed", errors.joinToString("\n"))
                // Gone, or busy right now: straight to the next model.
                if (code == 404 || code >= 500 || code == 429) dead.add(model)
                onStatus("$model ✗ $code")
                break
            } catch (e: Exception) {
                // A blink of the phone's connection: once more after a moment.
                if (e is java.net.UnknownHostException || e is java.net.ConnectException) {
                    if (!retried) { retried = true; Thread.sleep(1500); continue }
                    errors.add("$model: ${e.message?.take(100)}")
                    return LaptopClient.AiAnswer(null, null, "nonet", errors.joinToString("\n"))
                }
                errors.add("$model: ${e.javaClass.simpleName} ${e.message?.take(100)}")
                onStatus("$model ✗ ${e.javaClass.simpleName}")
                dead.add(model)
                break
            } finally {
                c.disconnect()
            }
            }
        }
        return LaptopClient.AiAnswer(null, null, "failed", errors.takeLast(4).joinToString("\n"))
    }
}
