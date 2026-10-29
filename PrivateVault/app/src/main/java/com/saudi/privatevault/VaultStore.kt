package com.saudi.privatevault

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.pdf.PdfRenderer
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.provider.OpenableColumns
import android.webkit.MimeTypeMap
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID

enum class Kind { VIDEO, AUDIO, IMAGE, PDF, TEXT, OTHER }

class Folder(val id: String, var name: String, var parentId: String?, val created: Long)

class VaultItem(
    val id: String,
    var name: String,
    val file: String,
    val mime: String,
    val size: Long,
    val added: Long,
    var folderId: String?,
    /** Set for videos that play from the internet or a laptop instead of from the phone. */
    val url: String? = null,
) {
    val kind: Kind get() = if (url != null && kindOf(mime, name) != Kind.AUDIO) Kind.VIDEO else kindOf(mime, name)
    val isLink: Boolean get() = url != null
    val playable: Boolean get() = kind == Kind.VIDEO || kind == Kind.AUDIO
}

private val VIDEO_EXT = setOf("mp4", "mkv", "webm", "3gp", "mov", "avi", "m4v", "ts")
private val AUDIO_EXT = setOf("mp3", "m4a", "aac", "wav", "ogg", "opus", "flac", "amr")
private val IMAGE_EXT = setOf("jpg", "jpeg", "png", "gif", "webp", "bmp", "heic", "heif")
private val TEXT_EXT = setOf("txt", "md", "csv", "json", "log", "xml", "srt", "html")

fun kindOf(mime: String, name: String): Kind {
    val ext = name.substringAfterLast('.', "").lowercase()
    return when {
        mime.startsWith("video/") || ext in VIDEO_EXT -> Kind.VIDEO
        mime.startsWith("audio/") || ext in AUDIO_EXT -> Kind.AUDIO
        mime.startsWith("image/") || ext in IMAGE_EXT -> Kind.IMAGE
        mime == "application/pdf" || ext == "pdf" -> Kind.PDF
        mime.startsWith("text/") || ext in TEXT_EXT -> Kind.TEXT
        else -> Kind.OTHER
    }
}

/** By name first: "2- Intro" comes before "10- Landing". */
const val SORT_DEFAULT = 2

/**
 * Compares names the way people number things: digit runs by their value,
 * the rest ignoring case, so "2-" sorts before "10-".
 */
object NaturalOrder : Comparator<String> {
    override fun compare(a: String, b: String): Int {
        var i = 0
        var j = 0
        while (i < a.length && j < b.length) {
            val ca = a[i]
            val cb = b[j]
            if (ca.isDigit() && cb.isDigit()) {
                val si = i
                val sj = j
                while (i < a.length && a[i].isDigit()) i++
                while (j < b.length && b[j].isDigit()) j++
                val na = a.substring(si, i).trimStart('0')
                val nb = b.substring(sj, j).trimStart('0')
                if (na.length != nb.length) return na.length - nb.length
                val c = na.compareTo(nb)
                if (c != 0) return c
            } else {
                val c = ca.lowercaseChar().compareTo(cb.lowercaseChar())
                if (c != 0) return c
                i++
                j++
            }
        }
        return (a.length - i) - (b.length - j)
    }
}

/**
 * Everything the vault holds lives in the app's private storage: the files
 * under vault_files/, small previews under vault_thumbs/, and the list of
 * folders and items in vault_index.json. Other apps, the gallery and the
 * file manager cannot see any of it.
 */
object VaultStore {
    private lateinit var root: File
    val folders = mutableListOf<Folder>()
    val items = mutableListOf<VaultItem>()

    fun init(ctx: Context) {
        root = ctx.filesDir
        filesDir().mkdirs()
        thumbsDir().mkdirs()
        load()
    }

    fun filesDir() = File(root, "vault_files")
    private fun thumbsDir() = File(root, "vault_thumbs")
    private fun indexFile() = File(root, "vault_index.json")

    fun fileOf(item: VaultItem) = if (item.file.startsWith("/")) File(item.file) else File(filesDir(), item.file)
    fun thumbOf(item: VaultItem) = File(thumbsDir(), item.id + ".jpg")

    fun item(id: String?) = items.firstOrNull { it.id == id } ?: viewing[id]

    // Laptop files fetched only to look at them: shown by the same viewers,
    // never added to the vault, and deleted when the laptop screen closes.
    private val viewing = mutableMapOf<String?, VaultItem>()

    fun viewOnly(item: VaultItem) {
        viewing[item.id] = item
    }

    fun forgetViewOnly() {
        viewing.values.forEach { fileOf(it).delete() }
        viewing.clear()
    }

