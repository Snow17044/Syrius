package fr.syrius.app;

import android.content.Context;
import android.content.SharedPreferences;

import com.google.ai.edge.litertlm.Backend;
import com.google.ai.edge.litertlm.Contents;
import com.google.ai.edge.litertlm.Conversation;
import com.google.ai.edge.litertlm.ConversationConfig;
import com.google.ai.edge.litertlm.Engine;
import com.google.ai.edge.litertlm.EngineConfig;
import com.google.ai.edge.litertlm.Message;
import com.google.ai.edge.litertlm.MessageCallback;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Pattern;

/**
 * « Syrius », NOTRE IA : Qwen 2.5 1.5B (licence Apache 2.0) entraînée pour devenir Syrius (caractère, outils,
 * français), puis convertie pour LiteRT-LM. Elle tourne entièrement sur le téléphone : gratuite, sans limite,
 * privée. Le fichier vient des « Releases » du projet, avec une empreinte SHA-256 inscrite ici.
 *
 * Mises à jour : après chaque entraînement réussi, ton Syrius annonce la nouvelle version (nom + empreinte).
 * L'application propose « Mettre à jour » ; la nouvelle version se télécharge à côté de l'ancienne (qui reste
 * utilisable), son empreinte est vérifiée, puis elle remplace l'ancienne. L'adresse reste celle des Releases.
 */
class SyriusAI {
    static final String RELEASE = "https://github.com/" + BuildConfig.SYRIUS_REPO + "/releases/download/syrius-ia/";
    /** Version publiée de notre IA (mise à jour après chaque entraînement validé). Vide = pas encore disponible. */
    static final ModelPack.Part[] PARTS = {
            // Entraînement du 14/11/2026 (524 exemples), converti par la CI ; empreinte vérifiée au téléchargement.
            new ModelPack.Part(RELEASE + "syrius-1.5b-43633673424-dynamic_wi8_afp32.litertlm",
                    "syrius-1.5b-43633673424-dynamic_wi8_afp32.litertlm",
                    "06bf04fbfbaeee4dc867e8eb1c53cc8b7d4628f2f73cb86a9af177e6bab6d942", 1_567_653_904L),
    };
    static final String LABEL = "Syrius — notre IA (1,6 Go)";
    private static final Pattern NAME = Pattern.compile("syrius-(0\\.5|1\\.5)b-[0-9]{6,15}-dynamic_wi[48]_afp32\\.litertlm");

    private final Context ctx;
    private final SharedPreferences prefs;
    private volatile ModelPack.Part model;       // version installée (ou à installer)
    volatile ModelPack pack;
    private volatile ModelPack update;           // nouvelle version en cours de téléchargement
    private volatile boolean switching;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private Engine engine;
    private volatile Conversation current;

    SyriusAI(Context ctx) {
        this.ctx = ctx.getApplicationContext();
        prefs = ctx.getSharedPreferences("syrius_ai", Context.MODE_PRIVATE);
        ModelPack.Part saved = part(prefs.getString("model", ""));
        model = saved != null ? saved : (PARTS.length > 0 ? PARTS[0] : null);
        pack = model == null ? null : new ModelPack(ctx, "syrius", LABEL, new ModelPack.Part[]{model});
        ModelPack.Part next = part(prefs.getString("update", ""));
        if (next != null && model != null && !next.file.equals(model.file))
            update = new ModelPack(ctx, "syrius-maj", "Nouvelle version de Syrius", new ModelPack.Part[]{next});
    }

    /** Version annoncée par ton Syrius : nom de fichier, empreinte et taille strictement contrôlés. */
    static ModelPack.Part part(String json) {
        try {
            JSONObject m = new JSONObject(json);
            String f = m.optString("file", ""), sha = m.optString("sha256", "");
            long size = m.optLong("size", 0);
            if (!NAME.matcher(f).matches() || !sha.matches("[0-9a-f]{64}") || size < 300_000_000L || size > 2_500_000_000L)
                return null;
            return new ModelPack.Part(RELEASE + f, f, sha, size);
        } catch (Exception e) {
            return null;
        }
    }

    private static String json(ModelPack.Part p) {
        try {
            return new JSONObject().put("file", p.file).put("sha256", p.sha256).put("size", p.size).toString();
        } catch (Exception e) {
            return "";
        }
    }

    boolean available() {
        return model != null;
    }

    /** État pour l'interface : celui du modèle installé, plus la mise à jour en cours s'il y en a une. */
    synchronized JSONObject info() throws Exception {
        if (model == null) return new JSONObject().put("available", false).put("installed", false);
        JSONObject o = pack.info().put("available", true).put("version", model.file);
        ModelPack up = update;
        if (switching) {
            o.put("update", new JSONObject().put("switching", true));
        } else if (up != null) {
            JSONObject u = up.info();
            if (u.optBoolean("installed")) {
                finishUpdate(up);
                o.put("update", new JSONObject().put("switching", true));
            } else {
                o.put("update", u.put("version", up.parts[0].file));
            }
        }
        return o;
    }

    /** « Mettre à jour » : télécharge la version annoncée à côté de l'ancienne. */
    synchronized String startUpdate(String manifest) {
        ModelPack.Part p = part(manifest);
        if (p == null) return "Version invalide";
        if (switching) return "Mise à jour en cours d'installation";
        if (model != null && p.file.equals(model.file)) return "Syrius est déjà à jour";
        if (update != null && update.parts[0].file.equals(p.file)) return update.download();
        if (update != null) update.delete();
        if (pack == null || !pack.ready()) {  // rien d'installé : on prend directement la nouvelle version
            if (pack != null) pack.delete();
            model = p;
            prefs.edit().putString("model", json(p)).remove("update").apply();
            pack = new ModelPack(ctx, "syrius", LABEL, new ModelPack.Part[]{p});
            update = null;
            return pack.download();
        }
        prefs.edit().putString("update", json(p)).apply();
        update = new ModelPack(ctx, "syrius-maj", "Nouvelle version de Syrius", new ModelPack.Part[]{p});
        return update.download();
    }

