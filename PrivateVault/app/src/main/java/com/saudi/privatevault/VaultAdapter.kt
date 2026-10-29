package com.saudi.privatevault

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Handler
import android.os.Looper
import android.text.format.DateFormat
import android.text.format.Formatter
import android.util.LruCache
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import com.saudi.privatevault.databinding.ItemEntryBinding
import java.util.Date
import java.util.concurrent.Executors

sealed class Entry {
    class FolderEntry(val folder: Folder, val count: Int, val path: String?) : Entry()
    class FileEntry(val item: VaultItem, val path: String?) : Entry()
}

class VaultAdapter(
    private val onClick: (Entry) -> Unit,
    private val onMore: (Entry, View) -> Unit,
) : RecyclerView.Adapter<VaultAdapter.Holder>() {

    class Holder(val b: ItemEntryBinding) : RecyclerView.ViewHolder(b.root)

    private var entries: List<Entry> = emptyList()
    private val loader = Executors.newFixedThreadPool(2)
    private val main = Handler(Looper.getMainLooper())
    private val cache = object : LruCache<String, Bitmap>(16 * 1024 * 1024) {
        override fun sizeOf(key: String, value: Bitmap) = value.byteCount
    }

    fun submit(list: List<Entry>) {
        entries = list
        notifyDataSetChanged()
    }

    override fun getItemCount() = entries.size

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int) =
        Holder(ItemEntryBinding.inflate(LayoutInflater.from(parent.context), parent, false))

    override fun onBindViewHolder(h: Holder, position: Int) {
        val e = entries[position]
        val ctx = h.itemView.context
        h.b.thumb.visibility = View.GONE
        h.b.thumb.setImageDrawable(null)
        h.b.play.visibility = View.GONE
        h.b.thumb.tag = null
        when (e) {
            is Entry.FolderEntry -> {
                h.b.icon.setImageResource(R.drawable.ic_folder)
                h.b.name.text = e.folder.name
                val count = ctx.getString(R.string.items_count, e.count)
                h.b.info.text = if (e.path.isNullOrEmpty()) count else "${e.path} · $count"
            }
            is Entry.FileEntry -> {
                val it = e.item
                h.b.icon.setImageResource(iconFor(it.kind))
                h.b.name.text = it.name
                val date = DateFormat.getDateFormat(ctx).format(Date(it.added))
                val line = "${Formatter.formatShortFileSize(ctx, it.size)} · $date"
                h.b.info.text = if (e.path != null) "${e.path.ifEmpty { ctx.getString(R.string.root) }} · $line" else line
                if (it.kind == Kind.VIDEO) h.b.play.visibility = View.VISIBLE
                loadThumb(h, it)
            }
        }
        h.itemView.setOnClickListener { onClick(e) }
        h.b.more.setOnClickListener { v -> onMore(e, v) }
        h.itemView.setOnLongClickListener { onMore(e, h.b.more); true }
    }

    private fun loadThumb(h: Holder, item: VaultItem) {
        val cached = cache.get(item.id)
        if (cached != null) {
            show(h, cached)
            return
        }
        val file = VaultStore.thumbOf(item)
        if (!file.exists()) return
        h.b.thumb.tag = item.id
        loader.execute {
            val bmp = BitmapFactory.decodeFile(file.absolutePath) ?: return@execute
            cache.put(item.id, bmp)
            main.post { if (h.b.thumb.tag == item.id) show(h, bmp) }
        }
    }

    private fun show(h: Holder, bmp: Bitmap) {
        h.b.thumb.setImageBitmap(bmp)
        h.b.thumb.visibility = View.VISIBLE
    }

    fun forget(id: String) {
        cache.remove(id)
    }

    companion object {
        fun iconFor(kind: Kind) = when (kind) {
            Kind.VIDEO -> R.drawable.ic_video
            Kind.AUDIO -> R.drawable.ic_audio
            Kind.IMAGE -> R.drawable.ic_image
            else -> R.drawable.ic_doc
        }
    }
}
