package com.saudi.privatevault

import android.content.Context
import android.content.SharedPreferences
import android.util.Base64
import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.PBEKeySpec

object VaultLock {
    @Volatile
    var unlocked = false

    // Set right before handing off to the system file picker or another
    // app, so coming back from it does not ask for the PIN again.
    @Volatile
    var keepUnlockedOnce = false

    private const val PREFS = "vault_prefs"
    private const val ITERATIONS = 20_000
    private const val MAX_TRIES = 5
    private const val LOCKOUT_MS = 30_000L

    fun prefs(ctx: Context): SharedPreferences =
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun hasPin(ctx: Context) = prefs(ctx).contains("pin_hash")

    fun pinLength(ctx: Context) = prefs(ctx).getInt("pin_len", 0)

    fun setPin(ctx: Context, pin: String) {
        val salt = ByteArray(16).also { SecureRandom().nextBytes(it) }
        prefs(ctx).edit()
            .putString("pin_salt", Base64.encodeToString(salt, Base64.NO_WRAP))
            .putString("pin_hash", Base64.encodeToString(hash(pin, salt), Base64.NO_WRAP))
            .putInt("pin_len", pin.length)
            .putInt("tries", 0)
            .apply()
    }

    fun checkPin(ctx: Context, pin: String): Boolean {
        val p = prefs(ctx)
        val salt = Base64.decode(p.getString("pin_salt", "") ?: "", Base64.NO_WRAP)
        val stored = Base64.decode(p.getString("pin_hash", "") ?: "", Base64.NO_WRAP)
        val ok = MessageDigest.isEqual(stored, hash(pin, salt))
        if (ok) {
            p.edit().putInt("tries", 0).apply()
        } else {
            val tries = p.getInt("tries", 0) + 1
            val edit = p.edit().putInt("tries", tries)
            if (tries >= MAX_TRIES) {
                edit.putInt("tries", 0).putLong("locked_until", System.currentTimeMillis() + LOCKOUT_MS)
            }
            edit.apply()
        }
        return ok
    }

    /** Seconds left before another PIN attempt is allowed, 0 when allowed now. */
    fun waitSeconds(ctx: Context): Int {
        val left = prefs(ctx).getLong("locked_until", 0) - System.currentTimeMillis()
        return if (left > 0) ((left + 999) / 1000).toInt() else 0
    }

    fun biometricEnabled(ctx: Context) = prefs(ctx).getBoolean("biometric", false)

    fun setBiometricEnabled(ctx: Context, on: Boolean) =
        prefs(ctx).edit().putBoolean("biometric", on).apply()

    private fun hash(pin: String, salt: ByteArray): ByteArray {
        val spec = PBEKeySpec(pin.toCharArray(), salt, ITERATIONS, 256)
        return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA1").generateSecret(spec).encoded
    }
}
