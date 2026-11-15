// Adapted from Mika 4387bfe; package renamed for LambChat. Apache-2.0.
package com.lambchat.phone.adb

import java.math.BigInteger

/**
 * edwards25519 上的点运算(扩展齐次坐标 X:Y:Z:T,x=X/Z、y=Y/Z、xy=T/Z),公式与编码按 RFC 8032 §5.1。
 * 只给配对时的 SPAKE2 用:每次配对只做几次标量乘,BigInteger 足够快;不追求常数时间,
 * 因为私钥是一次性的,配对码在局域网对话框里本来就可见。
 */
internal class EdPoint private constructor(
    private val x: BigInteger,
    private val y: BigInteger,
    private val z: BigInteger,
    private val t: BigInteger,
) {
    operator fun plus(o: EdPoint): EdPoint {
        val a = (y - x) * (o.y - o.x) % P
        val b = (y + x) * (o.y + o.x) % P
        val c = t * D2 % P * o.t % P
        val d = z * TWO * o.z % P
        val e = b - a
        val f = d - c
        val g = d + c
        val h = b + a
        return EdPoint(e * f % P, g * h % P, f * g % P, e * h % P)
    }

    operator fun unaryMinus() = EdPoint(P - x.mod(P), y, z, P - t.mod(P))

    operator fun minus(o: EdPoint) = this + (-o)

    /** k·this,k ≥ 0。 */
    fun times(k: BigInteger): EdPoint {
        require(k.signum() >= 0)
        var acc = IDENTITY
        for (i in k.bitLength() - 1 downTo 0) {
            acc += acc
            if (k.testBit(i)) acc += this
        }
        return acc
    }

    /** 仿射坐标 (x, y),都在 [0, p) 内。 */
    fun affine(): Pair<BigInteger, BigInteger> {
        val zi = z.mod(P).modInverse(P)
        return (x * zi).mod(P) to (y * zi).mod(P)
    }

    /** 32 字节:y 小端,最高位放 x 的奇偶。 */
    fun encode(): ByteArray {
        val zi = z.mod(P).modInverse(P)
        val ax = x * zi % P
        val ay = (y * zi).mod(P)
        val out = toLe(ay, 32)
        if (ax.mod(P).testBit(0)) out[31] = (out[31].toInt() or 0x80).toByte()
        return out
    }

    override fun equals(other: Any?): Boolean =
        other is EdPoint && (x * other.z - other.x * z).mod(P).signum() == 0 && (y * other.z - other.y * z).mod(P).signum() == 0

    override fun hashCode(): Int = encode().contentHashCode()

    companion object {
        // 不用 BigInteger.TWO:安卓 13 才有这个字段,安卓 12 上类一加载就抛 NoSuchFieldError,配对时整个进程崩掉
        private val TWO = BigInteger.valueOf(2)
        val P: BigInteger = TWO.pow(255) - BigInteger.valueOf(19)
        /** 素数阶子群的阶。 */
        val L: BigInteger = TWO.pow(252) + BigInteger("27742317777372353535851937790883648493")
        private val D: BigInteger = (BigInteger.valueOf(-121665) * BigInteger.valueOf(121666).modInverse(P)).mod(P)
        private val D2 = D * TWO % P
        private val SQRT_M1: BigInteger = TWO.modPow((P - BigInteger.ONE).shiftRight(2), P)

        val IDENTITY = EdPoint(BigInteger.ZERO, BigInteger.ONE, BigInteger.ONE, BigInteger.ZERO)

        val BASE: EdPoint = requireNotNull(
            decode(hex("5866666666666666666666666666666666666666666666666666666666666666")),
        )

        /** RFC 8032 §5.1.3;不在曲线上或编码不规范时返回 null。 */
        fun decode(bytes: ByteArray): EdPoint? {
            if (bytes.size != 32) return null
            val raw = bytes.copyOf()
            val sign = (raw[31].toInt() ushr 7) and 1
            raw[31] = (raw[31].toInt() and 0x7f).toByte()
            val y = fromLe(raw)
            if (y >= P) return null
            val yy = y * y % P
            val u = (yy - BigInteger.ONE).mod(P)
            val v = (D * yy + BigInteger.ONE) % P
            val v3 = v * v % P * v % P
            val v7 = v3 * v3 % P * v % P
            var x = u * v3 % P * (u * v7 % P).modPow((P - BigInteger.valueOf(5)).shiftRight(3), P) % P
            val vxx = v * x % P * x % P
            x = when {
                vxx == u -> x
                vxx == (P - u).mod(P) -> x * SQRT_M1 % P
                else -> return null
            }
            if (x.signum() == 0 && sign == 1) return null
            if (x.testBit(0) != (sign == 1)) x = P - x
            return EdPoint(x, y, BigInteger.ONE, x * y % P)
        }

        fun fromLe(b: ByteArray): BigInteger = BigInteger(1, b.reversedArray())

        fun toLe(n: BigInteger, len: Int): ByteArray {
            val be = n.toByteArray()
            val out = ByteArray(len)
            for (i in 0 until minOf(len, be.size)) out[i] = be[be.size - 1 - i]
            require(be.size <= len || be.copyOfRange(0, be.size - len).all { it == 0.toByte() }) { "value too large" }
            return out
        }

        fun hex(s: String): ByteArray = ByteArray(s.length / 2) { s.substring(it * 2, it * 2 + 2).toInt(16).toByte() }
    }
}
