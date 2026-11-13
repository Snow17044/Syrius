package fr.syrius.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.media.AudioManager;
import android.media.ToneGenerator;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.webkit.CookieManager;

import org.json.JSONObject;
import org.vosk.Model;
import org.vosk.Recognizer;
import org.vosk.android.SpeechService;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Pattern;

/**
 * « Hey Syrius » : écoute permanente (application fermée, écran éteint).
 * Le mot-clé est reconnu SUR le téléphone par Vosk (rien n'est envoyé tant qu'il n'est pas dit).
 * Ensuite : bip → question enregistrée puis transcrite par Whisper via ton serveur (bien plus fiable),
 * ou par Vosk sur le téléphone sans Internet → réponse lue à voix haute → relances.
 */
public class WakeService extends Service {
    static final String ACTION_STOP = "fr.syrius.app.WAKE_STOP";
    private static final String CHANNEL = "syrius_ecoute";
    private static final int NOTIF = 4242;
    // « hé / hey / eh / et / ok » suivi d'un mot qui sonne comme Syrius.
    private static final Pattern WAKE = Pattern.compile(
            "\\b(he|hey|hei|eh|e|et|ai|ok|okay|allo)\\s+(syrius|sirius|cyrus|syrus|sirus|siri|serius|seriu|serieu|serieux|syrie|siryus|cirius)\\b");

    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService net = Executors.newSingleThreadExecutor();
    private final ExecutorService mic = Executors.newSingleThreadExecutor();
    private final java.util.concurrent.atomic.AtomicBoolean micCancel = new java.util.concurrent.atomic.AtomicBoolean();
    private final java.util.concurrent.atomic.AtomicBoolean micStop = new java.util.concurrent.atomic.AtomicBoolean();
    private Model model;
    private SpeechService vosk;
    private TextToSpeech tts;
    private int followUps;
    private String conversationId;

    static boolean enabled(Context c) {
        return c.getSharedPreferences("syrius_wake", MODE_PRIVATE).getBoolean("enabled", false);
    }

