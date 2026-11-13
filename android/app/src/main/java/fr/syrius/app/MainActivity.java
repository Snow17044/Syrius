package fr.syrius.app;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.view.WindowManager;
import android.text.InputType;
import android.webkit.CookieManager;
import android.webkit.GeolocationPermissions;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.Toast;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Locale;

/**
 * Application Syrius : affiche ton Syrius en plein écran et ajoute la voix du téléphone.
 * Sécurité : HTTPS obligatoire, navigation limitée à l'adresse de ton Syrius,
 * aucun accès aux fichiers du téléphone, micro seulement sur ton appui.
 */
public class MainActivity extends Activity {
    private static final String PREFS = "syrius";
    private static final String KEY_URL = "url";
    private static final int REQ_MIC = 42;
    private static final int REQ_LOCATION = 44;
    private String pendingGeoOrigin;
    private GeolocationPermissions.Callback pendingGeoCallback;

    private WebView web;
    private String baseUrl;
    private String allowedHost;
    private TextToSpeech tts;
    private SpeechRecognizer recognizer;
    private DeviceActions device;
    private LocalAI local;
    private Vision vision;
    private ImageGen imageGen;
    private boolean pendingBriefing;
    private boolean voiceMode;
    private static final int REQ_PHOTO = 47;
    private ValueCallback<Uri[]> photoCallback;
    private Uri cameraUri;  // mode conversation 🎧 ouvert : le micro reste à l'app

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#0d0f16"));
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        s.setMediaPlaybackRequiresUserGesture(true);
        s.setSupportMultipleWindows(false);
        s.setJavaScriptCanOpenWindowsAutomatically(false);
        s.setGeolocationEnabled(true);
        s.setUserAgentString(s.getUserAgentString() + " SyriusAndroid/1.0");
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);

        web.setWebChromeClient(new WebChromeClient() {
            /** Bouton 📷 : prendre une photo ou en choisir une dans la galerie (page de Syrius uniquement). */
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                Uri page = Uri.parse(view.getUrl() == null ? "" : view.getUrl());
                if (!"https".equals(page.getScheme()) || allowedHost == null || !allowedHost.equals(page.getHost())) {
                    callback.onReceiveValue(null);
                    return true;
                }
                if (photoCallback != null) photoCallback.onReceiveValue(null);
                photoCallback = callback;
                Intent gallery = new Intent(Intent.ACTION_GET_CONTENT).setType("image/*").addCategory(Intent.CATEGORY_OPENABLE);
                Intent chooser = Intent.createChooser(gallery, "Photo pour Syrius");
                try {
                    java.io.File dir = new java.io.File(getCacheDir(), "photos");
                    //noinspection ResultOfMethodCallIgnored
                    dir.mkdirs();
                    java.io.File img = new java.io.File(dir, "photo.jpg");
                    cameraUri = androidx.core.content.FileProvider.getUriForFile(MainActivity.this,
                            getPackageName() + ".files", img);
                    Intent cam = new Intent(android.provider.MediaStore.ACTION_IMAGE_CAPTURE)
                            .putExtra(android.provider.MediaStore.EXTRA_OUTPUT, cameraUri)
                            .addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    chooser.putExtra(Intent.EXTRA_INITIAL_INTENTS, new Intent[]{cam});
                } catch (Exception e) {
                    cameraUri = null;
                }
                try {
                    startActivityForResult(chooser, REQ_PHOTO);
                } catch (Exception e) {
                    photoCallback = null;
                    callback.onReceiveValue(null);
                }
                return true;
            }

            @Override
            public void onGeolocationPermissionsShowPrompt(String origin, GeolocationPermissions.Callback callback) {
                Uri o = Uri.parse(origin);
                // Position donnée uniquement à ton Syrius (https), jamais à une autre page.
                if (!"https".equals(o.getScheme()) || allowedHost == null || !allowedHost.equals(o.getHost())) {
                    callback.invoke(origin, false, false);
                    return;
                }
                if (checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED) {
                    callback.invoke(origin, true, false);
                } else {
                    pendingGeoOrigin = origin;
                    pendingGeoCallback = callback;
                    requestPermissions(new String[]{Manifest.permission.ACCESS_COARSE_LOCATION}, REQ_LOCATION);
                }
            }
        });
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if ("https".equals(uri.getScheme()) && allowedHost != null && allowedHost.equals(uri.getHost())) {
                    return false; // page de ton Syrius : on reste dans l'app
                }
                // Tout autre lien (sites, emails…) s'ouvre dans le navigateur, hors de l'app.
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, uri));
                } catch (Exception ignored) {
                }
                return true;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                if (pendingBriefing) {  // ouverte depuis la notification du briefing du matin
                    pendingBriefing = false;
                    view.postDelayed(() -> view.evaluateJavascript(
                            "window.syriusBriefing && window.syriusBriefing()", null), 1500);
                }
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    showOfflineDialog();
                }
            }
        });
        device = new DeviceActions(this);
        local = new LocalAI(this);
        vision = new Vision(this);
        imageGen = new ImageGen(this);
        Reminders.ensureChannel(this);
        Reminders.rescheduleAll(this);
        // « Hey Syrius » : relancé à l'ouverture de l'app (Android l'interdit au démarrage du téléphone).
        if (WakeService.enabled(this) && WakeModel.ready(this)
                && checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            try { WakeService.setEnabled(this, true); } catch (Exception ignored) { }
        }
        pendingBriefing = getIntent() != null && getIntent().getBooleanExtra(Reminders.EXTRA_BRIEFING, false);
        web.addJavascriptInterface(new Bridge(), "SyriusAndroid");

        tts = new TextToSpeech(this, status -> {
            if (status == TextToSpeech.SUCCESS) {
                tts.setLanguage(Locale.FRANCE);
                // Prévient la page quand Syrius a fini de parler (mode conversation : il réécoute ensuite).
                tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                    @Override public void onStart(String id) { }

                    @Override
                    public void onDone(String id) {
                        sendJs("window.syriusOnSpeakEnd && window.syriusOnSpeakEnd()");
                    }

                    @Override
                    public void onError(String id) {
                        sendJs("window.syriusOnSpeakEnd && window.syriusOnSpeakEnd()");
                    }
                });
            }
        });

        SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        String saved = prefs.getString(KEY_URL, "");
        if (saved.isEmpty()) {
            askForUrl(BuildConfig.DEFAULT_URL);
        } else {
            open(saved);
        }
    }

    private static String normalize(String raw) {
        String url = raw == null ? "" : raw.trim();
        if (url.isEmpty()) return null;
        if (!url.startsWith("https://")) {
            if (url.startsWith("http://")) return null; // HTTPS obligatoire
            url = "https://" + url;
        }
        Uri uri = Uri.parse(url);
        if (uri.getHost() == null || uri.getHost().isEmpty()) return null;
        return "https://" + uri.getHost() + "/";
    }

    private void open(String url) {
        baseUrl = url;
        allowedHost = Uri.parse(url).getHost();
        web.loadUrl(url);
    }

    private void askForUrl(String prefill) {
        final EditText input = new EditText(this);
        input.setInputType(InputType.TYPE_TEXT_VARIATION_URI);
        input.setHint("monsyrius.vercel.app");
        input.setText(prefill == null ? "" : prefill);
        new AlertDialog.Builder(this)
                .setTitle("Adresse de ton Syrius")
                .setMessage("L'adresse donnée par Vercel (voir le guide).")
                .setView(input)
                .setCancelable(false)
                .setPositiveButton("Valider", (d, w) -> {
                    String url = normalize(input.getText().toString());
                    if (url == null) {
                        Toast.makeText(this, "Adresse invalide (https obligatoire)", Toast.LENGTH_LONG).show();
                        askForUrl(input.getText().toString());
                        return;
                    }
                    getSharedPreferences(PREFS, MODE_PRIVATE).edit().putString(KEY_URL, url).apply();
                    open(url);
                })
                .show();
    }

    private void showOfflineDialog() {
        new AlertDialog.Builder(this)
                .setTitle("Syrius injoignable")
                .setMessage("Vérifie ta connexion Internet.")
                .setPositiveButton("Réessayer", (d, w) -> web.reload())
                .setNegativeButton("Changer l'adresse", (d, w) -> askForUrl(baseUrl))
                .show();
    }

    // ------------------------------------------------------------------ voix
    private void startListening() {
        WakeService.appVisible(true);  // libère le micro pour la reconnaissance de l'app
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQ_MIC);
            return;
        }
        if (online()) {  // Whisper via ton serveur : bien plus fiable que la reconnaissance du téléphone
            startWhisperListening();
            return;
        }
        startGoogleListening();
    }

    private final java.util.concurrent.atomic.AtomicBoolean micStop = new java.util.concurrent.atomic.AtomicBoolean();
    private final java.util.concurrent.atomic.AtomicBoolean micCancel = new java.util.concurrent.atomic.AtomicBoolean();
    private final java.util.concurrent.ExecutorService micWorker = java.util.concurrent.Executors.newSingleThreadExecutor();
    private volatile boolean capturing;

    private boolean online() {
        try {
            android.net.ConnectivityManager cm = getSystemService(android.net.ConnectivityManager.class);
            android.net.NetworkCapabilities nc = cm.getNetworkCapabilities(cm.getActiveNetwork());
            return nc != null && nc.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_VALIDATED);
        } catch (Exception e) {
            return false;
        }
    }

    /** Une phrase enregistrée (fin automatique au silence), puis transcrite par Whisper via le serveur. */
    private void startWhisperListening() {
        if (capturing) return;
        capturing = true;
        micStop.set(false);
        micCancel.set(false);
        micWorker.execute(() -> {
            VoiceCapture.Result r = VoiceCapture.capture(null, 8000, micStop, micCancel);
            String text = null;
            if (r != null && !micCancel.get()) {
                sendJs("window.syriusOnSpeech && window.syriusOnSpeech(\"…\", false)");
                text = Transcriber.transcribe(this, r.wav);
            }
            capturing = false;
            final boolean spoke = r != null && !micCancel.get();
            final String t = text;
            runOnUiThread(() -> {
                if (t != null) {
                    if (!voiceMode) WakeService.appVisible(false);
                    sendJs("window.syriusOnSpeech && window.syriusOnSpeech(" + JSONObject.quote(t) + ", true)");
                } else if (spoke) {  // serveur injoignable : reconnaissance du téléphone, il faut répéter
                    Toast.makeText(this, "Répète, s'il te plaît", Toast.LENGTH_SHORT).show();
                    startGoogleListening();
                } else {
                    if (!voiceMode) WakeService.appVisible(false);
                    sendJs("window.syriusOnSpeechEnd && window.syriusOnSpeechEnd()");
                }
            });
        });
    }

    private void startGoogleListening() {
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            Toast.makeText(this, "Reconnaissance vocale indisponible sur ce téléphone", Toast.LENGTH_LONG).show();
            sendJs("window.syriusOnSpeechEnd && window.syriusOnSpeechEnd()");
            return;
        }
        if (recognizer == null) {
            recognizer = SpeechRecognizer.createSpeechRecognizer(this);
            recognizer.setRecognitionListener(new RecognitionListener() {
                @Override public void onReadyForSpeech(Bundle params) { }
                @Override public void onBeginningOfSpeech() { }
                @Override public void onRmsChanged(float rmsdB) { }
                @Override public void onBufferReceived(byte[] buffer) { }
                @Override public void onEndOfSpeech() { }
                @Override public void onEvent(int eventType, Bundle params) { }

                @Override
                public void onError(int error) {
                    if (!voiceMode) WakeService.appVisible(false);
                    sendJs("window.syriusOnSpeechEnd && window.syriusOnSpeechEnd()");
                }

                @Override
                public void onPartialResults(Bundle partial) {
                    deliver(partial, false);
                }

                @Override
                public void onResults(Bundle results) {
                    if (!voiceMode) WakeService.appVisible(false);
                    deliver(results, true);
                }
            });
        }
        Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "fr-FR");
        intent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true);
        recognizer.startListening(intent);
    }

    private void deliver(Bundle bundle, boolean isFinal) {
        ArrayList<String> list = bundle.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
        String text = (list == null || list.isEmpty()) ? "" : list.get(0);
        // JSONObject.quote échappe le texte : il ne peut pas être interprété comme du code.
        sendJs("window.syriusOnSpeech && window.syriusOnSpeech(" + JSONObject.quote(text) + ", " + isFinal + ")");
    }

    private void sendJs(String js) {
        runOnUiThread(() -> web.evaluateJavascript(js, null));
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] perms, int[] results) {
        super.onRequestPermissionsResult(code, perms, results);
        if (code == REQ_LOCATION) {
            boolean ok = results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED;
            if (pendingGeoCallback != null) pendingGeoCallback.invoke(pendingGeoOrigin, ok, false);
            pendingGeoCallback = null;
            pendingGeoOrigin = null;
            return;
        }
        if (code == DeviceActions.REQ_CALL) {
            device.onCallPermission(results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED);
            return;
        }
        if (code == DeviceActions.REQ_CONTACTS) {
            device.onContactsPermission(results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED);
            return;
        }
        if (code == REQ_MIC) {
            if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) {
                startListening();
            } else {
                sendJs("window.syriusOnSpeechEnd && window.syriusOnSpeechEnd()");
            }
        }
    }

    /** Fonctions appelables depuis la page de ton Syrius (et uniquement elle). */
    private class Bridge {
        private boolean trusted() {
            // Vérifie que la page affichée est bien celle de ton Syrius.
            final String[] url = {null};
            final Object lock = new Object();
            runOnUiThread(() -> {
                synchronized (lock) {
                    url[0] = web.getUrl();
                    lock.notify();
                }
            });
            synchronized (lock) {
                try {
                    if (url[0] == null) lock.wait(1000);
                } catch (InterruptedException ignored) {
                }
            }
            if (url[0] == null) return false;
            Uri uri = Uri.parse(url[0]);
            return "https".equals(uri.getScheme()) && allowedHost != null && allowedHost.equals(uri.getHost());
        }

        @JavascriptInterface
        public void speak(String text) {
            if (text == null || !trusted() || tts == null) return;
            String t = text.length() > 3000 ? text.substring(0, 3000) : text;
            tts.speak(t, TextToSpeech.QUEUE_FLUSH, null, "syrius");
        }

        /** Garde l'écran allumé pendant le mode conversation. */
        @JavascriptInterface
        public void keepScreenOn(boolean on) {
            if (!trusted()) return;
            voiceMode = on;  // mode conversation : l'écoute de fond reste en pause jusqu'à la fin
            WakeService.appVisible(on);
            runOnUiThread(() -> {
                if (on) getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                else getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            });
        }

        @JavascriptInterface
        public void startListening() {
            if (!trusted()) return;
            runOnUiThread(MainActivity.this::startListening);
        }

        /** Action sur le téléphone demandée par Syrius (liste fermée, revérifiée par DeviceActions). */
        @JavascriptInterface
        public String device(String json) {
            if (json == null || json.length() > 4000 || !trusted()) return "Refusé";
            final JSONObject req;
            try {
                req = new JSONObject(json);
            } catch (Exception e) {
                return "Demande illisible";
            }
            runOnUiThread(() -> device.run(req));
            return "ok";
        }

        /** Fonctions disponibles dans cette version de l'application. */
        @JavascriptInterface
        public String features() {
            return "[\"local\",\"reminders\",\"calendar\",\"briefing\",\"speakend\",\"wake\",\"music\",\"vision\",\"imagegen\"]";
        }

        @JavascriptInterface
        public String getBriefing() {
            if (!trusted()) return "{}";
            return Reminders.briefingJson(MainActivity.this);
        }

        @JavascriptInterface
        public String setBriefing(boolean on, int hour, int minute) {
            if (!trusted()) return "Refusé";
            try {
                Reminders.setBriefing(MainActivity.this, on, hour, minute);
            } catch (Exception e) {
                return "Heure invalide";
            }
            if (on) runOnUiThread(() -> DeviceActions.askNotifications(MainActivity.this));
            return "ok";
        }

        // ---------------------------------------------------------- « Hey Syrius »
        @JavascriptInterface
        public String wakeInfo() {
            if (!trusted()) return "{}";
            String m = WakeModel.info(MainActivity.this);
            android.content.SharedPreferences w = getSharedPreferences("syrius_wake", MODE_PRIVATE);
            try {
                JSONObject o = new JSONObject(m);
                o.put("enabled", WakeService.enabled(MainActivity.this))
                        .put("heard", w.getString("heard", ""))
                        .put("heardAgo", w.getLong("heard_at", 0) == 0 ? -1
                                : (System.currentTimeMillis() - w.getLong("heard_at", 0)) / 1000)
                        .put("status", w.getString("status", ""))
                        .put("learning", w.getBoolean("learning", false))
                        .put("learnCount", w.getInt("learn_count", 0))
                        .put("learned", new org.json.JSONArray(w.getString("learned", "[]")));
                return o.toString();
            } catch (Exception e) {
                return m;
            }
        }

        @JavascriptInterface
        public String wakeDownload() {
            if (!trusted()) return "Refusé";
            return WakeModel.download(MainActivity.this);
        }

        @JavascriptInterface
        public String wakeEnable(boolean on) {
            if (!trusted()) return "Refusé";
            if (on && !WakeModel.ready(MainActivity.this)) return "Télécharge d'abord la reconnaissance vocale.";
            if (on && checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQ_MIC);
                return "Autorise le micro puis réessaie.";
            }
            try {
                WakeService.setEnabled(MainActivity.this, on);
            } catch (Exception e) {
                return "Impossible de démarrer l'écoute : " + e.getClass().getSimpleName();
            }
            if (on) runOnUiThread(() -> DeviceActions.askNotifications(MainActivity.this));
            return "ok";
        }

        /** Apprentissage : l'utilisateur dit « Hey Syrius » 3 fois, on retient ce que le modèle entend. */
        @JavascriptInterface
        public void wakeLearn(boolean start) {
            if (!trusted()) return;
            android.content.SharedPreferences.Editor e = getSharedPreferences("syrius_wake", MODE_PRIVATE).edit();
            if (start) e.putBoolean("learning", true).putInt("learn_count", 0).putString("learned", "[]");
            else e.putBoolean("learning", false);
            e.apply();
        }

        @JavascriptInterface
        public void wakeDelete() {
            if (!trusted()) return;
            WakeService.setEnabled(MainActivity.this, false);
            WakeModel.delete(MainActivity.this);
        }

        /** « Afficher par-dessus les autres applis » : permet à « Hey Syrius » d'ouvrir la musique app fermée. */
        @JavascriptInterface
        public boolean canOpenApps() {
            return trusted() && android.provider.Settings.canDrawOverlays(MainActivity.this);
        }

        @JavascriptInterface
        public void overlaySettings() {
            if (!trusted()) return;
            runOnUiThread(() -> {
                try {
                    startActivity(new Intent(android.provider.Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                            Uri.parse("package:" + getPackageName())));
                } catch (Exception ignored) {
                }
            });
        }

        /** Ouvre le réglage « ne pas optimiser la batterie » (sinon le téléphone peut couper l'écoute). */
        @JavascriptInterface
        public void batterySettings() {
            if (!trusted()) return;
            runOnUiThread(() -> {
                try {
                    startActivity(new Intent(android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                            Uri.parse("package:" + getPackageName())));
                } catch (Exception e) {
                    try {
                        startActivity(new Intent(android.provider.Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS));
                    } catch (Exception ignored) {
                    }
                }
            });
        }

        // ---------------------------------------------------------- IA hors ligne
        @JavascriptInterface
        public String localInfo() {
            if (!trusted()) return "{}";
            return local.info();
        }

        @JavascriptInterface
        public String localDownload(String id) {
            if (id == null || !trusted()) return "Refusé";
            return local.download(id);
        }

        @JavascriptInterface
        public void localCancel() {
            if (trusted()) local.cancel();
        }

        @JavascriptInterface
        public void localDelete() {
            if (trusted()) local.delete();
        }

        /** Conversation hors ligne : la réponse arrive morceau par morceau dans window.SyriusLocal._chunk. */
        @JavascriptInterface
        public String localChat(String requestId, String json) {
            if (requestId == null || json == null || json.length() > 20000 || !trusted()) return "Refusé";
            if (!requestId.matches("[A-Za-z0-9_-]{1,40}")) return "Refusé";
            final JSONObject req;
            try {
                req = new JSONObject(json);
            } catch (Exception e) {
                return "Demande illisible";
            }
            if (!local.ready()) return "IA hors ligne non installée";
            local.chat(requestId, req, (id, text, done, error) -> sendJs(
                    "window.SyriusLocal && window.SyriusLocal._chunk(" + JSONObject.quote(id) + ", "
                            + JSONObject.quote(text == null ? "" : text) + ", " + done + ", "
                            + (error == null ? "null" : JSONObject.quote(error)) + ")"));
            return "ok";
        }

        @JavascriptInterface
        public void localStop(String requestId) {
            if (requestId != null && trusted()) local.stop(requestId);
        }

        // ---------------------------------------------------------- vision et images hors ligne
        private ModelPack pack(String id) {
            if ("vision".equals(id)) return vision.pack;
            if ("sd15".equals(id)) return imageGen.pack;
            return null;
        }

        /** État des modèles hors ligne de vision et d'images. */
        @JavascriptInterface
        public String packInfo() {
            if (!trusted()) return "{}";
            try {
                JSONObject o = new JSONObject();
                o.put("vision", vision.pack.info());
                o.put("sd15", imageGen.pack.info().put("engine", ImageGen.nativeAvailable()).put("busy", imageGen.busy()));
                return o.toString();
            } catch (Exception e) {
                return "{}";
            }
        }

        @JavascriptInterface
        public String packDownload(String id) {
            ModelPack p = pack(id);
            if (p == null || !trusted()) return "Refusé";
            return p.download();
        }

        @JavascriptInterface
        public void packCancel(String id) {
            ModelPack p = pack(id);
            if (p != null && trusted()) p.cancel();
        }

        @JavascriptInterface
        public void packDelete(String id) {
            if (!trusted()) return;
            if ("vision".equals(id)) vision.delete();
            else if ("sd15".equals(id) && !imageGen.busy()) imageGen.pack.delete();
        }

        /** Question sur une photo, sans Internet : réponse morceau par morceau dans window.SyriusLocal._chunk. */
        @JavascriptInterface
        public String visionAsk(String requestId, String json) {
            if (requestId == null || json == null || json.length() > 4_000_000 || !trusted()) return "Refusé";
            if (!requestId.matches("[A-Za-z0-9_-]{1,40}")) return "Refusé";
            final String system, question;
            final byte[] jpeg;
            try {
                JSONObject req = new JSONObject(json);
                system = req.optString("system", "");
                question = req.optString("question", "").trim();
                String image = req.optString("image", "");
                String prefix = "data:image/jpeg;base64,";
                if (question.isEmpty() || question.length() > 2000 || !image.startsWith(prefix)) return "Demande illisible";
                jpeg = android.util.Base64.decode(image.substring(prefix.length()), android.util.Base64.DEFAULT);
                if (jpeg.length < 4 || (jpeg[0] & 0xff) != 0xFF || (jpeg[1] & 0xff) != 0xD8) return "Image invalide";
            } catch (Exception e) {
                return "Demande illisible";
            }
            if (!vision.pack.ready()) return "Vision hors ligne non installée";
            if (imageGen.busy()) return "Une image est en cours de création : réessaie après.";
            local.release();
            vision.ask(requestId, system, question, jpeg, (id, text, done, error) -> sendJs(
                    "window.SyriusLocal && window.SyriusLocal._chunk(" + JSONObject.quote(id) + ", "
                            + JSONObject.quote(text == null ? "" : text) + ", " + done + ", "
                            + (error == null ? "null" : JSONObject.quote(error)) + ")"));
            return "ok";
        }

        @JavascriptInterface
        public void visionStop() {
            if (trusted()) vision.stop();
        }

        /** Crée une image sans Internet ; progression puis résultat dans window.SyriusLocal._image. */
        @JavascriptInterface
        public String imageGenerate(String requestId, String prompt, int steps) {
            if (requestId == null || prompt == null || !trusted()) return "Refusé";
            if (!requestId.matches("[A-Za-z0-9_-]{1,40}")) return "Refusé";
            prompt = prompt.replaceAll("[\\x00-\\x1f\\x7f]", " ").trim();
            if (prompt.isEmpty() || prompt.length() > 400) return "Description d'image invalide";
            int n = Math.max(2, Math.min(8, steps));
            local.release();  // libère la mémoire des autres IA du téléphone
            vision.releaseAsync();
            final String rid = requestId;
            String r = imageGen.generate(rid, prompt, n,
                    percent -> sendJs("window.SyriusLocal && window.SyriusLocal._image(" + JSONObject.quote(rid) + ", "
                            + percent + ", null, null)"),
                    (id, dataUrl, error) -> sendJs("window.SyriusLocal && window.SyriusLocal._image(" + JSONObject.quote(id)
                            + ", 100, " + (dataUrl == null ? "null" : JSONObject.quote(dataUrl)) + ", "
                            + (error == null ? "null" : JSONObject.quote(error)) + ")"));
            if ("ok".equals(r)) runOnUiThread(() -> getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON));
            return r;
        }

        @JavascriptInterface
        public String imageSave(String dataUrl) {
            if (!trusted()) return "Refusé";
            return ImageGen.save(MainActivity.this, dataUrl);
        }

        @JavascriptInterface
        public void imageDone() {
            if (trusted()) runOnUiThread(() -> getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON));
        }

        @JavascriptInterface
        public void cancelListening() {  // sortie du mode conversation : rien n'est envoyé
            micCancel.set(true);
            runOnUiThread(() -> {
                if (recognizer != null) recognizer.cancel();
            });
        }

        @JavascriptInterface
        public void stopListening() {
            micStop.set(true);  // fin de phrase demandée : ce qui a été dit est gardé
            runOnUiThread(() -> {
                if (recognizer != null) recognizer.stopListening();
            });
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQ_PHOTO || photoCallback == null) return;
        Uri[] result = null;
        if (resultCode == RESULT_OK) {
            if (data != null && data.getData() != null) result = new Uri[]{data.getData()};  // galerie
            else if (cameraUri != null) result = new Uri[]{cameraUri};                     // appareil photo
        }
        photoCallback.onReceiveValue(result);
        photoCallback = null;
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        if (intent != null && intent.getBooleanExtra(Reminders.EXTRA_BRIEFING, false)) {
            sendJs("window.syriusBriefing && window.syriusBriefing()");
        }
    }

    // ------------------------------------------------------------------ cycle de vie
    @Override
    public void onBackPressed() {
        if (web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (!voiceMode) WakeService.appVisible(false);
        CookieManager.getInstance().flush(); // reste connecté
        if (tts != null) tts.stop();
    }

    @Override
    protected void onDestroy() {
        if (recognizer != null) recognizer.destroy();
        if (tts != null) tts.shutdown();
        micCancel.set(true);
        micWorker.shutdownNow();
        if (local != null) local.shutdown();
        if (vision != null) vision.shutdown();
        if (imageGen != null) imageGen.shutdown();
        web.destroy();
        super.onDestroy();
    }
}
