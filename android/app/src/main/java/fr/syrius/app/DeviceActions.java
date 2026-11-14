package fr.syrius.app;

import android.Manifest;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.database.Cursor;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraManager;
import android.media.AudioManager;
import android.net.Uri;
import android.provider.AlarmClock;
import android.provider.CalendarContract;
import android.os.Build;
import android.provider.ContactsContract;
import android.provider.MediaStore;
import android.provider.Settings;
import android.widget.Toast;

import org.json.JSONObject;

import java.text.Normalizer;
import java.util.List;
import java.util.Locale;

/**
 * Exécute les actions demandées par Syrius. Liste fermée d'actions (aucune commande libre),
 * chaque paramètre est revérifié ici. Appels et SMS s'ouvrent dans l'app Téléphone/Messages :
 * c'est toujours l'utilisateur qui appuie sur « Appeler » / « Envoyer ».
 */
final class DeviceActions {
    static final int REQ_CONTACTS = 43;
    static final int REQ_NOTIF = 45;
    static final int REQ_CALL = 46;

    private final Activity activity;
    private JSONObject pending; // action en attente de la permission « contacts »

    DeviceActions(Activity activity) {
        this.activity = activity;
    }

    void run(JSONObject req) {
        try {
            String action = req.getString("action");
            JSONObject p = req.optJSONObject("params");
            if (p == null) p = new JSONObject();
            switch (action) {
                case "phone_alarm": alarm(p); break;
                case "phone_timer": timer(p); break;
                case "phone_call": callOrSms(req, p, false); break;
                case "phone_sms": callOrSms(req, p, true); break;
                case "phone_open_app": openApp(p.getString("app")); break;
                case "phone_map": map(p.getString("query"), p.optBoolean("navigate")); break;
                case "phone_open_url": url(p.getString("url")); break;
                case "phone_flashlight": flashlight(p.getBoolean("on")); break;
                case "phone_volume": volume(p.getInt("level")); break;
                case "phone_settings": settings(p.getString("page")); break;
                case "phone_reminder": reminder(p); break;
                case "phone_reminder_cancel": Reminders.remove(activity, p.getString("id")); toast("Rappel annulé"); break;
                case "phone_calendar": calendar(p); break;
                case "phone_music": music(p); break;
                default: toast("Action inconnue");
            }
        } catch (Exception e) {
            toast("Action impossible : " + e.getClass().getSimpleName());
        }
    }

    /** Appelé quand l'utilisateur a répondu à la demande d'accès aux contacts. */
    void onContactsPermission(boolean granted) {
        JSONObject req = pending;
        pending = null;
        if (req == null) return;
        if (granted) {
            run(req);
        } else {
            toast("Sans accès aux contacts, donne-moi plutôt le numéro.");
        }
    }

    // ------------------------------------------------------------------ actions
    private void alarm(JSONObject p) throws Exception {
        int h = p.getInt("hour"), m = p.getInt("minute");
        if (h < 0 || h > 23 || m < 0 || m > 59) throw new IllegalArgumentException();
        Intent i = new Intent(AlarmClock.ACTION_SET_ALARM)
                .putExtra(AlarmClock.EXTRA_HOUR, h)
                .putExtra(AlarmClock.EXTRA_MINUTES, m)
                .putExtra(AlarmClock.EXTRA_MESSAGE, clip(p.optString("label", "Syrius"), 60))
                .putExtra(AlarmClock.EXTRA_SKIP_UI, true);
        start(i, String.format(Locale.FRANCE, "Réveil réglé à %02dh%02d", h, m));
    }

    private void reminder(JSONObject p) throws Exception {
        Reminders.ensureChannel(activity);
        Reminders.add(activity, p.getString("id"), clip(p.getString("text"), 200), p.getLong("at"),
                p.optString("repeat", "none"));
        askNotifications(activity);
        askExactAlarms();
        toast("Rappel programmé : " + clip(p.optString("label", ""), 60));
    }

    /** Android 12+ : « Alarmes et rappels » pour sonner à l'heure exacte (proposé une seule fois). */
    private void askExactAlarms() {
        if (android.os.Build.VERSION.SDK_INT < 31) return;
        android.app.AlarmManager am = activity.getSystemService(android.app.AlarmManager.class);
        android.content.SharedPreferences prefs = activity.getSharedPreferences("syrius", Context.MODE_PRIVATE);
        if (am == null || am.canScheduleExactAlarms() || prefs.getBoolean("asked_exact", false)) return;
        prefs.edit().putBoolean("asked_exact", true).apply();
        activity.runOnUiThread(() -> new android.app.AlertDialog.Builder(activity)
                .setTitle("Rappels à l'heure exacte")
                .setMessage("Pour que tes rappels sonnent pile à l'heure, autorise « Alarmes et rappels » pour Syrius. "
                        + "Sinon, ils peuvent arriver avec quelques minutes de retard.")
                .setPositiveButton("Autoriser", (d, w) -> {
                    try {
                        activity.startActivity(new Intent(android.provider.Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM,
                                Uri.parse("package:" + activity.getPackageName())));
                    } catch (Exception ignored) {
                    }
                })
                .setNegativeButton("Plus tard", null)
                .show());
    }

