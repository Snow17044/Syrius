package fr.syrius.app;

import android.app.DownloadManager;
import android.content.Context;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.net.Uri;

import com.google.mediapipe.tasks.genai.llminference.LlmInference;
import com.google.mediapipe.tasks.genai.llminference.LlmInferenceSession;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.security.MessageDigest;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * IA hors ligne : un petit modèle open source (Qwen 2.5, licence Apache 2.0) qui tourne sur le téléphone
 * avec MediaPipe. Aucune donnée ne quitte le téléphone pendant la conversation.
 *
 * Sécurité : seuls deux fichiers connus peuvent être téléchargés (adresse et empreinte SHA-256 fixées
 * dans le code) ; le fichier est vérifié avant toute utilisation et supprimé s'il ne correspond pas.
 */
class LocalAI {
    interface Sink {
        void chunk(String requestId, String text, boolean done, String error);
    }

    static final class Model {
        final String id, label, file, sha256;
        final long size;

        Model(String id, String label, String file, String sha256, long size) {
            this.id = id;
            this.label = label;
            this.file = file;
            this.sha256 = sha256;
            this.size = size;
        }

        String url() {
            String repo = id.startsWith("qwen-0.5") ? "Qwen2.5-0.5B-Instruct" : "Qwen2.5-1.5B-Instruct";
            return "https://huggingface.co/litert-community/" + repo + "/resolve/main/" + file;
        }
    }

    static final Model[] MODELS = {
            new Model("qwen-1.5b", "Intelligent — Qwen 2.5 1.5B (1,6 Go)",
                    "Qwen2.5-1.5B-Instruct_multi-prefill-seq_q8_ekv1280.task",
                    "8d867a7c93a6acf2892f08e0174e2f6f351ad256b7e3cfb6d6cd9c89794b42e0", 1_598_000_000L),
            new Model("qwen-0.5b", "Rapide — Qwen 2.5 0.5B (550 Mo)",
                    "Qwen2.5-0.5B-Instruct_multi-prefill-seq_q8_ekv1280.task",
                    "e608953f169aeb1bd7b9155fec2559825e08453fc209b84eda3a781ed0452fd2", 547_000_000L),
    };
    private static final int MAX_TOKENS = 1280;  // taille de mémoire du fichier (« ekv1280 »)
    private static final int MAX_PROMPT_CHARS = 2400;  // garde de la place pour la réponse

    private final Context ctx;
    private final SharedPreferences prefs;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private LlmInference engine;
    private String engineModel;
    private LlmInferenceSession session;
    private volatile String verifying;
    private volatile String lastError = "";
    private volatile String stopped = "";

    LocalAI(Context ctx) {
        this.ctx = ctx.getApplicationContext();
        this.prefs = ctx.getSharedPreferences("syrius_local", Context.MODE_PRIVATE);
    }

    private static Model find(String id) {
        for (Model m : MODELS) if (m.id.equals(id)) return m;
        return null;
    }

    private File dir() {
        File d = new File(ctx.getExternalFilesDir(null), "models");
        //noinspection ResultOfMethodCallIgnored
        d.mkdirs();
        return d;
    }

    private File fileFor(Model m) {
        return new File(dir(), m.file);
    }

