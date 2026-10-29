package com.saudi.privatevault

import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.lifecycle.lifecycleScope
import com.saudi.privatevault.databinding.ActivityImageBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class ImageViewerActivity : BaseActivity() {

    companion object {
        const val EXTRA_IDS = "item_ids"
    }

    private lateinit var b: ActivityImageBinding
    private var ids: List<String> = emptyList()
    private var index = 0

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityImageBinding.inflate(layoutInflater)
        setContentView(b.root)
        val id = intent.getStringExtra(Viewers.EXTRA_ID) ?: return finish()
        ids = intent.getStringArrayExtra(EXTRA_IDS)?.toList()?.takeIf { id in it } ?: listOf(id)
        index = savedInstanceState?.getInt("index") ?: ids.indexOf(id)

        b.image.onSwipe = { dir -> go(index + dir) }
        b.image.onTap = {
            b.caption.visibility = if (b.caption.visibility == View.VISIBLE) View.GONE else View.VISIBLE
        }
        WindowCompat.getInsetsController(window, window.decorView).apply {
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            hide(WindowInsetsCompat.Type.systemBars())
        }
        show()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putInt("index", index)
    }

    private fun go(i: Int) {
        if (i < 0 || i >= ids.size || i == index) return
        index = i
        show()
    }

    private fun show() {
        val item = VaultStore.item(ids.getOrNull(index)) ?: return finish()
        b.caption.text = if (ids.size > 1) "${item.name}  (${index + 1}/${ids.size})" else item.name
        val maxSide = maxOf(resources.displayMetrics.widthPixels, resources.displayMetrics.heightPixels) * 2
        lifecycleScope.launch {
            val bmp = withContext(Dispatchers.IO) {
                try {
                    VaultStore.decodeSampled(VaultStore.fileOf(item), maxSide.coerceAtMost(4096))
                } catch (e: Throwable) {
                    null
                }
            }
            if (bmp == null) {
                Toast.makeText(this@ImageViewerActivity, R.string.open_failed, Toast.LENGTH_SHORT).show()
            } else if (ids.getOrNull(index) == item.id) {
                b.image.setImageBitmap(bmp)
            }
        }
    }
}
