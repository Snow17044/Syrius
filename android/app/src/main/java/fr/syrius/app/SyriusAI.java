package fr.syrius.app;

import android.content.Context;

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

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * « Syrius », NOTRE IA : Qwen 2.5 1.5B (licence Apache 2.0) entraînée pour devenir Syrius (caractère, outils,
 * français), puis convertie pour LiteRT-LM. Elle tourne entièrement sur le téléphone : gratuite, sans limite,
 * privée. Le fichier vient des « Releases » du projet, avec une empreinte SHA-256 inscrite ici.
 */
class SyriusAI {
    static final String RELEASE = "https://github.com/" + BuildConfig.SYRIUS_REPO + "/releases/download/syrius-ia/";
    /** Version publiée de notre IA (mise à jour après chaque entraînement validé). Vide = pas encore disponible. */
    static final ModelPack.Part[] PARTS = {};
    static final String FILE = PARTS.length > 0 ? PARTS[0].file : "";

    final ModelPack pack;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private Engine engine;
    private volatile Conversation current;

    SyriusAI(Context ctx) {
        pack = new ModelPack(ctx, "syrius", "Syrius — notre IA (1,6 Go)", PARTS);
    }

    boolean available() {
        return PARTS.length > 0;
    }

    /** Conversation : la réponse arrive morceau par morceau (chaque morceau est ajouté au précédent). */
    void chat(String requestId, JSONObject req, LocalAI.Sink sink) {
        worker.execute(() -> {
            try {
                if (!available() || !pack.ready()) {
                    sink.chunk(requestId, "", true, "Notre IA Syrius n'est pas installée.");
                    return;
                }
                if (engine == null) {
                    EngineConfig cfg = new EngineConfig(pack.file(FILE).getAbsolutePath(),
                            new Backend.CPU(4, null), new Backend.CPU(4, null), null, 1280, 1, pack.dir().getAbsolutePath());
                    Engine e = new Engine(cfg);
                    e.initialize();
                    engine = e;
                }
                JSONArray msgs = req.optJSONArray("messages");
                List<Message> history = new ArrayList<>();
                String last = "";
                int n = msgs == null ? 0 : msgs.length();
                for (int i = Math.max(0, n - 8); i < n; i++) {
                    JSONObject m = msgs.optJSONObject(i);
                    if (m == null) continue;
                    String text = m.optString("text", "");
                    if (text.length() > 900) text = text.substring(0, 900);
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
        worker.execute(() -> {
            release();
            pack.delete();
        });
    }

    void shutdown() {
        worker.execute(this::release);
        worker.shutdown();
    }
}