    // ------------------------------------------------------------------ état
    synchronized String info() {
        try {
            JSONObject o = new JSONObject();
            JSONArray list = new JSONArray();
            for (Model m : MODELS) {
                list.put(new JSONObject().put("id", m.id).put("label", m.label).put("size", m.size));
            }
            o.put("models", list);
            String installed = prefs.getString("installed", "");
            Model im = find(installed);
            o.put("installed", im != null && fileFor(im).exists() ? installed : "");
            o.put("verifying", verifying != null);
            o.put("error", lastError);
            long dl = prefs.getLong("download", -1);
            if (dl >= 0) {
                DownloadManager dm = (DownloadManager) ctx.getSystemService(Context.DOWNLOAD_SERVICE);
                try (Cursor c = dm.query(new DownloadManager.Query().setFilterById(dl))) {
                    if (c != null && c.moveToFirst()) {
                        int status = c.getInt(c.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));
                        long done = c.getLong(c.getColumnIndexOrThrow(DownloadManager.COLUMN_BYTES_DOWNLOADED_SO_FAR));
                        long total = c.getLong(c.getColumnIndexOrThrow(DownloadManager.COLUMN_TOTAL_SIZE_BYTES));
                        if (status == DownloadManager.STATUS_SUCCESSFUL) {
                            onDownloaded();
                        } else if (status == DownloadManager.STATUS_FAILED) {
                            prefs.edit().remove("download").apply();
                            lastError = "Le téléchargement a échoué. Vérifie ta connexion et réessaie.";
                        } else {
                            o.put("downloading", prefs.getString("downloading", ""));
                            o.put("progress", total > 0 ? (int) (done * 100 / total) : 0);
                        }
                    } else {
                        prefs.edit().remove("download").apply();
                    }
                }
            }
            return o.toString();
        } catch (Exception e) {
            return "{\"error\":\"Informations indisponibles\"}";
        }
    }

    boolean ready() {
        Model m = find(prefs.getString("installed", ""));
        return m != null && fileFor(m).exists() && verifying == null;
    }

    // ------------------------------------------------------------------ téléchargement
    synchronized String download(String id) {
        Model m = find(id);
        if (m == null) return "Modèle inconnu";
        if (prefs.getLong("download", -1) >= 0 || verifying != null) return "Téléchargement déjà en cours";
        lastError = "";
        File target = fileFor(m);
        //noinspection ResultOfMethodCallIgnored
        target.delete();
        DownloadManager.Request req = new DownloadManager.Request(Uri.parse(m.url()))
                .setTitle("Syrius — IA hors ligne")
                .setDescription(m.label)
                .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                .setDestinationInExternalFilesDir(ctx, null, "models/" + m.file)
                .setAllowedOverMetered(true)
                .setAllowedOverRoaming(false);
        DownloadManager dm = (DownloadManager) ctx.getSystemService(Context.DOWNLOAD_SERVICE);
        long dl = dm.enqueue(req);
        prefs.edit().putLong("download", dl).putString("downloading", id).apply();
        return "ok";
    }

    synchronized void cancel() {
        long dl = prefs.getLong("download", -1);
        if (dl >= 0) {
            ((DownloadManager) ctx.getSystemService(Context.DOWNLOAD_SERVICE)).remove(dl);
        }
        prefs.edit().remove("download").remove("downloading").apply();
    }

    /** Fichier reçu : on vérifie son empreinte avant de l'accepter. */
    private void onDownloaded() {
        String id = prefs.getString("downloading", "");
        prefs.edit().remove("download").remove("downloading").apply();
        Model m = find(id);
        if (m == null) return;
        verifying = id;
        worker.execute(() -> {
            File f = fileFor(m);
            String sha = sha256(f);
            if (m.sha256.equals(sha)) {
                closeEngine();
                // un seul modèle gardé : on supprime l'autre pour libérer la place
                for (Model other : MODELS) {
                    if (other != m) //noinspection ResultOfMethodCallIgnored
                        fileFor(other).delete();
                }
                prefs.edit().putString("installed", id).apply();
                lastError = "";
            } else {
                //noinspection ResultOfMethodCallIgnored
                f.delete();
                lastError = "Fichier corrompu ou modifié : supprimé par sécurité. Réessaie le téléchargement.";
            }
            verifying = null;
        });
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

    synchronized void delete() {
        cancel();
        closeEngine();
        for (Model m : MODELS) //noinspection ResultOfMethodCallIgnored
            fileFor(m).delete();
        prefs.edit().remove("installed").apply();
    }

    // ------------------------------------------------------------------ conversation
    private void closeEngine() {
        try {
            if (session != null) session.close();
        } catch (Exception ignored) {
        }
        try {
            if (engine != null) engine.close();
        } catch (Exception ignored) {
        }
        session = null;
        engine = null;
        engineModel = null;
    }

    /** Modèle de conversation Qwen (ChatML). */
    static String buildPrompt(JSONObject req) {
        String system = req.optString("system", "");
        JSONArray msgs = req.optJSONArray("messages");
        StringBuilder turns = new StringBuilder();
        if (msgs != null) {
            for (int i = msgs.length() - 1; i >= 0; i--) {  // les plus récents d'abord, dans la limite
                JSONObject m = msgs.optJSONObject(i);
                if (m == null) continue;
                String role = "assistant".equals(m.optString("role")) ? "assistant" : "user";
                String text = m.optString("text", "").replace("<|im_start|>", "").replace("<|im_end|>", "");
                if (text.length() > 900) text = text.substring(0, 900);
                String turn = "<|im_start|>" + role + "\n" + text + "<|im_end|>\n";
                if (turns.length() + turn.length() > MAX_PROMPT_CHARS && turns.length() > 0) break;
                turns.insert(0, turn);
            }
        }
        return "<|im_start|>system\n" + system + "<|im_end|>\n" + turns + "<|im_start|>assistant\n";
    }

    void chat(String requestId, JSONObject req, Sink sink) {
        worker.execute(() -> {
            try {
                Model m = find(prefs.getString("installed", ""));
                if (m == null || !fileFor(m).exists()) {
                    sink.chunk(requestId, "", true, "Aucune IA hors ligne installée.");
                    return;
                }
                if (engine == null || !m.id.equals(engineModel)) {
                    closeEngine();
                    LlmInference.LlmInferenceOptions opts = LlmInference.LlmInferenceOptions.builder()
                            .setModelPath(fileFor(m).getAbsolutePath())
                            .setMaxTokens(MAX_TOKENS)
                            .build();
                    engine = LlmInference.createFromOptions(ctx, opts);
                    engineModel = m.id;
                }
                if (session != null) {
                    session.close();
                }
                session = LlmInferenceSession.createFromOptions(engine,
                        LlmInferenceSession.LlmInferenceSessionOptions.builder()
                                .setTopK(40).setTemperature(0.6f).build());
                session.addQueryChunk(buildPrompt(req));
                final Object lock = new Object();
                final boolean[] finished = {false};
                session.generateResponseAsync((partial, done) -> {
                    String text = partial == null ? "" : partial.replace("<|im_end|>", "");
                    if (!requestId.equals(stopped) || done) sink.chunk(requestId, text, done, null);
                    if (done) {
                        synchronized (lock) {
                            finished[0] = true;
                            lock.notifyAll();
                        }
                    }
                });
                synchronized (lock) {  // une seule génération à la fois
                    long end = System.currentTimeMillis() + 180_000;
                    while (!finished[0] && System.currentTimeMillis() < end) lock.wait(1000);
                }
            } catch (Throwable e) {
                closeEngine();
                sink.chunk(requestId, "", true, "L'IA hors ligne n'a pas pu répondre : "
                        + (e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage()));
            }
        });
    }

    /** Arrêt demandé : la suite de la réponse est ignorée (la génération s'arrête d'elle-même). */
    void stop(String requestId) {
        stopped = requestId;
    }

    /** Libère la mémoire du modèle (rechargé automatiquement à la prochaine question). */
    void release() {
        worker.execute(this::closeEngine);
    }

    void shutdown() {
        worker.execute(this::closeEngine);
        worker.shutdown();
    }
}
