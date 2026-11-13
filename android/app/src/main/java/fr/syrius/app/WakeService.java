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
 * Ensuite : bip → question (reconnaissance Android) → réponse de Syrius lue à voix haute → une relance.
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
    private Model model;
    private SpeechService vosk;
    private SpeechRecognizer stt;
    private TextToSpeech tts;
    private boolean busy;
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
        if (vosk == null && !busy) startWakeListening();
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
        main.postDelayed(() -> { if (!busy) startWakeListening(); }, 3000);
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

    private void check(String json, boolean isFinal) {
        if (busy || json == null) return;
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
        if (isFinal && learn(text)) return;
        if (!matches(text)) return;
        busy = true;
        followUps = 0;
        conversationId = null;
        main.post(() -> {
            stopWakeListening();
            beep();
            main.postDelayed(this::listenQuestion, 350);
        });
    }

    private void beep() {
        try {
            ToneGenerator tg = new ToneGenerator(AudioManager.STREAM_MUSIC, 80);
            tg.startTone(ToneGenerator.TONE_PROP_BEEP, 160);
            main.postDelayed(tg::release, 400);
        } catch (Exception ignored) {
        }
    }

    // ------------------------------------------------------------------ question (reconnaissance Android)
    private void listenQuestion() {
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            say("La reconnaissance vocale n'est pas disponible sur ce téléphone.", false);
            return;
        }
        if (stt == null) stt = SpeechRecognizer.createSpeechRecognizer(this);
        stt.setRecognitionListener(new RecognitionListener() {
            @Override public void onReadyForSpeech(Bundle b) { }
            @Override public void onBeginningOfSpeech() { }
            @Override public void onRmsChanged(float v) { }
            @Override public void onBufferReceived(byte[] b) { }
            @Override public void onEndOfSpeech() { }
            @Override public void onPartialResults(Bundle b) { }
            @Override public void onEvent(int t, Bundle b) { }

            @Override
            public void onError(int error) {
                backToSleep();  // rien entendu : on se rendort
            }

            @Override
            public void onResults(Bundle results) {
                ArrayList<String> list = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                String q = (list == null || list.isEmpty()) ? "" : list.get(0).trim();
                if (q.isEmpty()) {
                    backToSleep();
                } else if (norm(q).matches("(stop|merci|merci syrius|au revoir|c est tout|rien)( .*)?")) {
                    say("À votre service.", false);
                } else {
                    ask(q);
                }
            }
        });
        Intent i = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE, "fr-FR");
        stt.startListening(i);
    }

    // ------------------------------------------------------------------ réponse de Syrius
    private void ask(String question) {
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
                    if (thenListen && followUps < 2) {  // la conversation peut continuer
                        followUps++;
                        beep();
                        main.postDelayed(WakeService.this::listenQuestion, 300);
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

    private void backToSleep() {
        busy = false;
        main.postDelayed(() -> { if (!busy && vosk == null) startWakeListening(); }, 500);
    }

    @Override
    public void onDestroy() {
        status("stopped");
        stopWakeListening();
        if (stt != null) stt.destroy();
        if (tts != null) tts.shutdown();
        if (model != null) model.close();
        net.shutdownNow();
        main.removeCallbacksAndMessages(null);
        super.onDestroy();
    }
}
