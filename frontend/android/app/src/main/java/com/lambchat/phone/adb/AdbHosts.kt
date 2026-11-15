// Adapted from Mika 4387bfe; package renamed for LambChat. Apache-2.0.
package com.lambchat.phone.adb

import java.net.Inet6Address
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.NetworkInterface

/**
 * adb 只连本机自己:127/8、IPv6 回环,或本机网卡上的地址。
 *
 * 这里不把域名交给系统解析。除精确的 `localhost`(可带一个末尾点,固定映射到 127.0.0.1)外,只收数字字面量;
 * 解析、核对和随后 Socket 实际使用的是同一个 [InetAddress],不存在校验后再解析原字符串的间隙。
 */
object AdbHosts {
    private val LOOPBACK4 = byteArrayOf(127, 0, 0, 1)

    private data class LocalInterface(
        val name: String,
        val index: Int,
        val addresses: List<InetAddress>,
    )

    /** 返回已核对为本机的地址;域名、非法字面量和别的机器的地址都返回 null。全程不做 DNS。 */
    fun ownAddress(host: String): InetAddress? {
        val interfaces = runCatching {
            NetworkInterface.getNetworkInterfaces()?.toList().orEmpty().map {
                LocalInterface(it.name, it.index, it.inetAddresses.toList())
            }
        }.getOrDefault(emptyList())
        return ownAddress(host, interfaces)
    }

    /** 返回可直接交给 Socket 的已解析地址,调用方不得再用原 host 建 [InetSocketAddress]。 */
    fun ownSocketAddress(host: String, port: Int): InetSocketAddress? =
        ownAddress(host)?.let { InetSocketAddress(it, port) }

    private fun ownAddress(host: String, interfaces: List<LocalInterface>): InetAddress? {
        val address = parseLiteral(host, interfaces) ?: return null
        if (address.isLoopbackAddress || address.address.size == 4 && address.address[0] == 127.toByte()) return address
        return address.takeIf { target ->
            interfaces.any { nic -> nic.addresses.any { local -> sameAddress(target, local) } }
        }
    }

    private fun sameAddress(target: InetAddress, local: InetAddress): Boolean {
        if (!target.address.contentEquals(local.address)) return false
        // 不带 scope 的字面量按地址匹配;带了的必须落到同一块网卡,不能拿同名地址的另一块网卡放行。
        return target !is Inet6Address || local !is Inet6Address || target.scopeId == 0 || target.scopeId == local.scopeId
    }

    private fun parseLiteral(raw: String, interfaces: List<LocalInterface>): InetAddress? {
        var host = raw.trim()
        if (host.equals("localhost", ignoreCase = true) || host.equals("localhost.", ignoreCase = true)) {
            return InetAddress.getByAddress(null, LOOPBACK4)
        }
        if (host.isEmpty() || host.any { it.isWhitespace() }) return null
        if (host.startsWith('[') || host.endsWith(']')) {
            if (!host.startsWith('[') || !host.endsWith(']') || host.length < 3) return null
            host = host.substring(1, host.length - 1)
            // 方括号是 IPv6 字面量写法,不是任意字符串的通用包装。
            if (':' !in host || '[' in host || ']' in host) return null
        }
        return if (':' in host) parseIpv6(host, interfaces) else parseIpv4(host)?.let { InetAddress.getByAddress(null, it) }
    }

    /** 严格四段十进制;不收缩写、十六进制、八进制或一个整数表示的 IPv4。 */
    private fun parseIpv4(host: String): ByteArray? {
        val parts = host.split('.')
        if (parts.size != 4) return null
        val out = ByteArray(4)
        for ((i, part) in parts.withIndex()) {
            if (part.isEmpty() || part.length > 3 || part.any { it !in '0'..'9' }) return null
            val value = part.fold(0) { n, c -> n * 10 + (c - '0') }
            if (value > 255) return null
            out[i] = value.toByte()
        }
        return out
    }

    private fun parseIpv6(host: String, interfaces: List<LocalInterface>): InetAddress? {
        val percent = host.indexOf('%')
        if (percent >= 0 && host.indexOf('%', percent + 1) >= 0) return null
        val address = if (percent >= 0) host.substring(0, percent) else host
        val zone = if (percent >= 0) host.substring(percent + 1) else ""
        if (percent >= 0 && zone.isEmpty()) return null
        val scope = when {
            percent < 0 -> 0
            zone.all { it in '0'..'9' } -> zone.toLongOrNull()?.takeIf { it <= Int.MAX_VALUE }?.toInt() ?: return null
            else -> interfaces.firstOrNull { it.name == zone }?.index ?: return null
        }
        val bytes = ipv6Bytes(address) ?: return null
        // IPv4-mapped IPv6 统一成 IPv4,确保 127/8 和本机网卡比较不会被 16 字节表示绕过。
        if (isIpv4Mapped(bytes)) {
            if (scope != 0) return null
            return InetAddress.getByAddress(null, bytes.copyOfRange(12, 16))
        }
        return Inet6Address.getByAddress(null, bytes, scope)
    }

    private fun isIpv4Mapped(bytes: ByteArray): Boolean =
        (0 until 10).all { bytes[it] == 0.toByte() } && bytes[10] == 0xff.toByte() && bytes[11] == 0xff.toByte()

    /** 自行展开 IPv6,避免 InetAddress.getByName 即使对畸形数字输入也可能走系统名字解析。 */
    private fun ipv6Bytes(address: String): ByteArray? {
        if (address.isEmpty()) return null
        val halves = address.split("::")
        if (halves.size > 2) return null
        val compressed = halves.size == 2
        val left: List<Int>
        val right: List<Int>
        val whole: List<Int>
        if (compressed) {
            left = ipv6Groups(halves[0], allowIpv4 = false) ?: return null
            right = ipv6Groups(halves[1], allowIpv4 = true) ?: return null
            whole = left + right
            if (whole.size >= 8) return null
        } else {
            whole = ipv6Groups(address, allowIpv4 = true) ?: return null
            if (whole.size != 8) return null
            left = whole
            right = emptyList()
        }
        val out = ByteArray(16)
        fun write(groups: List<Int>, startGroup: Int) {
            for ((i, group) in groups.withIndex()) {
                out[(startGroup + i) * 2] = (group ushr 8).toByte()
                out[(startGroup + i) * 2 + 1] = group.toByte()
            }
        }
        if (compressed) {
            write(left, 0)
            write(right, 8 - right.size)
        } else {
            write(whole, 0)
        }
        return out
    }

    /** 返回 16 位组;末尾嵌入式 IPv4 占两组。 */
    private fun ipv6Groups(text: String, allowIpv4: Boolean): List<Int>? {
        if (text.isEmpty()) return emptyList()
        val parts = text.split(':')
        if (parts.any { it.isEmpty() }) return null
        val groups = ArrayList<Int>(8)
        for ((i, part) in parts.withIndex()) {
            if ('.' in part) {
                if (!allowIpv4 || i != parts.lastIndex) return null
                val ipv4 = parseIpv4(part) ?: return null
                groups += ((ipv4[0].toInt() and 0xff) shl 8) or (ipv4[1].toInt() and 0xff)
                groups += ((ipv4[2].toInt() and 0xff) shl 8) or (ipv4[3].toInt() and 0xff)
            } else {
                if (part.length > 4 || part.any { it !in '0'..'9' && it !in 'a'..'f' && it !in 'A'..'F' }) return null
                groups += part.toInt(16)
            }
        }
        return groups.takeIf { it.size <= 8 }
    }
}
