package com.saudi.privatevault

import android.app.Activity
import android.content.Intent
import android.graphics.Paint
import android.graphics.pdf.PdfDocument
import com.google.android.material.dialog.MaterialAlertDialogBuilder

/**
 * Notebooks to write in with the pen: blank, lined or grid pages, or a
 * pilot's scratchpad (ATIS and clearance boxes, then lined pages). Each is a
 * PDF in the vault's «📝 Notes» folder, so the reader's pen, highlighter,
 * shapes and text all work on it, and it syncs like any document.
 */
object Notebooks {
    const val FOLDER = "📝 Notes"
    private const val W = 595   // A4 in points
    private const val H = 842

    enum class Kind(val label: String) { SCRATCHPAD("✈️ Scratchpad (ATIS + clearance)"), LINED("📄 Lined"), BLANK("⬜ Blank"), GRID("▦ Grid") }

    private fun folderId(): String =
        (VaultStore.childFolders(null).firstOrNull { it.name == FOLDER } ?: VaultStore.addFolder(FOLDER, null)).id

    /** The notebooks of a topic (an airport, or everything), newest first, then the choice of a new one. */
    fun choose(act: Activity, topic: String?) {
        val folder = folderId()
        val existing = VaultStore.itemsIn(folder).filter { topic == null || it.name.startsWith(topic) }.sortedByDescending { it.added }
        val labels = existing.map { "📝 " + it.name.removeSuffix(".pdf") } + Kind.values().map { "➕ " + it.label }
        MaterialAlertDialogBuilder(act)
            .setTitle(act.getString(R.string.notes_title) + (topic?.let { " · $it" } ?: ""))
            .setItems(labels.toTypedArray()) { _, i ->
                if (i < existing.size) open(act, existing[i])
                else open(act, create(Kind.values()[i - existing.size], topic, folder))
            }
            .show()
    }

    fun open(act: Activity, item: VaultItem) =
        act.startActivity(Intent(act, PdfViewerActivity::class.java).putExtra(Viewers.EXTRA_ID, item.id))

    private fun create(kind: Kind, topic: String?, folder: String): VaultItem {
        val stamp = java.text.SimpleDateFormat("yyyy-MM-dd HH.mm", java.util.Locale.US).format(java.util.Date())
        val name = listOfNotNull(topic, kind.name.lowercase().replaceFirstChar { it.uppercase() }, stamp).joinToString(" · ") + ".pdf"
        val target = VaultStore.downloadTarget(name)
        val doc = PdfDocument()
        val line = Paint().apply { color = 0xFFB0BEC5.toInt(); strokeWidth = 0.7f }
        val faint = Paint().apply { color = 0xFFE3E8EC.toInt(); strokeWidth = 0.5f }
        val ink = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF37474F.toInt(); textSize = 11f; isFakeBoldText = true }
        val small = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF78909C.toInt(); textSize = 8f }
        val box = Paint().apply { color = 0xFF90A4AE.toInt(); style = Paint.Style.STROKE; strokeWidth = 1f }
        for (n in 1..20) {
            val page = doc.startPage(PdfDocument.PageInfo.Builder(W, H, n).create())
            val c = page.canvas
            c.drawColor(0xFFFFFFFF.toInt())
            c.drawText(listOfNotNull(topic, stamp).joinToString(" · "), 36f, 24f, small)
            c.drawText("$n", W - 44f, 24f, small)
            var top = 40f
            if (kind == Kind.SCRATCHPAD && n == 1) {
                // ATIS, then clearance (CRAFT), as boxes to fill.
                c.drawText("ATIS / AWOS", 36f, top + 14, ink)
                top += 22
                val atis = listOf("Info", "Time Z", "Wind", "Visibility", "Sky", "Temp / Dew", "Altimeter", "Runway", "Remarks / NOTAMs")
                for ((i, t) in atis.withIndex()) {
                    val x = if (i % 2 == 0) 36f else W / 2f + 6
                    val y = top + (i / 2) * 44f
                    val wBox = if (i == atis.size - 1) W - 72f else W / 2f - 42
                    c.drawRect(x, y, x + wBox, y + 38, box)
                    c.drawText(t, x + 4, y + 10, small)
                }
                top += ((atis.size + 1) / 2) * 44f + 14
                c.drawText("CLEARANCE  (C R A F T)", 36f, top + 14, ink)
                top += 22
                for (t in listOf("C · Clearance limit", "R · Route", "A · Altitude", "F · Frequency", "T · Transponder")) {
                    c.drawRect(36f, top, W - 36f, top + 38, box)
                    c.drawText(t, 40f, top + 10, small)
                    top += 44
                }
                top += 10
            }
            when {
                kind == Kind.BLANK -> {}
                kind == Kind.GRID -> {
                    var x = 36f
                    while (x <= W - 36) { c.drawLine(x, top, x, H - 36f, faint); x += 18 }
                    var y = top
                    while (y <= H - 36) { c.drawLine(36f, y, W - 36f, y, faint); y += 18 }
                }
                else -> {
                    var y = top + 28
                    while (y <= H - 36) { c.drawLine(36f, y, W - 36f, y, line); y += 28 }
                }
            }
            doc.finishPage(page)
        }
        target.outputStream().use { doc.writeTo(it) }
        doc.close()
        return VaultStore.adopt(target, name, "application/pdf", folder)
    }
}
