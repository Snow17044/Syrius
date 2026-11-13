// Génération d'images hors ligne de Syrius, version « turbo » pour téléphone.
//
// Modèle : Stable Diffusion 1.5 (DreamShaper 7) + LCM-LoRA fusionné (4 à 8 étapes, sans double calcul)
// et décodeur ultra-léger TAESD. Exécuté avec MNN (Alibaba, Apache 2.0, version épinglée dans build.sh).
// Le modèle est préparé par la CI (.github/workflows/sd-model.yml) puis vérifié par empreinte sur le
// téléphone avant usage.
//
// Fichiers attendus dans le dossier du modèle :
//   text_encoder.mnn(.weight)  : input_ids[1,77] int32 → last_hidden_state[1,77,768]
//   unet.mnn(.weight)          : sample[1,4,64,64], timestep[1] int32, encoder_hidden_states → out_sample
//   taesd_decoder.mnn(.weight) : latent[1,4,64,64] → image[1,3,512,512] (valeurs -1..1)
//   vocab.json, merges.txt     : vocabulaire CLIP
#include <algorithm>
#include <atomic>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <memory>
#include <random>
#include <string>
#include <vector>

#include <MNN/Interpreter.hpp>
#include <MNN/expr/ExecutorScope.hpp>
#include <MNN/expr/ExprCreator.hpp>
#include <MNN/expr/Module.hpp>
#include <cv/cv.hpp>

#include "tokenizer.hpp"

using namespace MNN;
using namespace MNN::Express;

namespace {

constexpr int kTextLen = 77;
constexpr int kLatent = 4 * 64 * 64;
constexpr int kStart = 49406, kEnd = 49407;
std::atomic<bool> gBusy(false);

/** Texte → identifiants CLIP (77, complétés par le jeton de fin comme le tokenizer d'origine). */
bool tokenize(const std::string& dir, const std::string& prompt, std::vector<int>& out) {
    std::string clean;
    for (unsigned char c : prompt) {  // ASCII imprimable en minuscules (vocabulaire CLIP)
        if (c >= 32 && c < 127) clean.push_back((char)std::tolower(c));
        else if (c == '\n' || c == '\t') clean.push_back(' ');
    }
    if (clean.size() > 400) clean.resize(400);
    MNN::DIFFUSION::CLIPTokenizer tok;
    if (!tok.load(dir)) return false;
    std::vector<int> ids;
    try {
        // Grande longueur : l'encodeur MNN n'écrit jamais hors du tableau (≤ 1 jeton par octet).
        ids = tok.encode(clean, 1024);
    } catch (...) {
        return false;
    }
    // ids = [vide (1024)] + [début, jetons…, fin, 0…] : on garde la seconde moitié.
    std::vector<int> cond(ids.begin() + 1024, ids.end());
    int n = 0;
    while (n < (int)cond.size() && !(n > 0 && cond[n] == kEnd)) n++;
    out.assign(kTextLen, kEnd);
    out[0] = kStart;
    int count = std::min(n - 1, kTextLen - 2);  // jetons hors début/fin
    for (int i = 0; i < count; ++i) out[1 + i] = cond[1 + i];
    out[1 + count] = kEnd;
    return true;
}

/** Planificateur LCM (identique à diffusers.LCMScheduler, 50 pas d'origine). */
struct Lcm {
    std::vector<double> acp;  // alphas cumulés
    Lcm() {
        acp.resize(1000);
        double a = 1.0, b0 = std::sqrt(0.00085), b1 = std::sqrt(0.012);
        for (int i = 0; i < 1000; ++i) {
            double b = b0 + (b1 - b0) * i / 999.0;
            a *= 1.0 - b * b;
            acp[i] = a;
        }
    }
    static std::vector<int> timesteps(int steps) {
        std::vector<int> origin;  // 19, 39, …, 999
        for (int i = 1; i <= 50; ++i) origin.push_back(i * 20 - 1);
        std::reverse(origin.begin(), origin.end());
        std::vector<int> ts;
        for (int i = 0; i < steps; ++i) ts.push_back(origin[(int)std::floor(i * 50.0 / steps)]);
        return ts;
    }
};

struct SdRuntime {
    std::shared_ptr<Executor::RuntimeManager> rtm;
    Module::Config mc;
    explicit SdRuntime(int threads) {
        ScheduleConfig config;
        config.type = MNN_FORWARD_CPU;
        config.numThread = threads;
        BackendConfig bc;
        bc.memory = BackendConfig::Memory_Low;
        bc.precision = BackendConfig::Precision_Low;
        config.backendConfig = &bc;
        auto exe = ExecutorScope::Current();
        exe->lazyEval = false;
        exe->setGlobalExecutorConfig(config.type, bc, config.numThread);
        rtm.reset(Executor::RuntimeManager::createRuntimeManager(config));
        rtm->setHint(Interpreter::WINOGRAD_MEMORY_LEVEL, 0);
        rtm->setHint(Interpreter::DYNAMIC_QUANT_OPTIONS, 2);
        mc.shapeMutable = false;
    }
    Module* load(const std::string& path, const std::vector<std::string>& in, const std::vector<std::string>& out) {
        return Module::load(in, out, path.c_str(), rtm, &mc);
    }
};

}  // namespace

