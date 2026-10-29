package com.saudi.privatevault

import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.GridLayout
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import com.google.android.material.button.MaterialButton
import com.saudi.privatevault.databinding.ActivityLockBinding

class LockActivity : AppCompatActivity() {

    companion object {
        const val EXTRA_CHANGE = "change_pin"
        private const val MIN_LEN = 4
        private const val MAX_LEN = 8
    }

    private lateinit var b: ActivityLockBinding
    private val handler = Handler(Looper.getMainLooper())
    private val entered = StringBuilder()

    // Creating a PIN takes two passes: choose it, then type it again.
    private var setupMode = false
    private var firstPin: String? = null
    private var biometricShown = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
        b = ActivityLockBinding.inflate(layoutInflater)
        setContentView(b.root)

        val changing = intent.getBooleanExtra(EXTRA_CHANGE, false)
        setupMode = changing || !VaultLock.hasPin(this)
        b.title.setText(if (setupMode) R.string.lock_create else R.string.lock_enter)
        buildKeypad()
        updateDots()

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                // Changing the PIN can be cancelled; the lock screen itself cannot be skipped.
                if (changing) finish() else finishAffinity()
            }
        })
    }

    override fun onResume() {
        super.onResume()
        if (!setupMode && !biometricShown && canUseBiometric()) {
            biometricShown = true
            showBiometric()
        }
    }

    private fun buildKeypad() {
        val keys = listOf("1", "2", "3", "4", "5", "6", "7", "8", "9", "extra", "0", "del")
        val size = (resources.displayMetrics.density * 76).toInt()
        val margin = (resources.displayMetrics.density * 8).toInt()
        for (key in keys) {
            val btn = MaterialButton(this, null, com.google.android.material.R.attr.materialButtonOutlinedStyle)
            btn.insetTop = 0
            btn.insetBottom = 0
            btn.cornerRadius = size / 2
            btn.gravity = Gravity.CENTER
            btn.setPadding(0, 0, 0, 0)
            btn.iconPadding = 0
            btn.iconGravity = MaterialButton.ICON_GRAVITY_TEXT_START
            when (key) {
                "del" -> {
                    btn.setIconResource(R.drawable.ic_backspace)
                    btn.setOnClickListener {
                        if (entered.isNotEmpty()) entered.deleteCharAt(entered.length - 1)
                        updateDots()
                    }
                    btn.setOnLongClickListener { entered.clear(); updateDots(); true }
                }
                "extra" -> {
                    if (setupMode) {
                        btn.setIconResource(R.drawable.ic_check)
                        btn.setOnClickListener { submitSetup() }
                    } else if (VaultLock.biometricEnabled(this)) {
                        btn.setIconResource(R.drawable.ic_fingerprint)
                        btn.setOnClickListener { if (canUseBiometric()) showBiometric() }
                    } else {
                        btn.visibility = View.INVISIBLE
                    }
                }
                else -> {
                    btn.text = key
                    btn.textSize = 24f
                    btn.setOnClickListener { press(key) }
                }
            }
            val lp = GridLayout.LayoutParams().apply {
                width = size
                height = size
                setMargins(margin, margin, margin, margin)
            }
            b.keypad.addView(btn, lp)
        }
    }

    private fun press(digit: String) {
        if (entered.length >= MAX_LEN) return
        val wait = if (setupMode) 0 else VaultLock.waitSeconds(this)
        if (wait > 0) {
            b.error.text = getString(R.string.lock_wait, wait)
            return
        }
        entered.append(digit)
        b.error.text = ""
        updateDots()
        if (!setupMode && entered.length == VaultLock.pinLength(this)) {
            checkUnlock()
        }
    }

    private fun checkUnlock() {
        if (VaultLock.checkPin(this, entered.toString())) {
            unlock()
        } else {
            entered.clear()
            val wait = VaultLock.waitSeconds(this)
            b.error.text = if (wait > 0) getString(R.string.lock_wait, wait) else getString(R.string.lock_wrong)
            b.dots.animate().translationX(24f).setDuration(60).withEndAction {
                b.dots.animate().translationX(0f).setDuration(60).start()
            }.start()
            handler.postDelayed({ updateDots() }, 150)
        }
    }

    private fun submitSetup() {
        val pin = entered.toString()
        if (pin.length < MIN_LEN) {
            b.error.setText(R.string.lock_short)
            return
        }
        val first = firstPin
        if (first == null) {
            firstPin = pin
            entered.clear()
            b.title.setText(R.string.lock_confirm)
            b.error.text = ""
        } else if (first == pin) {
            VaultLock.setPin(this, pin)
            Toast.makeText(this, R.string.lock_saved, Toast.LENGTH_SHORT).show()
            unlock()
        } else {
            firstPin = null
            entered.clear()
            b.title.setText(R.string.lock_create)
            b.error.setText(R.string.lock_mismatch)
        }
        updateDots()
    }

    private fun updateDots() {
        val total = if (setupMode) maxOf(MIN_LEN, entered.length) else VaultLock.pinLength(this)
        val sb = StringBuilder()
        for (i in 0 until total) sb.append(if (i < entered.length) '●' else '○')
        b.dots.text = sb.toString()
    }

    private fun unlock() {
        VaultLock.unlocked = true
        finish()
        overridePendingTransition(0, 0)
    }

    private fun canUseBiometric(): Boolean =
        VaultLock.biometricEnabled(this) &&
            BiometricManager.from(this).canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_WEAK) ==
            BiometricManager.BIOMETRIC_SUCCESS

    private fun showBiometric() {
        val prompt = BiometricPrompt(this, ContextCompat.getMainExecutor(this),
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    unlock()
                }
            })
        val info = BiometricPrompt.PromptInfo.Builder()
            .setTitle(getString(R.string.biometric_title))
            .setNegativeButtonText(getString(R.string.biometric_use_pin))
            .setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_WEAK)
            .build()
        prompt.authenticate(info)
    }
}
