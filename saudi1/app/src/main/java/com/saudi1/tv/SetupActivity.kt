package com.saudi1.tv

import android.os.Bundle
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class SetupActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_setup)
        val server = findViewById<EditText>(R.id.server)
        val user = findViewById<EditText>(R.id.user)
        val pass = findViewById<EditText>(R.id.pass)
        val msg = findViewById<TextView>(R.id.msg)
        server.setText(Prefs.server.ifEmpty { "https://" })
        user.setText(Prefs.user); pass.setText(Prefs.pass)
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
                if (r.isEmpty()) finish() else msg.text = r
            }
        }
        (if (Prefs.ready) save else server).requestFocus()
    }
}
