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

    /**
     * A question with its choices and its answer, or a passage of a book.
     *
     * Which of the two it is comes from the page itself where the page can say — a question is sat
     * in a session, with its Mark For Review and its timer; a lesson is a numbered section of the
     * book. Reading the shape out of the words is the fallback, not the first resort, because a
     * page whose question did not parse used to be filed as a lesson and come out as nonsense.
     */
    fun parse(raw: String, hint: String = ""): JSONObject {
        val text = strip(raw.replace("\r", "").replace(" ", " ")).trim()
        if (hint == "note") return passage(text)
        val q = question(text) ?: looseQuestion(text)
        if (q != null) return q
        return passage(text).also { if (hint == "qa") it.put("kind", "qa").put("partial", true) }
    }

    /**
     * A question whose wording the strict reading missed. Where a page has lettered choices and a
     * verdict on one of them, it is a question whatever else it says — what comes before the first
     * choice is the question, and the rest is read as usual.
     */
    private fun looseQuestion(text: String): JSONObject? {
        val first = Regex("""^[ \t]*([A-E])[.)]\s""", setOf(RegexOption.MULTILINE)).find(text) ?: return null
        val body = text.substring(first.range.first)
        val choices = JSONArray()
        for (m in RE_CHOICE.findAll(body)) {
            val t = clean(m.groupValues[2])
            if (t.isNotEmpty()) choices.put(JSONObject().put("l", m.groupValues[1]).put("t", t))
            if (choices.length() >= 5) break
        }
        if (choices.length() < 2) return null
        if (!RE_ANS.containsMatchIn(body) && !RE_VERDICT.containsMatchIn(body)) return null
        val head = clean(text.substring(0, first.range.first))
            .lines().filter { it.isNotBlank() }.takeLast(3).joinToString(" ")
        val o = JSONObject()
            .put("kind", "qa")
            .put("n", "")
            .put("q", head.ifEmpty { "(question)" })
            .put("ch", choices)
            .put("acs", RE_ACS.find(text)?.groupValues?.get(1) ?: "")
            .put("src", RE_SRC.find(text)?.groupValues?.get(1)?.trim() ?: "")
            .put("unit", RE_UNIT.find(text)?.let { "Unit ${it.groupValues[1]} · ${it.groupValues[2].trim()}" } ?: "")
            .put("sub", RE_SUB.find(text)?.let { "Subunit ${it.groupValues[1]} · ${it.groupValues[2].trim()}" } ?: "")
        verdicts(body, choices, o)
        return o
    }

    /**
     * The bank's own furniture, taken out before anything is read: the index of every question in
     * the bank, the sitting instructions printed on every page, and the rest of the scaffolding
     * that is not the lesson in front of the pilot.
     */
    private val JUNK_LINE = Regex(
        """^(?:Question\s*\d+\s*\(\d+[.\d]*\)|Source\s+[\d ]+|Skip to Main Content|Spacer|Directions\b.*|.*Submit Testlet.*|.*Responding to Multiple-Choice.*|.*The Toolbar.*|.*Reminder flags.*|.*software malfunction.*)$""",
        RegexOption.IGNORE_CASE)
    private val INDEX_RUN = Regex("""Question\s*\d+\s*\(\d""")

    private fun strip(t: String): String = t.lines().filter { line ->
        val l = line.trim()
        when {
            l.isEmpty() -> false
            JUNK_LINE.matches(l) -> false
            // The index runs the whole bank together on one line; it is unmistakable by shape.
            INDEX_RUN.findAll(l).count() > 2 -> false
            else -> true
        }
    }.joinToString("\n")

    // ---- a question ----

    // "Question Properties" is a button on the bank's own toolbar, not a question. A question is
    // written "Question: 5" or "Question 5", so the colon or the number is required.
    private val RE_Q = Regex("""\bQuestion\b(?::\s*(\d+)?|\s+(\d+))[ \t]*\n?\s*(.+?)(?=\n\s*[A-E][.)]\s)""",
        RegexOption.DOT_MATCHES_ALL)
    /** Where a choice or an explanation ends: the next choice, the next verdict, or the page's furniture. */
    private const val STOP =
        """(?=\n[ \t]*[A-E][.)]\s|\n[ \t]*Answer\s*\(?[A-E]\)?\s*is\b|How Can We Help|Contact Gleim|Mark For Review|Questions:|Opens in a new window|\z)"""

    private val RE_CHOICE = Regex("""^[ \t]*([A-E])[.)]\s*(.+?)$STOP""",
        setOf(RegexOption.MULTILINE, RegexOption.DOT_MATCHES_ALL))
    private val RE_ANS = Regex("""Answer\s*\(?([A-E])\)?\s*is\s*correct""", RegexOption.IGNORE_CASE)
    /** Every verdict the bank gives, right or wrong, with the reason it gives for it. */
    private val RE_VERDICT = Regex(
        """Answer\s*\(?([A-E])\)?\s*is\s*(correct|incorrect)\b[.:]?\s*(.*?)$STOP""",
        setOf(RegexOption.DOT_MATCHES_ALL, RegexOption.IGNORE_CASE))
    private val RE_LEAD = Regex("""^\s*(\([^)]{0,40}\)\s*)+""")
    private val RE_ACS = Regex("""ACS Code:?\s*([A-Z]{2}\.[IVX]+\.[A-Z0-9.]+)""")
    private val RE_SRC = Regex("""Source:?\s*([^\n|]+)""")
    private val RE_UNIT = Regex("""Study Unit\s*(\d+)\s*:?\s*([^|\n]+)""")
    private val RE_SUB = Regex("""Subunit\s*(\d+)\s*:?\s*([^|\n]+)""")

    private fun question(text: String): JSONObject? {
        val q = RE_Q.findAll(text).lastOrNull() ?: return null
        val number = q.groupValues[1].ifEmpty { q.groupValues[2] }
        val body = text.substring(q.range.last + 1)
        val choices = JSONArray()
        for (m in RE_CHOICE.findAll(body)) {
            val letter = m.groupValues[1]
            val t = clean(m.groupValues[2])
            if (t.isNotEmpty()) choices.put(JSONObject().put("l", letter).put("t", t))
            if (choices.length() >= 5) break
        }
        if (choices.length() < 2) return null
        val holder = JSONObject()
        verdicts(body, choices, holder)
        val ans = holder.optString("ans")
        val why = holder.optString("why")
        return JSONObject()
            .put("kind", "qa")
            .put("n", number)
            .put("q", clean(q.groupValues[3]))
            .put("ch", choices)
            .put("ans", ans)
            .put("why", why)
            .put("acs", RE_ACS.find(text)?.groupValues?.get(1) ?: "")
            .put("src", RE_SRC.find(text)?.groupValues?.get(1)?.trim() ?: "")
            .put("unit", RE_UNIT.find(text)?.let { "Unit ${it.groupValues[1]} · ${it.groupValues[2].trim()}" } ?: "")
            .put("sub", RE_SUB.find(text)?.let { "Subunit ${it.groupValues[1]} · ${it.groupValues[2].trim()}" } ?: "")
    }

    /**
     * Each verdict the bank gives — this one is right, that one is wrong — with its reason, put
     * against the choice it belongs to. A wrong answer explained is half the learning.
     */
    private fun verdicts(body: String, choices: JSONArray, into: JSONObject) {
        var ans = ""
        var why = ""
        for (v in RE_VERDICT.findAll(body)) {
            val letter = v.groupValues[1]
            val right = v.groupValues[2].equals("correct", true)
            val reason = clean(RE_LEAD.replace(v.groupValues[3], ""))
            if (right) { ans = letter; why = reason }
            for (i in 0 until choices.length()) {
                val c = choices.optJSONObject(i) ?: continue
                if (c.optString("l") == letter) {
                    c.put("ok", right)
                    if (reason.isNotEmpty()) c.put("why", reason)
                }
            }
        }
        if (ans.isEmpty()) ans = RE_ANS.find(body)?.groupValues?.get(1) ?: ""
        into.put("ans", ans).put("why", why)
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

    /**
     * Everything from the page's furniture onward, cut away. The last choice on a page has nothing
     * after it to stop at, so without this it ran on through the Mark For Review, the index of
     * every question in the bank and all the rest of it.
     */
    private val TAIL = Regex(
        """\s*(How Can We Help|Contact Gleim|Mark For Review|Questions:|Opens in a new window|Question Filters|Elapsed Time|Average Time)[\s\S]*$""",
        RegexOption.IGNORE_CASE)
    /** A choice or a reason never contains the choice that follows it. */
    private val NEXT_CHOICE = Regex("""\n[ \t]*[A-E][.)]\s[\s\S]*$""")

    private fun clean(s: String) = NEXT_CHOICE.replace(TAIL.replace(s, ""), "")
        .replace(Regex("""[ \t]+"""), " ")
        .replace(Regex("""\n{3,}"""), "\n\n").trim()

    /** A short line naming what was found, for the pilot to check before it is kept. */
    fun describe(o: JSONObject): String = when (o.optString("kind")) {
        "qa" -> {
            val n = o.optString("n").let { if (it.isEmpty()) "" else "Question $it · " }
            val wrong = o.optJSONArray("ch")?.let { a2 ->
                (0 until a2.length()).count { k -> a2.optJSONObject(k)?.has("why") == true && a2.optJSONObject(k)?.optBoolean("ok") == false }
            } ?: 0
            val a = o.optString("ans").let { if (it.isEmpty()) "no answer marked" else "answer $it" } +
                (if (wrong > 0) " · $wrong explained wrong" else "")
            val acs = o.optString("acs").let { if (it.isEmpty()) "" else " · $it" }
            "$n${o.optJSONArray("ch")?.length() ?: 0} choices · $a$acs"
        }
        else -> {
            val h = o.optString("head")
            (if (h.isEmpty()) "A passage" else h) + " · ${o.optJSONArray("pts")?.length() ?: 0} points"
        }
    }
}
