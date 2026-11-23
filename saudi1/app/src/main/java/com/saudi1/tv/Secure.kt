package com.saudi1.tv

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** The logins kept on the device are stored encrypted (owner, 21 Nov 2026): AES-GCM with a key that lives in the
 *  Android Keystore, never in the app's files, so a copy of the app's data shows no server, username or password.
 *  A value saved by an older version (plain text) is read as it is and encrypted the next time it is saved; if the
 *  Keystore ever fails on a TV, the value stays readable rather than losing the login. */
object Secure {
    private const val ALIAS = "saudi1_prefs"
    private const val TAG = "enc1:"

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        val g = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        g.init(KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256).build())
        return g.generateKey()
    }

    private val cache = java.util.concurrent.ConcurrentHashMap<String, String>()

    fun enc(plain: String): String {
        if (plain.isEmpty()) return ""
        return try {
            val c = Cipher.getInstance("AES/GCM/NoPadding"); c.init(Cipher.ENCRYPT_MODE, key())
            TAG + Base64.encodeToString(c.iv + c.doFinal(plain.toByteArray(Charsets.UTF_8)), Base64.NO_WRAP)
        } catch (e: Exception) { plain }
    }

    fun dec(stored: String): String {
        if (!stored.startsWith(TAG)) return stored
        cache[stored]?.let { return it }
        return try {
            val b = Base64.decode(stored.substring(TAG.length), Base64.NO_WRAP)
            val c = Cipher.getInstance("AES/GCM/NoPadding"); c.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, b, 0, 12))
            String(c.doFinal(b, 12, b.size - 12), Charsets.UTF_8).also { cache[stored] = it }
        } catch (e: Exception) { "" }
    }

    fun get(name: String, def: String = ""): String {
        val v = App.prefs.getString(name, null) ?: return def
        val p = dec(v)
        // an older plain value is encrypted in place the first time it is read
        if (!v.startsWith(TAG) && v.isNotEmpty()) put(name, v)
        return p
    }

    fun put(name: String, plain: String) = App.prefs.edit().putString(name, enc(plain)).apply()
}
