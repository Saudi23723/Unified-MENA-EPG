package com.saudi.privatevault

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * The phone asks Gemini itself with the pilot's key: straight to Google, no
 * laptop or cloud in between. The key stays on the phone.
 */
object Gemini {
    private const val STREAM_FMT = "https://generativelanguage.googleapis.com/v1beta/models/%s:streamGenerateContent?alt=sse"
    private val MODELS = listOf("gemini-flash-latest", "gemini-2.5-flash", "gemini-flash-lite-latest", "gemini-2.0-flash")

    private const val SYSTEM = "You are a patient study assistant for a student pilot reading aviation books. " +
        "Answer in Arabic (Levantine-friendly Modern Standard Arabic), keeping technical terms in English " +
        "in brackets, e.g. قوة الرفع (Lift). Be accurate and concise, use short bullet points, and if the text " +
        "does not contain the answer, say so and answer from general aviation knowledge, clearly marked."

    fun key(ctx: Context) = VaultLock.prefs(ctx).getString("gemini_key", "") ?: ""
    fun hasKey(ctx: Context) = key(ctx).isNotEmpty()
    fun setKey(ctx: Context, k: String) = VaultLock.prefs(ctx).edit().putString("gemini_key", k.trim()).apply()

    private fun prompt(mode: String, text: String, question: String) = when (mode) {
        "summary" -> "لخّص النص التالي بنقاط قصيرة وواضحة، مع أهم الأفكار والأرقام والتعريفات:\n\n$text"
        "explain" -> "اشرح النص التالي بطريقة بسيطة كأنك تشرح لطالب، مع مثال إن أمكن:\n\n$text"
        else -> (if (text.isNotBlank()) "النص من الكتاب:\n\n$text\n\n" else "") + "سؤال الطالب: $question"
    }

    /**
     * Streams the answer: [onText] gets the text so far as Gemini writes it,
     * so the first words show within a second or two.
     */
    fun ask(ctx: Context, mode: String, text: String, question: String, onText: (String) -> Unit = {}): LaptopClient.AiAnswer {
        val key = key(ctx)
        val body = prompt(mode, text.take(30000), question)
        val errors = ArrayList<String>()
        for (model in MODELS) {
            // Without the long "thinking" first where the model allows it.
            for (fast in listOf(true, false)) {
                val cfg = JSONObject().put("temperature", 0.3)
                if (fast) cfg.put("thinkingConfig", JSONObject().put("thinkingBudget", 0))
                val req = JSONObject()
                    .put("systemInstruction", JSONObject().put("parts", JSONArray().put(JSONObject().put("text", SYSTEM))))
                    .put("contents", JSONArray().put(JSONObject().put("role", "user").put("parts", JSONArray().put(JSONObject().put("text", body)))))
                    .put("generationConfig", cfg)
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
                                    if (pt.optBoolean("thought")) continue
                                    sb.append(pt.optString("text"))
                                }
                                onText(sb.toString())
                            }
                        }
                        val answer = sb.toString().trim()
                        if (answer.isNotEmpty()) return LaptopClient.AiAnswer(answer, "gemini", null)
                        errors.add("$model: empty answer")
                        break
                    }
                    val msg = try { JSONObject(c.errorStream?.bufferedReader()?.readText() ?: "").optJSONObject("error")?.optString("message") ?: "" } catch (e: Exception) { "" }
                    errors.add("$model: HTTP $code ${msg.take(160)}")
                    // A wrong key or no quota left is the same for every model.
                    if ((code == 400 && msg.contains("API key", true)) || code == 401 || code == 403 || code == 429)
                        return LaptopClient.AiAnswer(null, null, "failed", errors.joinToString("\n"))
                    if (code == 404) break
                } catch (e: Exception) {
                    errors.add("$model: ${e.message?.take(100)}")
                    if (e is java.net.UnknownHostException) return LaptopClient.AiAnswer(null, null, "offline", errors.joinToString("\n"))
                    break
                } finally {
                    c.disconnect()
                }
            }
        }
        return LaptopClient.AiAnswer(null, null, "failed", errors.takeLast(4).joinToString("\n"))
    }
}
