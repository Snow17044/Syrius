package fr.syrius.app;

import android.app.SearchManager;
import android.content.Context;
import android.content.Intent;
import android.media.AudioManager;
import android.net.Uri;
import android.os.SystemClock;
import android.provider.MediaStore;
import android.view.KeyEvent;

/** Musique : lancer un titre / artiste / playlist dans l'app choisie, et contrôler la lecture en cours. */
final class Music {
    private Music() {
    }

    static String pkg(String app) {
        switch (app == null ? "" : app) {
            case "spotify": return "com.spotify.music";
            case "youtube_music": return "com.google.android.apps.youtube.music";
            case "deezer": return "deezer.android.app";
            case "youtube": return "com.google.android.youtube";
            default: return null;
        }
    }

    /** Intention qui lance (et en général joue directement) la recherche dans l'app de musique. */
    static Intent playIntent(Context c, String query, String app) {
        String q = query.length() > 120 ? query.substring(0, 120) : query;
        if ("youtube".equals(app)) {  // vidéos : résultats de recherche YouTube
            Intent yt = new Intent(Intent.ACTION_SEARCH).setPackage("com.google.android.youtube").putExtra("query", q);
            if (yt.resolveActivity(c.getPackageManager()) != null) return yt;
            return new Intent(Intent.ACTION_VIEW, Uri.parse("https://www.youtube.com/results?search_query=" + Uri.encode(q)));
        }
        Intent i = new Intent(MediaStore.INTENT_ACTION_MEDIA_PLAY_FROM_SEARCH)
                .putExtra(SearchManager.QUERY, q)
                .putExtra(MediaStore.EXTRA_MEDIA_FOCUS, "vnd.android.cursor.item/*");
        String p = pkg(app);
        if (p != null) {
            Intent withApp = new Intent(i).setPackage(p);
            if (withApp.resolveActivity(c.getPackageManager()) != null) return withApp;
        }
        if (i.resolveActivity(c.getPackageManager()) != null) return i;
        // Aucune app ne sait jouer une recherche : on ouvre YouTube.
        return new Intent(Intent.ACTION_VIEW, Uri.parse("https://www.youtube.com/results?search_query=" + Uri.encode(q)));
    }

    /** Pause / reprise / suivant / précédent sur la musique en cours (n'importe quelle app). */
    static boolean control(Context c, String action) {
        int code;
        switch (action) {
            case "pause": code = KeyEvent.KEYCODE_MEDIA_PAUSE; break;
            case "resume": code = KeyEvent.KEYCODE_MEDIA_PLAY; break;
            case "next": code = KeyEvent.KEYCODE_MEDIA_NEXT; break;
            case "previous": code = KeyEvent.KEYCODE_MEDIA_PREVIOUS; break;
            default: return false;
        }
        AudioManager am = c.getSystemService(AudioManager.class);
        long t = SystemClock.uptimeMillis();
        am.dispatchMediaKeyEvent(new KeyEvent(t, t, KeyEvent.ACTION_DOWN, code, 0));
        am.dispatchMediaKeyEvent(new KeyEvent(t, t, KeyEvent.ACTION_UP, code, 0));
        return true;
    }
}