    /** Android 13+ : les notifications doivent être autorisées une fois. */
    static void askNotifications(Activity a) {
        if (Build.VERSION.SDK_INT >= 33
                && a.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            a.requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, REQ_NOTIF);
        }
    }

    private void music(JSONObject p) throws Exception {
        String action = p.getString("action");
        if ("play".equals(action)) {
            start(Music.playIntent(activity, p.getString("query"), p.optString("app", "auto")),
                    "🎵 " + clip(p.getString("query"), 60));
        } else if (Music.control(activity, action)) {
            toast(action.equals("pause") ? "⏸ Pause" : action.equals("resume") ? "▶ Lecture"
                    : action.equals("next") ? "⏭ Suivant" : "⏮ Précédent");
        }
    }

    private void calendar(JSONObject p) throws Exception {
        long start = p.getLong("start"), end = p.getLong("end");
        if (end <= start) throw new IllegalArgumentException();
        Intent i = new Intent(Intent.ACTION_INSERT).setData(CalendarContract.Events.CONTENT_URI)
                .putExtra(CalendarContract.Events.TITLE, clip(p.getString("title"), 120))
                .putExtra(CalendarContract.EXTRA_EVENT_BEGIN_TIME, start)
                .putExtra(CalendarContract.EXTRA_EVENT_END_TIME, end)
                .putExtra(CalendarContract.Events.EVENT_LOCATION, clip(p.optString("location", ""), 160));
        start(i, "Vérifie puis enregistre le rendez-vous");
    }

    private void timer(JSONObject p) throws Exception {
        int s = p.getInt("seconds");
        if (s < 1 || s > 86400) throw new IllegalArgumentException();
        Intent i = new Intent(AlarmClock.ACTION_SET_TIMER)
                .putExtra(AlarmClock.EXTRA_LENGTH, s)
                .putExtra(AlarmClock.EXTRA_MESSAGE, clip(p.optString("label", "Syrius"), 60))
                .putExtra(AlarmClock.EXTRA_SKIP_UI, true);
        start(i, "Minuteur lancé");
    }

    private void callOrSms(JSONObject req, JSONObject p, boolean sms) throws Exception {
        String contact = p.getString("contact").trim();
        boolean isNumber = p.optBoolean("is_number");
        if (!isNumber && activity.checkSelfPermission(Manifest.permission.READ_CONTACTS) != PackageManager.PERMISSION_GRANTED) {
            pending = req;
            // Information claire AVANT la demande d'Android (règle Google Play sur les données sensibles).
            activity.runOnUiThread(() -> new android.app.AlertDialog.Builder(activity)
                    .setTitle("Accès à tes contacts")
                    .setMessage("Pour appeler ou écrire à « " + clip(contact, 40) + " », Syrius cherche son numéro "
                            + "dans tes contacts. Tes contacts restent sur ton téléphone : ils ne sont jamais envoyés "
                            + "sur Internet ni à une IA.")
                    .setPositiveButton("Continuer", (d, w) -> activity.requestPermissions(
                            new String[]{Manifest.permission.READ_CONTACTS}, REQ_CONTACTS))
                    .setNegativeButton("Non merci", (d, w) -> pending = null)
                    .show());
            return;
        }
        String number = Calls.number(activity, contact, isNumber);
        if (number == null) {
            toast("Contact « " + clip(contact, 40) + " » introuvable");
            return;
        }
        if (sms) {
            Intent i = new Intent(Intent.ACTION_SENDTO, Uri.fromParts("smsto", number, null))
                    .putExtra("sms_body", clip(p.optString("message", ""), 1000));
            start(i, "SMS prêt : appuie sur Envoyer");
            return;
        }
        // Appel : tu as déjà confirmé dans Syrius, l'appel part directement.
        if (!Calls.canCall(activity)) {
            pending = req;
            activity.requestPermissions(new String[]{Manifest.permission.CALL_PHONE}, REQ_CALL);
            return;
        }
        String err = Calls.place(activity, number);
        if (err == null) toast("📞 Appel de " + clip(contact, 40));
        else start(new Intent(Intent.ACTION_DIAL, Uri.fromParts("tel", number, null)), err);
    }

    /** Réponse à la demande d'autorisation des appels. */
    void onCallPermission(boolean granted) {
        JSONObject req = pending;
        pending = null;
        if (req == null) return;
        if (granted) {
            run(req);
            return;
        }
        try {  // refusé : on prépare simplement l'appel dans le téléphone
            JSONObject p = req.getJSONObject("params");
            String n = Calls.number(activity, p.getString("contact"), p.optBoolean("is_number"));
            if (n != null) start(new Intent(Intent.ACTION_DIAL, Uri.fromParts("tel", n, null)), "Appuie sur Appeler");
        } catch (Exception ignored) {
        }
    }

    private String lookup(String name) {
        Uri uri = Uri.withAppendedPath(ContactsContract.CommonDataKinds.Phone.CONTENT_FILTER_URI, Uri.encode(name));
        try (Cursor c = activity.getContentResolver().query(uri,
                new String[]{ContactsContract.CommonDataKinds.Phone.NUMBER}, null, null, null)) {
            if (c != null && c.moveToFirst()) return c.getString(0);
        } catch (Exception ignored) {
        }
        return null;
    }

    private void openApp(String name) {
        String wanted = norm(name);
        if (wanted.isEmpty()) {
            toast("Nom d'application vide");
            return;
        }
        if (wanted.contains("photo") || wanted.contains("camera")) {
            start(new Intent(MediaStore.INTENT_ACTION_STILL_IMAGE_CAMERA), "Appareil photo");
            return;
        }
        PackageManager pm = activity.getPackageManager();
        Intent launcher = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
        List<ResolveInfo> apps = pm.queryIntentActivities(launcher, 0);
        ResolveInfo best = null;
        for (ResolveInfo r : apps) {
            String label = norm(String.valueOf(r.loadLabel(pm)));
            if (label.equals(wanted)) { best = r; break; }
            if (best == null && label.length() >= 3 && (label.contains(wanted) || wanted.contains(label))) best = r;
        }
        if (best == null) {
            toast("Application « " + clip(name, 40) + " » introuvable");
            return;
        }
        Intent i = pm.getLaunchIntentForPackage(best.activityInfo.packageName);
        if (i != null) start(i, "Ouverture de " + best.loadLabel(pm));
    }

    private void map(String query, boolean navigate) {
        String q = Uri.encode(clip(query, 200));
        Intent nav = new Intent(Intent.ACTION_VIEW, Uri.parse("google.navigation:q=" + q));
        if (navigate && nav.resolveActivity(activity.getPackageManager()) != null) {
            start(nav, "Itinéraire");
        } else {
            start(new Intent(Intent.ACTION_VIEW, Uri.parse("geo:0,0?q=" + q)), "Carte");
        }
    }

    private void url(String raw) {
        Uri u = Uri.parse(raw);
        if (!"https".equals(u.getScheme()) || u.getHost() == null) {
            toast("Lien refusé (https uniquement)");
            return;
        }
        start(new Intent(Intent.ACTION_VIEW, u), null);
    }

    private void flashlight(boolean on) throws Exception {
        CameraManager cm = (CameraManager) activity.getSystemService(Context.CAMERA_SERVICE);
        for (String id : cm.getCameraIdList()) {
            Boolean flash = cm.getCameraCharacteristics(id).get(CameraCharacteristics.FLASH_INFO_AVAILABLE);
            if (Boolean.TRUE.equals(flash)) {
                cm.setTorchMode(id, on);
                toast(on ? "Lampe allumée" : "Lampe éteinte");
                return;
            }
        }
        toast("Pas de lampe sur ce téléphone");
    }

    private void volume(int level) {
        if (level < 0 || level > 100) throw new IllegalArgumentException();
        AudioManager am = (AudioManager) activity.getSystemService(Context.AUDIO_SERVICE);
        int max = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC);
        am.setStreamVolume(AudioManager.STREAM_MUSIC, Math.round(max * level / 100f), AudioManager.FLAG_SHOW_UI);
    }

    private void settings(String page) {
        String action;
        switch (page) {
            case "wifi": action = Settings.ACTION_WIFI_SETTINGS; break;
            case "bluetooth": action = Settings.ACTION_BLUETOOTH_SETTINGS; break;
            case "donnees_mobiles": action = Settings.ACTION_NETWORK_OPERATOR_SETTINGS; break;
            case "affichage": action = Settings.ACTION_DISPLAY_SETTINGS; break;
            case "son": action = Settings.ACTION_SOUND_SETTINGS; break;
            case "batterie": action = Intent.ACTION_POWER_USAGE_SUMMARY; break;
            case "localisation": action = Settings.ACTION_LOCATION_SOURCE_SETTINGS; break;
            default: action = Settings.ACTION_SETTINGS;
        }
        start(new Intent(action), null);
    }

    // ------------------------------------------------------------------ outils
    private void start(Intent i, String message) {
        try {
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            activity.startActivity(i);
            if (message != null) toast(message);
        } catch (ActivityNotFoundException | SecurityException e) {
            toast("Aucune application ne peut faire ça sur ce téléphone");
        }
    }

    private void toast(String text) {
        Toast.makeText(activity, text, Toast.LENGTH_SHORT).show();
    }

    private static String clip(String s, int max) {
        return s == null ? "" : (s.length() > max ? s.substring(0, max) : s);
    }

    private static String norm(String s) {
        String n = Normalizer.normalize(s == null ? "" : s, Normalizer.Form.NFD).replaceAll("\\p{M}", "");
        return n.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9]", "");
    }
}
