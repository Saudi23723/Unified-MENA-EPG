package com.saudi.privatevault

import android.content.Context
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.graphics.pdf.PdfDocument
import java.io.File

/**
 * The logbook printed the way a paper pilot logbook reads: landscape pages
 * of flights with page totals, amounts forward and totals to date, the
 * instructor's signature on each dual flight, then the 8710-1 totals and the
 * endorsements, signed.
 */
object LogbookPdf {
    private const val W = 792f
    private const val H = 612f
    private const val ROWS = 13

    private class Col(val title: String, val width: Float, val value: (LogEntry) -> String, val sum: ((List<LogEntry>) -> Double)? = null)

    private fun n(v: Double) = if (v == 0.0) "" else "%.1f".format(v)
    private fun i(v: Int) = if (v == 0) "" else v.toString()

    private val cols = listOf(
        Col("DATE", 52f, { it.date.drop(2) }),
        Col("AIRCRAFT", 52f, { it.aircraft.take(10) }),
        Col("IDENT", 40f, { it.tail.take(7) }),
        Col("FROM", 34f, { it.from.take(5) }),
        Col("TO", 34f, { it.to.take(5) }),
        Col("ROUTE / REMARKS", 132f, { (it.route.takeIf { r -> r.isNotBlank() && r != "${it.from} ${it.to}" }?.let { r -> "$r · " } ?: "") + it.remarks }),
        Col("APP", 24f, { i(it.approaches) }, { l -> l.sumOf { it.approaches }.toDouble() }),
        Col("LDG D", 28f, { i(it.dayLdg) }, { l -> l.sumOf { it.dayLdg }.toDouble() }),
        Col("LDG N", 28f, { i(it.nightLdg) }, { l -> l.sumOf { it.nightLdg }.toDouble() }),
        Col("NIGHT", 32f, { n(it.night) }, { l -> l.sumOf { it.night } }),
        Col("ACT", 28f, { n(it.actual) }, { l -> l.sumOf { it.actual } }),
        Col("SIM", 28f, { n(it.instrument) }, { l -> l.sumOf { it.instrument } }),
        Col("XC", 30f, { n(it.xc) }, { l -> l.sumOf { it.xc } }),
        Col("DUAL", 32f, { n(it.dual) }, { l -> l.sumOf { it.dual } }),
        Col("SOLO", 32f, { n(it.solo) }, { l -> l.sumOf { it.solo } }),
        Col("PIC", 32f, { n(it.pic) }, { l -> l.sumOf { it.pic } }),
        Col("TOTAL", 36f, { n(it.total) }, { l -> l.sumOf { it.total } }),
        Col("INSTRUCTOR", 70f, { it.instructor.take(14) }),
    )

    fun write(ctx: Context, entries: List<LogEntry>, endorsements: List<Endorsement>, pilot: String, cert: String): File {
        val doc = PdfDocument()
        val flights = entries.sortedWith(compareBy<LogEntry> { it.date }.thenBy { it.timeOut })
        val text = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = 7.5f; color = 0xFF111111.toInt() }
        val bold = Paint(text).apply { typeface = Typeface.DEFAULT_BOLD }
        val line = Paint().apply { color = 0xFF9AA5B1.toInt(); strokeWidth = 0.5f }
        val band = Paint().apply { color = 0xFFE8EEF5.toInt() }
        val left = 18f
        val chunks = flights.chunked(ROWS).ifEmpty { listOf(emptyList()) }
        var forward = emptyList<LogEntry>()
        var pageNo = 1
        for (chunk in chunks) {
            val page = doc.startPage(PdfDocument.PageInfo.Builder(W.toInt(), H.toInt(), pageNo).create())
            val c = page.canvas
            c.drawText("PILOT LOGBOOK", left, 26f, Paint(bold).apply { textSize = 13f })
            c.drawText("$pilot${if (cert.isNotBlank()) " · Certificate $cert" else ""}", left + 120f, 26f, text)
            c.drawText("Page $pageNo", W - 60f, 26f, text)
            var y = 44f
            c.drawRect(left, y - 10f, W - left, y + 6f, band)
            var x = left
            for (col in cols) {
                c.drawText(col.title, x + 2f, y, bold)
                x += col.width
            }
            y += 8f
            val rowH = 30f
            for (e in chunk) {
                c.drawLine(left, y, W - left, y, line)
                x = left
                for (col in cols) {
                    val v = col.value(e)
                    if (col.title == "ROUTE / REMARKS") {
                        // Two lines of remarks fit in the row.
                        val words = v.split(' ')
                        var l1 = ""; var l2 = ""
                        for (w in words) if (text.measureText("$l1 $w") < col.width - 4 && l2.isEmpty()) l1 = "$l1 $w".trim() else l2 = "$l2 $w".trim()
                        c.drawText(l1, x + 2f, y + 11f, text)
                        if (l2.isNotEmpty()) c.drawText(l2.take(34), x + 2f, y + 21f, text)
                    } else if (col.title == "INSTRUCTOR") {
                        c.drawText(v, x + 2f, y + 9f, text)
                        if (e.instructorCert.isNotEmpty()) c.drawText(e.instructorCert.take(14), x + 2f, y + 17f, text)
                        if (e.signed) File(Logbook.signatures(ctx), e.signature).takeIf { it.exists() }?.let { f ->
                            BitmapFactory.decodeFile(f.path)?.let { bmp ->
                                val h = 10f
                                val w = (bmp.width * h / bmp.height).coerceAtMost(col.width - 4)
                                c.drawBitmap(bmp, null, RectF(x + 2f, y + 18f, x + 2f + w, y + 18f + h), null)
                            }
                        }
                    } else {
                        c.drawText(v, x + 2f, y + 16f, text)
                    }
                    x += col.width
                }
                y += rowH
            }
            y = 44f + 8f + ROWS * rowH
            c.drawLine(left, y, W - left, y, line)
            val toDate = forward + chunk
            for ((label, list) in listOf("TOTALS THIS PAGE" to chunk, "AMOUNT FORWARD" to forward, "TOTALS TO DATE" to toDate)) {
                y += 13f
                c.drawText(label, left + 2f, y, bold)
                x = left
                for (col in cols) {
                    col.sum?.let { s ->
                        val v = s(list)
                        c.drawText(if (col.title.startsWith("LDG") || col.title == "APP") "%.0f".format(v) else "%.1f".format(v), x + 2f, y, bold)
                    }
                    x += col.width
                }
            }
            y += 22f
            c.drawText("I certify that the statements made within this logbook are true.", left, y, text)
            c.drawLine(left + 260f, y + 2f, left + 420f, y + 2f, line)
            c.drawText("Pilot signature", left + 300f, y + 11f, text)
            doc.finishPage(page)
            forward = toDate
            pageNo++
        }

