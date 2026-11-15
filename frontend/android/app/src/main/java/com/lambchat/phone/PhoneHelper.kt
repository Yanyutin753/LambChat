package com.lambchat.phone

import android.content.ComponentName
import android.content.Intent
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.os.Build
import android.os.Looper
import org.json.JSONObject
import java.io.BufferedReader
import java.util.concurrent.TimeUnit

/** Shell-only helper over the authenticated ADB stream. No exported socket or Binder. */
object PhoneHelper {
    @JvmStatic fun main(args: Array<String>) {
        check(android.os.Process.myUid() == 2000) { "shell identity required" }
        Looper.prepareMainLooper()
        val context = ShellContext.create()
        val manager = DisplayManager::class.java.getDeclaredConstructor(android.content.Context::class.java).apply { isAccessible = true }.newInstance(context)
        var virtual: VirtualDisplay? = null
        var images: ImageReader? = null
        val opened = mutableSetOf<String>()
        val keepAwake = java.util.concurrent.Executors.newSingleThreadScheduledExecutor()
        var awake: java.util.concurrent.ScheduledFuture<*>? = null

        fun tasks(): List<Any> {
            val atm = Class.forName("android.app.ActivityTaskManager").getMethod("getService").invoke(null)
            @Suppress("UNCHECKED_CAST")
            return atm.javaClass.getMethod("getAllRootTaskInfos").invoke(atm) as List<Any>
        }
        fun moveToMain() {
            val id = virtual?.display?.displayId ?: return
            val atm = Class.forName("android.app.ActivityTaskManager").getMethod("getService").invoke(null)
            tasks().filter { it.javaClass.getField("displayId").getInt(it) == id }.forEach {
                val top = it.javaClass.getField("topActivity").get(it) as? ComponentName
                val base = it.javaClass.getField("baseActivity").get(it) as? ComponentName
                if (top?.packageName in opened || base?.packageName in opened) atm.javaClass.getMethod("moveRootTaskToDisplay", Int::class.javaPrimitiveType, Int::class.javaPrimitiveType)
                    .invoke(atm, it.javaClass.getField("taskId").getInt(it), 0)
            }
        }
        Thread({
            try {
                val input = System.`in`.bufferedReader()
                while (true) {
                    val line = boundedLine(input, 65536) ?: break
                    val response = try {
                        val command = JSONObject(line)
                        when (command.getString("op")) {
                            "hello" -> JSONObject().put("uid", android.os.Process.myUid()).put("protocol", 1)
                            "background" -> {
                                check(Build.VERSION.SDK_INT >= 34) { "independent background focus requires Android 14" }
                                if (virtual == null) {
                                    images = ImageReader.newInstance(720, 1280, PixelFormat.RGBA_8888, 2)
                                    images!!.setOnImageAvailableListener({ reader -> reader.acquireLatestImage()?.close() }, android.os.Handler(Looper.getMainLooper()))
                                    // Mika's trusted display flags: separate group/focus, never steal the main focus.
                                    val flags = 1 or 8 or 64 or 128 or 256 or 1024 or 2048 or 4096 or 8192 or 16384 or 65536
                                    virtual = manager.createVirtualDisplay("LambChat Agent", 720, 1280, 240, images!!.surface, flags)
                                    val wm = Class.forName("android.view.WindowManagerGlobal").getMethod("getWindowManagerService").invoke(null)
                                    wm.javaClass.getMethod("setWindowingMode", Int::class.javaPrimitiveType, Int::class.javaPrimitiveType).invoke(wm, virtual!!.display.displayId, 1)
                                    wm.javaClass.getMethod("setDisplayImePolicy", Int::class.javaPrimitiveType, Int::class.javaPrimitiveType).invoke(wm, virtual!!.display.displayId, 0)
                                    val ownedDisplay = virtual!!.display.displayId
                                    val binder = Class.forName("android.os.ServiceManager").getMethod("getService", String::class.java).invoke(null, "power")
                                    val power = Class.forName("android.os.IPowerManager\$Stub").getMethod("asInterface", android.os.IBinder::class.java).invoke(null, binder)
                                    val activity = power.javaClass.getMethod("userActivity", Int::class.javaPrimitiveType, Long::class.javaPrimitiveType, Int::class.javaPrimitiveType, Int::class.javaPrimitiveType)
                                    awake = keepAwake.scheduleWithFixedDelay({ runCatching { activity.invoke(power, ownedDisplay, android.os.SystemClock.uptimeMillis(), 2, 0) } }, 0, 4, TimeUnit.SECONDS)
                                }
                                JSONObject().put("display", virtual!!.display.displayId)
                            }
                            "launch" -> {
                                val pkg = command.getString("app")
                                require(pkg.matches(Regex("[A-Za-z][A-Za-z0-9_]*(\\.[A-Za-z0-9_]+)+")))
                                val id = command.getInt("display")
                                require(id == 0 || id == virtual?.display?.displayId)
                                // Do not move an app the user is currently using to an invisible display.
                                if (id != 0) check(tasks().none {
                                    it.javaClass.getField("displayId").getInt(it) == 0 &&
                                        (it.javaClass.getField("topActivity").get(it) as? ComponentName)?.packageName == pkg &&
                                        runCatching { it.javaClass.getField("isVisible").getBoolean(it) }.getOrDefault(true)
                                }) { "app_in_use_on_main_display" }
                                val intent = context.packageManager.getLaunchIntentForPackage(pkg) ?: error("app has no launcher")
                                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                                val component = intent.component?.flattenToShortString() ?: error("missing app component")
                                val process = ProcessBuilder("/system/bin/am", "start", "-W", "--display", "$id", "-n", component).redirectErrorStream(true).start()
                                if (!process.waitFor(8, TimeUnit.SECONDS)) { process.destroyForcibly(); error("app launch timed out; observe before retry") }
                                val output = process.inputStream.bufferedReader().readText().take(8192)
                                check(process.exitValue() == 0 && !output.contains("Error:")) { "app launch rejected: $output" }
                                opened.add(pkg)
                                JSONObject().put("ok", true).put("display", id)
                            }
                            "key" -> {
                                val id = command.getInt("display"); val key = command.getInt("key")
                                require(id == 0 || id == virtual?.display?.displayId)
                                require(key in setOf(3, 4, 61, 66, 67))
                                val process = ProcessBuilder("/system/bin/input", "-d", "$id", "keyevent", "$key").redirectErrorStream(true).start()
                                if (!process.waitFor(3, TimeUnit.SECONDS)) { process.destroyForcibly(); error("input timeout") }
                                check(process.exitValue() == 0) { "input rejected" }
                                JSONObject().put("ok", true)
                            }
                            "takeover" -> { moveToMain(); JSONObject().put("ok", true) }
                            else -> error("unsupported helper operation")
                        }
                    } catch (e: Exception) { JSONObject().put("error", e.cause?.message ?: e.message ?: "helper failed") }
                    System.out.println("LAMBCHAT_PHONE " + response.toString())
                    System.out.flush()
                }
            } finally {
                runCatching { moveToMain() }
                awake?.cancel(false); keepAwake.shutdownNow()
                virtual?.release(); images?.close()
                kotlin.system.exitProcess(0)
            }
        }, "phone-commands").start()
        Looper.loop()
    }

    fun boundedLine(reader: BufferedReader, limit: Int): String? {
        val line = StringBuilder()
        while (true) {
            val char = reader.read()
            if (char == -1) return if (line.isEmpty()) null else error("truncated request")
            if (char == 10) return line.toString()
            check(line.length < limit) { "request too large" }
            line.append(char.toChar())
        }
    }
}
