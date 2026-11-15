// Adapted from Mika 4387bfe; package renamed for LambChat. Apache-2.0.
package com.lambchat.phone.adb

import java.math.BigInteger
import java.security.MessageDigest
import java.security.SecureRandom

/**
 * adb 无线配对用的 SPAKE2 变体(edwards25519 + SHA-512)。必须和设备上的实现逐字节一致:
 * - 私钥 = (64 字节随机数 mod L) × 8,乘以余因子;
 * - 口令标量 = SHA-512(口令) mod L,再按低三位依次加 L、2L、4L,使它成为 8 的倍数(与设备端的历史修正一致);
 * - 发送 P* = 私钥·B + 口令标量·(甲方用 M,乙方用 N);
 * - 共享密钥 = SHA-512(每段带 8 字节小端长度前缀:甲名、乙名、甲消息、乙消息、私钥·(Q* − 口令标量·对方常量)、SHA-512(口令))。
 * M、N 由公开种子串推导,见 [SEED_M]/[SEED_N];测试里重新推导并核对。
 */
class Spake2(
    private val role: Role,
    private val myName: ByteArray,
    private val theirName: ByteArray,
) {
    enum class Role { ALICE, BOB }

    private var privateKey: BigInteger? = null
    private var passwordScalar: BigInteger? = null
    private var passwordHash: ByteArray? = null
    private var myMsg: ByteArray? = null
    private var done = false

    fun generateMessage(password: ByteArray, random: SecureRandom = SecureRandom()): ByteArray =
        generateMessage(password, ByteArray(64).also { random.nextBytes(it) })

    /** [seed] 是 64 字节随机数;只有测试传入固定值。 */
    internal fun generateMessage(password: ByteArray, seed: ByteArray): ByteArray {
        check(myMsg == null) { "message already generated" }
        require(seed.size == 64)
        val priv = EdPoint.fromLe(seed).mod(EdPoint.L).shiftLeft(3)
        val hash = MessageDigest.getInstance("SHA-512").digest(password)
        var s = EdPoint.fromLe(hash).mod(EdPoint.L)
        if (s.testBit(0)) s += EdPoint.L
        if (s.testBit(1)) s += EdPoint.L.shiftLeft(1)
        if (s.testBit(2)) s += EdPoint.L.shiftLeft(2)
        val mask = (if (role == Role.ALICE) M else N).times(s)
        val msg = (EdPoint.BASE.times(priv) + mask).encode()
        privateKey = priv
        passwordScalar = s
        passwordHash = hash
        myMsg = msg
        return msg.copyOf()
    }

    /** 返回 64 字节共享密钥;对方的点不在曲线上时抛 [IllegalArgumentException]。 */
    fun processMessage(theirMsg: ByteArray): ByteArray {
        val msg = checkNotNull(myMsg) { "generateMessage first" }
        check(!done) { "already processed" }
        require(theirMsg.size == 32) { "peer message must be 32 bytes" }
        val qStar = requireNotNull(EdPoint.decode(theirMsg)) { "peer point not on curve" }
        val peerMask = (if (role == Role.ALICE) N else M).times(passwordScalar!!)
        val shared = (qStar - peerMask).times(privateKey!!).encode()
        val sha = MessageDigest.getInstance("SHA-512")
        fun put(b: ByteArray) {
            val len = ByteArray(8)
            var l = b.size.toLong()
            for (i in 0 until 8) { len[i] = (l and 0xff).toByte(); l = l ushr 8 }
            sha.update(len)
            sha.update(b)
        }
        if (role == Role.ALICE) {
            put(myName); put(theirName); put(msg); put(theirMsg)
        } else {
            put(theirName); put(myName); put(theirMsg); put(msg)
        }
        put(shared)
        put(passwordHash!!)
        done = true
        return sha.digest()
    }

    companion object {
        const val SEED_M = "edwards25519 point generation seed (M)"
        const val SEED_N = "edwards25519 point generation seed (N)"
        internal val M = requireNotNull(EdPoint.decode(EdPoint.hex("5ada7e4bf6ddd9adb6626d32131c6b5c51a1e347a3478f53cfcf441b88eed12e")))
        internal val N = requireNotNull(EdPoint.decode(EdPoint.hex("10e3df0ae37d8e7a99b5fe74b44672103dbddcbd06af680d71329a11693bc778")))

        /** 由种子串推导常量点:SHA-256(种子),解不出点就对摘要再取 SHA-256,直到落在曲线上。 */
        internal fun derivePoint(seed: String): EdPoint {
            var v = MessageDigest.getInstance("SHA-256").digest(seed.toByteArray(Charsets.US_ASCII))
            while (true) {
                EdPoint.decode(v)?.let { return it }
                v = MessageDigest.getInstance("SHA-256").digest(v)
            }
        }
    }
}
