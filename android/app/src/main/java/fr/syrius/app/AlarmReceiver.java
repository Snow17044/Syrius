package fr.syrius.app;

import android.app.Notification;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

import org.json.JSONObject;

/** Déclenchement d'un rappel, du briefing ou du journal du soir : affiche la notification. */
public class AlarmReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent intent) {
        Reminders.ensureChannel(c);
        boolean briefing = intent.getBooleanExtra(Reminders.EXTRA_BRIEFING, false);
        boolean journal = intent.getBooleanExtra(Reminders.EXTRA_JOURNAL, false);
        String title, text;
        int notifId;
        Intent open = new Intent(c, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        if (briefing) {
            title = "☀️ Ton briefing du matin";
            text = "Météo, rappels et actus du jour : touche pour l'écouter.";
            notifId = 777_000;
            open.putExtra(Reminders.EXTRA_BRIEFING, true);
            Reminders.scheduleBriefing(c);  // demain, même heure
        } else if (journal) {
            title = "🌙 Ton journal du soir";
            text = "Raconte-moi ta journée en quelques mots : touche pour commencer.";
            notifId = Reminders.JOURNAL_CODE;
            open.putExtra(Reminders.EXTRA_JOURNAL, true);
            Reminders.scheduleJournal(c);  // demain, même heure
        } else {
            String id = intent.getStringExtra(Reminders.EXTRA_ID);
            if (id == null) return;
            JSONObject r = Reminders.find(c, id);
            if (r == null) return;  // annulé entre-temps
            title = "⏰ Rappel de Syrius";
            text = r.optString("text", "Rappel");
            notifId = id.hashCode();
            Reminders.fired(c, id);
        }
        PendingIntent pi = PendingIntent.getActivity(c, notifId, open,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification n = new Notification.Builder(c, Reminders.CHANNEL)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(new Notification.BigTextStyle().bigText(text))
                .setAutoCancel(true)
                .setCategory(Notification.CATEGORY_REMINDER)
                .setContentIntent(pi)
                .build();
        try {
            c.getSystemService(NotificationManager.class).notify(notifId, n);
        } catch (SecurityException ignored) {
            // notifications refusées par l'utilisateur
        }
    }
}
