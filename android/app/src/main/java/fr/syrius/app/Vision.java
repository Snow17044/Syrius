package fr.syrius.app;

import android.content.Context;

import com.google.ai.edge.litertlm.Backend;
import com.google.ai.edge.litertlm.Content;
import com.google.ai.edge.litertlm.Contents;
import com.google.ai.edge.litertlm.Conversation;
import com.google.ai.edge.litertlm.ConversationConfig;
import com.google.ai.edge.litertlm.Engine;
import com.google.ai.edge.litertlm.EngineConfig;
import com.google.ai.edge.litertlm.Message;
import com.google.ai.edge.litertlm.MessageCallback;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Vision hors ligne : InternVL 3.5 1B (licence Apache 2.0) exécuté sur le téléphone avec Google LiteRT-LM.
 * La photo ne quitte jamais le téléphone.
 */
class Vision {
    static final String REPO = "litert-community/InternVL3_5-1B";
    static final String REV = "3e48aed2c49acbd4ad0e09a1f882b77adf4e5861";
    static final ModelPack.Part[] PARTS = {
            new ModelPack.Part("https://huggingface.co/" + REPO + "/resolve/" + REV + "/model.litertlm",
                    "model.litertlm", "7493d2c82fb3dffbc471c1dcecf97280faa71227c1700a1428473d33cd396957", 817_545_216L),
    };

    final ModelPack pack;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private Engine engine;
    private volatile Conversation current;

    Vision(Context ctx) {
        pack = new ModelPack(ctx, "vision", "Vision hors ligne — InternVL 3.5 1B (820 Mo)", PARTS);
    }

    /** Analyse une photo (JPEG) avec une question ; le texte arrive morceau par morceau. */
    void ask(String requestId, String system, String question, byte[] jpeg, LocalAI.Sink sink) {
        worker.execute(() -> {
            try {
                if (!pack.ready()) {
                    sink.chunk(requestId, "", true, "Vision hors ligne non installée.");
                    return;
                }
                if (engine == null) {
                    EngineConfig cfg = new EngineConfig(pack.file("model.litertlm").getAbsolutePath(),
                            new Backend.CPU(4, null), new Backend.CPU(4, null), null, 2048, 1,
                            pack.dir().getAbsolutePath());
                    Engine e = new Engine(cfg);
                    e.initialize();
                    engine = e;
                }
                final Object lock = new Object();
                final boolean[] finished = {false};
                try (Conversation conv = engine.createConversation(new ConversationConfig(Contents.Companion.of(system)))) {
                    current = conv;
                    List<Content> parts = new ArrayList<>();
                    parts.add(new Content.ImageBytes(jpeg));
                    parts.add(new Content.Text(question));
                    conv.sendMessageAsync(Message.Companion.user(Contents.Companion.of(parts)), new MessageCallback() {
                        @Override
                        public void onMessage(Message message) {
                            sink.chunk(requestId, message.toString(), false, null);
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
                                    : "La vision hors ligne n'a pas pu répondre : " + t.getMessage());
                            synchronized (lock) {
                                finished[0] = true;
                                lock.notifyAll();
                            }
                        }
                    });
                    synchronized (lock) {  // une seule analyse à la fois
                        long end = System.currentTimeMillis() + 300_000;
                        while (!finished[0] && System.currentTimeMillis() < end) lock.wait(1000);
                    }
                    if (!finished[0]) {
                        conv.cancelProcess();
                        sink.chunk(requestId, "", true, "Analyse trop longue : arrêtée.");
                    }
                } finally {
                    current = null;
                }
            } catch (Throwable e) {
                release();
                sink.chunk(requestId, "", true, "La vision hors ligne n'a pas pu démarrer : "
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

    /** Libère la mémoire (avant une génération d'image, par exemple). */
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
