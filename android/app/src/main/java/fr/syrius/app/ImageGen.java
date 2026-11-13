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
 * Génération d'images hors ligne : Stable Diffusion 1.5 (version MNN d'Alibaba, poids en 8 bits)
 * calculée entièrement par le téléphone. Lent sur un téléphone milieu de gamme (quelques minutes),
 * mais gratuit, sans limite et sans Internet.
 */
class ImageGen {
    interface Listener {
        void onProgress(int percent);
    }

    interface Result {
        void done(String requestId, String dataUrl, String error);
    }

    static final String REPO = "taobao-mnn/stable-diffusion-v1-5-mnn-general";
    static final String REV = "56c93a62ac9d6b5d18605632b85e25f87281f317";

    private static ModelPack.Part part(String file, String sha, long size) {
        return new ModelPack.Part("https://huggingface.co/" + REPO + "/resolve/" + REV + "/" + file, file, sha, size);
    }

    static final ModelPack.Part[] PARTS = {
            part("text_encoder.mnn", "9fb787d566512379dcdf9e25b43d9169b7b85eda423408706cf3a56c63dff6dd", 249_944L),
            part("text_encoder.mnn.weight", "c245ac80dd8a72279976414435801d579a8dcf83aba84e121c4e4a0b74bbed3d", 238_120_368L),
            part("unet.mnn", "3895d9101b16f99660010c87cf1413407103a237636d6a112de11a674a960d4c", 1_353_144L),
            part("unet.mnn.weight", "904302004049d81dfa88035dc945e18ea9823a1bfa75bdfefb8f792ade9ea8bb", 863_650_252L),
            part("vae_decoder.mnn", "8599ec07791cf635058f5d38981f318c7939e8d5274bb8bfe49d57d2962e3220", 183_960L),
            part("vae_decoder.mnn.weight", "251c9025a6ae2164746ca549ebfc3ce63df418e23abab5abe41c2bc0b1f9b7ff", 49_639_636L),
            part("vocab.json", "e089ad92ba36837a0d31433e555c8f45fe601ab5c221d4f607ded32d9f7a4349", 1_059_962L),
            part("merges.txt", "9fd691f7c8039210e0fced15865466c65820d09b63988b0174bfe25de299051a", 524_619L)
    };

    final ModelPack pack;
    private final Context ctx;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private static Boolean nativeOk;
    private volatile boolean busy;

    ImageGen(Context ctx) {
        this.ctx = ctx.getApplicationContext();
        pack = new ModelPack(ctx, "sd15", "Images hors ligne — Stable Diffusion 1.5 (1,2 Go)", PARTS);
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
