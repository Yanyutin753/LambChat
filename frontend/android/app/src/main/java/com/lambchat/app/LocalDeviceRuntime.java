package com.lambchat.app;

import android.content.Context;
import android.os.Build;
import org.json.JSONObject;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.*;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

final class LocalDeviceRuntime {
    static boolean supported() {
        return Build.VERSION.SDK_INT >= 30 && Arrays.asList(Build.SUPPORTED_ABIS).contains("arm64-v8a");
    }

    static File child(File root, String name) throws IOException {
        if (name.isEmpty() || name.startsWith("/") || name.contains("\\") || Arrays.asList(name.split("/")).contains(".."))
            throw new IOException("Invalid runtime path");
        File file = new File(root, name);
        if (!file.getCanonicalPath().startsWith(root.getCanonicalPath() + File.separator))
            throw new IOException("Runtime path escaped root");
        return file;
    }

    private static byte[] asset(Context context, String name) throws IOException {
        try (InputStream in = context.getAssets().open("local-device/" + name)) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buffer = new byte[65536]; int count;
            while ((count = in.read(buffer)) != -1) out.write(buffer, 0, count);
            return out.toByteArray();
        }
    }

    static File install(Context context) throws Exception {
        String digest = new String(asset(context, "runtime.sha256"), StandardCharsets.UTF_8).trim();
        if (!digest.matches("[a-f0-9]{64}")) throw new IOException("Invalid runtime digest");
        File base = new File(context.getNoBackupFilesDir(), "local-device-runtime");
        base.mkdirs();
        File root = new File(base, digest);
        if (new File(root, ".installed").isFile()) return root;
        File pending = new File(base, digest + ".pending");
        delete(pending);
        pending.mkdirs();
        try {
            MessageDigest sha = MessageDigest.getInstance("SHA-256");
            try (InputStream input = context.getAssets().open("local-device/runtime.zip")) {
                byte[] buffer = new byte[65536]; int count;
                while ((count = input.read(buffer)) != -1) sha.update(buffer, 0, count);
            }
            StringBuilder actual = new StringBuilder();
            for (byte value : sha.digest()) actual.append(String.format(Locale.ROOT, "%02x", value & 255));
            if (!digest.equals(actual.toString())) throw new IOException("Runtime checksum mismatch");
            long bytes = 0; int entries = 0;
            try (ZipInputStream zip = new ZipInputStream(context.getAssets().open("local-device/runtime.zip"))) {
                ZipEntry entry; byte[] buffer = new byte[65536];
                while ((entry = zip.getNextEntry()) != null) {
                    if (++entries > 100000) throw new IOException("Too many runtime entries");
                    File file = child(pending, entry.getName());
                    file.getParentFile().mkdirs();
                    if (entry.isDirectory()) { file.mkdirs(); continue; }
                    if (!file.createNewFile()) throw new IOException("Duplicate runtime entry");
                    try (OutputStream out = new FileOutputStream(file)) {
                        int count;
                        while ((count = zip.read(buffer)) != -1) {
                            bytes += count;
                            if (bytes > 1024L * 1024 * 1024) throw new IOException("Runtime exceeds size limit");
                            out.write(buffer, 0, count);
                        }
                    }
                }
            }
            JSONObject manifest = new JSONObject(new String(Files.readAllBytes(child(pending, "lambchat-runtime.json").toPath()), StandardCharsets.UTF_8));
            org.json.JSONArray executables = manifest.getJSONArray("executables");
            for (int i = 0; i < executables.length(); i++)
                if (!child(pending, executables.getString(i)).setExecutable(true, true)) throw new IOException("Cannot set runtime permissions");
            JSONObject links = manifest.getJSONObject("links");
            Iterator<String> names = links.keys();
            while (names.hasNext()) {
                String name = names.next();
                File file = child(pending, name);
                String target = links.getString(name);
                Path resolved = file.toPath().getParent().resolve(target).normalize();
                if (target.startsWith("/") || !resolved.startsWith(pending.toPath())) throw new IOException("Invalid runtime link");
                file.getParentFile().mkdirs();
                Files.createSymbolicLink(file.toPath(), java.nio.file.Paths.get(target));
            }
            for (String dir : Arrays.asList("tmp", "root", "lambchat", "proc", "sys", "dev")) new File(pending, dir).mkdirs();
            Files.write(new File(pending, ".installed").toPath(), digest.getBytes(StandardCharsets.UTF_8));
            if (!pending.renameTo(root)) throw new IOException("Cannot activate runtime");
            // Old runtimes are disposable; the workspace lives outside this directory.
            File[] old = base.listFiles();
            if (old != null) for (File item : old) if (!item.equals(root)) delete(item);
            return root;
        } catch (Exception e) { delete(pending); throw e; }
    }

    static void configureDns(Context context, File root) throws Exception {
        android.net.ConnectivityManager manager = context.getSystemService(android.net.ConnectivityManager.class);
        android.net.LinkProperties properties = manager.getLinkProperties(manager.getActiveNetwork());
        StringBuilder dns = new StringBuilder();
        if (properties != null) for (java.net.InetAddress address : properties.getDnsServers())
            dns.append("nameserver ").append(address.getHostAddress()).append("\n");
        if (dns.length() == 0) throw new IOException("No network DNS is available");
        Files.write(child(root, "etc/resolv.conf").toPath(), dns.toString().getBytes(StandardCharsets.UTF_8));
    }

    static Process start(Context context, File root, JSONObject pairing) throws Exception {
        Process process = command(context, root, Arrays.asList("/usr/bin/python3", "-u", "-m", "lambchat_sandbox.android"));
        try (OutputStream input = process.getOutputStream()) {
            input.write((pairing.toString() + "\n").getBytes(StandardCharsets.UTF_8));
        } catch (Exception e) { process.destroyForcibly(); throw e; }
        return process;
    }

    static Process command(Context context, File root, List<String> command) throws Exception {
        String libs = context.getApplicationInfo().nativeLibraryDir;
        File home = new LocalDeviceStore(context).home();
        new File(home, "workspaces/.shared").mkdirs();
        File tmp = new File(context.getCacheDir(), "local-device-proot"); tmp.mkdirs();
        List<String> argv = new ArrayList<>(Arrays.asList(libs + "/libmikarun.so", "--net", "on", "--",
                libs + "/libproot.so", "--kill-on-exit", "--link2symlink", "-0", "-r", root.getPath(),
                "-b", "/proc", "-b", "/sys", "-b", home.getPath() + ":/lambchat", "-w", "/lambchat"));
        for (String device : Arrays.asList("/dev/null", "/dev/zero", "/dev/random", "/dev/urandom")) {
            argv.add("-b"); argv.add(device);
        }
        argv.addAll(command);
        ProcessBuilder builder = new ProcessBuilder(argv).redirectErrorStream(true);
        Map<String, String> env = builder.environment(); env.clear();
        env.put("PROOT_LOADER", libs + "/libproot_loader.so");
        env.put("PROOT_TMP_DIR", tmp.getPath());
        env.put("PATH", "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin");
        env.put("PYTHONPATH", "/opt/lambchat");
        env.put("HOME", "/root"); env.put("TMPDIR", "/tmp"); env.put("LANG", "C.UTF-8");
        env.put("TZ", TimeZone.getDefault().getID());
        return builder.start();
    }

    static void delete(File file) throws IOException {
        if (!Files.exists(file.toPath(), LinkOption.NOFOLLOW_LINKS)) return;
        if (!Files.isSymbolicLink(file.toPath()) && file.isDirectory()) {
            File[] children = file.listFiles();
            if (children == null) throw new IOException("Cannot list runtime directory");
            for (File item : children) delete(item);
        }
        Files.delete(file.toPath());
    }
}