/** 0 = image écrite ; 1 = déjà occupé ; 2 = chargement impossible ; 3 = génération ratée. */
static int syrius_generate(const std::string& dir, const std::string& prompt, int steps, int seed,
                           const std::string& out, const std::function<void(int)>& progress) {
    bool expected = false;
    if (!gBusy.compare_exchange_strong(expected, true)) return 1;
    struct Release { ~Release() { gBusy = false; } } release;
    steps = std::max(2, std::min(8, steps));
    std::mt19937 rng((unsigned)seed);
    std::normal_distribution<float> normal(0.f, 1.f);
    SdRuntime rt(4);
    progress(2);

    // 1) Texte → vecteurs
    std::vector<int> ids;
    if (!tokenize(dir, prompt, ids)) return 2;
    std::vector<float> emb;
    {
        std::unique_ptr<Module> te(rt.load(dir + "/text_encoder.mnn", {"input_ids"}, {"last_hidden_state"}));
        if (!te) return 2;
        VARP in = _Input({1, kTextLen}, NCHW, halide_type_of<int>());
        std::memcpy(in->writeMap<int>(), ids.data(), kTextLen * sizeof(int));
        auto o = te->onForward({in});
        if (o.empty()) return 3;
        VARP e = _Convert(o[0], NCHW);
        auto info = e->getInfo();
        if (!info || info->size != kTextLen * 768) return 3;
        const float* p = e->readMap<float>();
        emb.assign(p, p + info->size);
    }
    progress(8);

    // 2) Débruitage LCM
    Lcm lcm;
    auto ts = Lcm::timesteps(steps);
    std::vector<float> x(kLatent);
    for (auto& v : x) v = normal(rng);
    {
        std::unique_ptr<Module> unet(rt.load(dir + "/unet.mnn", {"sample", "timestep", "encoder_hidden_states"},
                                             {"out_sample"}));
        if (!unet) return 2;
        VARP ctx = _Input({1, kTextLen, 768}, NCHW, halide_type_of<float>());
        std::memcpy(ctx->writeMap<float>(), emb.data(), emb.size() * sizeof(float));
        for (int i = 0; i < steps; ++i) {
            const int t = ts[i];
            VARP sample = _Input({1, 4, 64, 64}, NCHW, halide_type_of<float>());
            std::memcpy(sample->writeMap<float>(), x.data(), kLatent * sizeof(float));
            VARP tv = _Input({1}, NCHW, halide_type_of<int>());
            tv->writeMap<int>()[0] = t;
            auto o = unet->onForward({sample, tv, ctx});
            if (o.empty()) return 3;
            VARP epsVar = _Convert(o[0], NCHW);
            auto info = epsVar->getInfo();
            if (!info || info->size != kLatent) return 3;
            const float* eps = epsVar->readMap<float>();
            const double a = lcm.acp[t], b = 1.0 - a;
            const double st = t * 10.0, sd2 = 0.25;  // conditions limites LCM (sigma_data = 0,5)
            const double cSkip = sd2 / (st * st + sd2), cOut = st / std::sqrt(st * st + sd2);
            const bool last = i == steps - 1;
            const double aPrev = last ? 1.0 : lcm.acp[ts[i + 1]];
            for (int k = 0; k < kLatent; ++k) {
                double x0 = (x[k] - std::sqrt(b) * eps[k]) / std::sqrt(a);
                double den = cOut * x0 + cSkip * x[k];
                x[k] = (float)(last ? den : std::sqrt(aPrev) * den + std::sqrt(1.0 - aPrev) * normal(rng));
            }
            progress(8 + (i + 1) * 80 / steps);
        }
    }

    // 3) Décodage (TAESD) → JPEG
    {
        std::unique_ptr<Module> dec(rt.load(dir + "/taesd_decoder.mnn", {"latent"}, {"image"}));
        if (!dec) return 2;
        VARP lat = _Input({1, 4, 64, 64}, NCHW, halide_type_of<float>());
        std::memcpy(lat->writeMap<float>(), x.data(), kLatent * sizeof(float));
        auto o = dec->onForward({lat});
        if (o.empty()) return 3;
        VARP img = _Convert(o[0], NCHW);
        auto info = img->getInfo();
        if (!info || info->size != 3 * 512 * 512) return 3;
        const float* p = img->readMap<float>();
        VARP bgr = _Input({512, 512, 3}, NHWC, halide_type_of<uint8_t>());
        uint8_t* d = bgr->writeMap<uint8_t>();
        const int plane = 512 * 512;
        for (int i = 0; i < plane; ++i) {
            for (int c = 0; c < 3; ++c) {  // ordre BGR attendu par imwrite
                float v = (p[(2 - c) * plane + i] * 0.5f + 0.5f) * 255.f;
                d[i * 3 + c] = (uint8_t)std::lround(std::max(0.f, std::min(255.f, v)));
            }
        }
        if (!CV::imwrite(out, bgr)) return 3;
    }
    progress(100);
    return 0;
}