        // Totals for FAA Form 8710-1.
        val page = doc.startPage(PdfDocument.PageInfo.Builder(W.toInt(), H.toInt(), pageNo++).create())
        var c: Canvas = page.canvas
        c.drawText("TOTALS FOR FAA FORM 8710-1 (IACRA)", left, 30f, Paint(bold).apply { textSize = 13f })
        c.drawText("$pilot · as of ${LogEntry.today()}", left, 46f, text)
        var y = 70f
        for ((k, v) in Logbook.iacra(flights)) {
            c.drawText(k, left, y, Paint(text).apply { textSize = 10f })
            c.drawText(if (k.contains("landings") || k.contains("Number")) "%.0f".format(v) else "%.1f".format(v), left + 260f, y, Paint(bold).apply { textSize = 10f })
            c.drawLine(left, y + 4f, left + 320f, y + 4f, line)
            y += 18f
        }
        doc.finishPage(page)

        // Endorsements, two to a page.
        for (pair in endorsements.sortedBy { it.date }.chunked(2)) {
            val p = doc.startPage(PdfDocument.PageInfo.Builder(W.toInt(), H.toInt(), pageNo++).create())
            c = p.canvas
            c.drawText("ENDORSEMENTS", left, 30f, Paint(bold).apply { textSize = 13f })
            y = 56f
            val body = Paint(text).apply { textSize = 10f }
            for (e in pair) {
                c.drawText("${e.title}  (${e.rule})", left, y, Paint(bold).apply { textSize = 11f })
                y += 16f
                for (l in wrap(e.text, body, W - 2 * left)) { c.drawText(l, left, y, body); y += 13f }
                y += 6f
                c.drawText("Date ${e.date}${e.expires()?.let { " · valid to " + LogEntry.FMT.format(java.util.Date(it)) } ?: ""}", left, y, body)
                y += 14f
                c.drawText("${e.instructor}  ·  CFI ${e.instructorCert}  ·  Exp. ${e.instructorExp}", left, y, body)
                if (e.signature.isNotEmpty()) File(Logbook.signatures(ctx), e.signature).takeIf { it.exists() }?.let { f ->
                    BitmapFactory.decodeFile(f.path)?.let { bmp ->
                        val h = 34f
                        c.drawBitmap(bmp, null, RectF(left + 380f, y - 30f, left + 380f + bmp.width * h / bmp.height, y + 4f), null)
                    }
                }
                y += 40f
                c.drawLine(left, y - 20f, W - left, y - 20f, line)
            }
            doc.finishPage(p)
        }
        val out = File(ctx.cacheDir, "exports").apply { mkdirs() }.let { File(it, "Logbook_${LogEntry.today()}.pdf") }
        out.outputStream().use { doc.writeTo(it) }
        doc.close()
        return out
    }

    private fun wrap(s: String, p: Paint, width: Float): List<String> {
        val out = ArrayList<String>()
        for (para in s.split('\n')) {
            var line = ""
            for (w in para.split(' ')) {
                if (p.measureText("$line $w") > width && line.isNotEmpty()) { out.add(line); line = w } else line = "$line $w".trim()
            }
            out.add(line)
        }
        return out
    }
}
