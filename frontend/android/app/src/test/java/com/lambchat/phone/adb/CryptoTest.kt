// Adapted from Mika 4387bfe, Apache-2.0; package renamed.
package com.lambchat.phone.adb

import com.lambchat.phone.adb.EdPoint.Companion.hex
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigInteger
import java.security.MessageDigest
import javax.crypto.AEADBadTagException

private fun ByteArray.hexs() = joinToString("") { "%02x".format(it) }

class EdPointTest {
    private class Vector(val secret: String, val public: String, val message: String, val sig: String)

    // RFC 8032 §7.1 TEST 1–3
    private val vectors = listOf(
        Vector(
            "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
            "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
            "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
        ),
        Vector(
            "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
            "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
            "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00",
        ),
        Vector(
            "c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
            "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025", "af82",
            "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a",
        ),
    )

    @Test
    fun publicKeyFromSecretMatchesRfc8032() {
        for (v in vectors) {
            val h = MessageDigest.getInstance("SHA-512").digest(hex(v.secret))
            val a = h.copyOf(32)
            a[0] = (a[0].toInt() and 248).toByte()
            a[31] = ((a[31].toInt() and 127) or 64).toByte()
            assertEquals(v.public, EdPoint.BASE.times(EdPoint.fromLe(a)).encode().hexs())
        }
    }

    /** 验签等式 [S]B = R + [k]A 同时考验解码、加法和任意点的标量乘。 */
    @Test
    fun signatureEquationHoldsForRfc8032Vectors() {
        for (v in vectors) {
            val sig = hex(v.sig)
            val r = EdPoint.decode(sig.copyOf(32))!!
            val pub = EdPoint.decode(hex(v.public))!!
            val s = EdPoint.fromLe(sig.copyOfRange(32, 64))
            val sha = MessageDigest.getInstance("SHA-512")
            sha.update(sig.copyOf(32)); sha.update(hex(v.public)); sha.update(hex(v.message))
            val k = EdPoint.fromLe(sha.digest()).mod(EdPoint.L)
            assertEquals(EdPoint.BASE.times(s), r + pub.times(k))
            assertTrue(EdPoint.BASE.times(s) != r + pub.times(k + BigInteger.ONE))
        }
    }

    @Test
    fun groupLaws() {
        val b = EdPoint.BASE
        assertEquals(EdPoint.IDENTITY, b.times(EdPoint.L))
        assertEquals(b.times(BigInteger.valueOf(5)), b + b + b + b + b)
        assertEquals(EdPoint.IDENTITY, b - b)
        assertEquals(b, EdPoint.decode(b.encode()))
        assertEquals("5866666666666666666666666666666666666666666666666666666666666666", b.encode().hexs())
    }

    @Test
    fun decodeRejectsBadEncodings() {
        // y = p(不规范)
        assertNull(EdPoint.decode(EdPoint.toLe(EdPoint.P, 32)))
        // y = 2 时 x² 无解
        assertNull(EdPoint.decode(EdPoint.toLe(BigInteger.TWO, 32)))
        // x = 0 却标了负号(y = 1)
        assertNull(EdPoint.decode(ByteArray(32).also { it[0] = 1; it[31] = 0x80.toByte() }))
        assertNull(EdPoint.decode(ByteArray(31)))
    }
}

class Spake2ConstantsTest {
    @Test
    fun mAndNDeriveFromSeeds() {
        assertEquals(Spake2.M, Spake2.derivePoint(Spake2.SEED_M))
        assertEquals(Spake2.N, Spake2.derivePoint(Spake2.SEED_N))
        assertEquals("5ada7e4bf6ddd9adb6626d32131c6b5c51a1e347a3478f53cfcf441b88eed12e", Spake2.derivePoint(Spake2.SEED_M).encode().hexs())
        assertEquals("10e3df0ae37d8e7a99b5fe74b44672103dbddcbd06af680d71329a11693bc778", Spake2.derivePoint(Spake2.SEED_N).encode().hexs())
    }

    /** 与参考实现源码里写死的坐标和预计算表首项(x、y 各 32 字节小端)逐一比对。 */
    @Test
    fun mAndNMatchHardCodedReferenceValues() {
        val (mx, my) = Spake2.M.affine()
        assertEquals(BigInteger("31406539342727633121250288103050113562375374900226415211311216773867585644232"), mx)
        assertEquals(BigInteger("21177308356423958466833845032658859666296341766942662650232962324899758529114"), my)
        val (nx, ny) = Spake2.N.affine()
        assertEquals(BigInteger("49918732221787544735331783592030787422991506689877079631459872391322455579424"), nx)
        assertEquals(BigInteger("54629554431565467720832445949441049581317094546788069926228343916274969994000"), ny)
        assertEquals("c8a663c597f1ee40ab6242ee256f326c752ca7d3bd323b1e119cbd04a9786f45", EdPoint.toLe(mx, 32).hexs())
        assertEquals("201bc5b343177110441e73b3ae3fbf9ff544c8138fd101c28a1a6dea4d005d6e", EdPoint.toLe(nx, 32).hexs())
    }
}

class Spake2GoldenTest {
    private fun cases(): List<Map<String, String>> {
        val text = javaClass.getResource("/adb/spake2-vectors.txt")!!.readText()
        return text.split("\n\n").map { block ->
            block.lines().filter { it.isNotBlank() && !it.startsWith("#") }.associate { it.substringBefore('=') to it.substringAfter('=') }
        }.filter { it.isNotEmpty() }
    }

