// Adapted from Mika 4387bfe, Apache-2.0; package renamed.
package com.lambchat.phone.adb

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test
import java.net.Inet4Address
import java.net.NetworkInterface

class AdbHostsTest {
    @Test
    fun loopbackLiteralsAndExactLocalhostAreOwn() {
        for (host in listOf(
            "127.0.0.1", "127.255.255.254", "127.000.000.001", " 127.0.0.1 ",
            "::1", "[::1]", " [::1%0] ", "0:0:0:0:0:0:0:1",
            "::ffff:127.0.0.1", "[::ffff:127.255.255.254]", "0:0:0:0:0:ffff:7f00:1",
            "localhost", "LOCALHOST.", " localhost ",
        )) {
            assertNotNull(host, AdbHosts.ownAddress(host))
        }
        // localhost 不查 hosts/DNS,也不接受它的子域;固定成这个已验证的 IPv4 回环。
        assertArrayEquals(byteArrayOf(127, 0, 0, 1), AdbHosts.ownAddress("LOCALHOST.")!!.address)
        val target = AdbHosts.ownSocketAddress("[::1]", 5555)
        assertNotNull(target)
        assertFalse(target!!.isUnresolved)
    }

    @Test
    fun everyAddressOnThisMachineIncludingScopedIpv6IsOwn() {
        val own = runCatching {
            NetworkInterface.getNetworkInterfaces()?.toList().orEmpty().flatMap { it.inetAddresses.toList() }
        }.getOrDefault(emptyList())
        for (address in own) {
            // hostAddress 可能带 %en0 或 %3;保留 scope,验证后再连接也必须是这份地址。
            assertNotNull(address.hostAddress, AdbHosts.ownAddress(address.hostAddress))
            if (address is Inet4Address) {
                assertNotNull(address.hostAddress, AdbHosts.ownAddress("::ffff:${address.hostAddress}"))
            }
        }
    }

    @Test
    fun lookalikeNamesAndNonCanonicalNumbersAreRejectedWithoutResolution() {
        for (host in listOf(
            "127.evil.com", "127.0.0.1.example.com", "localhost.example.com", "evil.localhost", ".localhost",
            "adb.example.com", "my-phone.local", "127.0.0.1@evil.com", "http://127.0.0.1",
            "127.1", "2130706433", "0x7f000001", "127.0.0.1.", "256.1.1.1", "1..2.3", "1.2.3.4.5",
        )) {
            assertNull(host, AdbHosts.ownAddress(host))
        }
    }

    @Test
    fun otherMachinesAndMappedOrTranslatedRemoteAddressesAreRejected() {
        for (host in listOf(
            "192.0.2.1", "203.0.113.9", "8.8.8.8", "2001:db8::1",
            "::ffff:192.0.2.1", "::ffff:8.8.8.8", "::127.0.0.1", "::ffff:0:127.0.0.1", "64:ff9b::7f00:1",
        )) {
            assertNull(host, AdbHosts.ownAddress(host))
        }
    }

    @Test
    fun malformedIpv6BracketsAndScopesAreRejected() {
        for (host in listOf(
            "", "   ", "[127.0.0.1]", "[::1", "::1]", "[[::1]]", "[ ::1 ]", "::1%", "::1%a%b",
            "::1%interface-that-does-not-exist", "1::2::3", "1:2:3:4:5:6:7:8:9", "1:2:3:4:5:6:7:8::",
            "::ffff:999.0.0.1", ":::1", "127.0.0. 1",
        )) {
            assertNull(host, AdbHosts.ownAddress(host))
        }
    }
}