#ifdef __ANDROID__
#include <jni.h>

extern "C" JNIEXPORT jint JNICALL
Java_fr_syrius_app_ImageGen_nativeGenerate(JNIEnv* env, jclass, jstring jdir, jstring jprompt, jint steps,
                                           jint seed, jstring jout, jobject listener) {
    auto str = [env](jstring s) {
        const char* c = env->GetStringUTFChars(s, nullptr);
        std::string r(c ? c : "");
        if (c) env->ReleaseStringUTFChars(s, c);
        return r;
    };
    std::string dir = str(jdir), prompt = str(jprompt), out = str(jout);
    jmethodID onProgress = nullptr;
    if (listener) {
        jclass cls = env->GetObjectClass(listener);
        onProgress = env->GetMethodID(cls, "onProgress", "(I)V");
    }
    auto progress = [env, listener, onProgress](int p) {
        if (listener && onProgress) env->CallVoidMethod(listener, onProgress, (jint)p);
    };
    return syrius_generate(dir, prompt, steps, seed, out, progress);
}
#else
// Programme de test (CI Linux) : syrius_sd <dossier_modele> <etapes> <graine> <sortie.jpg> <description…>
int main(int argc, char** argv) {
    if (argc < 6) {
        std::fprintf(stderr, "usage: %s model_dir steps seed out.jpg prompt...\n", argv[0]);
        return 64;
    }
    std::string prompt;
    for (int i = 5; i < argc; ++i) prompt += std::string(i > 5 ? " " : "") + argv[i];
    int code = syrius_generate(argv[1], prompt, std::atoi(argv[2]), std::atoi(argv[3]), argv[4],
                               [](int p) { std::printf("progression %d%%\n", p); std::fflush(stdout); });
    std::printf("code %d\n", code);
    return code;
}
#endif
