package fr.syrius.app;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
import android.provider.ContactsContract;
import android.telecom.TelecomManager;

/**
 * Lancement direct d'un appel (après confirmation de l'utilisateur, dans l'app ou à la voix).
 * Fonctionne aussi depuis l'écoute « Hey Syrius », application fermée (TelecomManager).
 */
final class Calls {
    private Calls() {
    }

    /** Numéro d'un contact (ou le numéro donné), ou null s'il est introuvable. */
    static String number(Context c, String contact, boolean isNumber) {
        String t = contact == null ? "" : contact.trim();
        if (isNumber || t.matches("\\+?[0-9 .()-]{3,20}")) {
            String n = t.replaceAll("[^0-9+]", "");
            return n.length() >= 3 && n.length() <= 20 ? n : null;
        }
        if (c.checkSelfPermission(Manifest.permission.READ_CONTACTS) != PackageManager.PERMISSION_GRANTED) return null;
        Uri uri = Uri.withAppendedPath(ContactsContract.CommonDataKinds.Phone.CONTENT_FILTER_URI, Uri.encode(t));
        try (Cursor cur = c.getContentResolver().query(uri,
                new String[]{ContactsContract.CommonDataKinds.Phone.NUMBER}, null, null, null)) {
            if (cur != null && cur.moveToFirst()) {
                String n = cur.getString(0).replaceAll("[^0-9+]", "");
                return n.length() >= 3 && n.length() <= 20 ? n : null;
            }
        } catch (Exception ignored) {
        }
        return null;
    }

    static boolean canCall(Context c) {
        return c.checkSelfPermission(Manifest.permission.CALL_PHONE) == PackageManager.PERMISSION_GRANTED;
    }

    /** Lance l'appel. Renvoie null si c'est parti, sinon un message d'explication. */
    static String place(Context c, String number) {
        if (!canCall(c)) return "Autorise d'abord les appels dans l'application Syrius.";
        try {
            TelecomManager tm = c.getSystemService(TelecomManager.class);
            tm.placeCall(Uri.fromParts("tel", number, null), new Bundle());
            return null;
        } catch (SecurityException e) {
            return "Le téléphone a refusé l'appel.";
        }
    }
}