    static void setEnabled(Context c, boolean on) {
        c.getSharedPreferences("syrius_wake", MODE_PRIVATE).edit().putBoolean("enabled", on).apply();
        Intent i = new Intent(c, WakeService.class);
        if (on) c.startForegroundService(i);
        else c.stopService(i);
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm.getNotificationChannel(CHANNEL) == null) {
            NotificationChannel ch = new NotificationChannel(CHANNEL, "Écoute « Hey Syrius »",
                    NotificationManager.IMPORTANCE_LOW);
            ch.setShowBadge(false);
            nm.createNotificationChannel(ch);
        }
        Intent stop = new Intent(this, WakeService.class).setAction(ACTION_STOP);
        PendingIntent stopPi = PendingIntent.getService(this, 1, stop, PendingIntent.FLAG_IMMUTABLE);
        PendingIntent openPi = PendingIntent.getActivity(this, 2, new Intent(this, MainActivity.class),
                PendingIntent.FLAG_IMMUTABLE);
        Notification n = new Notification.Builder(this, CHANNEL)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle("Syrius vous écoute")
                .setContentText("Dites « Hey Syrius » pour lui parler")
                .setOngoing(true)
                .setContentIntent(openPi)
                .addAction(new Notification.Action.Builder(null, "Arrêter", stopPi).build())
                .build();
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(NOTIF, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE);
        } else {
            startForeground(NOTIF, n);
        }
        instance = this;
        tts = new TextToSpeech(this, status -> {
            if (status == TextToSpeech.SUCCESS) tts.setLanguage(Locale.FRANCE);
        });
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            getSharedPreferences("syrius_wake", MODE_PRIVATE).edit().putBoolean("enabled", false).apply();
            stopSelf();
            return START_NOT_STICKY;
        }
        if (!WakeModel.ready(this)) {
            stopSelf();
            return START_NOT_STICKY;
        }
        if (vosk == null && mode == IDLE && !appVisible) startWakeListening();
        return START_STICKY;
    }

    // ------------------------------------------------------------------ mot-clé (Vosk, hors ligne)
    private void startWakeListening() {
        try {
            if (model == null) model = new Model(WakeModel.dir(this).getAbsolutePath());
            Recognizer rec = new Recognizer(model, 16000.0f);
            vosk = new SpeechService(rec, 16000.0f);
            status("listening");
            vosk.startListening(new org.vosk.android.RecognitionListener() {
                @Override public void onPartialResult(String hyp) { check(hyp, false); }
                @Override public void onResult(String hyp) { check(hyp, true); }
                @Override public void onFinalResult(String hyp) { }
                @Override public void onError(Exception e) { status("Erreur micro : " + e.getClass().getSimpleName()); restartLater(); }
                @Override public void onTimeout() { restartLater(); }
            });
        } catch (Exception e) {
            status("Erreur de démarrage : " + e.getClass().getSimpleName());
            restartLater();
        }
    }

    private void status(String s) {
        wakePrefs().edit().putString("status", s).putLong("status_at", System.currentTimeMillis()).apply();
    }

    private void stopWakeListening() {
        if (vosk != null) {
            try {
                vosk.stop();
                vosk.shutdown();
            } catch (Exception ignored) {
            }
            vosk = null;
        }
    }

    private void restartLater() {
        stopWakeListening();
        main.postDelayed(() -> { if (mode == IDLE && !appVisible && vosk == null) startWakeListening(); }, 3000);
    }

    static String norm(String s) {
        String n = Normalizer.normalize(s == null ? "" : s, Normalizer.Form.NFD).replaceAll("\\p{M}", "");
        return n.toLowerCase(Locale.ROOT).replaceAll("[^a-z ]", " ").replaceAll("\\s+", " ").trim();
    }

    static boolean isWake(String text) {
        return WAKE.matcher(norm(text)).find();
    }

    private SharedPreferences wakePrefs() {
        return getSharedPreferences("syrius_wake", MODE_PRIVATE);
    }

    /** Mot-clé reconnu : forme connue OU l'une des façons apprises de le dire (bouton « Apprendre »). */
    private boolean matches(String text) {
        String n = norm(text);
        if (n.isEmpty()) return false;
        if (WAKE.matcher(n).find()) return true;
        try {
            org.json.JSONArray learned = new org.json.JSONArray(wakePrefs().getString("learned", "[]"));
            for (int i = 0; i < learned.length(); i++) {
                String l = learned.optString(i);
                if (l.length() >= 4 && (" " + n + " ").contains(" " + l + " ")) return true;
            }
        } catch (Exception ignored) {
        }
        return false;
    }

    /** Mode apprentissage : on retient ce que le modèle entend quand l'utilisateur dit « Hey Syrius ». */
    private boolean learn(String finalText) {
        SharedPreferences p = wakePrefs();
        if (!p.getBoolean("learning", false)) return false;
        String n = norm(finalText);
        if (n.length() < 4 || n.length() > 40) return true;
        try {
            org.json.JSONArray learned = new org.json.JSONArray(p.getString("learned", "[]"));
            org.json.JSONArray out = new org.json.JSONArray();
            for (int i = Math.max(0, learned.length() - 5); i < learned.length(); i++) out.put(learned.optString(i));
            out.put(n);
            int count = p.getInt("learn_count", 0) + 1;
            p.edit().putString("learned", out.toString()).putInt("learn_count", count)
                    .putBoolean("learning", count < 3).apply();
            if (count >= 3) main.post(this::beep);  // appris
        } catch (Exception ignored) {
        }
        return true;
    }

    // États : en veille (attend le mot-clé), attend la question, occupé (réflexion / parole).
    private static final int IDLE = 0, QUESTION = 1, BUSY = 2;
    private int mode = IDLE;
    private volatile JSONObject pendingCall;  // appel préparé par Syrius, en attente du « oui »
    private final java.util.List<JSONObject> pendingMusic = new java.util.concurrent.CopyOnWriteArrayList<>();
    private boolean confirming;
    private static final Pattern YES = Pattern.compile("^(oui|ouais|ouai|vas y|vas-y|d accord|ok|okay|appelle|lance|confirme|bien sur|c est ca)\\b.*");
    private static final Pattern PREFIX = Pattern.compile("(he|hey|hei|eh|e|et|ai|ok|okay|allo)");
    private static final Pattern NAME = Pattern.compile(
            "(syrius|sirius|cyrus|syrus|sirus|siri|serius|seriu|serieu|serieux|syrie|siryus|cirius)");

    /** Texte qui suit le mot-clé dans une phrase (« hey syrius quelle heure est-il » → « quelle heure est-il »).
     *  Renvoie null si la phrase ne contient pas le mot-clé. */
    private String afterWake(String raw) {
        String[] tok = raw.trim().split("\\s+");
        String[] n = new String[tok.length];
        for (int i = 0; i < tok.length; i++) n[i] = norm(tok[i]);
        for (int i = 0; i + 1 < tok.length; i++) {
            if (PREFIX.matcher(n[i]).matches() && NAME.matcher(n[i + 1]).matches()) return join(tok, i + 2);
        }
        try {
            org.json.JSONArray learned = new org.json.JSONArray(wakePrefs().getString("learned", "[]"));
            for (int k = 0; k < learned.length(); k++) {
                String[] l = learned.optString(k).split(" ");
                if (learned.optString(k).length() < 4) continue;
                for (int i = 0; i + l.length <= tok.length; i++) {
                    boolean ok = true;
                    for (int j = 0; j < l.length && ok; j++) ok = l[j].equals(n[i + j]);
                    if (ok) return join(tok, i + l.length);
                }
            }
        } catch (Exception ignored) {
        }
        return null;
    }

    private static String join(String[] tok, int from) {
        StringBuilder sb = new StringBuilder();
        for (int i = from; i < tok.length; i++) sb.append(i > from ? " " : "").append(tok[i]);
        return sb.toString().trim();
    }

    private void check(String json, boolean isFinal) {
        if (json == null || mode == BUSY) return;
        String text;
        try {
            JSONObject o = new JSONObject(json);
            text = o.optString("partial", o.optString("text", ""));
        } catch (Exception e) {
            return;
        }
        if (!text.trim().isEmpty()) {  // diagnostic : dernière chose entendue (reste sur le téléphone)
            wakePrefs().edit().putString("heard", text.trim()).putLong("heard_at", System.currentTimeMillis()).apply();
        }
        if (mode != IDLE) return;
        if (isFinal && learn(text)) return;
        if (!matches(text)) return;
        followUps = 0;  // mot-clé entendu
        conversationId = null;
        mode = QUESTION;
        stopWakeListening();
        if (isFinal) {  // « Hey Syrius, quelle heure est-il ? » dit d'une traite
            String rest = afterWake(text.trim());
            if (rest != null && rest.split(" ").length >= 2) {
                handleQuestion(rest);
                return;
            }
        }
        beep();
        listenQuestion();
    }

    /** Enregistre la question, la fait transcrire (Whisper via le serveur, sinon Vosk hors ligne). */
    private void listenQuestion() {
        micCancel.set(false);
        micStop.set(false);
        status("question");
        mic.execute(() -> {
            try {
                Thread.sleep(250);  // laisse passer le bip
            } catch (InterruptedException e) {
                return;
            }
            VoiceCapture.Result r = VoiceCapture.capture(model, 7000, micStop, micCancel);
            if (micCancel.get()) return;
            String text = null;
            if (r != null) {
                text = Transcriber.transcribe(this, r.wav);
                if (text == null) text = r.offlineText;
                if (text != null && !text.trim().isEmpty()) {
                    wakePrefs().edit().putString("heard", text.trim()).putLong("heard_at", System.currentTimeMillis()).apply();
                    String rest = afterWake(text);  // « Hey Syrius » répété dans la question
                    if (rest != null && !rest.isEmpty()) text = rest;
                }
            }
            final String q = text == null ? "" : text.trim();
            main.post(() -> {
                if (mode != QUESTION) return;
                if (q.isEmpty()) {  // personne n'a parlé
                    confirming = false;
                    pendingCall = null;
                    backToSleep();
                } else {
                    handleQuestion(q);
                }
            });
        });
    }

    private void handleQuestion(String q) {
        mode = BUSY;
        if (confirming) {  // réponse à « Je lance l'appel ? »
            confirming = false;
            JSONObject call = pendingCall;
            pendingCall = null;
            final boolean yes = YES.matcher(norm(q)).matches();
            placeCall(call, yes);
            return;
        }
        if (norm(q).matches("(stop|merci|merci syrius|au revoir|c est tout|rien|non merci)( .*)?")) {
            say("À votre service.", false);
        } else {
            ask(q);
        }
    }

    private void beep() {
        try {
            ToneGenerator tg = new ToneGenerator(AudioManager.STREAM_MUSIC, 80);
            tg.startTone(ToneGenerator.TONE_PROP_BEEP, 160);
            main.postDelayed(tg::release, 400);
        } catch (Exception ignored) {
        }
    }

    // ------------------------------------------------------------------ réponse de Syrius
    private void ask(String question) {
        pendingCall = null;
        pendingMusic.clear();
        net.execute(() -> {
            String reply;
            try {
                reply = askServer(question);
            } catch (SecurityException e) {
                reply = "Je dois me reconnecter : ouvrez l'application Syrius une fois.";
            } catch (Exception e) {
                reply = askLocal(question);
            }
            final String r = reply == null || reply.trim().isEmpty() ? "Désolé, je n'ai pas de réponse." : reply;
            main.post(() -> say(r, true));
        });
    }

    private String baseUrl() {
        return getSharedPreferences("syrius", MODE_PRIVATE).getString("url", "");
    }

    private HttpURLConnection post(String url, String body) throws Exception {
        if (!url.startsWith("https://")) throw new IllegalStateException("https obligatoire");
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setRequestMethod("POST");
        c.setConnectTimeout(15000);
        c.setReadTimeout(90000);
        c.setDoOutput(true);
        c.setRequestProperty("Content-Type", "application/json");
        c.setRequestProperty("X-Syrius", "1");
        String cookie = CookieManager.getInstance().getCookie(baseUrl());
        if (cookie != null) c.setRequestProperty("Cookie", cookie);
        try (OutputStream o = c.getOutputStream()) {
            o.write(body.getBytes(StandardCharsets.UTF_8));
        }
        if (c.getResponseCode() == 401) throw new SecurityException("connexion");
        if (c.getResponseCode() >= 400) throw new IllegalStateException("http " + c.getResponseCode());
        return c;
    }

    private String askServer(String question) throws Exception {
        String base = baseUrl();
        if (base.isEmpty()) throw new IllegalStateException("adresse");
        if (conversationId == null) {
            HttpURLConnection c = post(base + "api/conversations", "{}");
            try (BufferedReader r = new BufferedReader(new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8))) {
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = r.readLine()) != null) sb.append(line);
                conversationId = new JSONObject(sb.toString()).getString("id");
            }
            if (!conversationId.matches("[A-Za-z0-9_-]{1,64}")) throw new IllegalStateException("id");
        }
        JSONObject body = new JSONObject().put("text", question).put("voice", true);
        HttpURLConnection c = post(base + "api/conversations/" + conversationId + "/messages", body.toString());
        StringBuilder text = new StringBuilder();
        boolean error = false;
        try (BufferedReader r = new BufferedReader(new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = r.readLine()) != null) {
                if (!line.startsWith("data: ")) continue;
                JSONObject ev = new JSONObject(line.substring(6));
                switch (ev.optString("type")) {
                    case "text": text.append(ev.optString("text")); break;
                    case "text_replace": text.setLength(0); text.append(ev.optString("text")); break;
                    case "error": error = true; break;
                    case "device":
                        if ("phone_call".equals(ev.optString("action"))) pendingCall = ev.optJSONObject("params");
                        else if ("phone_music".equals(ev.optString("action")) && ev.optJSONObject("params") != null)
                            pendingMusic.add(ev.optJSONObject("params"));
                        break;
                    default: break;
                }
            }
        }
        if (error && text.length() == 0) throw new IllegalStateException("IA en ligne indisponible");
        return clean(text.toString());
    }

    /** Pas de réseau / IA en ligne épuisées : l'IA hors ligne répond si elle est installée. */
    private String askLocal(String question) {
        LocalAI ai = new LocalAI(this);
        if (!ai.ready()) return "Je n'arrive pas à joindre mes serveurs pour le moment.";
        final StringBuilder sb = new StringBuilder();
        final Object lock = new Object();
        final boolean[] done = {false};
        try {
            JSONObject req = new JSONObject()
                    .put("system", "Tu es Syrius, assistant personnel. Réponds en français, en 1 à 3 phrases "
                            + "simples, car ta réponse sera lue à voix haute. Tu es hors ligne.")
                    .put("messages", new org.json.JSONArray().put(new JSONObject().put("role", "user").put("text", question)));
            ai.chat("wake", req, (id, t, fin, err) -> {
                synchronized (lock) {
                    if (t != null) sb.append(t);
                    if (fin) { done[0] = true; lock.notifyAll(); }
                }
            });
            synchronized (lock) {
                long end = System.currentTimeMillis() + 120_000;
                while (!done[0] && System.currentTimeMillis() < end) lock.wait(1000);
            }
        } catch (Exception e) {
            return "Je n'arrive pas à répondre pour le moment.";
        } finally {
            ai.shutdown();
        }
        return clean(sb.toString());
    }

    static String clean(String s) {
        return (s == null ? "" : s).replaceAll("```[\\s\\S]*?```", " ").replaceAll("[`*#>_\\[\\]()|]", "")
                .replaceAll("https?://\\S+", "lien").replaceAll("\\s+", " ").trim();
    }

    // ------------------------------------------------------------------ parole
    private void say(String text, boolean thenListen) {
        String t = text.length() > 1500 ? text.substring(0, 1500) : text;
        tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
            @Override public void onStart(String id) { }

            @Override
            public void onDone(String id) {
                main.post(() -> {
                    if (!pendingMusic.isEmpty()) {  // musique demandée : on la lance et on se rendort
                        for (JSONObject m : pendingMusic) runMusic(m);
                        pendingMusic.clear();
                        backToSleep();
                        return;
                    }
                    if (thenListen && pendingCall != null && !confirming) {  // Syrius a préparé un appel
                        confirming = true;
                        String who = pendingCall.optString("contact", "ce contact");
                        say("J'appelle " + who + ". Je lance l'appel ? Dites oui ou non.", true);
                        return;
                    }
                    if (confirming) {  // on attend « oui » ou « non »
                        mode = QUESTION;
                        beep();
                        listenQuestion();
                        return;
                    }
                    if (thenListen && followUps < 2) {  // la conversation peut continuer
                        followUps++;
                        mode = QUESTION;
                        beep();
                        listenQuestion();
                    } else {
                        backToSleep();
                    }
                });
            }

            @Override
            public void onError(String id) {
                main.post(WakeService.this::backToSleep);
            }
        });
        tts.speak(t, TextToSpeech.QUEUE_FLUSH, null, "wake");
    }

    /** Musique depuis « Hey Syrius » : contrôles directs ; lancement d'un titre via l'app de musique. */
    private void runMusic(JSONObject m) {
        String action = m.optString("action");
        if (!"play".equals(action)) {
            Music.control(this, action);
            return;
        }
        Intent i = Music.playIntent(this, m.optString("query"), m.optString("app", "auto"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        // Android n'autorise une app en arrière-plan à en ouvrir une autre qu'avec « afficher par-dessus ».
        if (android.provider.Settings.canDrawOverlays(this)) {
            try {
                startActivity(i);
                return;
            } catch (Exception ignored) {
            }
        }
        PendingIntent pi = PendingIntent.getActivity(this, 7, i,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Reminders.ensureChannel(this);
        Notification n = new Notification.Builder(this, Reminders.CHANNEL)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle("🎵 " + m.optString("query"))
                .setContentText("Touchez pour lancer la musique")
                .setAutoCancel(true)
                .setContentIntent(pi)
                .build();
        try {
            getSystemService(NotificationManager.class).notify(7, n);
        } catch (SecurityException ignored) {
        }
    }

    /** Appel confirmé à la voix : lancé directement (TelecomManager), même application fermée. */
    private void placeCall(JSONObject call, boolean yes) {
        if (call == null || !yes) {
            say("D'accord, je n'appelle pas.", false);
            return;
        }
        String who = call.optString("contact", "");
        String number = Calls.number(this, who, call.optBoolean("is_number"));
        if (number == null) {
            say("Je ne trouve pas le numéro de " + who + ". Ouvrez l'application pour autoriser les contacts.", false);
            return;
        }
        String err = Calls.place(this, number);
        if (err != null) say(err, false);
        else backToSleep();  // l'appel est parti
    }

    private void backToSleep() {
        micCancel.set(true);
        mode = IDLE;
        if (appVisible) return;
        if (vosk == null) startWakeListening();
    }

    // ------------------------------------------------------------------ app ouverte : micro libéré
    static volatile WakeService instance;
    private boolean appVisible;

    /** L'application est au premier plan : l'écoute de fond s'efface pour lui laisser le micro. */
    static void appVisible(boolean visible) {
        WakeService s = instance;
        if (s == null) return;
        s.main.post(() -> {
            s.appVisible = visible;
            if (visible) {
                s.micCancel.set(true);
                s.stopWakeListening();
                s.status("En pause pendant que l'application utilise le micro");
            } else if (s.mode == IDLE && s.vosk == null) {
                s.main.postDelayed(() -> { if (!s.appVisible && s.vosk == null) s.startWakeListening(); }, 800);
            }
        });
    }

    @Override
    public void onDestroy() {
        instance = null;
        status("stopped");
        micCancel.set(true);
        stopWakeListening();
        mic.shutdownNow();
        if (tts != null) tts.shutdown();
        if (model != null) model.close();
        net.shutdownNow();
        main.removeCallbacksAndMessages(null);
        super.onDestroy();
    }
}
