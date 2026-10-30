package com.saudi.privatevault

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.DocumentsContract
import android.text.format.DateFormat
import android.text.format.Formatter
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.widget.PopupMenu
import androidx.appcompat.widget.SearchView
import androidx.biometric.BiometricManager
import androidx.core.content.FileProvider
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.saudi.privatevault.databinding.ActivityMainBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.Date

class MainActivity : BaseActivity() {

    private lateinit var b: ActivityMainBinding
    private lateinit var adapter: VaultAdapter

    private var folderId: String? = null
    private var query = ""
    private var importing = false
    private var pendingShared: List<Uri> = emptyList()
    private var exportItem: VaultItem? = null

    private val backInFolder = object : OnBackPressedCallback(false) {
        override fun handleOnBackPressed() {
            folderId = VaultStore.folder(folderId)?.parentId
            refresh()
        }
    }

    private val pickFiles = registerForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        if (uris.isNotEmpty()) askCopyOrMove(uris, canDelete = true)
    }

    private val exportFile = registerForActivityResult(ActivityResultContracts.CreateDocument("*/*")) { uri ->
        val item = exportItem
        exportItem = null
        if (uri != null && item != null) export(item, uri)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityMainBinding.inflate(layoutInflater)
        setContentView(b.root)
        setSupportActionBar(b.toolbar)
        b.toolbar.setNavigationOnClickListener { onBackPressedDispatcher.onBackPressed() }

        folderId = savedInstanceState?.getString("folder")
        adapter = VaultAdapter(::open, ::showMenu)
        b.list.layoutManager = LinearLayoutManager(this)
        b.list.adapter = adapter
        b.filters.setOnCheckedStateChangeListener { _, _ -> refresh() }
        b.fab.setOnClickListener { showAddMenu() }
        onBackPressedDispatcher.addCallback(this, backInFolder)
        takeShared(intent)
        refresh()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        takeShared(intent)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putString("folder", folderId)
    }

    override fun onUnlockedResume() {
        refresh()
        Updater.checkQuietly(this)
        // Files shared from another app are only taken in once the PIN is entered.
        if (pendingShared.isNotEmpty() && !importing) {
            val uris = pendingShared
            pendingShared = emptyList()
            askCopyOrMove(uris, canDelete = false)
        }
    }

    private fun takeShared(intent: Intent?) {
        intent ?: return
        val uris = when (intent.action) {
            Intent.ACTION_SEND -> listOfNotNull(intent.streamExtra())
            Intent.ACTION_SEND_MULTIPLE -> intent.streamListExtra()
            else -> emptyList()
        }
        if (uris.isNotEmpty()) pendingShared = uris
        intent.action = null
    }

    @Suppress("DEPRECATION")
    private fun Intent.streamExtra(): Uri? =
        if (Build.VERSION.SDK_INT >= 33) getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
        else getParcelableExtra(Intent.EXTRA_STREAM)

    @Suppress("DEPRECATION")
    private fun Intent.streamListExtra(): List<Uri> =
        (if (Build.VERSION.SDK_INT >= 33) getParcelableArrayListExtra(Intent.EXTRA_STREAM, Uri::class.java)
        else getParcelableArrayListExtra<Uri>(Intent.EXTRA_STREAM)) ?: emptyList()

    // ---- list ----

    private fun refresh() {
        if (folderId != null && VaultStore.folder(folderId) == null) folderId = null
        val searching = query.isNotBlank()
        val filter = b.filters.checkedChipId
        fun passes(it: VaultItem) = when (filter) {
            R.id.chip_video -> it.kind == Kind.VIDEO || it.kind == Kind.AUDIO
            R.id.chip_docs -> it.kind == Kind.PDF || it.kind == Kind.TEXT || it.kind == Kind.OTHER
            R.id.chip_images -> it.kind == Kind.IMAGE
            else -> true
        }

        val list = mutableListOf<Entry>()
        if (searching) {
            val q = query.trim()
            VaultStore.folders.filter { it.name.contains(q, ignoreCase = true) }
                .sortedWith(compareBy(NaturalOrder) { it.name })
                .forEach { list.add(Entry.FolderEntry(it, VaultStore.countIn(it.id), VaultStore.pathOf(it.parentId))) }
            sortItems(VaultStore.items.filter { it.name.contains(q, ignoreCase = true) && passes(it) })
                .forEach { list.add(Entry.FileEntry(it, VaultStore.pathOf(it.folderId))) }
        } else {
            // A type filter shows every match in this folder and below it, so
            // "videos" at the top level means all videos in the vault.
            val scoped = filter != R.id.chip_all
            if (!scoped) {
                VaultStore.childFolders(folderId).sortedWith(compareBy(NaturalOrder) { it.name })
                    .forEach { list.add(Entry.FolderEntry(it, VaultStore.countIn(it.id), null)) }
                sortItems(VaultStore.itemsIn(folderId)).forEach { list.add(Entry.FileEntry(it, null)) }
            } else {
                val ids: Set<String?> = folderId?.let { VaultStore.subtree(it) } ?: (VaultStore.folders.map { it.id } + listOf<String?>(null)).toSet()
                sortItems(VaultStore.items.filter { it.folderId in ids && passes(it) })
                    .forEach { list.add(Entry.FileEntry(it, if (it.folderId == folderId) null else VaultStore.pathOf(it.folderId))) }
            }
        }
        adapter.submit(list)
        b.empty.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
        b.empty.setText(if (searching) R.string.empty_search else R.string.empty)

        val inFolder = folderId != null
        backInFolder.isEnabled = inFolder
        supportActionBar?.title = if (inFolder) VaultStore.folder(folderId)?.name else getString(R.string.app_name)
        supportActionBar?.subtitle = if (inFolder) VaultStore.pathOf(folderId) else null
        if (inFolder) b.toolbar.setNavigationIcon(R.drawable.ic_back) else b.toolbar.navigationIcon = null
    }

    private fun sortItems(list: List<VaultItem>): List<VaultItem> =
        when (VaultLock.prefs(this).getInt("sort_v2", SORT_DEFAULT)) {
            1 -> list.sortedBy { it.added }
            2 -> list.sortedWith(compareBy(NaturalOrder) { it.name })
            3 -> list.sortedByDescending { it.size }
            else -> list.sortedByDescending { it.added }
        }

    private fun open(e: Entry) {
        when (e) {
            is Entry.FolderEntry -> {
                folderId = e.folder.id
                if (query.isNotBlank()) clearSearch()
                b.filters.check(R.id.chip_all)
                refresh()
            }
            is Entry.FileEntry -> openItem(e.item)
        }
    }

    private fun openItem(item: VaultItem) {
        val cls = when (item.kind) {
            Kind.VIDEO, Kind.AUDIO -> VideoPlayerActivity::class.java
            Kind.PDF -> PdfViewerActivity::class.java
            Kind.TEXT -> TextViewerActivity::class.java
            Kind.IMAGE -> ImageViewerActivity::class.java
            Kind.OTHER -> null
        }
        if (cls == null) {
            openWith(item)
            return
        }
        val intent = Intent(this, cls).putExtra(Viewers.EXTRA_ID, item.id)
        if (item.kind == Kind.IMAGE) {
            // Swipe between the pictures of the same folder.
            val images = sortItems(VaultStore.itemsIn(item.folderId).filter { it.kind == Kind.IMAGE })
            intent.putExtra(ImageViewerActivity.EXTRA_IDS, images.map { it.id }.toTypedArray())
        } else if (item.playable) {
            // The rest of the folder's videos play one after another, in the order shown.
            val queue = sortItems(VaultStore.itemsIn(item.folderId).filter { it.playable })
            intent.putExtra(VideoPlayerActivity.EXTRA_IDS, queue.map { it.id }.toTypedArray())
        }
        startActivity(intent)
    }

    private fun openWith(item: VaultItem) = Viewers.openWith(this, item)

    // ---- menus ----

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.main_menu, menu)
        val searchItem = menu.findItem(R.id.action_search)
        val sv = searchItem.actionView as SearchView
        sv.queryHint = getString(R.string.search)
        sv.setOnQueryTextListener(object : SearchView.OnQueryTextListener {
            override fun onQueryTextSubmit(q: String?) = true
            override fun onQueryTextChange(q: String?): Boolean {
                query = q ?: ""
                refresh()
                return true
            }
        })
        menu.findItem(R.id.action_biometric).isChecked = VaultLock.biometricEnabled(this)
        return true
    }

    private var searchMenuItem: MenuItem? = null

    override fun onPrepareOptionsMenu(menu: Menu): Boolean {
        searchMenuItem = menu.findItem(R.id.action_search)
        menu.findItem(R.id.action_biometric).isChecked = VaultLock.biometricEnabled(this)
        menu.findItem(R.id.action_screenshots)?.isChecked = VaultLock.blockScreenshots(this)
        return super.onPrepareOptionsMenu(menu)
    }

    private fun clearSearch() {
        query = ""
        searchMenuItem?.collapseActionView()
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        when (item.itemId) {
            R.id.action_laptop -> startActivity(Intent(this, LaptopActivity::class.java))
            R.id.action_map -> startActivity(Intent(this, EfbHomeActivity::class.java))
            R.id.action_sort -> chooseSort()
            R.id.action_biometric -> toggleBiometric(item)
            R.id.action_change_pin -> startActivity(
                Intent(this, LockActivity::class.java).putExtra(LockActivity.EXTRA_CHANGE, true)
            )
            R.id.action_storage -> MaterialAlertDialogBuilder(this)
                .setTitle(R.string.storage_info)
                .setMessage(
                    Formatter.formatFileSize(this, VaultStore.totalBytes()) + "\n" +
                        getString(R.string.items_count, VaultStore.items.size)
                )
                .setPositiveButton(android.R.string.ok, null)
                .show()
            R.id.action_update -> Updater.check(this, quiet = false)
            R.id.action_lock_after -> chooseLockAfter()
            R.id.action_screenshots -> {
                val block = !VaultLock.blockScreenshots(this)
                VaultLock.prefs(this).edit().putBoolean("block_screenshots", block).apply()
                item.isChecked = block
                VaultLock.applySecure(this)
            }
            R.id.action_lock -> {
                VaultLock.unlocked = false
                startActivity(Intent(this, LockActivity::class.java))
            }
            else -> return super.onOptionsItemSelected(item)
        }
        return true
    }

    private fun chooseLockAfter() {
        val labels = resources.getStringArray(R.array.lock_after_labels)
        val current = VaultLock.LOCK_AFTER.indexOf(VaultLock.lockAfter(this)).coerceAtLeast(0)
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.lock_after)
            .setSingleChoiceItems(labels, current) { d, which ->
                VaultLock.prefs(this).edit().putLong("lock_after", VaultLock.LOCK_AFTER[which]).apply()
                d.dismiss()
            }
            .show()
    }

    private fun chooseSort() {
        val labels = arrayOf(
            getString(R.string.sort_newest), getString(R.string.sort_oldest),
            getString(R.string.sort_name), getString(R.string.sort_size),
        )
        val current = VaultLock.prefs(this).getInt("sort_v2", SORT_DEFAULT)
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.sort)
            .setSingleChoiceItems(labels, current) { d, which ->
                VaultLock.prefs(this).edit().putInt("sort_v2", which).apply()
                d.dismiss()
                refresh()
            }
            .show()
    }

    private fun toggleBiometric(item: MenuItem) {
        val turnOn = !VaultLock.biometricEnabled(this)
        if (turnOn && BiometricManager.from(this)
                .canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_WEAK) != BiometricManager.BIOMETRIC_SUCCESS
        ) {
            Toast.makeText(this, R.string.biometric_unavailable, Toast.LENGTH_LONG).show()
            return
        }
        VaultLock.setBiometricEnabled(this, turnOn)
        item.isChecked = turnOn
    }

    private fun showAddMenu() {
        val labels = arrayOf(getString(R.string.add_files), getString(R.string.add_link), getString(R.string.new_folder))
        MaterialAlertDialogBuilder(this)
            .setItems(labels) { _, which ->
                when (which) {
                    0 -> {
                        VaultLock.keepUnlockedOnce = true
                        pickFiles.launch(arrayOf("*/*"))
                    }
                    1 -> askLink()
                    else -> askName(getString(R.string.new_folder), "") { name ->
                        VaultStore.addFolder(name, folderId)
                        refresh()
                    }
                }
            }
            .show()
    }

    private fun showMenu(e: Entry, anchor: View) {
        val popup = PopupMenu(this, anchor)
        when (e) {
            is Entry.FolderEntry -> {
                popup.menuInflater.inflate(R.menu.folder_menu, popup.menu)
                popup.setOnMenuItemClickListener { mi ->
                    when (mi.itemId) {
                        R.id.d_rename -> askName(getString(R.string.rename), e.folder.name) {
                            e.folder.name = it
                            VaultStore.save()
                            refresh()
                        }
                        R.id.d_move -> chooseFolder(exclude = VaultStore.subtree(e.folder.id)) { target ->
                            e.folder.parentId = target
                            VaultStore.save()
                            refresh()
                        }
                        R.id.d_delete -> confirm(getString(R.string.delete_folder_confirm, e.folder.name)) {
                            VaultStore.deleteFolder(e.folder.id)
                            refresh()
                        }
                    }
                    true
                }
            }
            is Entry.FileEntry -> {
                val item = e.item
                popup.menuInflater.inflate(R.menu.file_menu, popup.menu)
                popup.menu.findItem(R.id.f_export).isVisible = !item.isLink
                popup.setOnMenuItemClickListener { mi ->
                    when (mi.itemId) {
                        R.id.f_open_with -> openWith(item)
                        R.id.f_rename -> askName(getString(R.string.rename), item.name) {
                            item.name = it
                            VaultStore.save()
                            refresh()
                        }
                        R.id.f_move -> chooseFolder(exclude = emptySet()) { target ->
                            item.folderId = target
                            VaultStore.save()
                            refresh()
                        }
                        R.id.f_export -> {
                            exportItem = item
                            VaultLock.keepUnlockedOnce = true
                            exportFile.launch(item.name)
                        }
                        R.id.f_details -> showDetails(item)
                        R.id.f_delete -> confirm(getString(R.string.delete_confirm, item.name)) {
                            adapter.forget(item.id)
                            VaultStore.deleteItem(item)
                            refresh()
                        }
                    }
                    true
                }
            }
        }
        popup.show()
    }

    private fun showDetails(item: VaultItem) {
        val date = DateFormat.getDateFormat(this).format(Date(item.added)) + " " +
            DateFormat.getTimeFormat(this).format(Date(item.added))
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.details)
            .setMessage(
                getString(
                    R.string.details_text, item.name, item.mime.ifEmpty { "—" },
                    item.url ?: Formatter.formatFileSize(this, item.size), date
                )
            )
            .setPositiveButton(android.R.string.ok, null)
            .show()
    }

    // ---- dialogs ----

    private fun askName(title: String, initial: String, done: (String) -> Unit) {
        val input = EditText(this).apply {
            setText(initial)
            setSingleLine()
            setSelection(text.length)
            hint = getString(R.string.folder_name)
        }
        val pad = (resources.displayMetrics.density * 20).toInt()
        val box = FrameLayout(this).apply {
            setPadding(pad, pad / 2, pad, 0)
            addView(input)
        }
        MaterialAlertDialogBuilder(this)
            .setTitle(title)
            .setView(box)
            .setPositiveButton(R.string.ok) { _, _ ->
                val name = input.text.toString().trim()
                if (name.isNotEmpty()) done(name)
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun askLink() {
        val pad = (resources.displayMetrics.density * 20).toInt()
        val nameInput = EditText(this).apply {
            setSingleLine()
            hint = getString(R.string.link_name)
        }
        val urlInput = EditText(this).apply {
            setSingleLine()
            hint = getString(R.string.link_url)
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_URI
        }
        val box = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(pad, pad / 2, pad, 0)
            addView(urlInput)
            addView(nameInput)
        }
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.add_link)
            .setMessage(R.string.link_help)
            .setView(box)
            .setPositiveButton(R.string.ok) { _, _ ->
                val url = urlInput.text.toString().trim()
                if (!url.startsWith("http://") && !url.startsWith("https://")) {
                    Toast.makeText(this, R.string.link_invalid, Toast.LENGTH_LONG).show()
                    return@setPositiveButton
                }
                val fallback = Uri.decode(Uri.parse(url).lastPathSegment ?: "").ifEmpty { url }
                val name = nameInput.text.toString().trim().ifEmpty { fallback }
                VaultStore.addLink(name, url, folderId)
                refresh()
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    private fun confirm(message: String, yes: () -> Unit) {
        MaterialAlertDialogBuilder(this)
            .setMessage(message)
            .setPositiveButton(R.string.delete) { _, _ -> yes() }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    /** Pick a destination folder; null means the top level. */
    private fun chooseFolder(exclude: Set<String>, done: (String?) -> Unit) {
        val targets = listOf<Folder?>(null) + VaultStore.folders.filter { it.id !in exclude }
            .sortedWith(compareBy(NaturalOrder) { VaultStore.pathOf(it.id) })
        val labels = targets.map { if (it == null) getString(R.string.root) else VaultStore.pathOf(it.id) }
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.move)
            .setItems(labels.toTypedArray()) { _, which -> done(targets[which]?.id) }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    // ---- import / export ----

    private fun askCopyOrMove(uris: List<Uri>, canDelete: Boolean) {
        if (!canDelete) {
            runImport(uris, deleteOriginals = false)
            return
        }
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.import_title)
            .setMessage(R.string.import_msg)
            .setPositiveButton(R.string.import_move) { _, _ -> runImport(uris, deleteOriginals = true) }
            .setNegativeButton(R.string.import_copy) { _, _ -> runImport(uris, deleteOriginals = false) }
            .setCancelable(false)
            .show()
    }

    private fun runImport(uris: List<Uri>, deleteOriginals: Boolean) {
        importing = true
        val target = folderId
        val progress = MaterialAlertDialogBuilder(this)
            .setMessage(getString(R.string.importing, 0, uris.size))
            .setCancelable(false)
            .show()
        lifecycleScope.launch {
            var added = 0
            var failed = 0
            var notDeleted = 0
            for ((i, uri) in uris.withIndex()) {
                progress.setMessage(getString(R.string.importing, i + 1, uris.size))
                val item = withContext(Dispatchers.IO) { VaultStore.copyIn(this@MainActivity, uri, target) }
                if (item == null) {
                    failed++
                    continue
                }
                VaultStore.items.add(item)
                VaultStore.save()
                added++
                if (deleteOriginals) {
                    val gone = withContext(Dispatchers.IO) {
                        try {
                            DocumentsContract.deleteDocument(contentResolver, uri)
                        } catch (e: Exception) {
                            false
                        }
                    }
                    if (!gone) notDeleted++
                }
                refresh()
            }
            progress.dismiss()
            importing = false
            refresh()
            val msg = buildList {
                if (added > 0) add(getString(R.string.import_done, added))
                if (failed > 0) add(getString(R.string.import_failed, failed))
                if (notDeleted > 0) add(getString(R.string.import_not_deleted, notDeleted))
            }.joinToString("\n")
            if (msg.isNotEmpty()) Toast.makeText(this@MainActivity, msg, Toast.LENGTH_LONG).show()
        }
    }

    private fun export(item: VaultItem, uri: Uri) {
        lifecycleScope.launch {
            val ok = withContext(Dispatchers.IO) {
                try {
                    contentResolver.openOutputStream(uri)?.use { out ->
                        VaultStore.fileOf(item).inputStream().use { it.copyTo(out, 256 * 1024) }
                    } != null
                } catch (e: Exception) {
                    false
                }
            }
            Toast.makeText(this@MainActivity, if (ok) R.string.exported else R.string.export_failed, Toast.LENGTH_SHORT)
                .show()
        }
    }
}

object Viewers {
    const val EXTRA_ID = "item_id"

    /** Hand the file to another installed app (Word, WPS, a different player…). */
    fun openWith(activity: android.app.Activity, item: VaultItem) {
        val uri = item.url?.let { Uri.parse(it) }
            ?: FileProvider.getUriForFile(activity, activity.packageName + ".files", VaultStore.fileOf(item))
        val mime = item.mime.ifEmpty { "*/*" }
        val view = Intent(Intent.ACTION_VIEW).setDataAndType(uri, mime)
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        try {
            VaultLock.keepUnlockedOnce = true
            activity.startActivity(Intent.createChooser(view, item.name))
        } catch (e: ActivityNotFoundException) {
            VaultLock.keepUnlockedOnce = false
            Toast.makeText(activity, R.string.no_app, Toast.LENGTH_SHORT).show()
        }
    }
}
