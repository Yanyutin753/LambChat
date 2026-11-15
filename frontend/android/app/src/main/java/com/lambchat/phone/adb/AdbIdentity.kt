// Adapted from Mika 4387bfe; package renamed for LambChat. Apache-2.0.
package com.lambchat.phone.adb

import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.math.BigInteger
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.KeyFactory
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.Signature
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import java.security.interfaces.RSAPrivateCrtKey
import java.security.interfaces.RSAPrivateKey
import java.security.interfaces.RSAPublicKey
import java.security.spec.PKCS8EncodedKeySpec
import java.security.spec.RSAKeyGenParameterSpec
import java.security.spec.RSAPublicKeySpec
import java.util.Base64
import javax.crypto.Cipher
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Mika 自己的 adb 身份:一把 RSA-2048 钥匙 + 自签名证书。配对时把 [adbPublicKey] 交给设备,
 * 之后每次 TLS 连接都出示 [certificate](设备只比对证书里的公钥)。
 */
class AdbIdentity(val keyPair: KeyPair, val name: String) {
    val publicKey: RSAPublicKey get() = keyPair.public as RSAPublicKey

    val certificate: X509Certificate by lazy { SelfSignedCertificate.create(keyPair) }

    /**
     * 设备 keystore 里的一行:base64(524 字节公钥结构) + 空格 + 名字。
     * 名字里不能有空白:系统设置按空白切分这一行,名字带空格时「已配对的设备」里删不掉。
     */
    val adbPublicKey: String by lazy {
        Base64.getEncoder().encodeToString(AdbPublicKey.encode(publicKey)) + " " + name.replace(Regex("\\s"), "_")
    }

    companion object {
        /** 新钥匙的公开指数:F4(65537)。读回钥匙时拿不到指数就按它补,并验证补得对。 */
        val PUBLIC_EXPONENT: BigInteger = RSAKeyGenParameterSpec.F4

        fun generate(name: String): AdbIdentity {
            val g = KeyPairGenerator.getInstance("RSA")
            g.initialize(RSAKeyGenParameterSpec(2048, PUBLIC_EXPONENT))
            return AdbIdentity(g.generateKeyPair(), name)
        }

        /**
         * 从存下的 PKCS#8 读回身份。不要求平台给的是带 CRT 参数的私钥:只要是 RSA 私钥就取模数,
         * 公开指数按 [publicExponent] 找。读不出抛 [AdbKeyUnreadableException]。
         */
        fun fromPkcs8(pkcs8: ByteArray, name: String): AdbIdentity {
            val kf = KeyFactory.getInstance("RSA")
            val priv = try {
                kf.generatePrivate(PKCS8EncodedKeySpec(pkcs8))
            } catch (e: Exception) {
                throw AdbKeyUnreadableException("stored key is not valid PKCS#8", e)
            }
            val rsa = priv as? RSAPrivateKey ?: throw AdbKeyUnreadableException("stored key is not RSA (${priv.javaClass.simpleName})")
            val pub = kf.generatePublic(RSAPublicKeySpec(rsa.modulus, publicExponent(rsa, pkcs8))) as RSAPublicKey
            return AdbIdentity(KeyPair(pub, rsa), name)
        }

        /**
         * 私钥对应的公开指数:平台给了 CRT 形式就直接用;否则从 PKCS#8 里的 RSAPrivateKey 结构读;
         * 结构里没有(写的是 0)才按 [PUBLIC_EXPONENT] 补,补之前签一次名验一次,对不上就抛,不拿错的公钥去连。
         */
        internal fun publicExponent(key: RSAPrivateKey, pkcs8: ByteArray): BigInteger {
            (key as? RSAPrivateCrtKey)?.publicExponent?.takeIf { it.signum() > 0 }?.let { return it }
            Pkcs8Rsa.publicExponent(pkcs8)?.takeIf { it.signum() > 0 }?.let { return it }
            if (!signsWith(key, PUBLIC_EXPONENT)) throw AdbKeyUnreadableException("cannot recover the public exponent of the stored key")
            return PUBLIC_EXPONENT
        }

        private fun signsWith(key: RSAPrivateKey, e: BigInteger): Boolean = runCatching {
            val pub = KeyFactory.getInstance("RSA").generatePublic(RSAPublicKeySpec(key.modulus, e))
            val data = "mika-adb-key-check".toByteArray()
            val sig = Signature.getInstance("SHA256withRSA").run { initSign(key); update(data); sign() }
            Signature.getInstance("SHA256withRSA").run { initVerify(pub); update(data); verify(sig) }
        }.getOrDefault(false)
    }
}

/** 已存的钥匙在,却读不出来(解不开或解析不了)。不能悄悄换新的:设备只认配对时那一把。 */
class AdbKeyUnreadableException(message: String, cause: Throwable? = null) : Exception(message, cause)

