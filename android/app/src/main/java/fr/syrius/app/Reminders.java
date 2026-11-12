package fr.syrius.app;

import android.app.AlarmManager;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.Calendar;

/**
 * Rappels et briefing du matin : programmés sur le téléphone avec AlarmManager,
 * conservés dans les préférences de l'app et reprogrammés après un redémarrage.
 */
final class Reminders {
    static final String CHANNEL = "syrius_rappels";
    static final String EXTRA_ID = "syrius_reminder_id";
    static final String EXTRA_BRIEFING = "syrius_briefing";
    private static final String PREFS = "syrius_reminders";
    private static final int MAX = 100;
    private static final int BRIEFING_CODE = 777_000;

    private Reminders() {
    }

    private static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    static void ensureChannel(Context c) {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        if (nm.getNotificationChannel(CHANNEL) == null) {
            NotificationChannel ch = new NotificationChannel(CHANNEL, "Rappels de Syrius",
                    NotificationManager.IMPORTANCE_HIGH);
            ch.setDescription("Rappels et briefing du matin");
            nm.createNotificationChannel(ch);
        }
    }

    // ------------------------------------------------------------------ stockage
    static synchronized JSONArray all(Context c) {
        try {
            return new JSONArray(prefs(c).getString("list", "[]"));
        } catch (Exception e) {
            return new JSONArray();
        }
    }

    private static synchronized void save(Context c, JSONArray a) {
        prefs(c).edit().putString("list", a.toString()).apply();
    }

    static synchronized JSONObject find(Context c, String id) {
        JSONArray a = all(c);
        for (int i = 0; i < a.length(); i++) {
            JSONObject r = a.optJSONObject(i);
            if (r != null && id.equals(r.optString("id"))) return r;
        }
        return null;
    }

    static synchronized void add(Context c, String id, String text, long at, String repeat) throws Exception {
        if (!id.matches("[0-9a-f]{6,20}") || text.isEmpty() || text.length() > 200) throw new IllegalArgumentException();
        if (!repeat.equals("daily") && !repeat.equals("weekly")) repeat = "none";
        JSONArray a = all(c);
        JSONArray out = new JSONArray();
        for (int i = 0; i < a.length(); i++) {
            JSONObject r = a.optJSONObject(i);
            if (r != null && !id.equals(r.optString("id"))) out.put(r);
        }
        while (out.length() >= MAX) out.remove(0);
        out.put(new JSONObject().put("id", id).put("text", text).put("at", at).put("repeat", repeat));
        save(c, out);
        schedule(c, id, at);
    }

    static synchronized void remove(Context c, String id) {
        JSONArray a = all(c);
        JSONArray out = new JSONArray();
        for (int i = 0; i < a.length(); i++) {
            JSONObject r = a.optJSONObject(i);
            if (r != null && !id.equals(r.optString("id"))) out.put(r);
        }
        save(c, out);
        AlarmManager am = c.getSystemService(AlarmManager.class);
        am.cancel(pending(c, id, 0));
    }

    /** Après déclenchement : rappel répété → prochaine occurrence ; sinon il est retiré. */
    static synchronized void fired(Context c, String id) {
        JSONObject r = find(c, id);
        if (r == null) return;
        String repeat = r.optString("repeat", "none");
        if (repeat.equals("none")) {
            remove(c, id);
            return;
        }
        long step = repeat.equals("daily") ? 86_400_000L : 7 * 86_400_000L;
        long next = r.optLong("at");
        long now = System.currentTimeMillis();
        while (next <= now) next += step;
        try {
            add(c, id, r.optString("text"), next, repeat);
        } catch (Exception ignored) {
        }
    }

    // ------------------------------------------------------------------ programmation
    private static PendingIntent pending(Context c, String id, int flags) {
        Intent i = new Intent(c, AlarmReceiver.class).setAction("fr.syrius.app.REMINDER." + id)
                .putExtra(EXTRA_ID, id);
        return PendingIntent.getBroadcast(c, id.hashCode(), i, PendingIntent.FLAG_IMMUTABLE | flags);
    }

    private static void exact(Context c, long at, PendingIntent pi) {
        AlarmManager am = c.getSystemService(AlarmManager.class);
        boolean canExact = Build.VERSION.SDK_INT < 31 || am.canScheduleExactAlarms();
        if (canExact) am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi);
        else am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pi);  // à quelques minutes près
    }

    private static void schedule(Context c, String id, long at) {
        if (at < System.currentTimeMillis() - 60_000) return;
        exact(c, Math.max(at, System.currentTimeMillis() + 1000), pending(c, id, PendingIntent.FLAG_UPDATE_CURRENT));
    }

    static synchronized void rescheduleAll(Context c) {
        JSONArray a = all(c);
        long now = System.currentTimeMillis();
        for (int i = 0; i < a.length(); i++) {
            JSONObject r = a.optJSONObject(i);
            if (r == null) continue;
            if (r.optLong("at") <= now) fired(c, r.optString("id"));  // manqué pendant l'arrêt : avance
            else schedule(c, r.optString("id"), r.optLong("at"));
        }
        scheduleBriefing(c);
    }

    // ------------------------------------------------------------------ briefing du matin
    static void setBriefing(Context c, boolean on, int hour, int minute) {
        if (hour < 0 || hour > 23 || minute < 0 || minute > 59) throw new IllegalArgumentException();
        prefs(c).edit().putBoolean("briefing", on).putInt("bh", hour).putInt("bm", minute).apply();
        scheduleBriefing(c);
    }

    static String briefingJson(Context c) {
        SharedPreferences p = prefs(c);
        return "{\"on\":" + p.getBoolean("briefing", false) + ",\"hour\":" + p.getInt("bh", 7)
                + ",\"minute\":" + p.getInt("bm", 30) + "}";
    }

    static void scheduleBriefing(Context c) {
        SharedPreferences p = prefs(c);
        Intent i = new Intent(c, AlarmReceiver.class).setAction("fr.syrius.app.BRIEFING").putExtra(EXTRA_BRIEFING, true);
        PendingIntent pi = PendingIntent.getBroadcast(c, BRIEFING_CODE, i,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        AlarmManager am = c.getSystemService(AlarmManager.class);
        am.cancel(pi);
        if (!p.getBoolean("briefing", false)) return;
        Calendar cal = Calendar.getInstance();
        cal.set(Calendar.HOUR_OF_DAY, p.getInt("bh", 7));
        cal.set(Calendar.MINUTE, p.getInt("bm", 30));
        cal.set(Calendar.SECOND, 0);
        cal.set(Calendar.MILLISECOND, 0);
        if (cal.getTimeInMillis() <= System.currentTimeMillis()) cal.add(Calendar.DAY_OF_YEAR, 1);
        exact(c, cal.getTimeInMillis(), pi);
    }
}
