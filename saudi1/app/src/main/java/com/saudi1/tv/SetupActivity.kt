package com.saudi1.tv

import android.os.Bundle
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class SetupActivity : AppCompatActivity() {
    private lateinit var codeStatus: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_setup)
        val server = findViewById<EditText>(R.id.server)
        val user = findViewById<EditText>(R.id.user)
        val pass = findViewById<EditText>(R.id.pass)
        val msg = findViewById<TextView>(R.id.msg)
        codeStatus = findViewById(R.id.codeStatus)
        findViewById<TextView>(R.id.code).text = Device.pretty
        if (Device.manual) { server.setText(Prefs.server); user.setText(Prefs.user); pass.setText(Prefs.pass) }
        else server.setText("https://")

        val reload = findViewById<TextView>(R.id.reload)
        reload.setTextColor(getColorStateList(R.color.on_focus))
        reload.setOnClickListener { lifecycleScope.launch { activate(true) } }

        val save = findViewById<TextView>(R.id.save)
        save.setTextColor(getColorStateList(R.color.on_focus))
        save.setOnClickListener {
            var s = server.text.toString().trim()
            if (!s.startsWith("http")) s = "http://$s"
            Prefs.server = s; Prefs.user = user.text.toString(); Prefs.pass = pass.text.toString()
            msg.text = "Checking…"
            lifecycleScope.launch {
                val r = withContext(Dispatchers.IO) {
                    try {
                        if (!Api.login()) "Wrong username or password"
                        else if (Api.load(cached = false)) "" else "Could not load the channels"
                    } catch (e: Exception) { "Could not reach the server" }
                }
                if (r.isEmpty()) { Device.manual = true; finish() } else msg.text = r
            }
        }
        // a promo code from the owner: spent on this device (once), the owner then sees the device marked with it
        val promo = findViewById<TextView>(R.id.promo)
        promo.setTextColor(getColorStateList(R.color.on_focus))
        promo.setOnClickListener {
            val e = EditText(this).apply { hint = "XXXX-XXXX"; gravity = android.view.Gravity.CENTER; textSize = 26f
                inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS or android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
                filters = arrayOf(android.text.InputFilter.LengthFilter(9)) }
            androidx.appcompat.app.AlertDialog.Builder(this).setTitle("Promo code").setView(e)
                .setPositiveButton("OK") { _, _ ->
                    codeStatus.text = "Checking the promo code…"
                    lifecycleScope.launch {
                        val r = withContext(Dispatchers.IO) { Device.promo(e.text.toString()) }
                        codeStatus.text = if (r.isEmpty()) "Promo code accepted ✓  Your provider will finish the activation — this screen opens by itself." else r
                        if (r.isEmpty()) promo.text = "🎟  Promo code accepted ✓"
                    }
                }.setNegativeButton("Cancel", null).show()
            e.requestFocus()
        }
        if (App.prefs.getBoolean("promo_ok", false)) promo.text = "🎟  Promo code accepted ✓"
        reload.requestFocus()
        // the owner may add this device any moment: check every 10 seconds while this screen is open
        lifecycleScope.launch { while (isActive) { activate(false); delay(10_000) } }
    }

    private suspend fun activate(byHand: Boolean) {
        if (byHand) codeStatus.text = "Checking…"
        val st = withContext(Dispatchers.IO) { Device.check() }
        when (st) {
            "active" -> {
                codeStatus.text = "Activated ✓  Loading channels…"
                val ok = withContext(Dispatchers.IO) { try { Api.load(cached = false) } catch (e: Exception) { false } }
                if (ok) finish() else codeStatus.text = "Activated, but the channels could not load. Press Reload."
            }
            "stopped" -> codeStatus.text = "This device is stopped. Contact your provider."
            "expired" -> codeStatus.text = "Your subscription has ended. Contact your provider."
            "offline" -> codeStatus.text = "No internet connection"
            else -> if (!codeStatus.text.startsWith("Promo code accepted") || byHand) codeStatus.text = if (App.prefs.getBoolean("promo_ok", false)) "Promo code accepted ✓  Waiting for your provider to finish the activation…" else "Waiting for activation…"
        }
    }
}
