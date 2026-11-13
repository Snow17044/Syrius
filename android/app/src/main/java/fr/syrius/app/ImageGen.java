package fr.syrius.app;

import android.content.ContentValues;
import android.content.Context;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;

import java.io.File;
import java.io.FileInputStream;
import java.io.OutputStream;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Génération d'images hors ligne, version « turbo » : DreamShaper 7 (Stable Diffusion 1.5) + LCM-LoRA
 * (4 étapes) + décodeur TAESD, poids en 8 bits, calculée entièrement par le téléphone avec MNN.
 * Le modèle est préparé par la CI du projet (.github/workflows/sd-model.yml) et publié dans la release
 * « models-sd-turbo-1 » ; chaque fichier est vérifié par son empreinte SHA-256 avant usage.
 */
class ImageGen {
    interface Listener {
        void onProgress(int percent);
    }

    interface Result {
        void done(String requestId, String dataUrl, String error);
    }

    static final String BASE = "https://github.com/Snow17044/Syrius/releases/download/models-sd-turbo-1/";

    private static ModelPack.Part part(String file, String sha, long size) {
        return new ModelPack.Part(BASE + file, file, sha, size);
    }

    static final ModelPack.Part[] PARTS = {
            // @SD_PARTS@ : empreintes ajoutées dès que la CI a préparé et testé le modèle turbo
    };

    final ModelPack pack;
    private final Context ctx;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private static Boolean nativeOk;
    private volatile boolean busy;

    ImageGen(Context ctx) {
        this.ctx = ctx.getApplicationContext();
        pack = new ModelPack(ctx, "sdturbo", "Images hors ligne — turbo (1,2 Go)", PARTS);
    }

    static synchronized boolean nativeAvailable() {
        if (nativeOk == null) {
            try {
                System.loadLibrary("MNN");
                System.loadLibrary("syrius_sd");
                nativeOk = true;
            } catch (Throwable t) {
                nativeOk = false;
            }
        }
        return nativeOk;
    }

    private static native int nativeGenerate(String modelDir, String prompt, int steps, int seed, String outPath,
                                             Listener listener);

    boolean busy() {
        return busy;
    }

    /** Lance la génération ; progress(0..100) puis result(dataUrl JPEG) ou une erreur. */
    String generate(String requestId, String prompt, int steps, Listener progress, Result result) {
        if (!pack.ready()) return "Générateur d'images hors ligne non installé (Réglages → IA hors ligne).";
        if (!nativeAvailable()) return "Le moteur d'images n'est pas présent dans cette version de l'application.";
        if (busy) return "Une image est déjà en cours de création.";
        busy = true;
        worker.execute(() -> {
            File out = new File(ctx.getCacheDir(), "syrius_image.jpg");
            //noinspection ResultOfMethodCallIgnored
            out.delete();
            try {
                int seed = (int) (System.nanoTime() & 0x3fffffff);
                int code = nativeGenerate(pack.dir().getAbsolutePath(), prompt, steps, seed, out.getAbsolutePath(), progress);
                if (code != 0 || !out.exists() || out.length() < 1000) {
                    result.done(requestId, null, code == 2 ? "Le modèle d'images n'a pas pu être chargé (mémoire insuffisante ?)."
                            : "La création de l'image a échoué.");
                    return;
                }
                byte[] data = new byte[(int) out.length()];
                try (FileInputStream in = new FileInputStream(out)) {
                    int off = 0, n;
                    while (off < data.length && (n = in.read(data, off, data.length - off)) > 0) off += n;
                }
                result.done(requestId, "data:image/jpeg;base64," + Base64.encodeToString(data, Base64.NO_WRAP), null);
            } catch (Throwable t) {
                result.done(requestId, null, "La création de l'image a échoué : " + t.getMessage());
            } finally {
                //noinspection ResultOfMethodCallIgnored
                out.delete();
                busy = false;
            }
        });
        return "ok";
    }

    /** Enregistre une image JPEG (data URL) dans la galerie, dossier Images/Syrius. */
    static String save(Context ctx, String dataUrl) {
        String prefix = "data:image/jpeg;base64,";
        if (dataUrl == null || !dataUrl.startsWith(prefix) || dataUrl.length() > 8_000_000) return "Image invalide";
        try {
            byte[] bytes = Base64.decode(dataUrl.substring(prefix.length()), Base64.DEFAULT);
            if (bytes.length < 4 || (bytes[0] & 0xff) != 0xFF || (bytes[1] & 0xff) != 0xD8) return "Image invalide";
            ContentValues v = new ContentValues();
            v.put(MediaStore.Images.Media.DISPLAY_NAME, "Syrius_" + System.currentTimeMillis() + ".jpg");
            v.put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg");
            if (Build.VERSION.SDK_INT >= 29) {
                v.put(MediaStore.Images.Media.RELATIVE_PATH, Environment.DIRECTORY_PICTURES + "/Syrius");
            } else {
                return "Enregistrement disponible à partir d'Android 10.";
            }
            Uri uri = ctx.getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, v);
            if (uri == null) return "Enregistrement impossible";
            try (OutputStream os = ctx.getContentResolver().openOutputStream(uri)) {
                if (os == null) return "Enregistrement impossible";
                os.write(bytes);
            }
            return "ok";
        } catch (Exception e) {
            return "Enregistrement impossible";
        }
    }

    void shutdown() {
        worker.shutdown();
    }
}
