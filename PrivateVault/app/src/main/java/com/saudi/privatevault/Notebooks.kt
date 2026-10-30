package com.saudi.privatevault

import android.app.Activity
import android.content.Intent
import android.graphics.pdf.PdfDocument
import android.view.Gravity
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import com.google.android.material.dialog.MaterialAlertDialogBuilder

/**
 * The notebooks of an airport (or of any topic): open one, delete one, or
 * start a new one, which opens in the notepad (small on the right, or full
 * page). A notebook can be kept as a PDF in the vault's «📝 Notes» folder.
 */
object Notebooks {
    const val FOLDER = "📝 Notes"

    private fun folderId(): String =
        (VaultStore.childFolders(null).firstOrNull { it.name == FOLDER } ?: VaultStore.addFolder(FOLDER, null)).id

    /** big: open as a full page (screens with no map behind); otherwise small on the right. */
    fun choose(act: Activity, topic: String?, big: Boolean = act !is MapActivity) {
        val d = act.resources.displayMetrics.density
        fun dp(v: Int) = (v * d).toInt()
        val list = LinearLayout(act).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(8), dp(16), dp(8)) }
        lateinit var dialog: androidx.appcompat.app.AlertDialog
        fun row(label: String, onOpen: () -> Unit, onDelete: (() -> Unit)?) {
            val r = LinearLayout(act).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
            r.addView(TextView(act).apply {
                text = label; textSize = 15f; setPadding(dp(4), dp(12), dp(4), dp(12))
                setOnClickListener { dialog.dismiss(); onOpen() }
            }, LinearLayout.LayoutParams(0, -2, 1f))
            if (onDelete != null) r.addView(TextView(act).apply {
                text = "🗑"; textSize = 20f; setPadding(dp(12), dp(8), dp(6), dp(8))
                setOnClickListener {
                    MaterialAlertDialogBuilder(act).setMessage(act.getString(R.string.notes_delete_q, label.drop(2)))
                        .setPositiveButton(R.string.notes_delete) { _, _ -> onDelete(); list.removeView(r) }
                        .setNegativeButton(R.string.cancel, null).show()
                }
            })
            list.addView(r)
        }
        val books = NoteBook.all(act).filter { topic == null || it.topic == topic }
        for (b in books) row("📝 " + b.title, { NotePad.show(act, b, big) }) { b.file.delete() }
        // Notebooks made as PDFs, kept in the vault.
        val folder = folderId()
        for (item in VaultStore.itemsIn(folder).filter { topic == null || it.name.startsWith(topic) }.sortedByDescending { it.added })
            row("📄 " + item.name.removeSuffix(".pdf"), {
                act.startActivity(Intent(act, PdfViewerActivity::class.java).putExtra(Viewers.EXTRA_ID, item.id))
            }) { VaultStore.deleteItem(item) }
        for (s in NoteBook.Style.values()) row("➕ " + s.label, { NotePad.show(act, NoteBook.create(act, s, topic), big) }, null)
        dialog = MaterialAlertDialogBuilder(act)
            .setTitle(act.getString(R.string.notes_title) + (topic?.let { " · $it" } ?: ""))
            .setView(ScrollView(act).apply { addView(list) })
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    /** The notebook drawn into a PDF in the vault, to keep, print or send. */
    fun exportPdf(act: Activity, book: NoteBook) {
        val name = book.title.replace(":", ".") + ".pdf"
        val target = VaultStore.downloadTarget(name)
        val doc = PdfDocument()
        val w = 595; val h = 842
        val canvas = NoteCanvas(act, book)
        for (i in book.pages.indices) {
            val page = doc.startPage(PdfDocument.PageInfo.Builder(w, h, i + 1).create())
            canvas.page = i
            canvas.layout(0, 0, w, h)
            canvas.draw(page.canvas)
            doc.finishPage(page)
        }
        target.outputStream().use { doc.writeTo(it) }
        doc.close()
        VaultStore.items.firstOrNull { it.folderId == folderId() && it.name == name }?.let { VaultStore.deleteItem(it) }
        VaultStore.adopt(target, name, "application/pdf", folderId())
        Toast.makeText(act, act.getString(R.string.notes_saved_pdf, FOLDER), Toast.LENGTH_LONG).show()
    }
}
