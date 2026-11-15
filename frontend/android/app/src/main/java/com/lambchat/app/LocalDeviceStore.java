package com.lambchat.app;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.AtomicFile;
import org.json.JSONObject;
import java.io.File;
import java.io.FileOutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.KeyStore;
import java.util.Arrays;
import java.util.UUID;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** Pairing is encrypted, excluded from backup, and bound to its issuing origin. */
final class LocalDeviceStore {
    private static final String KEY = "lambchat.local-device";
    private final Context context;
    LocalDeviceStore(Context context) { this.context = context; }

    static String origin(String value) throws Exception {
        URI uri = new URI(value);
        String host = uri.getHost();
        String scheme = uri.getScheme();
        if (host == null || uri.getRawUserInfo() != null || uri.getRawQuery() != null
                || uri.getRawFragment() != null || value.chars().anyMatch(c -> c <= 32)
                || !("https".equals(scheme) || "http".equals(scheme)))
            throw new IllegalArgumentException("Invalid server URL");
        host = host.toLowerCase(java.util.Locale.ROOT);
        boolean loopback = host.equals("localhost") || host.equals("[::1]") || host.equals("::1")
                || host.matches("127\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}");
        if ("http".equals(scheme) && !loopback)
            throw new IllegalArgumentException("Remote servers require HTTPS");
        int port = uri.getPort();
        if (port > 65535 || port == 0) throw new IllegalArgumentException("Invalid port");
        return scheme + "://" + host + (port == -1 || port == (scheme.equals("https") ? 443 : 80) ? "" : ":" + port);
    }

    File home() { return new File(context.getNoBackupFilesDir(), "local-device"); }
    private AtomicFile credential() { return new AtomicFile(new File(home(), "pairing.enc")); }

    String machineId() throws Exception {
        home().mkdirs();
        AtomicFile file = new AtomicFile(new File(home(), "machine-id"));
        if (file.getBaseFile().exists()) return new String(file.readFully(), StandardCharsets.UTF_8);
        String id = UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        write(file, id.getBytes(StandardCharsets.UTF_8));
        return id;
    }

    private SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (store.containsAlias(KEY)) return (SecretKey) store.getKey(KEY, null);
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(KEY, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
        return generator.generateKey();
    }

    JSONObject read() throws Exception {
        if (!credential().getBaseFile().exists()) return null;
        byte[] data = credential().readFully();
        if (data.length < 29) throw new IllegalStateException("Invalid pairing record");
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Arrays.copyOfRange(data, 0, 12)));
        return new JSONObject(new String(cipher.doFinal(data, 12, data.length - 12), StandardCharsets.UTF_8));
    }

    void save(JSONObject data) throws Exception {
        origin(data.getString("serverUrl"));
        String token = data.getString("pat");
        if (token.isEmpty() || token.length() > 8192 || token.chars().anyMatch(c -> c < 33 || c > 126))
            throw new IllegalArgumentException("Invalid pairing token");
        policy(data.getString("confirmPolicy"));
        data.put("machineId", machineId());
        data.put("machineName", android.os.Build.MODEL);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key());
        byte[] encrypted = cipher.doFinal(data.toString().getBytes(StandardCharsets.UTF_8));
        byte[] result = new byte[12 + encrypted.length];
        System.arraycopy(cipher.getIV(), 0, result, 0, 12);
        System.arraycopy(encrypted, 0, result, 12, encrypted.length);
        write(credential(), result);
    }

    static void policy(String policy) {
        if (!Arrays.asList("all", "commands", "none").contains(policy))
            throw new IllegalArgumentException("Invalid confirmation policy");
    }

    void clear() { credential().delete(); }

    static void write(AtomicFile file, byte[] data) throws Exception {
        FileOutputStream stream = null;
        try { stream = file.startWrite(); stream.write(data); file.finishWrite(stream); }
        catch (Exception e) { file.failWrite(stream); throw e; }
    }
}