    @Test
    fun matchesReferenceImplementation() {
        val all = cases()
        assertEquals(8, all.size)
        var matched = 0
        for (c in all) {
            val alice = PairingAuth.client(hex(c.getValue("alice_password")), hex(c.getValue("alice_seed")))
            val bob = PairingAuth.server(hex(c.getValue("bob_password")), hex(c.getValue("bob_seed")))
            assertEquals(c["alice_msg"], alice.message.hexs())
            assertEquals(c["bob_msg"], bob.message.hexs())

            val aliceSpake = Spake2(Spake2.Role.ALICE, PairingAuth.CLIENT_NAME, PairingAuth.SERVER_NAME)
            aliceSpake.generateMessage(hex(c.getValue("alice_password")), hex(c.getValue("alice_seed")))
            val aliceKey = aliceSpake.processMessage(hex(c.getValue("bob_msg")))
            val bobSpake = Spake2(Spake2.Role.BOB, PairingAuth.SERVER_NAME, PairingAuth.CLIENT_NAME)
            bobSpake.generateMessage(hex(c.getValue("bob_password")), hex(c.getValue("bob_seed")))
            val bobKey = bobSpake.processMessage(hex(c.getValue("alice_msg")))
            assertEquals(c["alice_key"], aliceKey.hexs())
            assertEquals(c["bob_key"], bobKey.hexs())
            assertEquals(c["alice_aes_key"], Hkdf.sha256(aliceKey, null, "adb pairing_auth aes-128-gcm key".toByteArray(), 16).hexs())

            alice.initCipher(bob.message)
            bob.initCipher(alice.message)
            val plain = hex(c.getValue("plaintext"))
            val s0 = alice.encrypt(plain)
            val s1 = alice.encrypt(plain)
            assertEquals(c["alice_sealed0"], s0.hexs())
            assertEquals(c["alice_sealed1"], s1.hexs())
            if (c["alice_password"] == c["bob_password"]) {
                assertEquals(c["alice_key"], c["bob_key"])
                assertArrayEquals(plain, bob.decrypt(s0))
                assertArrayEquals(plain, bob.decrypt(s1))
                matched++
            } else {
                assertFalse(c["alice_key"] == c["bob_key"])
                assertThrows(AEADBadTagException::class.java) { bob.decrypt(s0) }
            }
        }
        assertEquals(7, matched)
    }
}

class Spake2RoundTripTest {
    @Test
    fun randomKeysAgreeAndWrongCodeDisagrees() {
        val pw = "654321".toByteArray() + ByteArray(64) { it.toByte() }
        val c = PairingAuth.client(pw)
        val s = PairingAuth.server(pw)
        c.initCipher(s.message); s.initCipher(c.message)
        val msg = ByteArray(8192) { (it * 7).toByte() }
        assertArrayEquals(msg, s.decrypt(c.encrypt(msg)))
        assertArrayEquals(msg, c.decrypt(s.encrypt(msg)))

        val wrong = PairingAuth.server("654320".toByteArray() + ByteArray(64) { it.toByte() })
        val c2 = PairingAuth.client(pw)
        c2.initCipher(wrong.message); wrong.initCipher(c2.message)
        assertThrows(AEADBadTagException::class.java) { wrong.decrypt(c2.encrypt(msg)) }
    }

    @Test
    fun sequenceNumbersMustLineUp() {
        val pw = "000000".toByteArray()
        val c = PairingAuth.client(pw)
        val s = PairingAuth.server(pw)
        c.initCipher(s.message); s.initCipher(c.message)
        c.encrypt(byteArrayOf(1)) // 对方没收到这一条
        assertThrows(AEADBadTagException::class.java) { s.decrypt(c.encrypt(byteArrayOf(2))) }
    }

    @Test
    fun rejectsOffCurvePeerMessage() {
        val c = PairingAuth.client("1".toByteArray())
        assertThrows(IllegalArgumentException::class.java) { c.initCipher(EdPoint.toLe(BigInteger.TWO, 32)) }
        val c2 = PairingAuth.client("1".toByteArray())
        assertThrows(IllegalArgumentException::class.java) { c2.initCipher(ByteArray(16)) }
    }
}

class HkdfTest {
    @Test
    fun rfc5869Sha256Cases() {
        assertEquals(
            "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865",
            Hkdf.sha256(ByteArray(22) { 0x0b }, ByteArray(13) { it.toByte() }, ByteArray(10) { (0xf0 + it).toByte() }, 42).hexs(),
        )
        assertEquals(
            "b11e398dc80327a1c8e7f78c596a49344f012eda2d4efad8a050cc4c19afa97c59045a99cac7827271cb41c65e590e09da3275600c2f09b8367793a9aca3db71cc30c58179ec3e87c14c01d5c1f3434f1d87",
            Hkdf.sha256(ByteArray(80) { it.toByte() }, ByteArray(80) { (0x60 + it).toByte() }, ByteArray(80) { (0xb0 + it).toByte() }, 82).hexs(),
        )
        assertEquals(
            "8da4e775a563c18f715f802a063c5a31b8a11f5c5ee1879ec3454e5f3c738d2d9d201395faa4b61a96c8",
            Hkdf.sha256(ByteArray(22) { 0x0b }, null, ByteArray(0), 42).hexs(),
        )
    }
}
