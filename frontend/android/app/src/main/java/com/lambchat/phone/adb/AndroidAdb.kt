// Adapted from Mika 4387bfe; package and key identity changed for LambChat.
package com.lambchat.phone.adb

import android.content.Context
import android.net.ssl.SSLSockets
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Log
import com.lambchat.phone.adb.AdbIdentity
import com.lambchat.phone.adb.AdbIdentitySource
import com.lambchat.phone.adb.AdbKeyStore
import com.lambchat.phone.adb.AdbTls
import com.lambchat.phone.adb.KeyingMaterialExporter
import com.lambchat.phone.adb.WrappedKeyFile
import java.io.File
import java.security.KeyStore
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.net.ssl.SSLException

/** Android 上的 adb 身份与 TLS:钥匙用 Keystore 里的 AES 密钥包装后放在 App 私有目录;导出密钥走平台 TLS。 */
object AndroidAdb {
    private const val KEYSTORE = "AndroidKeyStore"
    private const val WRAP_ALIAS = "lambchat_adb_key_wrap"
    private const val TAG = "MikaAdbKey"

    // 设备端导出时不带 context;TLS 1.3 里空 context 与不带 context 的结果相同(RFC 8446 §7.5)
    val exporter = KeyingMaterialExporter { socket, label, length ->
        SSLSockets.exportKeyingMaterial(socket, label, ByteArray(0), length) ?: throw SSLException("keying material export failed")
    }

    @Volatile private var source: AdbIdentitySource? = null

    /** 本进程唯一的一份身份来源:配对和连接都从这里拿,拿到的是同一把钥匙。 */
    fun identities(context: Context): AdbIdentitySource = source ?: synchronized(this) {
        source ?: AdbIdentitySource(keyStore(context), { "lambchat@${Build.MODEL}" }) { msg, e -> Log.w(TAG, msg, e) }.also { source = it }
    }

    /** 连接用的身份;存着的钥匙读不出时抛 [com.lambchat.phone.adb.AdbKeyUnreadableException]。 */
    fun identity(context: Context): AdbIdentity = identities(context).forConnect()

    /** 配对用的身份:存着的钥匙读不出时换一把新的(见 [AdbIdentitySource.forPairing])。 */
    fun pairingIdentity(context: Context): AdbIdentity = identities(context).forPairing()

    fun tls(identity: AdbIdentity) = AdbTls(identity, exporter)

    /** 删除钥匙和本进程里的缓存(「解除配对」用);设备那边的授权记录要由用户在系统设置里撤销。 */
    fun forget(context: Context) = identities(context).forget()

    /** 钥匙文件 + 包装它的 Keystore 密钥:清掉时两样一起删。 */
    private fun keyStore(context: Context): AdbKeyStore {
        val file = WrappedKeyFile(File(context.applicationContext.noBackupFilesDir, "adb/adbkey.bin")) { wrappingKey() }
        return object : AdbKeyStore by file {
            override fun clear() {
                file.clear()
                runCatching { KeyStore.getInstance(KEYSTORE).apply { load(null) }.deleteEntry(WRAP_ALIAS) }
            }
        }
    }

    private fun wrappingKey(): SecretKey {
        val ks = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        (ks.getKey(WRAP_ALIAS, null) as? SecretKey)?.let { return it }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE)
        gen.init(
            KeyGenParameterSpec.Builder(WRAP_ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return gen.generateKey()
    }
}