    /** Where a laptop file is downloaded before [adopt] keeps it. */
    fun downloadTarget(name: String): File {
        val ext = name.substringAfterLast('.', "").lowercase()
        val id = UUID.randomUUID().toString()
        return File(filesDir(), if (ext.isNotEmpty() && ext.length <= 6) "$id.$ext" else id)
    }

    /** Keeps a file already written into [filesDir]; call from the main thread. */
    fun adopt(file: File, name: String, mime: String, folderId: String?): VaultItem {
        val item = VaultItem(
            UUID.randomUUID().toString(), name, file.name, mime, file.length(), System.currentTimeMillis(), folderId,
        )
        items.add(item)
        save()
        return item
    }
    fun folder(id: String?) = folders.firstOrNull { it.id == id }

    private fun load() {
        folders.clear()
        items.clear()
        val f = indexFile()
        if (!f.exists()) return
        try {
            val json = JSONObject(f.readText())
            val fa = json.optJSONArray("folders") ?: JSONArray()
            for (i in 0 until fa.length()) {
                val o = fa.getJSONObject(i)
                folders.add(
                    Folder(o.getString("id"), o.getString("name"), o.optStringOrNull("parent"), o.optLong("created"))
                )
            }
            val ia = json.optJSONArray("items") ?: JSONArray()
            for (i in 0 until ia.length()) {
                val o = ia.getJSONObject(i)
                items.add(
                    VaultItem(
                        o.getString("id"), o.getString("name"), o.getString("file"),
                        o.optString("mime"), o.optLong("size"), o.optLong("added"),
                        o.optStringOrNull("folder"),
                        o.optStringOrNull("url"),
                    )
                )
            }
        } catch (e: Exception) {
            // Keep the broken index aside rather than overwrite it on the next save.
            f.copyTo(File(root, "vault_index.broken.json"), overwrite = true)
        }
    }

    @Synchronized
    fun save() {
        val fa = JSONArray()
        for (d in folders) {
            fa.put(JSONObject().put("id", d.id).put("name", d.name).put("parent", d.parentId ?: JSONObject.NULL)
                .put("created", d.created))
        }
        val ia = JSONArray()
        for (it in items) {
            ia.put(JSONObject().put("id", it.id).put("name", it.name).put("file", it.file).put("mime", it.mime)
                .put("size", it.size).put("added", it.added).put("folder", it.folderId ?: JSONObject.NULL)
                .put("url", it.url ?: JSONObject.NULL))
        }
        val text = JSONObject().put("version", 1).put("folders", fa).put("items", ia).toString()
        // Write beside the index and swap it in, so a crash mid-write never loses the list.
        val tmp = File(root, "vault_index.json.tmp")
        tmp.writeText(text)
        if (!tmp.renameTo(indexFile())) {
            indexFile().writeText(text)
            tmp.delete()
        }
    }

    // ---- folders ----

    fun addFolder(name: String, parentId: String?): Folder {
        val d = Folder(UUID.randomUUID().toString(), name, parentId, System.currentTimeMillis())
        folders.add(d)
        save()
        return d
    }

    fun childFolders(parentId: String?) = folders.filter { it.parentId == parentId }

    fun itemsIn(folderId: String?) = items.filter { it.folderId == folderId }

    /** The folder and every folder below it. */
    fun subtree(id: String): Set<String> {
        val out = mutableSetOf(id)
        var grew = true
        while (grew) {
            grew = false
            for (d in folders) if (d.parentId in out && out.add(d.id)) grew = true
        }
        return out
    }

    fun countIn(folderId: String): Int {
        val ids = subtree(folderId)
        return items.count { it.folderId in ids }
    }

    fun deleteFolder(id: String) {
        val ids = subtree(id)
        items.filter { it.folderId in ids }.forEach { removeFiles(it) }
        items.removeAll { it.folderId in ids }
        folders.removeAll { it.id in ids }
        save()
    }

    fun pathOf(folderId: String?): String {
        val names = mutableListOf<String>()
        var cur = folder(folderId)
        while (cur != null) {
            names.add(0, cur.name)
            cur = folder(cur.parentId)
        }
        return names.joinToString(" / ")
    }

    // ---- items ----

    fun deleteItem(item: VaultItem) {
        removeFiles(item)
        items.remove(item)
        save()
    }

    private fun removeFiles(item: VaultItem) {
        if (item.file.isNotEmpty()) fileOf(item).delete()
        thumbOf(item).delete()
    }

