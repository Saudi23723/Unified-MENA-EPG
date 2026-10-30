package com.saudi.privatevault

import android.app.Activity
import android.content.Context
import android.content.Intent
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import com.tom_roush.pdfbox.multipdf.PDFMergerUtility
import java.io.File

/**
 * Chart Supplement pages kept where the pilot can see them: one PDF per
 * airport in the vault's «📘 Chart Supplement» folder, named with its
 * edition. A new edition replaces the airport's old one, so the folder only
 * ever holds the current pages; notes written on a page stay with it.
 */
object SupplementShelf {
    const val FOLDER = "📘 Chart Supplement"
    private val EDITION = Regex("\\d{2}[A-Z]{3}\\d{4}")

    private fun folderId(): String =
        (VaultStore.childFolders(null).firstOrNull { it.name == FOLDER } ?: VaultStore.addFolder(FOLDER, null)).id

    private fun prefix(ident: String) = "$ident · Chart Supplement"

    /** The airport's pages as one PDF in the folder, replacing an older edition; returns the vault item. */
    fun keep(ctx: Context, ident: String, pages: List<File>): VaultItem? {
        if (pages.isEmpty()) return null
        val edition = pages.firstNotNullOfOrNull { f -> EDITION.find(f.parentFile?.name ?: "")?.value ?: EDITION.find(f.name.uppercase())?.value }
            ?: OfflinePack.csEdition()
        val name = "${prefix(ident)} · $edition.pdf"
        val folder = folderId()
        val mine = VaultStore.itemsIn(folder).filter { it.name.startsWith(prefix(ident)) }
        mine.firstOrNull { it.name == name && VaultStore.fileOf(it).length() > 0 }?.let { return it }
        // The new edition in; every older edition of this airport out.
        val target = VaultStore.downloadTarget(name)
        try {
            if (pages.size == 1) pages[0].copyTo(target, overwrite = true)
            else {
                PDFBoxResourceLoader.init(ctx.applicationContext)
                PDFMergerUtility().apply {
                    for (p in pages) addSource(p)
                    destinationFileName = target.absolutePath
                    mergeDocuments(null)
                }
            }
        } catch (e: Exception) {
            target.delete()
            return null
        }
        for (old in mine) VaultStore.deleteItem(old)
        return VaultStore.adopt(target, name, "application/pdf", folder)
    }

    fun open(act: Activity, item: VaultItem) =
        act.startActivity(Intent(act, PdfViewerActivity::class.java).putExtra(Viewers.EXTRA_ID, item.id))
}
