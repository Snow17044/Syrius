package fr.syrius.app;

import android.app.DownloadManager;
import android.content.Context;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.net.Uri;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.security.MessageDigest;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Un « paquet » de modèle hors ligne (un ou plusieurs fichiers) téléchargé depuis une adresse FIXE.
 *
 * Sécurité : chaque fichier a une adresse figée (révision précise du dépôt, impossible à modifier
 * après coup) et une empreinte SHA-256 inscrite dans le code. Tout fichier qui ne correspond pas est
 * supprimé et le paquet n'est jamais utilisé.
 */
class ModelPack {
    static final class Part {
        final String url, file, sha256;
        final long size;

        Part(String url, String file, String sha256, long size) {
            this.url = url;
            this.file = file;
            this.sha256 = sha256;
            this.size = size;
        }
    }

    final String id, label;
    final Part[] parts;
    private final Context ctx;
    private final SharedPreferences prefs;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private volatile boolean verifying;
    private volatile String lastError = "";

    ModelPack(Context ctx, String id, String label, Part[] parts) {
        this.ctx = ctx.getApplicationContext();
        this.id = id;
        this.label = label;
        this.parts = parts;
        this.prefs = ctx.getSharedPreferences("syrius_pack_" + id, Context.MODE_PRIVATE);
    }

    File dir() {
        File d = new File(ctx.getExternalFilesDir(null), "packs/" + id);
        //noinspection ResultOfMethodCallIgnored
        d.mkdirs();
        return d;
    }

    File file(String name) {
        return new File(dir(), name);
    }

    long totalSize() {
        long t = 0;
        for (Part p : parts) t += p.size;
        return t;
    }

    boolean ready() {
        if (verifying || !prefs.getBoolean("installed", false)) return false;
        for (Part p : parts) if (!file(p.file).exists()) return false;
        return true;
    }

    private long[] downloads() {
        String s = prefs.getString("downloads", "");
        if (s.isEmpty()) return new long[0];
        String[] bits = s.split(",");
        long[] out = new long[bits.length];
        for (int i = 0; i < bits.length; i++) out[i] = Long.parseLong(bits[i]);
        return out;
    }

    /** État pour l'interface : installé, progression, erreur. */
    synchronized JSONObject info() {
        JSONObject o = new JSONObject();
        try {
            o.put("id", id).put("label", label).put("size", totalSize());
            long[] dls = downloads();
            if (dls.length > 0) {
                DownloadManager dm = (DownloadManager) ctx.getSystemService(Context.DOWNLOAD_SERVICE);
                long done = 0;
                int finished = 0;
                boolean failed = false;
                try (Cursor c = dm.query(new DownloadManager.Query().setFilterById(dls))) {
                    while (c != null && c.moveToNext()) {
                        int status = c.getInt(c.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));
                        done += Math.max(0, c.getLong(c.getColumnIndexOrThrow(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR)));
                        if (status == DownloadManager.STATUS_SUCCESSFUL) finished++;
                        if (status == DownloadManager.STATUS_FAILED) failed = true;
                    }
                }
                if (failed) {
                    cancel();
                    lastError = "Le téléchargement a échoué. Vérifie ta connexion et la place libre, puis réessaie.";
                } else if (finished == dls.length) {
                    prefs.edit().remove("downloads").apply();
                    verify();
                } else {
                    o.put("downloading", true).put("progress", (int) Math.min(99, done * 100 / Math.max(1, totalSize())));
                }
            }
            o.put("installed", ready());
            o.put("verifying", verifying);
            o.put("error", lastError);
        } catch (Exception e) {
            try { o.put("error", "Informations indisponibles"); } catch (Exception ignored) { }
        }
        return o;
    }

    synchronized String download() {
        if (downloads().length > 0 || verifying) return "Téléchargement déjà en cours";
        if (ready()) return "ok";
        lastError = "";
        DownloadManager dm = (DownloadManager) ctx.getSystemService(Context.DOWNLOAD_SERVICE);
        StringBuilder ids = new StringBuilder();
        prefs.edit().putBoolean("installed", false).apply();
        for (Part p : parts) {
            File target = file(p.file);
            //noinspection ResultOfMethodCallIgnored
            target.delete();
            DownloadManager.Request req = new DownloadManager.Request(Uri.parse(p.url))
                    .setTitle("Syrius — " + label)
                    .setDescription(p.file)
                    .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE)
                    .setDestinationInExternalFilesDir(ctx, null, "packs/" + id + "/" + p.file)
                    .setAllowedOverMetered(true)
                    .setAllowedOverRoaming(false);
            if (ids.length() > 0) ids.append(',');
            ids.append(dm.enqueue(req));
        }
        prefs.edit().putString("downloads", ids.toString()).apply();
        return "ok";
    }

    synchronized void cancel() {
        long[] dls = downloads();
        if (dls.length > 0) ((DownloadManager) ctx.getSystemService(Context.DOWNLOAD_SERVICE)).remove(dls);
        prefs.edit().remove("downloads").apply();
    }

    synchronized void delete() {
        cancel();
        for (Part p : parts) //noinspection ResultOfMethodCallIgnored
            file(p.file).delete();
        prefs.edit().putBoolean("installed", false).apply();
    }

    /** Tous les fichiers sont arrivés : on vérifie chaque empreinte avant d'accepter le paquet. */
    private void verify() {
        verifying = true;
        worker.execute(() -> {
            boolean ok = true;
            for (Part p : parts) {
                File f = file(p.file);
                if (!p.sha256.equals(sha256(f))) {
                    ok = false;
                    break;
                }
            }
            if (ok) {
                prefs.edit().putBoolean("installed", true).apply();
                lastError = "";
            } else {
                for (Part p : parts) //noinspection ResultOfMethodCallIgnored
                    file(p.file).delete();
                lastError = "Fichier corrompu ou modifié : supprimé par sécurité. Réessaie le téléchargement.";
            }
            verifying = false;
        });
    }

    static String sha256(File f) {
        try (InputStream in = new FileInputStream(f)) {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] buf = new byte[1 << 20];
            int n;
            while ((n = in.read(buf)) > 0) md.update(buf, 0, n);
            StringBuilder sb = new StringBuilder();
            for (byte b : md.digest()) sb.append(String.format("%02x", b));
            return sb.toString();
        } catch (Exception e) {
            return "";
        }
    }
}
