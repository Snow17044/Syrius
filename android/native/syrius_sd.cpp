// Génération d'images hors ligne de Syrius : Stable Diffusion 1.5 exécuté sur le téléphone avec MNN
// (bibliothèque open source d'Alibaba, licence Apache 2.0, version épinglée dans build.sh).
//
// Ce fichier contient :
//  - le constructeur/destructeur de la classe de base MNN « Diffusion » (on n'embarque que la partie
//    Stable Diffusion du moteur MNN, pas les autres modèles) ;
//  - syrius_generate() : charge le modèle, génère l'image et l'écrit en JPEG ;
//  - l'interface JNI pour l'application Android, ou un petit programme de test pour Linux (CI).
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <memory>
#include <string>

#include "diffusion/stable_diffusion.hpp"

namespace MNN {
namespace DIFFUSION {
Diffusion::Diffusion(std::string modelPath, DiffusionModelType modelType, MNNForwardType backendType, int memoryMode)
    : mModelPath(modelPath), mModelType(modelType), mBackendType(backendType), mMemoryMode(memoryMode) {}
Diffusion::~Diffusion() {
    mModules.clear();
    runtime_manager_.reset();
}
}  // namespace DIFFUSION
}  // namespace MNN

using namespace MNN::DIFFUSION;

static std::atomic<bool> gBusy(false);

/** 0 = image écrite ; 1 = déjà occupé ; 2 = chargement impossible ; 3 = génération ratée. */
static int syrius_generate(const std::string& dir, const std::string& prompt, int steps, int seed,
                           const std::string& out, const std::function<void(int)>& progress) {
    bool expected = false;
    if (!gBusy.compare_exchange_strong(expected, true)) return 1;
    int code = 0;
    {
        // Mode mémoire 0 : chaque partie du modèle est chargée puis libérée (téléphone avec peu de RAM).
        std::unique_ptr<StableDiffusion> sd(new StableDiffusion(dir, STABLE_DIFFUSION_1_5, MNN_FORWARD_CPU, 0));
        if (!sd->load()) {
            code = 2;
        } else if (!sd->run(prompt, out, steps, seed, progress)) {
            code = 3;
        }
    }
    gBusy = false;
    return code;
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
