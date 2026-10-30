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
    private val MODELS = listOf("gemini-flash-latest", "gemini-2.5-flash", "gemini-flash-lite-latest", "gemini-2.0-flash")

    // Least thinking first: the newest models take a level, 2.5 a budget, older ones neither.
    private val THINKING = listOf(
        JSONObject().put("thinkingLevel", "minimal"),
        JSONObject().put("thinkingBudget", 0),
        null,
    )

    private const val BASE = "You are a patient flight instructor helping a student pilot (PPL, Evektor SportStar MAX, " +
        "Boulder City KBVU) study aviation books. Be accurate, clear and concise, use short bullet points and bold " +
        "for key terms. If the page does not hold the answer, say so and answer from general aviation knowledge, clearly marked."

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
    fun chat(ctx: Context, turns: List<Turn>, onText: (String) -> Unit): LaptopClient.AiAnswer {
        val key = key(ctx)
        val body = contents(turns)
        val sys = JSONObject().put("parts", JSONArray().put(JSONObject().put("text", system(ctx))))
        val prefs = VaultLock.prefs(ctx)
        val combos = MODELS.flatMap { m -> THINKING.indices.map { m to it } }.toMutableList()
        prefs.getString("gemini_combo", null)?.split("|")?.let { s ->
            val c = s.getOrNull(0).orEmpty() to (s.getOrNull(1)?.toIntOrNull() ?: 0)
            if (combos.remove(c)) combos.add(0, c)
        }
        val errors = ArrayList<String>()
        val dead = HashSet<String>()
        for ((model, ti) in combos) {
            if (model in dead) continue
            val cfg = JSONObject().put("temperature", 0.4)
            THINKING[ti]?.let { cfg.put("thinkingConfig", it) }
            val req = JSONObject().put("systemInstruction", sys).put("contents", body).put("generationConfig", cfg)
            val c = URL(STREAM_FMT.format(model)).openConnection() as HttpURLConnection
            try {
                c.connectTimeout = 15000
                c.readTimeout = 60000
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
                        prefs.edit().putString("gemini_combo", "$model|$ti").apply()
                        return LaptopClient.AiAnswer(answer, "gemini", null)
                    }
                    errors.add("$model: empty answer")
                    continue
                }
                val msg = try { JSONObject(c.errorStream?.bufferedReader()?.readText() ?: "").optJSONObject("error")?.optString("message") ?: "" } catch (e: Exception) { "" }
                errors.add("$model: HTTP $code ${msg.take(160)}")
                // A wrong key or no quota left is the same for every model.
                if ((code == 400 && msg.contains("API key", true)) || code == 401 || code == 403 || code == 429)
                    return LaptopClient.AiAnswer(null, null, "failed", errors.joinToString("\n"))
                if (code == 404) dead.add(model)
            } catch (e: Exception) {
                errors.add("$model: ${e.message?.take(100)}")
                if (e is java.net.UnknownHostException) return LaptopClient.AiAnswer(null, null, "offline", errors.joinToString("\n"))
                dead.add(model)
            } finally {
                c.disconnect()
            }
        }
        return LaptopClient.AiAnswer(null, null, "failed", errors.takeLast(4).joinToString("\n"))
    }
}
