package fr.syrius.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Après un redémarrage du téléphone, les rappels et le briefing sont reprogrammés. */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent intent) {
        if (Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())
                || "android.intent.action.MY_PACKAGE_REPLACED".equals(intent.getAction())) {
            Reminders.rescheduleAll(c);
        }
    }
}