    synchronized void cancelUpdate() {
        if (update != null) update.delete();
        update = null;
        prefs.edit().remove("update").apply();
    }

    /** Nouvelle version vérifiée : elle remplace l'ancienne (entre deux réponses, jamais pendant). */
    private void finishUpdate(ModelPack up) {
        switching = true;
        update = null;
        worker.execute(() -> {
            synchronized (SyriusAI.this) {
                ModelPack.Part p = up.parts[0];
                ModelPack old = pack;
                ModelPack.Part oldModel = model;
                try {
                    release();
                    File dst = old.file(p.file);
                    if (up.file(p.file).renameTo(dst)) {
                        ModelPack np = new ModelPack(ctx, "syrius", LABEL, new ModelPack.Part[]{p});
                        np.markInstalled();
                        model = p;
                        pack = np;
                        prefs.edit().putString("model", json(p)).remove("update").apply();
                        if (oldModel != null && !oldModel.file.equals(p.file))
                            //noinspection ResultOfMethodCallIgnored
                            old.file(oldModel.file).delete();
                    }
                    up.delete();
                } finally {
                    switching = false;
                }
            }
        });
    }

    /** Conversation : la réponse arrive morceau par morceau (chaque morceau est ajouté au précédent). */
    void chat(String requestId, JSONObject req, LocalAI.Sink sink) {
        worker.execute(() -> {
            try {
                ModelPack pk = pack;
                if (!available() || pk == null || !pk.ready()) {
                    sink.chunk(requestId, "", true, "Notre IA Syrius n'est pas installée.");
                    return;
                }
                if (engine == null) {
                    EngineConfig cfg = new EngineConfig(pk.file(pk.parts[0].file).getAbsolutePath(),
                            new Backend.CPU(4, null), new Backend.CPU(4, null), null, 1280, 1, pk.dir().getAbsolutePath());
                    Engine e = new Engine(cfg);
                    e.initialize();
                    engine = e;
                }
                JSONArray msgs = req.optJSONArray("messages");
                List<Message> history = new ArrayList<>();
                String last = "";
                int n = msgs == null ? 0 : msgs.length();
                // Le téléphone relit tout l'historique à chaque question : on n'en garde que le strict nécessaire
                // (3 derniers messages + la question), sinon la réponse met de plus en plus longtemps à démarrer.
                for (int i = Math.max(0, n - 4); i < n; i++) {
                    JSONObject m = msgs.optJSONObject(i);
                    if (m == null) continue;
                    String text = m.optString("text", "");
                    boolean isLast = i == n - 1;
                    int cap = isLast ? 900 : 350;
                    if (text.length() > cap) text = text.substring(0, cap);
                    boolean assistant = "assistant".equals(m.optString("role"));
                    if (i == n - 1 && !assistant) {
                        last = text;
                    } else {
                        history.add(assistant ? Message.Companion.model(text) : Message.Companion.user(text));
                    }
                }
                if (last.isEmpty()) {
                    sink.chunk(requestId, "", true, "Question vide.");
                    return;
                }
                final Object lock = new Object();
                final boolean[] finished = {false};
                ConversationConfig cc = new ConversationConfig(Contents.Companion.of(req.optString("system", "")), history);
                try (Conversation conv = engine.createConversation(cc)) {
                    current = conv;
                    conv.sendMessageAsync(Message.Companion.user(last), new MessageCallback() {
                        @Override
                        public void onMessage(Message message) {
                            sink.chunk(requestId, message.toString(), false, null);  // morceau ajouté
                        }

                        @Override
                        public void onDone() {
                            sink.chunk(requestId, "", true, null);
                            synchronized (lock) {
                                finished[0] = true;
                                lock.notifyAll();
                            }
                        }

                        @Override
                        public void onError(Throwable t) {
                            boolean cancelled = t instanceof java.util.concurrent.CancellationException;
                            sink.chunk(requestId, "", true, cancelled ? null
                                    : "Syrius n'a pas pu répondre : " + t.getMessage());
                            synchronized (lock) {
                                finished[0] = true;
                                lock.notifyAll();
                            }
                        }
                    });
                    synchronized (lock) {
                        long end = System.currentTimeMillis() + 180_000;
                        while (!finished[0] && System.currentTimeMillis() < end) lock.wait(1000);
                    }
                    if (!finished[0]) {
                        conv.cancelProcess();
                        sink.chunk(requestId, "", true, "Réponse trop longue : arrêtée.");
                    }
                } finally {
                    current = null;
                }
            } catch (Throwable e) {
                release();
                sink.chunk(requestId, "", true, "Syrius n'a pas pu démarrer : "
                        + (e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage()));
            }
        });
    }

    void stop() {
        Conversation c = current;
        if (c != null) {
            try { c.cancelProcess(); } catch (Exception ignored) { }
        }
    }

    void release() {
        try {
            if (engine != null) engine.close();
        } catch (Exception ignored) {
        }
        engine = null;
    }

    void releaseAsync() {
        worker.execute(this::release);
    }

    void delete() {
        cancelUpdate();
        worker.execute(() -> {
            release();
            if (pack != null) pack.delete();
        });
    }

    void shutdown() {
        worker.execute(this::release);
        worker.shutdown();
    }
}
