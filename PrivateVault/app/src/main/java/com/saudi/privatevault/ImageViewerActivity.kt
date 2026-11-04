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

    // The remote on a TV: left / right the next photo (or move about a zoomed one),
    // OK zooms (whole, 2×, 3×), up / down move a zoomed photo, Back shows it whole first.
    private var zoomStep = 0

    override fun dispatchKeyEvent(event: android.view.KeyEvent): Boolean {
        if (!Tv.isTv(this)) return super.dispatchKeyEvent(event)
        if (event.action != android.view.KeyEvent.ACTION_DOWN) return if (event.keyCode == android.view.KeyEvent.KEYCODE_BACK && zoomStep == 0) super.dispatchKeyEvent(event) else true
        val v = b.image
        val sx = v.width * 0.45f; val sy = v.height * 0.5f
        when (event.keyCode) {
            android.view.KeyEvent.KEYCODE_DPAD_CENTER, android.view.KeyEvent.KEYCODE_ENTER -> {
                zoomStep = (zoomStep + 1) % 3
                if (zoomStep == 0) v.fit() else v.zoomKeep(if (zoomStep == 1) 2f else 3f)
            }
            android.view.KeyEvent.KEYCODE_DPAD_RIGHT -> if (v.zoomed() && !v.atRight()) v.panSmooth(-sx, 0f) else { zoomStep = 0; go(index + 1) }
            android.view.KeyEvent.KEYCODE_DPAD_LEFT -> if (v.zoomed() && !v.atLeft()) v.panSmooth(sx, 0f) else { zoomStep = 0; go(index - 1) }
            android.view.KeyEvent.KEYCODE_DPAD_DOWN -> if (v.zoomed()) v.panSmooth(0f, -sy)
            android.view.KeyEvent.KEYCODE_DPAD_UP -> if (v.zoomed()) v.panSmooth(0f, sy)
            android.view.KeyEvent.KEYCODE_BACK -> if (zoomStep != 0 || v.zoomed()) { zoomStep = 0; v.fit() } else return super.dispatchKeyEvent(event)
            else -> return super.dispatchKeyEvent(event)
        }
        return true
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
