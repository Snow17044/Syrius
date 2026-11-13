package fr.syrius.app;

import android.content.Context;
import android.webkit.CookieManager;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * Transcription fiable de la voix : le son (WAV) est envoyé à TON serveur Syrius, qui le fait transcrire
 * par Whisper (Groq, gratuit). Uniquement en https, avec ta session ; le son n'est jamais enregistré.
 */
class Transcriber {
    /** Texte reconnu, ou null (pas de réseau, pas connecté, service indisponible). */
    static String transcribe(Context ctx, byte[] wav) {
        String base = ctx.getSharedPreferences("syrius", Context.MODE_PRIVATE).getString("url", "");
        if (!base.startsWith("https://") || wav == null || wav.length < 44 + 16000 * 2 / 4) return null;
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(base + "api/transcribe").openConnection();
            c.setRequestMethod("POST");
            c.setConnectTimeout(6000);
            c.setReadTimeout(20000);
            c.setDoOutput(true);
            c.setRequestProperty("Content-Type", "audio/wav");
            c.setRequestProperty("X-Syrius", "1");
            String cookie = CookieManager.getInstance().getCookie(base);
            if (cookie != null) c.setRequestProperty("Cookie", cookie);
            c.setFixedLengthStreamingMode(wav.length);
            try (OutputStream o = c.getOutputStream()) {
                o.write(wav);
            }
            if (c.getResponseCode() != 200) return null;
            StringBuilder sb = new StringBuilder();
            try (BufferedReader r = new BufferedReader(new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = r.readLine()) != null) sb.append(line);
            }
            String text = new JSONObject(sb.toString()).optString("text", "").trim();
            return text.isEmpty() ? null : text;
        } catch (Exception e) {
            return null;
        } finally {
            if (c != null) c.disconnect();
        }
    }
}
