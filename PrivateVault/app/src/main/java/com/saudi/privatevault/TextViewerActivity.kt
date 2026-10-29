package com.saudi.privatevault

import android.os.Bundle
import androidx.lifecycle.lifecycleScope
import com.saudi.privatevault.databinding.ActivityTextBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class TextViewerActivity : BaseActivity() {

    private lateinit var b: ActivityTextBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityTextBinding.inflate(layoutInflater)
        setContentView(b.root)
        val item = VaultStore.item(intent.getStringExtra(Viewers.EXTRA_ID)) ?: return finish()
        b.toolbar.title = item.name
        b.toolbar.setNavigationOnClickListener { finish() }
        b.toolbar.inflateMenu(R.menu.viewer_menu)
        b.toolbar.setOnMenuItemClickListener { Viewers.openWith(this, item); true }
        lifecycleScope.launch {
            val text = withContext(Dispatchers.IO) {
                try {
                    // Very large files are cut at 2 MB to keep the screen responsive.
                    VaultStore.fileOf(item).inputStream().use { inp ->
                        val buf = ByteArray(2 * 1024 * 1024)
                        var n = 0
                        while (n < buf.size) {
                            val r = inp.read(buf, n, buf.size - n)
                            if (r < 0) break
                            n += r
                        }
                        String(buf, 0, n, Charsets.UTF_8)
                    }
                } catch (e: Exception) {
                    getString(R.string.open_failed)
                }
            }
            b.text.text = text
        }
    }
}
