package com.saudi.privatevault

import org.json.JSONArray
import org.json.JSONObject

/**
 * What a page of a question bank is made of, read off the page itself.
 *
 * A question in a bank is never a block of prose: it is a question, a set of lettered choices, one
 * of them correct, the reason it is correct, and the place the reason comes from — the ACS code,
 * the advisory circular, the handbook. A paragraph of an electronic book is a different shape
 * again: a numbered heading and the text under it, often with a table or a figure beside it.
 *
 * So the text taken off the page is read into whichever of those shapes it is, and the book then
 * sets each one out in its own form. Nothing here is guessed: every field is either found on the
 * page or left out.
 */
object StudyParse {

    /** A question with its choices and its answer, or a passage of a book. */
    fun parse(raw: String): JSONObject {
        val text = raw.replace("\r", "").replace(" ", " ").trim()
        return question(text) ?: passage(text)
    }

    // ---- a question ----

    private val RE_Q = Regex("""Question:?\s*(\d+)?[ \t]*\n?\s*(.+?)(?=\n\s*[A-E][.)]\s)""", RegexOption.DOT_MATCHES_ALL)
    private val RE_CHOICE = Regex("""^[ \t]*([A-E])[.)]\s*(.+?)(?=\n[ \t]*[A-E][.)]\s|\n[ \t]*Answer\b|\z)""",
        setOf(RegexOption.MULTILINE, RegexOption.DOT_MATCHES_ALL))
    private val RE_ANS = Regex("""Answer\s*\(?([A-E])\)?\s*is\s*correct""", RegexOption.IGNORE_CASE)
    private val RE_ACS = Regex("""ACS Code:?\s*([A-Z]{2}\.[IVX]+\.[A-Z0-9.]+)""")
    private val RE_SRC = Regex("""Source:?\s*([^\n|]+)""")
    private val RE_UNIT = Regex("""Study Unit\s*(\d+)\s*:?\s*([^|\n]+)""")
    private val RE_SUB = Regex("""Subunit\s*(\d+)\s*:?\s*([^|\n]+)""")

    private fun question(text: String): JSONObject? {
        val q = RE_Q.find(text) ?: return null
        val body = text.substring(q.range.last + 1)
        val choices = JSONArray()
        for (m in RE_CHOICE.findAll(body)) {
            val letter = m.groupValues[1]
            val t = clean(m.groupValues[2])
            if (t.isNotEmpty()) choices.put(JSONObject().put("l", letter).put("t", t))
            if (choices.length() >= 5) break
        }
        if (choices.length() < 2) return null
        val ans = RE_ANS.find(body)?.groupValues?.get(1) ?: ""
        val why = ans.takeIf { it.isNotEmpty() }?.let {
            val i = RE_ANS.find(body)!!.range.last
            clean(body.substring(i + 1)
                .substringBefore("How Can We Help")
                .substringBefore("Contact Gleim")
                .replace(Regex("""^[^\n]*"""), "")   // the rest of the "is correct" line
                .trim())
        } ?: ""
        return JSONObject()
            .put("kind", "qa")
            .put("n", q.groupValues[1])
            .put("q", clean(q.groupValues[2]))
            .put("ch", choices)
            .put("ans", ans)
            .put("why", why)
            .put("acs", RE_ACS.find(text)?.groupValues?.get(1) ?: "")
            .put("src", RE_SRC.find(text)?.groupValues?.get(1)?.trim() ?: "")
            .put("unit", RE_UNIT.find(text)?.let { "Unit ${it.groupValues[1]} · ${it.groupValues[2].trim()}" } ?: "")
            .put("sub", RE_SUB.find(text)?.let { "Subunit ${it.groupValues[1]} · ${it.groupValues[2].trim()}" } ?: "")
    }

    // ---- a passage of a book ----

    private val RE_HEAD = Regex("""^\s*(\d+\.\d+)\s+([A-Z][A-Z0-9 ,.\-&/()]{3,})\s*$""", RegexOption.MULTILINE)

    /**
     * A passage: its numbered heading if it has one, and the text under it broken into the points
     * it is written in — a bank's prose is almost always numbered or lettered, and keeping that is
     * the difference between something readable and a wall.
     */
    private fun passage(text: String): JSONObject {
        val h = RE_HEAD.find(text)
        val head = h?.let { it.groupValues[1] + "  " + it.groupValues[2].trim() } ?: ""
        val body = if (h != null) text.substring(h.range.last + 1) else text
        val points = JSONArray()
        var cur = StringBuilder()
        for (line in body.lines()) {
            val l = line.trim()
            if (l.isEmpty()) continue
            if (l.contains("Contact Gleim") || l.startsWith("Copyright") || l.startsWith("Phone:") ||
                l.startsWith("Terms and Conditions")) break
            val starts = Regex("""^(\d+\.|[a-z]\.|[ivx]+\.|[-•])\s""").containsMatchIn(l)
            if (starts && cur.isNotEmpty()) { points.put(clean(cur.toString())); cur = StringBuilder() }
            if (cur.isNotEmpty()) cur.append(' ')
            cur.append(l)
        }
        if (cur.isNotEmpty()) points.put(clean(cur.toString()))
        return JSONObject()
            .put("kind", "note")
            .put("head", head)
            .put("pts", points)
            .put("q", head.ifEmpty { clean(body).take(90) })
    }

    private fun clean(s: String) = s.replace(Regex("""[ \t]+"""), " ")
        .replace(Regex("""\n{3,}"""), "\n\n").trim()

    /** A short line naming what was found, for the pilot to check before it is kept. */
    fun describe(o: JSONObject): String = when (o.optString("kind")) {
        "qa" -> {
            val n = o.optString("n").let { if (it.isEmpty()) "" else "Question $it · " }
            val a = o.optString("ans").let { if (it.isEmpty()) "no answer marked" else "answer $it" }
            val acs = o.optString("acs").let { if (it.isEmpty()) "" else " · $it" }
            "$n${o.optJSONArray("ch")?.length() ?: 0} choices · $a$acs"
        }
        else -> {
            val h = o.optString("head")
            (if (h.isEmpty()) "A passage" else h) + " · ${o.optJSONArray("pts")?.length() ?: 0} points"
        }
    }
}