/** 钥匙此刻的状况(诊断信息用)。 */
enum class AdbKeyState {
    /** 这个进程里还没用过钥匙。 */
    NotLoaded,
    /** 读回了已存的那把。 */
    Loaded,
    /** 之前没有(或配对时换掉了读不出的那把),新建了一把并存下。 */
    Created,
    /** 存着一把却读不出来:要重新配对。 */
    Unreadable,
}

/**
 * 一个进程里的 adb 身份只有一份:配对和连接拿到的一定是同一把钥匙,不会因为某次读失败各用各的。
 * 只有配对([forPairing])会在存着的钥匙读不出时换一把新的(配对本来就会把新钥匙交给设备);
 * 连接([forConnect])遇到读不出就抛 [AdbKeyUnreadableException],界面据此请用户重新配对。
 */
class AdbIdentitySource(
    private val store: AdbKeyStore,
    private val name: () -> String,
    private val log: (String, Throwable?) -> Unit = { _, _ -> },
) {
    private var cached: AdbIdentity? = null

    @Volatile var state: AdbKeyState = AdbKeyState.NotLoaded
        private set

    /** 最近一次读不出的原因(诊断信息用);读得出时为 null。 */
    @Volatile var problem: String? = null
        private set

    /** 连接用:已存的那把;一把都没有就新建并存下;存着却读不出就抛,不覆盖。 */
    @Synchronized
    fun forConnect(): AdbIdentity = cached ?: load()

    /** 配对用:和 [forConnect] 同一把;只有存着的读不出时,在这里换一把新的存下(随后的配对会把它交给设备)。 */
    @Synchronized
    fun forPairing(): AdbIdentity = cached ?: try {
        load()
    } catch (e: AdbKeyUnreadableException) {
        log("replacing the unreadable adb key for a new pairing", e)
        store.clear()
        create()
    }

    /** 解除配对:钥匙和缓存一起删掉,下次配对用新钥匙。 */
    @Synchronized
    fun forget() {
        cached = null
        store.clear()
        state = AdbKeyState.NotLoaded
        problem = null
    }

    private fun load(): AdbIdentity {
        val bytes = try {
            store.read()
        } catch (e: AdbKeyUnreadableException) {
            throw unreadable(e)
        } ?: return create()
        val id = try {
            AdbIdentity.fromPkcs8(bytes, name())
        } catch (e: AdbKeyUnreadableException) {
            throw unreadable(e)
        }
        state = AdbKeyState.Loaded
        problem = null
        return id.also { cached = it }
    }

    private fun create(): AdbIdentity {
        val id = AdbIdentity.generate(name())
        store.write(id.keyPair.private.encoded)
        state = AdbKeyState.Created
        problem = null
        return id.also { cached = it }
    }

    private fun unreadable(e: AdbKeyUnreadableException): AdbKeyUnreadableException {
        state = AdbKeyState.Unreadable
        problem = generateSequence<Throwable>(e) { it.cause }.joinToString(" <- ") { it.message ?: it.javaClass.simpleName }.take(200)
        log("stored adb key is unreadable; pair again to replace it", e)
        return e
    }
}

/**
 * 钥匙(PKCS#8)的存取。App 里用 Android Keystore 包一层加密存放。
 * [read] 没存过返回 null;存着却读不出抛 [AdbKeyUnreadableException](两者要分开,后者不能当作没有)。
 */
interface AdbKeyStore {
    fun read(): ByteArray?
    fun write(pkcs8: ByteArray)
    fun clear()
}

/**
 * 加密存放在文件里的钥匙:文件内容 = 1 字节 IV 长度 + IV + AES-GCM 密文。
 * IV 由 Cipher 自己生成(Android Keystore 的密钥不许调用方指定 IV)。
 */
class WrappedKeyFile(private val file: File, private val wrappingKey: () -> SecretKey) : AdbKeyStore {
    override fun read(): ByteArray? {
        if (!file.isFile) return null
        return try {
            val b = file.readBytes()
            require(b.isNotEmpty()) { "key file is empty" }
            val ivLen = b[0].toInt() and 0xff
            require(b.size > 1 + ivLen) { "key file is truncated" }
            val c = Cipher.getInstance("AES/GCM/NoPadding")
            c.init(Cipher.DECRYPT_MODE, wrappingKey(), GCMParameterSpec(128, b.copyOfRange(1, 1 + ivLen)))
            c.doFinal(b, 1 + ivLen, b.size - 1 - ivLen)
        } catch (e: Exception) {
            throw AdbKeyUnreadableException("cannot unwrap ${file.name}", e)
        }
    }

    override fun write(pkcs8: ByteArray) {
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.ENCRYPT_MODE, wrappingKey())
        val iv = c.iv
        val out = byteArrayOf(iv.size.toByte()) + iv + c.doFinal(pkcs8)
        file.parentFile?.mkdirs()
        val tmp = File(file.path + ".tmp")
        tmp.writeBytes(out)
        check(tmp.renameTo(file)) { "cannot write ${file.name}" }
    }

    override fun clear() {
        file.delete()
    }
}

