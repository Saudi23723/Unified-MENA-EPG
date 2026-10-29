package com.saudi.privatevault

import android.content.Intent
import android.os.Bundle
import android.text.InputType
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.widget.PopupMenu
import androidx.appcompat.widget.SearchView
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.saudi.privatevault.databinding.ActivityMainBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.io.IOException

/**
 * The vault on the laptop, browsed from the phone. Videos stream straight
 * from the laptop; other files are fetched only while they are open, unless
 * "download to phone" keeps a copy in the phone's own vault.
 */
class LaptopActivity : BaseActivity() {

    private lateinit var b: ActivityMainBinding
    private lateinit var adapter: VaultAdapter

    private var laptopName = ""
    private var folders: List<Folder> = emptyList()
    private var items: List<VaultItem> = emptyList()
    private var folderId: String? = null
    private var query = ""
    private var loaded = false
    private var loading = false
    private var searchMenuItem: MenuItem? = null
    private var linkDialog: AlertDialog? = null

    private val backInFolder = object : OnBackPressedCallback(false) {
        override fun handleOnBackPressed() {
            folderId = folders.firstOrNull { it.id == folderId }?.parentId
            render()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityMainBinding.inflate(layoutInflater)
        setContentView(b.root)
        setSupportActionBar(b.toolbar)
        b.toolbar.setNavigationIcon(R.drawable.ic_back)
        b.toolbar.setNavigationOnClickListener { onBackPressedDispatcher.onBackPressed() }
        b.fab.visibility = View.GONE
        folderId = savedInstanceState?.getString("folder")

        adapter = VaultAdapter(::open, ::showMenu)
        b.list.layoutManager = LinearLayoutManager(this)
        b.list.adapter = adapter
        b.filters.setOnCheckedStateChangeListener { _, _ -> render() }
        onBackPressedDispatcher.addCallback(this, backInFolder)
        laptopCache().deleteRecursively()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putString("folder", folderId)
    }

    override fun onUnlockedResume() {
        if (!LaptopClient.isLinked(this)) {
            if (!loading) connectDialog()
        } else {
            // Pick up whatever was added on the laptop meanwhile.
            load()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        if (isFinishing) {
            VaultStore.forgetViewOnly()
            laptopCache().deleteRecursively()
        }
    }

    private fun laptopCache() = File(cacheDir, "laptop")

    // ---- loading ----

    private fun load() {
        if (loading) return
        loading = true
        if (!loaded) {
            b.empty.visibility = View.VISIBLE
            b.empty.setText(R.string.laptop_loading)
        }
        lifecycleScope.launch {
            val result = withContext(Dispatchers.IO) {
                try {
                    LaptopClient.index(this@LaptopActivity)
                } catch (e: Exception) {
                    e
                }
            }
            loading = false
            when (result) {
                is LaptopClient.Index -> {
                    laptopName = result.name
                    folders = result.folders
                    items = result.items
                    loaded = true
                    render()
                }
                is LaptopClient.NotAuthorized -> {
                    LaptopClient.unlink(this@LaptopActivity)
                    Toast.makeText(this@LaptopActivity, R.string.laptop_relink, Toast.LENGTH_LONG).show()
                    connectDialog()
                }
                else -> {
                    if (!loaded) {
                        b.empty.visibility = View.VISIBLE
                        b.empty.setText(R.string.laptop_offline)
                    } else {
                        Toast.makeText(this@LaptopActivity, R.string.laptop_offline_short, Toast.LENGTH_SHORT).show()
                    }
                }
            }
        }
    }

    private fun folder(id: String?) = folders.firstOrNull { it.id == id }

    private fun subtree(id: String): Set<String> {
        val out = mutableSetOf(id)
        var grew = true
        while (grew) {
            grew = false
            for (d in folders) if (d.parentId in out && out.add(d.id)) grew = true
        }
        return out
    }

    private fun pathOf(id: String?): String {
        val names = mutableListOf<String>()
        var cur = folder(id)
        while (cur != null) {
            names.add(0, cur.name)
            cur = folder(cur.parentId)
        }
        return names.joinToString(" / ")
    }

    private fun countIn(id: String): Int {
        val ids = subtree(id)
        return items.count { it.folderId in ids }
    }

    private fun sortItems(list: List<VaultItem>): List<VaultItem> =
        when (VaultLock.prefs(this).getInt("sort", 0)) {
            1 -> list.sortedBy { it.added }
            2 -> list.sortedBy { it.name.lowercase() }
            3 -> list.sortedByDescending { it.size }
            else -> list.sortedByDescending { it.added }
        }

    /** Same rules as the phone's own vault screen. */
    private fun visibleItems(): Pair<List<Folder>, List<Pair<VaultItem, String?>>> {
        val filter = b.filters.checkedChipId
        fun passes(it: VaultItem) = when (filter) {
            R.id.chip_video -> it.playable
            R.id.chip_docs -> it.kind == Kind.PDF || it.kind == Kind.TEXT || it.kind == Kind.OTHER
            R.id.chip_images -> it.kind == Kind.IMAGE
            else -> true
        }
        val q = query.trim()
        return when {
            q.isNotEmpty() -> Pair(
                folders.filter { it.name.contains(q, ignoreCase = true) }.sortedBy { it.name.lowercase() },
                sortItems(items.filter { it.name.contains(q, ignoreCase = true) && passes(it) })
                    .map { it to pathOf(it.folderId) },
            )
            filter != R.id.chip_all -> {
                val scope: Set<String?>? = folderId?.let { subtree(it) }
                Pair(
                    emptyList(),
                    sortItems(items.filter { (scope == null || it.folderId in scope) && passes(it) })
                        .map { it to if (it.folderId == folderId) null else pathOf(it.folderId) },
                )
            }
            else -> Pair(
                folders.filter { it.parentId == folderId }.sortedBy { it.name.lowercase() },
                sortItems(items.filter { it.folderId == folderId }).map { it to null },
            )
        }
    }

    private fun render() {
        if (folderId != null && folder(folderId) == null) folderId = null
        val (fs, its) = visibleItems()
        val searching = query.isNotBlank()
        val list = mutableListOf<Entry>()
        fs.forEach { list.add(Entry.FolderEntry(it, countIn(it.id), if (searching) pathOf(it.parentId) else null)) }
        its.forEach { (item, path) -> list.add(Entry.FileEntry(item, path)) }
        adapter.submit(list)
        b.empty.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
        b.empty.setText(if (searching) R.string.empty_search else R.string.laptop_empty)

        val inFolder = folderId != null
        backInFolder.isEnabled = inFolder
        supportActionBar?.title = if (inFolder) folder(folderId)?.name else getString(R.string.laptop)
        supportActionBar?.subtitle = if (inFolder) pathOf(folderId) else laptopName.ifEmpty { null }
    }

    // ---- opening ----

    private fun open(e: Entry) {
        when (e) {
            is Entry.FolderEntry -> {
                folderId = e.folder.id
                if (query.isNotBlank()) {
                    query = ""
                    searchMenuItem?.collapseActionView()
                }
                b.filters.check(R.id.chip_all)
                render()
            }
            is Entry.FileEntry -> openItem(e.item)
        }
    }

    private fun openItem(item: VaultItem) {
        if (item.playable) {
            // The folder's videos play one after another, streamed from the laptop.
            val queue = sortItems(items.filter { it.folderId == item.folderId && it.playable })
            startActivity(
                Intent(this, VideoPlayerActivity::class.java)
                    .putExtra(Viewers.EXTRA_ID, "laptop:" + item.id)
                    .putExtra(VideoPlayerActivity.EXTRA_IDS, queue.map { "laptop:" + it.id }.toTypedArray())
                    .putExtra(VideoPlayerActivity.EXTRA_NAMES, queue.map { it.name }.toTypedArray())
                    .putExtra(VideoPlayerActivity.EXTRA_URLS, queue.map { LaptopClient.fileUrl(this, it.id) }.toTypedArray())
            )
            return
        }
        val dir = laptopCache().apply { mkdirs() }
        val ext = item.name.substringAfterLast('.', "").lowercase()
        val target = File(dir, item.id + if (ext.isNotEmpty() && ext.length <= 6) ".$ext" else "")
        fetch(item, target) {
            val local = VaultItem("laptop:" + item.id, item.name, target.absolutePath, item.mime, item.size, item.added, null)
            VaultStore.viewOnly(local)
            val cls = when (item.kind) {
                Kind.PDF -> PdfViewerActivity::class.java
                Kind.TEXT -> TextViewerActivity::class.java
                Kind.IMAGE -> ImageViewerActivity::class.java
                else -> null
            }
            if (cls == null) Viewers.openWith(this, local)
            else startActivity(Intent(this, cls).putExtra(Viewers.EXTRA_ID, local.id))
        }
    }

    /** Downloads with a progress dialog, then runs [done] on the main thread. */
    private fun fetch(item: VaultItem, target: File, done: () -> Unit) {
        if (target.exists() && target.length() == item.size) {
            done()
            return
        }
        val dialog = MaterialAlertDialogBuilder(this)
            .setTitle(item.name)
            .setMessage(getString(R.string.downloading, 0))
            .setCancelable(false)
            .show()
        lifecycleScope.launch {
            val ok = withContext(Dispatchers.IO) {
                try {
                    LaptopClient.download(this@LaptopActivity, item.id, target) { pct ->
                        runOnUiThread { dialog.setMessage(getString(R.string.downloading, pct)) }
                    }
                    true
                } catch (e: IOException) {
                    false
                }
            }
            dialog.dismiss()
            if (ok) done() else Toast.makeText(this@LaptopActivity, R.string.download_failed, Toast.LENGTH_LONG).show()
        }
    }

    private fun showMenu(e: Entry, anchor: View) {
        if (e !is Entry.FileEntry) return
        val item = e.item
        val popup = PopupMenu(this, anchor)
        popup.menu.add(0, 1, 0, R.string.download_to_phone)
        popup.setOnMenuItemClickListener {
            downloadToPhone(item)
            true
        }
        popup.show()
    }

    private fun downloadToPhone(item: VaultItem) {
        val target = VaultStore.downloadTarget(item.name)
        fetch(item, target) {
            lifecycleScope.launch {
                val kept = VaultStore.adopt(target, item.name, item.mime, null)
                withContext(Dispatchers.IO) { VaultStore.makeThumb(kept) }
                Toast.makeText(this@LaptopActivity, R.string.downloaded_to_phone, Toast.LENGTH_LONG).show()
            }
        }
    }

    // ---- linking ----

    private fun connectDialog() {
        if (linkDialog?.isShowing == true) return
        val pad = (resources.displayMetrics.density * 20).toInt()
        val address = EditText(this).apply {
            setSingleLine()
            hint = getString(R.string.laptop_address)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            setText(LaptopClient.url(this@LaptopActivity)?.removePrefix("http://") ?: "")
        }
        val password = EditText(this).apply {
            setSingleLine()
            hint = getString(R.string.laptop_password)
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad / 2, pad, 0)
            addView(address)
            addView(password)
        }
        val dialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.laptop_link_title)
            .setMessage(R.string.laptop_link_help)
            .setView(box)
            .setPositiveButton(R.string.laptop_connect, null)
            .setNeutralButton(R.string.laptop_find, null)
            .setNegativeButton(R.string.cancel) { _, _ -> finish() }
            .setCancelable(false)
            .show()
        linkDialog = dialog
        dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener { find(address) }
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
            val raw = address.text.toString().trim()
            if (raw.isEmpty()) {
                address.error = getString(R.string.laptop_address)
                return@setOnClickListener
            }
            val url = LaptopClient.normalize(raw)
            val pw = password.text.toString()
            loading = true
            lifecycleScope.launch {
                val r = withContext(Dispatchers.IO) { LaptopClient.login(this@LaptopActivity, url, pw) }
                loading = false
                when (r) {
                    LaptopClient.LoginResult.Ok -> {
                        dialog.dismiss()
                        load()
                    }
                    LaptopClient.LoginResult.Wrong -> password.error = getString(R.string.lock_wrong)
                    is LaptopClient.LoginResult.Wait -> password.error = getString(R.string.lock_wait, r.seconds)
                    LaptopClient.LoginResult.Unreachable -> address.error = getString(R.string.laptop_unreachable)
                }
            }
        }
        if (address.text.isEmpty()) find(address)
    }

    private fun find(address: EditText) {
        Toast.makeText(this, R.string.laptop_searching, Toast.LENGTH_SHORT).show()
        lifecycleScope.launch {
            val found = withContext(Dispatchers.IO) {
                try {
                    LaptopClient.discover()
                } catch (e: Exception) {
                    emptyList()
                }
            }
            if (found.isEmpty()) {
                Toast.makeText(this@LaptopActivity, R.string.laptop_not_found, Toast.LENGTH_LONG).show()
            } else {
                address.setText(found[0].url.removePrefix("http://"))
                address.error = null
            }
        }
    }

    // ---- menu ----

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.laptop_menu, menu)
        searchMenuItem = menu.findItem(R.id.l_search)
        val sv = searchMenuItem?.actionView as SearchView
        sv.queryHint = getString(R.string.search)
        sv.setOnQueryTextListener(object : SearchView.OnQueryTextListener {
            override fun onQueryTextSubmit(q: String?) = true
            override fun onQueryTextChange(q: String?): Boolean {
                query = q ?: ""
                render()
                return true
            }
        })
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        when (item.itemId) {
            R.id.l_refresh -> load()
            R.id.l_unlink -> {
                LaptopClient.unlink(this)
                folders = emptyList()
                items = emptyList()
                loaded = false
                render()
                connectDialog()
            }
            else -> return super.onOptionsItemSelected(item)
        }
        return true
    }
}
