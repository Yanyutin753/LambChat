// Adapted from Mika 4387bfe; package renamed for LambChat. Apache-2.0.
package com.lambchat.phone.adb

import java.io.DataInputStream
import java.io.EOFException
import java.io.IOException
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * adb 传输层的一个包:24 字节小端头(命令、arg0、arg1、数据长度、数据校验和、命令按位取反)+ 数据。
 * 校验和是数据所有字节(无符号)之和;协议版本 ≥ [VERSION_SKIP_CHECKSUM] 时接收方不再核对。
 */
class AdbMessage(val command: Int, val arg0: Int, val arg1: Int, val data: ByteArray = EMPTY) {
    fun encode(): ByteArray {
        val bb = ByteBuffer.allocate(HEADER_SIZE + data.size).order(ByteOrder.LITTLE_ENDIAN)
        bb.putInt(command).putInt(arg0).putInt(arg1).putInt(data.size).putInt(checksum(data)).putInt(command.inv())
        bb.put(data)
        return bb.array()
    }

    override fun toString() = "${name(command)}($arg0, $arg1, ${data.size} bytes)"

    companion object {
        const val CNXN = 0x4e584e43
        const val AUTH = 0x48545541
        const val OPEN = 0x4e45504f
        const val OKAY = 0x59414b4f
        const val CLSE = 0x45534c43
        const val WRTE = 0x45545257
        const val STLS = 0x534c5453

        const val VERSION = 0x01000001
        const val VERSION_SKIP_CHECKSUM = 0x01000001
        const val STLS_VERSION = 0x01000000
        const val MAX_PAYLOAD = 1024 * 1024
        const val HEADER_SIZE = 24
        private val EMPTY = ByteArray(0)

        fun checksum(data: ByteArray): Int {
            var sum = 0
            for (b in data) sum += b.toInt() and 0xff
            return sum
        }

        fun name(cmd: Int): String =
            ByteArray(4) { (cmd ushr (8 * it)).toByte() }.toString(Charsets.US_ASCII).takeIf { s -> s.all { it in 'A'..'Z' } } ?: "0x%08x".format(cmd)

        /** 读一个包;在包头之前遇到流结束返回 null,格式不对抛 [IOException]。 */
        fun read(input: DataInputStream, maxData: Int = MAX_PAYLOAD, verifyChecksum: Boolean = false): AdbMessage? {
            val header = ByteArray(HEADER_SIZE)
            try {
                input.readFully(header)
            } catch (e: EOFException) {
                return null
            }
            val bb = ByteBuffer.wrap(header).order(ByteOrder.LITTLE_ENDIAN)
            val cmd = bb.getInt()
            val a0 = bb.getInt()
            val a1 = bb.getInt()
            val len = bb.getInt()
            val sum = bb.getInt()
            val magic = bb.getInt()
            if (magic != cmd.inv()) throw IOException("bad adb packet magic for ${name(cmd)}")
            if (len < 0 || len > maxData) throw IOException("adb packet too large: $len")
            val data = if (len == 0) EMPTY else ByteArray(len).also { input.readFully(it) }
            if (verifyChecksum && checksum(data) != sum) throw IOException("bad adb packet checksum")
            return AdbMessage(cmd, a0, a1, data)
        }
    }
}
