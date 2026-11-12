package fr.syrius.app;

import android.app.DownloadManager;
import android.content.Context;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.net.Uri;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.security.MessageDigest;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/**
 * Modèle de reconnaissance vocale hors ligne Vosk (français, 42 Mo, licence Apache 2.0) pour « Hey Syrius ».
 * Adresse et empreinte SHA-256 fixées ici ; le fichier est vérifié avant d'être décompressé.
 */
final class WakeModel {
    static final String URL = "https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip";
    static final String SHA256 = "cabf6180e177eb9b3a9a9d43a437bd5e549f3a7d09525e5d69a3fed787be12ad";
    static final String FOLDER = "vosk-model-small-fr-0.22";
    private static final long MAX_UNZIPPED = 200L * 1024 * 1024;

    private WakeModel() {
    }

    private static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences("syrius_wake", Context.MODE_PRIVATE);
    }

    static File dir(Context c) {
        return new File(new File(c.getFilesDir(), "vosk"), FOLDER);
    }

    static boolean ready(Context c) {
        return new File(dir(c), "am/final.mdl").exists() && prefs(c).getBoolean("model_ok", false);
    }

    private static File zip(Context c) {
        return new File(c.getExternalFilesDir(null), "vosk/" + FOLDER + ".zip");
    }

    static synchronized String download(Context c) {
        if (prefs(c).getLong("dl", -1) >= 0) return "Téléchargement déjà en cours";
        //noinspection ResultOfMethodCallIgnored
        zip(c).delete();
        DownloadManager.Request r = new DownloadManager.Request(Uri.parse(URL))
                .setTitle("Syrius — « Hey Syrius »").setDescription("Reconnaissance vocale hors ligne (42 Mo)")
                .setDestinationInExternalFilesDir(c, null, "vosk/" + FOLDER + ".zip")
                .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE);
        long id = ((DownloadManager) c.getSystemService(Context.DOWNLOAD_SERVICE)).enqueue(r);
        prefs(c).edit().putLong("dl", id).putString("err", "").apply();
        return "ok";
    }

    /** État : {ready, downloading, progress, installing, error}. Termine l'installation si le fichier est arrivé. */
    static synchronized String info(Context c) {
        SharedPreferences p = prefs(c);
        String state = "{\"ready\":" + ready(c);
        long id = p.getLong("dl", -1);
        if (id >= 0) {
            DownloadManager dm = (DownloadManager) c.getSystemService(Context.DOWNLOAD_SERVICE);
            try (Cursor cur = dm.query(new DownloadManager.Query().setFilterById(id))) {
                if (cur != null && cur.moveToFirst()) {
                    int st = cur.getInt(cur.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));
                    long done = cur.getLong(cur.getColumnIndexOrThrow(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR));
                    long total = cur.getLong(cur.getColumnIndexOrThrow(DownloadManager.COLUMN_TOTAL_SIZE_BYTES));
                    if (st == DownloadManager.STATUS_SUCCESSFUL) {
                        p.edit().remove("dl").putBoolean("installing", true).apply();
                        new Thread(() -> install(c)).start();
                    } else if (st == DownloadManager.STATUS_FAILED) {
                        p.edit().remove("dl").putString("err", "Téléchargement échoué, réessaie.").apply();
                    } else {
                        state += ",\"downloading\":true,\"progress\":" + (total > 0 ? done * 100 / total : 0);
                    }
                } else {
                    p.edit().remove("dl").apply();
                }
            }
        }
        state += ",\"installing\":" + p.getBoolean("installing", false);
        String err = p.getString("err", "");
        return state + ",\"error\":" + org.json.JSONObject.quote(err == null ? "" : err) + "}";
    }

    private static void install(Context c) {
        SharedPreferences p = prefs(c);
        File z = zip(c);
        try {
            if (!SHA256.equals(sha256(z))) throw new SecurityException("empreinte");
            File root = new File(c.getFilesDir(), "vosk");
            deleteTree(root);
            unzip(z, root);
            if (!new File(dir(c), "am/final.mdl").exists()) throw new IllegalStateException("contenu");
            p.edit().putBoolean("model_ok", true).putString("err", "").apply();
        } catch (SecurityException e) {
            p.edit().putString("err", "Fichier modifié ou corrompu : supprimé par sécurité.").apply();
        } catch (Exception e) {
            p.edit().putString("err", "Installation impossible : " + e.getClass().getSimpleName()).apply();
        } finally {
            //noinspection ResultOfMethodCallIgnored
            z.delete();
            p.edit().putBoolean("installing", false).apply();
        }
    }

    /** Décompression protégée (aucun fichier ne peut sortir du dossier prévu, taille limitée). */
    private static void unzip(File zipFile, File dest) throws Exception {
        String base = dest.getCanonicalPath() + File.separator;
        long total = 0;
        byte[] buf = new byte[1 << 16];
        try (ZipInputStream zin = new ZipInputStream(new FileInputStream(zipFile))) {
            ZipEntry e;
            while ((e = zin.getNextEntry()) != null) {
                File out = new File(dest, e.getName());
                if (!out.getCanonicalPath().startsWith(base)) throw new SecurityException("chemin");
                if (e.isDirectory()) {
                    //noinspection ResultOfMethodCallIgnored
                    out.mkdirs();
                    continue;
                }
                //noinspection ResultOfMethodCallIgnored
                out.getParentFile().mkdirs();
                try (FileOutputStream fo = new FileOutputStream(out)) {
                    int n;
                    while ((n = zin.read(buf)) > 0) {
                        total += n;
                        if (total > MAX_UNZIPPED) throw new SecurityException("taille");
                        fo.write(buf, 0, n);
                    }
                }
            }
        }
    }

    private static void deleteTree(File f) {
        File[] kids = f.listFiles();
        if (kids != null) for (File k : kids) deleteTree(k);
        //noinspection ResultOfMethodCallIgnored
        f.delete();
    }

    static void delete(Context c) {
        prefs(c).edit().putBoolean("model_ok", false).apply();
        deleteTree(new File(c.getFilesDir(), "vosk"));
    }

    private static String sha256(File f) {
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
