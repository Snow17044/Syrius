package fr.syrius.app;

import android.annotation.SuppressLint;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;

import org.json.JSONObject;
import org.vosk.Model;
import org.vosk.Recognizer;

import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.ArrayDeque;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Enregistre UNE phrase au micro (16 kHz, mono) : démarre quand on parle, s'arrête après un court silence.
 * Le son reste sur le téléphone ; il n'est envoyé (pour une transcription bien plus fiable) que par
 * {@link Transcriber}. Si un modèle Vosk est fourni, une transcription hors ligne est faite en même temps
 * (solution de secours sans Internet).
 */
class VoiceCapture {
    static final int RATE = 16000;
    private static final int FRAME = 320;            // 20 ms
    private static final int PREROLL_FRAMES = 15;    // 300 ms gardées avant le début de la parole
    private static final int END_SILENCE_MS = 1100;  // fin de phrase
    private static final int MAX_MS = 20000;

    static final class Result {
        final byte[] wav;
        final String offlineText;

        Result(byte[] wav, String offlineText) {
            this.wav = wav;
            this.offlineText = offlineText;
        }
    }

    /**
     * Bloquant (à appeler hors du fil principal). Renvoie null si personne n'a parlé à temps.
     * stop : fin anticipée (la phrase déjà dite est gardée) ; cancel : abandon complet.
     */
    @SuppressLint("MissingPermission")  // permission vérifiée par l'appelant
    static Result capture(Model model, int noSpeechMs, AtomicBoolean stop, AtomicBoolean cancel) {
        int min = AudioRecord.getMinBufferSize(RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
        AudioRecord rec = new AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, RATE,
                AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, Math.max(min, FRAME * 2 * 8));
        Recognizer vosk = null;
        try {
            if (rec.getState() != AudioRecord.STATE_INITIALIZED) return null;
            if (model != null) vosk = new Recognizer(model, RATE);
            rec.startRecording();
            short[] frame = new short[FRAME];
            ArrayDeque<short[]> preroll = new ArrayDeque<>();
            ByteArrayOutputStream pcm = new ByteArrayOutputStream();
            double noise = -1;
            int speechRun = 0, silenceMs = 0, elapsed = 0, spoken = 0;
            boolean speaking = false;
            while (!cancel.get()) {
                int n = 0;
                while (n < FRAME) {
                    int r = rec.read(frame, n, FRAME - n);
                    if (r <= 0) return null;
                    n += r;
                }
                elapsed += 20;
                double rms = rms(frame);
                if (noise < 0) noise = rms;
                if (!speaking) noise = 0.95 * noise + 0.05 * Math.min(rms, noise * 3 + 1);  // bruit de fond
                boolean voice = rms > Math.max(450, noise * 3.0);
                if (!speaking) {
                    preroll.addLast(frame.clone());
                    if (preroll.size() > PREROLL_FRAMES) preroll.removeFirst();
                    speechRun = voice ? speechRun + 1 : 0;
                    if (speechRun >= 3) {  // 60 ms de voix : la phrase commence
                        speaking = true;
                        for (short[] f : preroll) write(pcm, vosk, f);
                        preroll.clear();
                    } else if (stop.get() || elapsed >= noSpeechMs) {
                        return null;
                    }
                    continue;
                }
                write(pcm, vosk, frame);
                spoken += 20;
                silenceMs = voice ? 0 : silenceMs + 20;
                if ((silenceMs >= END_SILENCE_MS && spoken >= 400) || spoken >= MAX_MS || stop.get()) break;
            }
            if (cancel.get()) return null;
            String text = "";
            if (vosk != null) {
                try {
                    text = new JSONObject(vosk.getFinalResult()).optString("text", "");
                } catch (Exception ignored) {
                }
            }
            return new Result(wav(pcm.toByteArray()), text);
        } catch (Exception e) {
            return null;
        } finally {
            try { rec.stop(); } catch (Exception ignored) { }
            rec.release();
            if (vosk != null) vosk.close();
        }
    }

    private static double rms(short[] f) {
        double s = 0;
        for (short v : f) s += (double) v * v;
        return Math.sqrt(s / f.length);
    }

    private static void write(ByteArrayOutputStream out, Recognizer vosk, short[] f) {
        ByteBuffer b = ByteBuffer.allocate(f.length * 2).order(ByteOrder.LITTLE_ENDIAN);
        for (short v : f) b.putShort(v);
        out.write(b.array(), 0, f.length * 2);
        if (vosk != null) vosk.acceptWaveForm(f, f.length);
    }

    /** En-tête WAV (PCM 16 bits, mono, 16 kHz). */
    static byte[] wav(byte[] pcm) {
        ByteBuffer h = ByteBuffer.allocate(44 + pcm.length).order(ByteOrder.LITTLE_ENDIAN);
        h.put(new byte[]{'R', 'I', 'F', 'F'}).putInt(36 + pcm.length).put(new byte[]{'W', 'A', 'V', 'E'});
        h.put(new byte[]{'f', 'm', 't', ' '}).putInt(16).putShort((short) 1).putShort((short) 1)
                .putInt(RATE).putInt(RATE * 2).putShort((short) 2).putShort((short) 16);
        h.put(new byte[]{'d', 'a', 't', 'a'}).putInt(pcm.length).put(pcm);
        return h.array();
    }
}
