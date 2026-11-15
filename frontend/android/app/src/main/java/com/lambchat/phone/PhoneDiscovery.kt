package com.lambchat.phone

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import com.lambchat.phone.adb.AdbHosts
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** Only this phone's advertised ADB ports are returned; never scans other devices. */
object PhoneDiscovery {
    @JvmStatic fun discover(context: Context): JSONObject {
        val manager = context.getSystemService(NsdManager::class.java)
        val result = JSONObject()
        for ((kind, serviceType) in listOf("pairing" to "_adb-tls-pairing._tcp.", "connect" to "_adb-tls-connect._tcp.")) {
            val ports = java.util.Collections.synchronizedSet(linkedSetOf<Int>())
            val found = CountDownLatch(1)
            val active = java.util.concurrent.atomic.AtomicBoolean(true)
            val listener = object : NsdManager.DiscoveryListener {
                override fun onDiscoveryStarted(type: String) {}
                override fun onDiscoveryStopped(type: String) {}
                override fun onStartDiscoveryFailed(type: String, code: Int) { found.countDown() }
                override fun onStopDiscoveryFailed(type: String, code: Int) {}
                override fun onServiceLost(service: NsdServiceInfo) {}
                override fun onServiceFound(service: NsdServiceInfo) {
                    if (!active.get()) return
                    manager.resolveService(service, object : NsdManager.ResolveListener {
                        override fun onResolveFailed(service: NsdServiceInfo, code: Int) {}
                        override fun onServiceResolved(service: NsdServiceInfo) {
                            val host = service.host?.hostAddress ?: return
                            if (active.get() && AdbHosts.ownAddress(host) != null && service.port in 1..65535) { ports.add(service.port); found.countDown() }
                        }
                    })
                }
            }
            try { manager.discoverServices(serviceType, NsdManager.PROTOCOL_DNS_SD, listener); found.await(3, TimeUnit.SECONDS) }
            finally { active.set(false); runCatching { manager.stopServiceDiscovery(listener) } }
            result.put(kind, JSONArray(synchronized(ports) { ports.toList() }))
        }
        return result
    }
}