/**
 * 从 PKCS#8 里读 RSA 公开指数:PrivateKeyInfo ::= SEQUENCE { version, algorithm, privateKey OCTET STRING },
 * privateKey 里是 RSAPrivateKey ::= SEQUENCE { version, modulus, publicExponent, ... }。结构不对返回 null。
 */
internal object Pkcs8Rsa {
    fun publicExponent(pkcs8: ByteArray): BigInteger? = runCatching {
        val info = Der(pkcs8).read(0x30)
        val inner = Der(info).apply { read(0x02); read(0x30) }.read(0x04)
        val rsa = Der(Der(inner).read(0x30))
        rsa.read(0x02)
        rsa.read(0x02)
        BigInteger(rsa.read(0x02))
    }.getOrNull()

    /** 只够读上面那几层的 DER:按顺序取指定标签的内容。 */
    private class Der(private val b: ByteArray) {
        private var pos = 0

        fun read(tag: Int): ByteArray {
            require((b[pos++].toInt() and 0xff) == tag) { "unexpected tag" }
            var len = b[pos++].toInt() and 0xff
            if (len >= 0x80) {
                val n = len and 0x7f
                require(n in 1..3) { "unsupported length" }
                len = 0
                repeat(n) { len = (len shl 8) or (b[pos++].toInt() and 0xff) }
            }
            require(pos + len <= b.size) { "truncated" }
            return b.copyOfRange(pos, pos + len).also { pos += len }
        }
    }
}

/**
 * adb 的 RSA 公钥二进制格式(全部小端,共 524 字节):
 * 模数字数(64)、n0inv = −1/n mod 2^32、模数 n、rr = (2^2048)^2 mod n、公开指数。
 */
object AdbPublicKey {
    private const val WORDS = 64
    const val SIZE = 4 + 4 + WORDS * 4 * 2 + 4

    fun encode(key: RSAPublicKey): ByteArray {
        val n = key.modulus
        require(n.bitLength() == 2048) { "adb keys are RSA-2048" }
        val r32 = BigInteger.ONE.shiftLeft(32)
        val n0inv = r32 - n.mod(r32).modInverse(r32)
        val rr = BigInteger.ONE.shiftLeft(2048 * 2).mod(n)
        val buf = ByteBuffer.allocate(SIZE).order(ByteOrder.LITTLE_ENDIAN)
        buf.putInt(WORDS)
        buf.putInt(n0inv.toInt())
        buf.put(EdPoint.toLe(n, 256))
        buf.put(EdPoint.toLe(rr, 256))
        buf.putInt(key.publicExponent.toInt())
        return buf.array()
    }
}

/** 最小的自签名 X.509 v3 证书(无扩展):CN=Mika,1970-01-01 到 2099-12-31,SHA256withRSA。 */
internal object SelfSignedCertificate {
    private val SHA256_WITH_RSA = byteArrayOf(0x2a, 0x86.toByte(), 0x48, 0x86.toByte(), 0xf7.toByte(), 0x0d, 0x01, 0x01, 0x0b)
    private val COMMON_NAME = byteArrayOf(0x55, 0x04, 0x03)

    fun create(keyPair: KeyPair): X509Certificate {
        val algId = seq(tlv(0x06, SHA256_WITH_RSA), tlv(0x05, ByteArray(0)))
        val name = seq(tlv(0x31, seq(tlv(0x06, COMMON_NAME), tlv(0x0c, "Mika".toByteArray()))))
        val validity = seq(tlv(0x17, "700101000000Z".toByteArray()), tlv(0x18, "20991231235959Z".toByteArray()))
        val tbs = seq(
            tlv(0xa0, tlv(0x02, byteArrayOf(2))),
            tlv(0x02, byteArrayOf(1)),
            algId, name, validity, name,
            keyPair.public.encoded,
        )
        val sig = Signature.getInstance("SHA256withRSA").run {
            initSign(keyPair.private)
            update(tbs)
            sign()
        }
        val der = seq(tbs, algId, tlv(0x03, byteArrayOf(0) + sig))
        return CertificateFactory.getInstance("X.509").generateCertificate(ByteArrayInputStream(der)) as X509Certificate
    }

    private fun seq(vararg parts: ByteArray) = tlv(0x30, parts.fold(ByteArray(0)) { a, b -> a + b })

    internal fun tlv(tag: Int, content: ByteArray): ByteArray {
        val out = ByteArrayOutputStream()
        out.write(tag)
        val n = content.size
        when {
            n < 0x80 -> out.write(n)
            n < 0x100 -> { out.write(0x81); out.write(n) }
            n < 0x10000 -> { out.write(0x82); out.write(n ushr 8); out.write(n and 0xff) }
            else -> { out.write(0x83); out.write(n ushr 16); out.write((n ushr 8) and 0xff); out.write(n and 0xff) }
        }
        out.write(content)
        return out.toByteArray()
    }
}
