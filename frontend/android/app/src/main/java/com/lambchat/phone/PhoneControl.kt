package com.lambchat.phone

import android.content.Context
import android.content.Intent
import android.os.Build
import com.lambchat.phone.adb.*
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.InetAddress
import java.net.ServerSocket
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** Native endpoint exists only for the locally running, paired daemon. */
object PhoneControl {
    private val timer = Executors.newSingleThreadScheduledExecutor()
    @Volatile private var connection: AdbConnection? = null
    @Volatile private var stream: AdbConnection.AdbStream? = null
    private var reader: java.io.BufferedReader? = null
    @Volatile private var server: ServerSocket? = null
    @Volatile private var display = 0
    @Volatile private var paused = true
    private var context: Context? = null
    private var bridgeFile: File? = null

    @JvmStatic fun state(): JSONObject = JSONObject().put("connected", connection?.isClosed == false && stream != null)
        .put("accessibility", PhoneAccessibility.instance != null).put("paused", paused).put("display", display)
        .put("backgroundSupported", Build.VERSION.SDK_INT >= 34)

    @JvmStatic @Synchronized fun pair(context: Context, port: Int, code: String) {
        require(Build.VERSION.SDK_INT >= 30 && port in 1..65535 && code.matches(Regex("[0-9]{6}"))) { "invalid pairing details" }
        AdbPairing(AndroidAdb.tls(AndroidAdb.pairingIdentity(context))).pair("127.0.0.1", port, code)
    }

    @JvmStatic @Synchronized fun connect(context: Context, port: Int, background: Boolean) {
        require(Build.VERSION.SDK_INT >= 31 && port in 1..65535) { "phone control requires Android 12 or newer" }
        require(server != null) { "start the local device first" }
        disconnect()
        try {
            val conn = AdbConnection.open("127.0.0.1", port, AndroidAdb.tls(AndroidAdb.identity(context)))
            connection = conn
            val apk = context.applicationInfo.sourceDir.replace("'", "'\\''")
            stream = conn.exec("CLASSPATH='$apk' /system/bin/app_process /system/bin --nice-name=com.lambchat.app:phone com.lambchat.phone.PhoneHelper")
            reader = stream!!.inputStream.bufferedReader()
            check(rpc(JSONObject().put("op", "hello")).getInt("uid") == 2000)
            display = if (background) rpc(JSONObject().put("op", "background")).getInt("display") else 0
            paused = false
        } catch (e: Exception) { disconnect(); throw e }
    }

    @JvmStatic fun disconnect() {
        paused = true
        val old = stream; stream = null; old?.close()
        connection?.close(); connection = null; display = 0
        PhoneAccessibility.instance?.invalidate()
    }

    @JvmStatic fun pause() { paused = true; PhoneAccessibility.instance?.invalidate() }
    @JvmStatic @Synchronized fun resume() { check(stream != null) { "phone disconnected" }; PhoneAccessibility.instance?.invalidate(); paused = false }
    @JvmStatic @Synchronized fun takeover() { pause(); if (stream != null) rpc(JSONObject().put("op", "takeover")); display = 0 }
    fun key(display: Int, key: Int) { rpc(JSONObject().put("op", "key").put("display", display).put("key", key)) }

    private fun rpc(command: JSONObject): JSONObject {
        val current = stream ?: error("phone disconnected")
        val deadline = timer.schedule({ if (stream === current) disconnect() }, 10, TimeUnit.SECONDS)
        try {
            current.write((command.toString() + "\n").toByteArray())
            repeat(32) {
                val line = PhoneHelper.boundedLine(reader ?: error("missing stream"), 65536) ?: error("phone helper stopped")
                if (line.startsWith("LAMBCHAT_PHONE ")) {
                    val result = JSONObject(line.substring(15))
                    check(!result.has("error")) { result.optString("error") }
                    return result
                }
            }
            error("invalid helper response")
        } catch (e: Exception) { disconnect(); throw e }
        finally { deadline.cancel(false) }
    }

    @JvmStatic @Synchronized fun startBridge(context: Context) {
        if (server != null) return
        this.context = context.applicationContext
        val socket = ServerSocket(0, 4, InetAddress.getByName("127.0.0.1")); server = socket
        val token = ByteArray(32).also { SecureRandom().nextBytes(it) }.joinToString("") { "%02x".format(it) }
        val file = File(context.noBackupFilesDir, "local-device/phone-bridge.json"); file.parentFile!!.mkdirs(); bridgeFile = file
        val atomic = android.util.AtomicFile(file)
        val output = atomic.startWrite()
        try { output.write(JSONObject().put("host", "127.0.0.1").put("port", socket.localPort).put("token", token).toString().toByteArray()); atomic.finishWrite(output) }
        catch (e: Exception) { atomic.failWrite(output); socket.close(); server = null; throw e }
        file.setReadable(false, false); file.setWritable(false, false); file.setReadable(true, true); file.setWritable(true, true)
        Thread({
            while (server === socket && !socket.isClosed) {
                try { socket.accept().use { client ->
                    client.soTimeout = 5000
                    val request = JSONObject(PhoneHelper.boundedLine(client.getInputStream().bufferedReader(), 65536) ?: return@use)
                    if (!MessageDigest.isEqual(token.toByteArray(), request.optString("token").toByteArray())) return@use
                    val result = try { execute(request.getString("op"), request.getJSONObject("payload")) }
                        catch (e: Exception) { JSONObject().put("error", "phone_operation_failed").put("detail", e.cause?.message ?: e.message) }
                    client.getOutputStream().write((result.toString() + "\n").toByteArray())
                } } catch (_: Exception) { /* Closing the service cancels the endpoint; malformed peers are dropped. */ }
            }
        }, "phone-local-bridge").start()
    }

    @JvmStatic fun stopBridge() { pause(); runCatching { server?.close() }; server = null; bridgeFile?.delete(); disconnect() }

    @Synchronized private fun execute(op: String, args: JSONObject): JSONObject {
        if (op == "cua_status") return state().put("platform", "android")
        if (paused || stream == null || connection?.isClosed != false) return JSONObject().put("error", "phone_control_paused_or_disconnected")
        require(args.optString("session_id").isNotEmpty()) { "trusted session required" }
        val appContext = context ?: error("service stopped")
        if (op == "cua_apps") {
            val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
            val apps = JSONArray()
            appContext.packageManager.queryIntentActivities(intent, 0).distinctBy { it.activityInfo.packageName }.forEach {
                apps.put(JSONObject().put("name", it.activityInfo.packageName).put("title", it.loadLabel(appContext.packageManager).toString()).put("pid", it.activityInfo.applicationInfo.uid))
            }
            return JSONObject().put("apps", apps).put("platform", "android")
        }
        val target = args.optString("name", args.optString("app", ""))
        require(target.isNotEmpty() && target != appContext.packageName && target != "com.android.settings" && !target.contains("permissioncontroller")) { "choose an app package; local consent UI is protected" }
        if (op == "cua_launch" || op == "cua_activate") {
            PhoneAccessibility.instance?.invalidate()
            return rpc(JSONObject().put("op", "launch").put("app", target).put("display", display)).put("platform", "android")
        }
        val accessibility = PhoneAccessibility.instance ?: return JSONObject().put("error", "enable_phone_accessibility")
        val action = if (op == "cua_snapshot_action") args.getString("operation") else op.removePrefix("cua_")
        return accessibility.execute(action, args, display)
    }
}