    fun addLink(name: String, url: String, folderId: String?): VaultItem {
        val path = Uri.parse(url).lastPathSegment ?: ""
        val ext = path.substringAfterLast('.', "").lowercase()
        val mime = MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext) ?: "video/*"
        val item = VaultItem(UUID.randomUUID().toString(), name, "", mime, 0L, System.currentTimeMillis(), folderId, url)
        items.add(item)
        save()
        return item
    }

    fun totalBytes(): Long = filesDir().listFiles()?.sumOf { it.length() } ?: 0L

    /**
     * Copies one picked document into the vault. Runs off the main thread;
     * the caller adds the returned item to [items] and saves.
     */
    fun copyIn(ctx: Context, uri: Uri, folderId: String?): VaultItem? {
        val cr = ctx.contentResolver
        var name: String? = null
        var size = -1L
        try {
            cr.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)?.use { c ->
                if (c.moveToFirst()) {
                    val ni = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    val si = c.getColumnIndex(OpenableColumns.SIZE)
                    if (ni >= 0) name = c.getString(ni)
                    if (si >= 0 && !c.isNull(si)) size = c.getLong(si)
                }
            }
        } catch (_: Exception) {
        }
        var mime = cr.getType(uri) ?: ""
        val displayName = name ?: uri.lastPathSegment?.substringAfterLast('/') ?: "file"
        val ext = displayName.substringAfterLast('.', "").lowercase()
        if (mime.isEmpty() || mime == "application/octet-stream") {
            mime = MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext) ?: mime
        }

        val id = UUID.randomUUID().toString()
        val stored = if (ext.isNotEmpty() && ext.length <= 6) "$id.$ext" else id
        val target = File(filesDir(), stored)
        try {
            val input = cr.openInputStream(uri) ?: return null
            input.use { inp -> target.outputStream().use { out -> inp.copyTo(out, 256 * 1024) } }
        } catch (e: Exception) {
            target.delete()
            return null
        }
        if (size < 0) size = target.length()
        val item = VaultItem(id, displayName, stored, mime, target.length(), System.currentTimeMillis(), folderId)
        makeThumb(item)
        return item
    }

    fun makeThumb(item: VaultItem) {
        val f = fileOf(item)
        val bmp: Bitmap? = try {
            when (item.kind) {
                Kind.VIDEO -> {
                    val r = MediaMetadataRetriever()
                    try {
                        r.setDataSource(f.absolutePath)
                        r.getFrameAtTime(1_000_000) ?: r.frameAtTime
                    } finally {
                        r.release()
                    }
                }
                Kind.IMAGE -> decodeSampled(f, 320)
                Kind.PDF -> renderPdfPage(f, 0, 320)
                else -> null
            }
        } catch (e: Throwable) {
            null
        }
        if (bmp != null) {
            val scaled = scaleDown(bmp, 320)
            thumbOf(item).outputStream().use { scaled.compress(Bitmap.CompressFormat.JPEG, 80, it) }
        }
    }

    fun decodeSampled(f: File, maxSide: Int): Bitmap? {
        val opts = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(f.absolutePath, opts)
        var sample = 1
        while (opts.outWidth / (sample * 2) >= maxSide && opts.outHeight / (sample * 2) >= maxSide) sample *= 2
        return BitmapFactory.decodeFile(f.absolutePath, BitmapFactory.Options().apply { inSampleSize = sample })
    }

    private fun scaleDown(bmp: Bitmap, maxSide: Int): Bitmap {
        val big = maxOf(bmp.width, bmp.height)
        if (big <= maxSide) return bmp
        val s = maxSide.toFloat() / big
        return Bitmap.createScaledBitmap(bmp, (bmp.width * s).toInt().coerceAtLeast(1), (bmp.height * s).toInt().coerceAtLeast(1), true)
    }

    private fun renderPdfPage(f: File, index: Int, width: Int): Bitmap? {
        val pfd = ParcelFileDescriptor.open(f, ParcelFileDescriptor.MODE_READ_ONLY)
        val renderer = PdfRenderer(pfd)
        try {
            if (renderer.pageCount == 0) return null
            val page = renderer.openPage(index)
            try {
                val h = (width.toFloat() * page.height / page.width).toInt().coerceAtLeast(1)
                val bmp = Bitmap.createBitmap(width, h, Bitmap.Config.ARGB_8888)
                bmp.eraseColor(Color.WHITE)
                page.render(bmp, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                return bmp
            } finally {
                page.close()
            }
        } finally {
            renderer.close()
        }
    }
}

private fun JSONObject.optStringOrNull(key: String): String? =
    if (isNull(key)) null else optString(key, "").ifEmpty { null }
