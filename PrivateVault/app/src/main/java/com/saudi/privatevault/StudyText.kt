package com.saudi.privatevault

/**
 * An explanation's text, put back into its shape: sentences the page broke at a link or a number
 * joined again, and a worked schedule (a label and its figures, row after row) found as a table.
 */
object StudyText {
    sealed class Block
    class Para(val text: String) : Block()
    class Row(val label: String, val nums: List<String>)
    class Table(val head: List<String>, val rows: List<Row>, val cols: Int) : Block()

    private val marker = Regex("^(\\d{1,2}|[a-z]|[ivx]{1,4})[.)]$")
    private val num = Regex("^[-−–]?\\$?[\\d,]*\\.?\\d+%?$|^-{2,}$|^—$|^\\?$")

    /** A line that is a row of figures: words, then one to four numbers to its end. */
    fun row(line: String): Row? {
        val toks = line.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }
        if (toks.isEmpty()) return null
        var k = toks.size
        while (k > 0 && num.matches(toks[k - 1])) k--
        val n = toks.size - k
        if (n == 0 || n > 4) return null
        val label = toks.subList(0, k).joinToString(" ")
        // A sentence that happens to end in a number is not a row.
        if (label.length > 45 || label.endsWith(".") && !label.endsWith(".)")) return null
        if (Regex("\\b(is|are|was|the|of|to|by|and)$", RegexOption.IGNORE_CASE).containsMatchIn(label)) return null
        return Row(label, toks.subList(k, toks.size))
    }

    fun blocks(text: String): List<Block> {
        val lines = text.split('\n').map { it.trim() }.filter { it.isNotEmpty() }
        val out = ArrayList<Block>()
        var i = 0
        val para = StringBuilder()
        fun flush() { if (para.isNotEmpty()) { out.add(Para(para.toString())); para.setLength(0) } }
        while (i < lines.size) {
            // A run of three or more rows is a table; the short line just above it is its heading.
            var j = i
            val rows = ArrayList<Row>()
            while (j < lines.size) { val r = row(lines[j]) ?: break; rows.add(r); j++ }
            if (rows.size >= 3) {
                var head = emptyList<String>()
                // The heading went into the paragraph before; take it back out.
                val last = para.toString().substringAfterLast('\n')
                val prev = if (i > 0) lines[i - 1] else ""
                if (prev.isNotEmpty() && prev.length <= 40 && !Regex("[.:!?]$").containsMatchIn(prev) && last.endsWith(prev) && row(prev) == null) {
                    head = prev.split(Regex("\\s+"))
                    val cut = para.length - prev.length
                    para.setLength(cut.coerceAtLeast(0))
                    while (para.isNotEmpty() && (para.last() == ' ' || para.last() == '\n')) para.setLength(para.length - 1)
                }
                flush()
                val cols = rows.maxOf { it.nums.size }
                out.add(Table(head, rows, cols))
                i = j
                continue
            }
            // A number standing alone on its line ("1.", "2.", "a.") belongs to the step after it:
            // the page puts the marker and the words in two cells.
            val l0 = lines[i]
            if (marker.matches(l0) && i + 1 < lines.size && row(lines[i + 1]) == null && !marker.matches(lines[i + 1])) {
                if (para.isNotEmpty()) para.append('\n')
                para.append(l0).append(' ').append(lines[i + 1])
                i += 2
                continue
            }
            val l = l0
            if (para.isEmpty()) para.append(l)
            else {
                val p = para.toString()
                val joins = !Regex("[.:!?)]$").containsMatchIn(p) || l.first().isLowerCase() || l.first() in "(.,;"
                if (joins) para.append(if (l.first() in ".,;)") "" else " ").append(l)
                else para.append('\n').append(l)
            }
            i++
        }
        flush()
        return out
    }
}
