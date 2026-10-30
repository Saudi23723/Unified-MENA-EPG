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

    /** When the app was last left for another app or the home screen; 0 while in use. */
    @Volatile
    var leftAt = 0L

    /** How long the app may stay in the background before asking for the PIN again; -1 means never. */
    val LOCK_AFTER = longArrayOf(0L, 60_000L, 5 * 60_000L, 15 * 60_000L, -1L)

    fun lockAfter(ctx: Context): Long = prefs(ctx).getLong("lock_after", 5 * 60_000L)

    /** Locks if the app was away longer than allowed. */
    fun checkTimeout(ctx: Context) {
        val left = leftAt
        leftAt = 0L
        if (left == 0L || !unlocked) return
        val after = lockAfter(ctx)
        if (after >= 0 && System.currentTimeMillis() - left >= after) unlocked = false
    }

    /** Screenshots and the recent-apps preview are allowed unless this is turned on. */
    fun blockScreenshots(ctx: Context) = prefs(ctx).getBoolean("block_screenshots", false)

    fun applySecure(a: android.app.Activity) {
        if (blockScreenshots(a)) a.window.addFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE)
        else a.window.clearFlags(android.view.WindowManager.LayoutParams.FLAG_SECURE)
    }

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
