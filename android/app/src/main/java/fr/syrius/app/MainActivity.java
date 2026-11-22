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
    private boolean googleTts;
    private SpeechRecognizer recognizer;
    private DeviceActions device;
    private LocalAI local;
    private Vision vision;
    private ImageGen imageGen;
    private SyriusAI syrius;
    private boolean pendingBriefing;
    private boolean pendingJournal;
    private volatile String auroraRetry;  // texte d'Aurora à relire avec la voix de secours si sa voix échoue
    private boolean voiceMode;
    private static final int REQ_PHOTO = 47;
    private ValueCallback<Uri[]> photoCallback;
    private Uri cameraUri;  // mode conversation 🎧 ouvert : le micro reste à l'app

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#0d0f16"));
        // Android 15+ : l'app s'affiche bord à bord ; on laisse la place aux barres système et au clavier.
        android.widget.FrameLayout root = new android.widget.FrameLayout(this);
        root.setBackgroundColor(Color.parseColor("#0d0f16"));
        root.addView(web, new android.widget.FrameLayout.LayoutParams(-1, -1));
        setContentView(root);
        root.setOnApplyWindowInsetsListener((v, insets) -> {
            if (android.os.Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets i = insets.getInsets(android.view.WindowInsets.Type.systemBars()
                        | android.view.WindowInsets.Type.ime() | android.view.WindowInsets.Type.displayCutout());
                v.setPadding(i.left, i.top, i.right, i.bottom);
            }
            return insets;
        });
        if (android.os.Build.VERSION.SDK_INT >= 33) {  // retour (geste prédictif d'Android 13+)
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                    android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT, this::goBack);
        }

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
                if (pendingJournal) {  // ouverte depuis la notification du journal du soir
                    pendingJournal = false;
                    view.postDelayed(() -> view.evaluateJavascript(
                            "window.syriusJournal && window.syriusJournal()", null), 1500);
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
        syrius = new SyriusAI(this);
        Reminders.ensureChannel(this);
        Reminders.rescheduleAll(this);
        // « Hey Syrius » : relancé à l'ouverture de l'app (Android l'interdit au démarrage du téléphone).
        if (WakeService.enabled(this) && WakeModel.ready(this)
                && checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            try { WakeService.setEnabled(this, true); } catch (Exception ignored) { }
        }
        pendingBriefing = getIntent() != null && getIntent().getBooleanExtra(Reminders.EXTRA_BRIEFING, false);
        pendingJournal = getIntent() != null && getIntent().getBooleanExtra(Reminders.EXTRA_JOURNAL, false);
        web.addJavascriptInterface(new Bridge(), "SyriusAndroid");

        initTts();

        SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        String saved = prefs.getString(KEY_URL, "");
        String link = sharedLink(getIntent());
        if (saved.isEmpty() && link != null && sameHost(link, BuildConfig.DEFAULT_URL)) {
            saved = normalize(BuildConfig.DEFAULT_URL);  // invitation reçue avant toute configuration
            prefs.edit().putString(KEY_URL, saved).apply();
        }
        if (saved.isEmpty()) {
            askForUrl(BuildConfig.DEFAULT_URL);
        } else {
            open(saved);
            if (link != null && sameHost(link, saved)) web.loadUrl(link);
        }
    }

    /** Lien d'invitation ou d'essai (https://ton-syrius/rejoindre/… ou /essai/…) qui a ouvert l'app. */
    private static String sharedLink(Intent intent) {
        if (intent == null || !Intent.ACTION_VIEW.equals(intent.getAction()) || intent.getData() == null) return null;
        Uri u = intent.getData();
        String path = u.getPath() == null ? "" : u.getPath();
        if (!"https".equals(u.getScheme()) || !path.matches("/(rejoindre|essai)/[A-Za-z0-9_-]{4,80}/?")) return null;
        return "https://" + u.getHost() + path;
    }

    private static boolean sameHost(String a, String b) {
        String ha = Uri.parse(a == null ? "" : a).getHost();
        String hb = Uri.parse(normalize(b) == null ? "" : normalize(b)).getHost();
        return ha != null && ha.equalsIgnoreCase(hb);
    }

    private void goBack() {
        if (web.canGoBack()) web.goBack();
        else moveTaskToBack(true);
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
        web.loadUrl(url + BuildConfig.START_PATH);  // « code » pour Syrius Code, vide pour Syrius
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

    private static final String GOOGLE_TTS = "com.google.android.tts";

    /** Découpe un long texte en morceaux d'au plus `max` caractères, de préférence à la fin d'une phrase. */
    static java.util.List<String> splitForSpeech(String text, int max) {
        java.util.List<String> out = new java.util.ArrayList<>();
        String rest = text.trim();
        while (rest.length() > max) {
            int cut = -1;
            for (int i = max; i > max / 2; i--) {
                char c = rest.charAt(i - 1);
                if ((c == '.' || c == '!' || c == '?' || c == '\n') && (i == rest.length() || Character.isWhitespace(rest.charAt(i)))) {
                    cut = i;
                    break;
                }
            }
            if (cut < 0) {  // pas de fin de phrase : on coupe à un espace
                cut = rest.lastIndexOf(' ', max);
                if (cut <= max / 2) cut = max;
            }
            out.add(rest.substring(0, cut).trim());
            rest = rest.substring(cut).trim();
        }
        if (!rest.isEmpty() || out.isEmpty()) out.add(rest);
        return out;
    }

    private boolean packageInstalled(String pkg) {
        try {
            getPackageManager().getPackageInfo(pkg, 0);
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    /**
     * Voix de Syrius. Le moteur « Synthèse vocale Google » (voix neuronales, bien plus naturelles) est pris en
     * priorité s'il est installé ; sinon la voix du constructeur, souvent robotique, avec une aide pour l'installer.
     */
    private void initTts() {
        if (tts != null) {
            try { tts.stop(); tts.shutdown(); } catch (Exception ignored) { }
        }
        googleTts = packageInstalled(GOOGLE_TTS);
        TextToSpeech.OnInitListener ready = status -> {
            if (status != TextToSpeech.SUCCESS) return;
            tts.setLanguage(Locale.FRANCE);
            applyVoice();
            // Prévient la page quand Syrius a fini de parler (mode conversation : il réécoute ensuite).
            tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                @Override public void onStart(String id) { }

                @Override
                public void onDone(String id) {
                    if (id != null && id.endsWith("-part")) return;  // il reste des morceaux à lire
                    if (id != null && id.startsWith("aurora")) auroraRetry = null;
                    sendJs("window.syriusOnSpeakEnd && window.syriusOnSpeakEnd()");
                }

                @Override
                public void onError(String id) {
                    // La voix d'Aurora a échoué (voix pas téléchargée, moteur occupé…) : elle reparle aussitôt avec
                    // la voix de secours (autre ton) au lieu de se taire.
                    String retry = auroraRetry;
                    auroraRetry = null;
                    if (retry != null && id != null && id.startsWith("aurora")) {
                        runOnUiThread(() -> {
                            try {
                                applyVoice();
                                tts.setPitch(1.18f);
                                tts.speak(retry, TextToSpeech.QUEUE_FLUSH, null, "syrius");
                            } catch (Exception e) {
                                sendJs("window.syriusOnSpeakEnd && window.syriusOnSpeakEnd()");
                            }
                        });
                        return;
                    }
                    sendJs("window.syriusOnSpeakEnd && window.syriusOnSpeakEnd()");
                }
            });
        };
        tts = googleTts ? new TextToSpeech(this, ready, GOOGLE_TTS) : new TextToSpeech(this, ready);
    }

    /** Voix choisie par la personne, sinon la plus belle voix française installée ; vitesse enregistrée. */
    private void applyVoice() {
        try {
            SharedPreferences vp = getSharedPreferences("syrius_voice", MODE_PRIVATE);
            tts.setSpeechRate(Math.max(0.7f, Math.min(1.5f, vp.getFloat("rate", 1.05f))));
            String wanted = vp.getString("voice", "");
            android.speech.tts.Voice pick = null;
            if (!wanted.isEmpty()) {
                for (android.speech.tts.Voice v : frenchVoices()) if (v.getName().equals(wanted)) pick = v;
            }
            if (pick == null) {
                java.util.List<android.speech.tts.Voice> all = frenchVoices();
                if (!all.isEmpty()) pick = all.get(0);
            }
            if (pick != null) tts.setVoice(pick);
        } catch (Exception ignored) {
            // on garde la voix par défaut du téléphone
        }
    }

    /** Voix d'Aurora (discussions à plusieurs) : celle choisie, sinon une voix française DIFFÉRENTE de celle de Nova. */
    private android.speech.tts.Voice auroraVoice() {
        java.util.List<android.speech.tts.Voice> all = frenchVoices();
        if (all.isEmpty()) return null;
        String wanted = getSharedPreferences("syrius_voice", MODE_PRIVATE).getString("aurora_voice", "");
        for (android.speech.tts.Voice v : all) if (v.getName().equals(wanted)) return v;
        String novaName = getSharedPreferences("syrius_voice", MODE_PRIVATE).getString("voice", "");
        if (novaName.isEmpty()) novaName = all.get(0).getName();  // voix de Nova par défaut : la meilleure
        // par défaut : une voix installée sur le téléphone (une voix « en ligne » peut échouer sans prévenir)
        for (android.speech.tts.Voice v : all) if (!v.getName().equals(novaName) && !v.isNetworkConnectionRequired()) return v;
        for (android.speech.tts.Voice v : all) if (!v.getName().equals(novaName)) return v;
        return all.get(0);
    }

    /** Chacun sa voix : Nova = la voix choisie, ton un peu grave ; Aurora = une autre voix, ton un peu plus aigu. */
    private void voiceFor(String who) {
        try {
            if ("aurora".equals(who)) {
                android.speech.tts.Voice v = auroraVoice();
                if (v != null) tts.setVoice(v);
                tts.setPitch(1.12f);
            } else {
                applyVoice();
                tts.setPitch(0.94f);
            }
        } catch (Exception ignored) {
            // on garde la voix actuelle
        }
    }

    private static int voiceScore(android.speech.tts.Voice v) {
        return v.getQuality() * 10 + ("FR".equals(v.getLocale().getCountry()) ? 5 : 0)
                - (v.isNetworkConnectionRequired() ? 3 : 0);  // la voix locale marche aussi sans Internet
    }

    /** Voix françaises réellement installées, les plus belles d'abord. */
    private java.util.List<android.speech.tts.Voice> frenchVoices() {
        java.util.List<android.speech.tts.Voice> out = new java.util.ArrayList<>();
        try {
            java.util.Set<android.speech.tts.Voice> voices = tts.getVoices();
            if (voices == null) return out;
            for (android.speech.tts.Voice v : voices) {
                if (v.getLocale() == null || !"fr".equals(v.getLocale().getLanguage())) continue;
                if (v.getFeatures() != null && v.getFeatures().contains(TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED)) continue;
                out.add(v);
            }
            java.util.Collections.sort(out, (a, b) -> {
                int d = voiceScore(b) - voiceScore(a);
                return d != 0 ? d : a.getName().compareTo(b.getName());
            });
        } catch (Exception ignored) {
            // liste vide : la voix par défaut sera utilisée
        }
        return out;
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

        /** État de la voix pour les réglages : moteur, voix actuelle, voix françaises disponibles, vitesse. */
        @JavascriptInterface
        public String ttsInfo() {
            if (!trusted()) return "{}";
            try {
                JSONObject o = new JSONObject();
                o.put("google", googleTts);
                o.put("ready", tts != null);
                SharedPreferences vp = getSharedPreferences("syrius_voice", MODE_PRIVATE);
                o.put("rate", vp.getFloat("rate", 1.05f));
                android.speech.tts.Voice cur = tts == null ? null : tts.getVoice();
                o.put("current", cur == null ? "" : cur.getName());
                android.speech.tts.Voice au = tts == null ? null : auroraVoice();
                o.put("aurora", au == null ? "" : au.getName());
                org.json.JSONArray list = new org.json.JSONArray();
                int n = 0;
                for (android.speech.tts.Voice v : frenchVoices()) {
                    if (n++ >= 14) break;
                    String q = v.getQuality() >= 500 ? "très haute" : v.getQuality() >= 400 ? "haute"
                            : v.getQuality() >= 300 ? "normale" : "basse";
                    String country = v.getLocale().getDisplayCountry(Locale.FRENCH);
                    list.put(new JSONObject().put("name", v.getName())
                            .put("label", "Voix " + n + " · " + (country.isEmpty() ? "français" : country) + " · qualité " + q
                                    + (v.isNetworkConnectionRequired() ? " · en ligne" : " · sur le téléphone")));
                }
                o.put("voices", list);
                return o.toString();
            } catch (Exception e) {
                return "{}";
            }
        }

        @JavascriptInterface
        public String ttsSetVoice(String name) {
            if (name == null || !trusted() || tts == null) return "Refusé";
            for (android.speech.tts.Voice v : frenchVoices()) {
                if (v.getName().equals(name)) {
                    tts.setVoice(v);
                    getSharedPreferences("syrius_voice", MODE_PRIVATE).edit().putString("voice", name).apply();
                    return "ok";
                }
            }
            return "Voix introuvable";
        }

        @JavascriptInterface
        public void ttsSetRate(float rate) {
            if (!trusted() || tts == null || Float.isNaN(rate)) return;
            float r = Math.max(0.7f, Math.min(1.5f, rate));
            tts.setSpeechRate(r);
            getSharedPreferences("syrius_voice", MODE_PRIVATE).edit().putFloat("rate", r).apply();
        }

        /** Ouvre les réglages « Synthèse vocale » d'Android (choix du moteur, téléchargement des voix). */
        @JavascriptInterface
        public String ttsOpenSettings() {
            if (!trusted()) return "Refusé";
            try {
                startActivity(new Intent("com.android.settings.TTS_SETTINGS").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                return "ok";
            } catch (Exception e) {
                try {
                    startActivity(new Intent(android.provider.Settings.ACTION_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                    return "ok";
                } catch (Exception e2) {
                    return "Impossible d'ouvrir les réglages";
                }
            }
        }

        /** Ouvre la page Play Store de « Synthèse vocale Google » (voix neuronales, gratuites). */
        @JavascriptInterface
        public String ttsInstallGoogle() {
            if (!trusted()) return "Refusé";
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=" + GOOGLE_TTS))
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                return "ok";
            } catch (Exception e) {
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW,
                            Uri.parse("https://play.google.com/store/apps/details?id=" + GOOGLE_TTS))
                            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                    return "ok";
                } catch (Exception e2) {
                    return "Impossible d'ouvrir le Play Store";
                }
            }
        }

        /** Préchauffe notre IA (chargement du modèle) pour que le premier ordre soit instantané. */
        @JavascriptInterface
        public void syriusWarmUp() {
            if (trusted() && syrius != null) syrius.warmUp();
        }

        /** Lecture avec la voix de Nova ou d'Aurora (discussions à plusieurs, mode conversation). */
        @JavascriptInterface
        public void speakAs(String text, String who) {
            if (text == null || !trusted() || tts == null) return;
            boolean aurora = "aurora".equals(who);
            voiceFor(aurora ? "aurora" : "nova");
            auroraRetry = aurora ? (text.length() > 3500 ? text.substring(0, 3500) : text) : null;
            say(text, aurora ? "aurora" : "syrius");
        }

        @JavascriptInterface
        public String ttsSetAuroraVoice(String name) {
            if (name == null || !trusted() || tts == null) return "Refusé";
            for (android.speech.tts.Voice v : frenchVoices()) {
                if (v.getName().equals(name)) {
                    getSharedPreferences("syrius_voice", MODE_PRIVATE).edit().putString("aurora_voice", name).apply();
                    return "ok";
                }
            }
            return "Voix introuvable";
        }

        @JavascriptInterface
        public void speak(String text) {
            if (text == null || !trusted() || tts == null) return;
            voiceFor("nova");  // après une réplique d'Aurora, la voix redevient celle de Nova
            auroraRetry = null;
            say(text, "syrius");
        }

        private void say(String text, String tag) {
            String t = text.length() > 8000 ? text.substring(0, 8000) : text;
            // Android refuse un texte trop long d'un coup (≈ 4 000 caractères) : on lit les longues réponses en morceaux,
            // à la suite. Seul le dernier morceau (« syrius ») prévient la page que Syrius a fini de parler.
            java.util.List<String> parts = splitForSpeech(t, Math.max(500, Math.min(3500, TextToSpeech.getMaxSpeechInputLength() - 100)));
            for (int i = 0; i < parts.size(); i++) {
                // le dernier morceau prévient la page (« syrius » / « aurora ») ; « …-part » : il en reste à lire
                tts.speak(parts.get(i), i == 0 ? TextToSpeech.QUEUE_FLUSH : TextToSpeech.QUEUE_ADD, null,
                        i == parts.size() - 1 ? tag : tag + "-part");
            }
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
            return "[\"local\",\"reminders\",\"calendar\",\"briefing\",\"journal\",\"speakend\",\"wake\",\"music\",\"vision\",\"imagegen\",\"voicepick\",\"warmup\",\"voices2\"]";
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

        @JavascriptInterface
        public String getJournal() {
            if (!trusted()) return "{}";
            return Reminders.journalJson(MainActivity.this);
        }

        @JavascriptInterface
        public String setJournal(boolean on, int hour, int minute) {
            if (!trusted()) return "Refusé";
            try {
                Reminders.setJournal(MainActivity.this, on, hour, minute);
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
            return false;  // autorisation « par-dessus les autres applis » retirée (exigence Google Play)
        }

        @JavascriptInterface
        public void overlaySettings() {
            if (!trusted()) return;
            // Plus utilisé : la musique se lance depuis une notification quand l'app est fermée.
        }

        /** Ouvre le réglage « ne pas optimiser la batterie » (sinon le téléphone peut couper l'écoute). */
        @JavascriptInterface
        public void batterySettings() {
            if (!trusted()) return;
            runOnUiThread(() -> {
                try {  // liste des applis : l'utilisateur choisit lui-même « Ne pas optimiser » pour Syrius
                    startActivity(new Intent(android.provider.Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS));
                } catch (Exception ignored) {
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
            if ("syrius".equals(id) && syrius.available()) return syrius.pack;
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
                o.put("syrius", syrius.info());
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
            else if ("syrius".equals(id)) syrius.delete();
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
            syrius.releaseAsync();
            vision.ask(requestId, system, question, jpeg, (id, text, done, error) -> sendJs(
                    "window.SyriusLocal && window.SyriusLocal._chunk(" + JSONObject.quote(id) + ", "
                            + JSONObject.quote(text == null ? "" : text) + ", " + done + ", "
                            + (error == null ? "null" : JSONObject.quote(error)) + ")"));
            return "ok";
        }

        /** Conversation avec NOTRE IA Syrius (sur le téléphone) : morceaux dans window.SyriusLocal._chunk. */
        @JavascriptInterface
        public String syriusChat(String requestId, String json) {
            if (requestId == null || json == null || json.length() > 30000 || !trusted()) return "Refusé";
            if (!requestId.matches("[A-Za-z0-9_-]{1,40}")) return "Refusé";
            final JSONObject req;
            try {
                req = new JSONObject(json);
            } catch (Exception e) {
                return "Demande illisible";
            }
            if (!syrius.available() || !syrius.pack.ready()) return "Notre IA Syrius n'est pas installée";
            if (imageGen.busy()) return "Une image est en cours de création : réessaie après.";
            local.release();
            vision.releaseAsync();
            syrius.chat(requestId, req, (id, text, done, error) -> sendJs(
                    "window.SyriusLocal && window.SyriusLocal._chunk(" + JSONObject.quote(id) + ", "
                            + JSONObject.quote(text == null ? "" : text) + ", " + done + ", "
                            + (error == null ? "null" : JSONObject.quote(error)) + ")"));
            return "ok";
        }

        /** « Mettre à jour » notre IA : version annoncée par ton Syrius (contrôlée, empreinte vérifiée). */
        @JavascriptInterface
        public String syriusUpdate(String manifest) {
            if (manifest == null || manifest.length() > 2000 || !trusted()) return "Refusé";
            return syrius.startUpdate(manifest);
        }

        @JavascriptInterface
        public void syriusUpdateCancel() {
            if (trusted()) syrius.cancelUpdate();
        }

        @JavascriptInterface
        public void syriusStop() {
            if (trusted()) syrius.stop();
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
            syrius.releaseAsync();
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
        if (intent != null && intent.getBooleanExtra(Reminders.EXTRA_JOURNAL, false)) {
            sendJs("window.syriusJournal && window.syriusJournal()");
        }
        String link = sharedLink(intent);
        if (link != null && baseUrl != null && sameHost(link, baseUrl)) web.loadUrl(link);
    }

    // ------------------------------------------------------------------ cycle de vie
    @Override
    public void onBackPressed() {  // Android 12 et moins
        goBack();
    }

    @Override
    protected void onResume() {
        super.onResume();
        // Retour des réglages ou du Play Store : si le moteur Google vient d'être installé, on s'en sert aussitôt.
        if (tts != null && !googleTts && packageInstalled(GOOGLE_TTS)) initTts();
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
        if (syrius != null) syrius.shutdown();
        web.destroy();
        super.onDestroy();
    }
}
