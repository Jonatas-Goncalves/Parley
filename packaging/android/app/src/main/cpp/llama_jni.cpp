#include <jni.h>

#include <android/log.h>
#include <dirent.h>
#include <dlfcn.h>

#include <llama.h>
#include "whisper.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cctype>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <shared_mutex>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

namespace {

struct Session {
    llama_model * model = nullptr;
    llama_context * ctx = nullptr;
    const llama_vocab * vocab = nullptr;
};

// Readers (generate/isReady) hold a shared lock so a load or free cannot pull
// the model out from under a running generation. Cancel only flips an atomic,
// which is safe even after the session has been released.
std::shared_mutex g_session_mutex;
std::mutex g_generate_mutex;
std::atomic<bool> g_backend_started{false};
std::atomic<bool> g_cancel_requested{false};
// Counts queued and running generations so Diagnostics can tell that a probe
// would block behind the Voice Practice turn instead of hanging forever.
std::atomic<int> g_active_generations{0};
jlong g_active = 0;

struct ActiveGeneration {
    ActiveGeneration() { g_active_generations.fetch_add(1); }
    ~ActiveGeneration() { g_active_generations.fetch_sub(1); }
};

// Lightweight counters exposed to the Diagnostics screen. They tell us whether
// llama.cpp really loaded a model and whether a request produced any tokens.
std::atomic<long> g_generations{0};
std::atomic<long> g_tokens_total{0};
std::atomic<long> g_prompt_tokens{0};
std::atomic<int> g_prompt_batches{0};
std::atomic<int> g_prompt_batches_total{0};
std::atomic<long> g_last_prompt_ms{0};
std::atomic<long> g_last_first_token_ms{0};
std::atomic<bool> g_last_cancelled{false};
std::mutex g_model_info_mutex;
std::string g_model_info = "none";

// llama.cpp logs load errors to stderr, which Android does not surface in a
// useful way. Keep the recent warnings/errors so a failed GGUF load can show
// the real reason in Diagnostics instead of a generic "could not load".
std::mutex g_log_mutex;
std::string g_recent_log;

Session * session(jlong handle) {
    return reinterpret_cast<Session *>(handle);
}

std::mutex g_backend_mutex;
std::string g_backend_dir;
std::string g_backend_status;

void llamaLog(enum ggml_log_level level, const char * text, void *) {
    if (text == nullptr) return;
    __android_log_print(ANDROID_LOG_INFO, "parley-llama", "%s", text);
    if (level < GGML_LOG_LEVEL_WARN) return;
    std::lock_guard<std::mutex> lock(g_log_mutex);
    g_recent_log.append(text);
    if (g_recent_log.size() > 12000) {
        g_recent_log.erase(0, g_recent_log.size() - 12000);
    }
}

std::string recentLog() {
    std::lock_guard<std::mutex> lock(g_log_mutex);
    return g_recent_log;
}

void clearLog() {
    std::lock_guard<std::mutex> lock(g_log_mutex);
    g_recent_log.clear();
}

void pushLog(const std::string & text) {
    if (text.empty()) return;
    __android_log_print(ANDROID_LOG_WARN, "parley-native", "%s", text.c_str());
    std::lock_guard<std::mutex> lock(g_log_mutex);
    g_recent_log.append(text);
    if (g_recent_log.back() != '\n') g_recent_log.push_back('\n');
    if (g_recent_log.size() > 12000) {
        g_recent_log.erase(0, g_recent_log.size() - 12000);
    }
}

std::string backendStatus() {
    std::lock_guard<std::mutex> lock(g_backend_mutex);
    return g_backend_status;
}

void startBackend();

// CPU backends are shipped as libggml-cpu-*.so modules. Android extracts them
// next to this JNI library, but /proc/self/exe points at the linker and the
// working directory is "/", so llama.cpp cannot find them by itself. Try the
// directory supplied by Kotlin first, then a few known APK lib locations.
void loadBackends(const std::string & supplied) {
    std::vector<std::string> candidates;
    if (!supplied.empty()) candidates.push_back(supplied);
    if (!g_backend_dir.empty()) candidates.push_back(g_backend_dir);

    Dl_info info;
    if (dladdr(reinterpret_cast<void *>(&startBackend), &info) != 0 &&
        info.dli_fname != nullptr) {
        std::string path(info.dli_fname);
        const size_t slash = path.find_last_of('/');
        if (slash != std::string::npos) {
            path.resize(slash);
            candidates.push_back(path);
        }
    }
    const char * env_dir = std::getenv("GGML_BACKEND_DIR");
    if (env_dir != nullptr && env_dir[0] != '\0') candidates.push_back(env_dir);

    std::ostringstream status;
    bool loaded = false;
    for (const std::string & path : candidates) {
        if (path.empty()) continue;
        status << path << ": ";
        ggml_backend_load_all_from_path(path.c_str());
        const size_t count = ggml_backend_reg_count();
        status << count << " backend(s)";
        if (count > 0) {
            loaded = true;
            std::lock_guard<std::mutex> lock(g_backend_mutex);
            g_backend_dir = path;
            break;
        }
        // Diagnostic: show why loading failed in this directory.
        DIR * dir = opendir(path.c_str());
        if (dir == nullptr) {
            status << " [opendir failed]";
        } else {
            int cpu_libs = 0;
            struct dirent * entry = nullptr;
            while ((entry = readdir(dir)) != nullptr) {
                const std::string name(entry->d_name);
                if (name.rfind("libggml-cpu-", 0) != 0) continue;
                if (name.size() < 3 || name.substr(name.size() - 3) != ".so") continue;
                ++cpu_libs;
                if (cpu_libs <= 3) {
                    const std::string full = path + "/" + name;
                    void * handle = dlopen(full.c_str(), RTLD_NOW | RTLD_LOCAL);
                    if (handle == nullptr) {
                        const char * err = dlerror();
                        status << " [" << name << ": " << (err ? err : "dlopen failed") << "]";
                    } else {
                        const void * score = dlsym(handle, "ggml_backend_score");
                        status << " [" << name << ": ok score=" << (score ? "yes" : "no") << "]";
                        dlclose(handle);
                    }
                }
            }
            closedir(dir);
            if (cpu_libs == 0) status << " [no libggml-cpu-*.so]";
            else if (cpu_libs > 3) status << " [+" << (cpu_libs - 3) << " more]";
        }
        status << "; ";
    }
    if (!loaded) {
        ggml_backend_load_all();
        status << "fallback: " << ggml_backend_reg_count() << " backend(s)";
    }
    {
        std::lock_guard<std::mutex> lock(g_backend_mutex);
        g_backend_status = status.str();
    }
    __android_log_print(ANDROID_LOG_INFO, "parley-llama", "backends: %s",
        g_backend_status.c_str());
}

void startBackend() {
    std::string supplied;
    {
        std::lock_guard<std::mutex> lock(g_backend_mutex);
        supplied = g_backend_dir;
    }
    if (!g_backend_started.exchange(true)) {
        llama_log_set(llamaLog, nullptr);
    }
    if (ggml_backend_reg_count() == 0) {
        loadBackends(supplied);
    }
    llama_backend_init();
}

std::string javaString(JNIEnv * env, jstring value) {
    if (value == nullptr) return {};
    const char * chars = env->GetStringUTFChars(value, nullptr);
    if (chars == nullptr) return {};
    std::string result(chars);
    env->ReleaseStringUTFChars(value, chars);
    return result;
}

void raise(JNIEnv * env, const char * message) {
    jclass error = env->FindClass("java/lang/IllegalStateException");
    if (error != nullptr) {
        env->ThrowNew(error, message);
    }
}

void raiseDetailed(JNIEnv * env, const char * message) {
    jclass error = env->FindClass("java/lang/IllegalStateException");
    if (error == nullptr) return;
    std::string detail(message);
    const std::string log = recentLog();
    if (!log.empty()) {
        detail += "\n";
        detail += log;
    }
    env->ThrowNew(error, detail.c_str());
}

// Tokens can split a multi-byte character, so keep incomplete byte sequences
// until the next token completes them. Output is UTF-16 for NewString().
class TextDecoder {
public:
    std::u16string feed(const char * data, size_t length) {
        pending_.append(data, length);
        std::u16string out;
        size_t offset = 0;
        while (offset < pending_.size()) {
            const unsigned char lead = static_cast<unsigned char>(pending_[offset]);
            uint32_t point = 0;
            size_t width = 0;
            if (lead < 0x80) {
                point = lead;
                width = 1;
            } else if ((lead & 0xE0) == 0xC0) {
                point = lead & 0x1F;
                width = 2;
            } else if ((lead & 0xF0) == 0xE0) {
                point = lead & 0x0F;
                width = 3;
            } else if ((lead & 0xF8) == 0xF0) {
                point = lead & 0x07;
                width = 4;
            } else {
                pending_.erase(offset, 1);
                continue;
            }
            if (offset + width > pending_.size()) break;
            bool valid = true;
            for (size_t i = 1; i < width; ++i) {
                const unsigned char byte = static_cast<unsigned char>(pending_[offset + i]);
                if ((byte & 0xC0) != 0x80) {
                    valid = false;
                    break;
                }
                point = (point << 6) | (byte & 0x3F);
            }
            if (!valid || point > 0x10FFFF || (point >= 0xD800 && point <= 0xDFFF)) {
                pending_.erase(offset, 1);
                continue;
            }
            if (point < 0x10000) {
                out.push_back(static_cast<char16_t>(point));
            } else {
                point -= 0x10000;
                out.push_back(static_cast<char16_t>(0xD800 + (point >> 10)));
                out.push_back(static_cast<char16_t>(0xDC00 + (point & 0x3FF)));
            }
            offset += width;
        }
        pending_.erase(0, offset);
        return out;
    }

private:
    std::string pending_;
};

bool isStopText(const std::string & text) {
    return text.find("<|im_end|>") != std::string::npos ||
        text.find("<|endoftext|>") != std::string::npos ||
        text.find("<|eot_id|>") != std::string::npos ||
        // The note is the last section; do not spend tokens on a goodbye.
        text.find("</NOTE>") != std::string::npos;
}

// Lets Cancel interrupt a long llama_decode() instead of only waiting for the
// next batch boundary. CPU execution checks this callback while computing.
bool abortIfCancelled(void *) {
    return g_cancel_requested.load();
}

void destroy(Session * value) {
    if (value == nullptr) return;
    llama_free(value->ctx);
    llama_model_free(value->model);
    delete value;
}

} // namespace

extern "C" {

JNIEXPORT void JNICALL
Java_io_github_jonatasgoncalves_parley_LlamaEngine_nativeInitBackends(
        JNIEnv * env, jclass, jstring path) {
    const std::string dir = javaString(env, path);
    {
        std::lock_guard<std::mutex> lock(g_backend_mutex);
        g_backend_dir = dir;
    }
    startBackend();
}

JNIEXPORT jlong JNICALL
Java_io_github_jonatasgoncalves_parley_LlamaEngine_nativeInitModel(
        JNIEnv * env, jclass, jobjectArray paths) {
    startBackend();
    clearLog();
    const jsize count = env->GetArrayLength(paths);
    if (count <= 0) {
        raise(env, "No model file was selected");
        return 0;
    }
    std::vector<std::string> files;
    std::vector<const char *> pointers;
    files.reserve(count);
    pointers.reserve(count);
    for (jsize i = 0; i < count; ++i) {
        auto element = static_cast<jstring>(env->GetObjectArrayElement(paths, i));
        files.push_back(javaString(env, element));
        env->DeleteLocalRef(element);
        if (files.back().empty()) {
            raise(env, "A model path is empty");
            return 0;
        }
    }
    for (const auto & file : files) {
        pointers.push_back(file.c_str());
    }

    llama_model_params model_params = llama_model_default_params();
    llama_model * model = nullptr;
    if (pointers.size() == 1) {
        model = llama_model_load_from_file(pointers.front(), model_params);
    } else {
        model = llama_model_load_from_splits(pointers.data(), pointers.size(), model_params);
    }
    if (model == nullptr) {
        raiseDetailed(env, "Could not load the GGUF model");
        return 0;
    }

    llama_context_params context_params = llama_context_default_params();
    const int cores = std::max(1, static_cast<int>(std::thread::hardware_concurrency()));
    context_params.n_ctx = 1536;
    context_params.n_batch = 512;
    context_params.n_ubatch = 512;
    // Prefill is highly parallel; a single-token decode is memory bound and
    // runs best on a small set of big cores.
    context_params.n_threads = std::min(4, cores);
    context_params.n_threads_batch = std::min(8, cores);
    // Quantized KV cache and flash attention lower memory traffic on phones.
    context_params.type_k = GGML_TYPE_Q8_0;
    context_params.type_v = GGML_TYPE_Q8_0;
    // AUTO avoids flash-attention backend incompatibilities seen on some Android CPU setups.
    context_params.flash_attn_type = LLAMA_FLASH_ATTN_TYPE_AUTO;
    // Cancel can now stop a long prompt decode in the middle of a batch.
    context_params.abort_callback = abortIfCancelled;
    context_params.abort_callback_data = nullptr;
    llama_context * ctx = llama_init_from_model(model, context_params);
    if (ctx == nullptr) {
        llama_model_free(model);
        raiseDetailed(env, "Could not create the inference context");
        return 0;
    }

    auto * value = new Session();
    value->model = model;
    value->ctx = ctx;
    value->vocab = llama_model_get_vocab(model);

    {
        std::ostringstream info;
        info << files.front()
             << " | bytes=" << llama_model_size(model)
             << " | layers=" << llama_model_n_layer(model)
             << " | ctx=" << context_params.n_ctx
             << " (trained " << llama_model_n_ctx_train(model) << ")"
             << " | batch=" << context_params.n_batch
             << " | threads=" << context_params.n_threads
             << "/" << context_params.n_threads_batch
             << " | kv=q8_0 | flash=auto"
             << " | vocab=" << llama_vocab_n_tokens(value->vocab);
        std::lock_guard<std::mutex> lock(g_model_info_mutex);
        g_model_info = info.str();
    }

    // Compile the CPU graphs and start the thread pool while the model is
    // loading, so the first real turn does not pay that one-time cost.
    {
        std::vector<llama_token> warm(16);
        const int warm_count = llama_tokenize(
            value->vocab, "hello", 5, warm.data(), static_cast<int>(warm.size()), true, false);
        if (warm_count > 0) {
            const int warm_decoded = llama_decode(value->ctx, llama_batch_get_one(warm.data(), warm_count));
            if (warm_decoded == 0) {
                llama_sampler * warm_sampler =
                    llama_sampler_chain_init(llama_sampler_chain_default_params());
                llama_sampler_chain_add(warm_sampler, llama_sampler_init_dist(LLAMA_DEFAULT_SEED));
                llama_sampler_sample(warm_sampler, value->ctx, -1);
                llama_sampler_free(warm_sampler);
            }
            llama_memory_clear(llama_get_memory(value->ctx), true);
        }
    }

    // Stop any in-flight generation before waiting for the session lock.
    g_cancel_requested.store(true);
    std::unique_lock<std::shared_mutex> lock(g_session_mutex);
    destroy(session(g_active));
    g_active = reinterpret_cast<jlong>(value);
    g_cancel_requested.store(false);
    return g_active;
}

JNIEXPORT void JNICALL
Java_io_github_jonatasgoncalves_parley_LlamaEngine_nativeGenerate(
        JNIEnv * env, jclass, jlong handle, jstring prompt, jint max_tokens, jobject sink) {
    // Mark busy before waiting for the generate mutex, so a diagnostics probe
    // sees the pending turn and can avoid blocking on the Kotlin monitor.
    ActiveGeneration active_generation;
    const auto started = std::chrono::steady_clock::now();
    g_generations.fetch_add(1);
    // One reply at a time, and the session stays alive until this returns.
    std::lock_guard<std::mutex> generate_lock(g_generate_mutex);
    std::shared_lock<std::shared_mutex> session_lock(g_session_mutex);
    Session * value = session(handle);
    if (g_active != handle || value == nullptr ||
        value->model == nullptr || value->ctx == nullptr) {
        raise(env, "No model is loaded");
        return;
    }
    if (sink == nullptr) {
        raise(env, "Missing token callback");
        return;
    }
    jclass sink_class = env->GetObjectClass(sink);
    jmethodID on_token = env->GetMethodID(sink_class, "onToken", "(Ljava/lang/String;)V");
    env->DeleteLocalRef(sink_class);
    if (on_token == nullptr) return;

    std::string text = javaString(env, prompt);
    if (text.empty()) {
        raise(env, "The prompt is empty");
        return;
    }

    // A previous turn (or a cancelled load) must not leave a pending cancel or
    // stale KV cells in front of the new prompt.
    g_cancel_requested.store(false);
    llama_memory_clear(llama_get_memory(value->ctx), true);

    std::vector<llama_token> tokens(text.size() + 8);
    const int token_count = llama_tokenize(
        value->vocab, text.data(), static_cast<int32_t>(text.size()),
        tokens.data(), static_cast<int32_t>(tokens.size()), true, true);
    if (token_count <= 0) {
        raise(env, "Could not tokenize the prompt");
        return;
    }
    tokens.resize(token_count);
    g_prompt_tokens.store(token_count);
    g_prompt_batches.store(0);
    g_prompt_batches_total.store(0);

    // Decode the prompt in small pieces. A single 233-token llama_decode can
    // not be interrupted; chunks let Cancel and Diagnostics take effect between
    // batches and let the UI see progress.
    const uint32_t batch = std::min<uint32_t>(llama_n_batch(value->ctx), 128);
    for (size_t offset = 0; offset < tokens.size(); offset += batch) {
        if (g_cancel_requested.load()) {
            g_last_cancelled.store(true);
            return;
        }
        const int size = static_cast<int>(std::min<size_t>(batch, tokens.size() - offset));
        g_prompt_batches_total.fetch_add(1);
        const int decoded = llama_decode(
            value->ctx, llama_batch_get_one(tokens.data() + offset, size));
        if (decoded != 0) {
            llama_memory_clear(llama_get_memory(value->ctx), true);
            if (g_cancel_requested.load()) {
                g_last_cancelled.store(true);
                return;
            }
            raise(env, "Could not process the prompt");
            return;
        }
        // Updated after every batch so Diagnostics can see progress while a
        // slow phone is still evaluating a long prompt.
        g_prompt_batches.fetch_add(1);
        g_last_prompt_ms.store(static_cast<long>(
            std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - started).count()));
    }

    llama_sampler_chain_params sampler_params = llama_sampler_chain_default_params();
    llama_sampler * sampler = llama_sampler_chain_init(sampler_params);
    llama_sampler_chain_add(sampler, llama_sampler_init_dist(LLAMA_DEFAULT_SEED));

    TextDecoder decoder;
    std::string raw;
    bool emitted = false;
    bool cancelled = false;
    const int limit = std::max(1, max_tokens);
    for (int step = 0; step < limit; ++step) {
        if (g_cancel_requested.load()) {
            cancelled = true;
            break;
        }
        llama_token token = llama_sampler_sample(sampler, value->ctx, -1);
        if (llama_vocab_is_eog(value->vocab, token) ||
            token == llama_vocab_eos(value->vocab) ||
            token == llama_vocab_eot(value->vocab)) break;

        char buffer[256];
        const int32_t written = llama_token_to_piece(
            value->vocab, token, buffer, static_cast<int32_t>(sizeof(buffer)), 0, true);
        if (written <= 0) {
            if (step + 1 < limit) {
                const int decoded = llama_decode(
                    value->ctx, llama_batch_get_one(&token, 1));
                if (decoded != 0) {
                    if (g_cancel_requested.load()) cancelled = true;
                    else llama_memory_clear(llama_get_memory(value->ctx), true);
                    break;
                }
            }
            continue;
        }
        std::string piece(buffer, static_cast<size_t>(written));
        raw += piece;

        std::u16string output = decoder.feed(piece.data(), piece.size());
        if (!output.empty()) {
            if (!emitted) {
                emitted = true;
                g_last_first_token_ms.store(static_cast<long>(
                    std::chrono::duration_cast<std::chrono::milliseconds>(
                        std::chrono::steady_clock::now() - started).count()));
            }
            g_tokens_total.fetch_add(1);
            jstring java_text = env->NewString(
                reinterpret_cast<const jchar *>(output.data()),
                static_cast<jsize>(output.size()));
            if (java_text != nullptr) {
                env->CallVoidMethod(sink, on_token, java_text);
                env->DeleteLocalRef(java_text);
            }
            if (env->ExceptionCheck()) break;
        }
        // Stop only after the closing tag has been delivered, so the reply
        // parser still sees a complete <NOTE> section.
        if (isStopText(raw)) break;
        if (step + 1 < limit) {
            const int decoded = llama_decode(
                value->ctx, llama_batch_get_one(&token, 1));
            if (decoded != 0) {
                if (g_cancel_requested.load()) cancelled = true;
                else llama_memory_clear(llama_get_memory(value->ctx), true);
                break;
            }
        }
    }
    g_last_cancelled.store(cancelled);
    llama_sampler_free(sampler);
}

JNIEXPORT void JNICALL
Java_io_github_jonatasgoncalves_parley_LlamaEngine_nativeCancel(JNIEnv *, jclass, jlong) {
    // Never touch the Session here: it may already have been freed on another
    // thread while a generation was running.
    g_cancel_requested.store(true);
}

JNIEXPORT void JNICALL
Java_io_github_jonatasgoncalves_parley_LlamaEngine_nativeFreeModel(JNIEnv *, jclass, jlong handle) {
    // The generation loop checks this flag while holding a shared lock; set it
    // before requesting the unique lock or we would wait for ourselves.
    g_cancel_requested.store(true);
    std::unique_lock<std::shared_mutex> lock(g_session_mutex);
    if (g_active != handle) return;
    g_active = 0;
    destroy(session(handle));
}

JNIEXPORT jboolean JNICALL
Java_io_github_jonatasgoncalves_parley_LlamaEngine_nativeIsReady(JNIEnv *, jclass, jlong handle) {
    std::shared_lock<std::shared_mutex> lock(g_session_mutex);
    Session * value = session(handle);
    return g_active == handle && value != nullptr &&
        value->model != nullptr && value->ctx != nullptr;
}

JNIEXPORT jboolean JNICALL
Java_io_github_jonatasgoncalves_parley_LlamaEngine_nativeIsGenerating(JNIEnv *, jclass) {
    return g_active_generations.load() > 0;
}

JNIEXPORT jboolean JNICALL
Java_io_github_jonatasgoncalves_parley_LlamaEngine_nativeWasLastCancelled(JNIEnv *, jclass) {
    return g_last_cancelled.load();
}

// Qwen3 generates a <think> block unless the chat template pre-fills an empty
// one. We render ChatML ourselves, so Kotlin needs to know when to add it.
JNIEXPORT jboolean JNICALL
Java_io_github_jonatasgoncalves_parley_LlamaEngine_nativeIsThinkingModel(
        JNIEnv *, jclass, jlong handle) {
    std::shared_lock<std::shared_mutex> lock(g_session_mutex);
    Session * value = session(handle);
    if (g_active != handle || value == nullptr || value->model == nullptr) {
        return JNI_FALSE;
    }
    const char * keys[] = {
        "general.architecture", "general.name", "tokenizer.ggml.model",
    };
    for (const char * key : keys) {
        char buffer[256] = {};
        if (llama_model_meta_val_str(value->model, key, buffer, sizeof(buffer)) <= 0) continue;
        std::string lower(buffer);
        std::transform(lower.begin(), lower.end(), lower.begin(),
            [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        if (lower.find("qwen3") != std::string::npos) return JNI_TRUE;
    }
    {
        std::lock_guard<std::mutex> info_lock(g_model_info_mutex);
        std::string lower(g_model_info);
        std::transform(lower.begin(), lower.end(), lower.begin(),
            [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        if (lower.find("qwen3") != std::string::npos) return JNI_TRUE;
    }
    return JNI_FALSE;
}

JNIEXPORT jstring JNICALL
Java_io_github_jonatasgoncalves_parley_LlamaEngine_nativeDiagnostics(JNIEnv * env, jclass) {
    std::string info;
    {
        std::lock_guard<std::mutex> lock(g_model_info_mutex);
        info = g_model_info;
    }
    std::ostringstream out;
    out << "llama.cpp " << llama_version() << " (Android, CPU)\n"
        << "backends: ";
    for (size_t i = 0; i < ggml_backend_reg_count(); ++i) {
        if (i != 0) out << ", ";
        out << ggml_backend_reg_name(ggml_backend_reg_get(i));
    }
    out << "\nbackend search: " << backendStatus() << "\n"
        << "model: " << info << "\n"
        << "handle: active=" << g_active << "\n"
        << "generating: " << (g_active_generations.load() > 0 ? "yes" : "no") << "\n"
        << "generations: " << g_generations.load() << "\n"
        << "prompt tokens (last): " << g_prompt_tokens.load() << "\n"
        << "prompt batches: " << g_prompt_batches.load() << "/"
        << g_prompt_batches_total.load() << "\n"
        << "prompt decode ms (last): " << g_last_prompt_ms.load() << "\n"
        << "first token ms (last): " << g_last_first_token_ms.load() << "\n"
        << "tokens emitted (total): " << g_tokens_total.load() << "\n"
        << "last run cancelled: " << (g_last_cancelled.load() ? "yes" : "no");
    const std::string log = recentLog();
    if (!log.empty()) {
        out << "\nnative log:\n" << log;
    }
    return env->NewStringUTF(out.str().c_str());
}

JNIEXPORT jstring JNICALL
Java_io_github_jonatasgoncalves_parley_LlamaEngine_nativeVersion(JNIEnv * env, jclass) {
    std::string version = std::string("llama.cpp ") + llama_version() + " (Android, CPU)";
    return env->NewStringUTF(version.c_str());
}

// ---------------------------------------------------------------------------
// Whisper STT
// ---------------------------------------------------------------------------

struct WhisperSession {
    whisper_context * ctx = nullptr;
};

std::shared_mutex g_whisper_mutex;
jlong g_whisper_active = 0;
std::mutex g_whisper_info_mutex;
std::string g_whisper_info = "none";

WhisperSession * whisper_session(jlong handle) {
    return reinterpret_cast<WhisperSession *>(handle);
}

JNIEXPORT jlong JNICALL
Java_io_github_jonatasgoncalves_parley_WhisperEngine_nativeLoad(JNIEnv * env, jclass, jstring model_path) {
    if (model_path == nullptr) return 0;
    const char * raw_path = env->GetStringUTFChars(model_path, nullptr);
    const std::string path = raw_path ? raw_path : "";
    env->ReleaseStringUTFChars(model_path, raw_path);

    struct whisper_context_params cparams = whisper_context_default_params();
    cparams.use_gpu = false;
    cparams.flash_attn = false;

    whisper_context * ctx = whisper_init_from_file_with_params(path.c_str(), cparams);
    if (ctx == nullptr) {
        pushLog(std::string("whisper: failed to load model: ") + path);
        return 0;
    }

    auto * value = new WhisperSession();
    value->ctx = ctx;

    {
        std::ostringstream info;
        info << path;
        std::lock_guard<std::mutex> lock(g_whisper_info_mutex);
        g_whisper_info = info.str();
    }

    std::unique_lock<std::shared_mutex> lock(g_whisper_mutex);
    const jlong old_handle = g_whisper_active;
    g_whisper_active = reinterpret_cast<jlong>(value);
    lock.unlock();

    if (old_handle != 0) {
        auto * old = whisper_session(old_handle);
        if (old != nullptr) {
            if (old->ctx) whisper_free(old->ctx);
            delete old;
        }
    }

    __android_log_print(ANDROID_LOG_INFO, "parley-whisper", "loaded: %s", path.c_str());
    return g_whisper_active;
}

JNIEXPORT void JNICALL
Java_io_github_jonatasgoncalves_parley_WhisperEngine_nativeFree(JNIEnv *, jclass, jlong handle) {
    if (handle == 0) return;
    std::unique_lock<std::shared_mutex> lock(g_whisper_mutex);
    if (g_whisper_active == handle) g_whisper_active = 0;
    lock.unlock();

    auto * value = whisper_session(handle);
    if (value == nullptr) return;
    if (value->ctx) whisper_free(value->ctx);
    delete value;
}

JNIEXPORT jboolean JNICALL
Java_io_github_jonatasgoncalves_parley_WhisperEngine_nativeIsReady(JNIEnv *, jclass) {
    std::shared_lock<std::shared_mutex> lock(g_whisper_mutex);
    return g_whisper_active != 0 ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jstring JNICALL
Java_io_github_jonatasgoncalves_parley_WhisperEngine_nativeTranscribe(
        JNIEnv * env, jclass, jfloatArray samples, jstring language, jboolean translate) {
    if (samples == nullptr) return env->NewStringUTF("");

    std::shared_lock<std::shared_mutex> lock(g_whisper_mutex);
    const jlong handle = g_whisper_active;
    auto * value = whisper_session(handle);
    if (value == nullptr || value->ctx == nullptr) {
        return env->NewStringUTF("");
    }

    const jsize n_samples = env->GetArrayLength(samples);
    std::vector<float> pcm(static_cast<size_t>(n_samples));
    env->GetFloatArrayRegion(samples, 0, n_samples, pcm.data());

    const char * raw_lang = language ? env->GetStringUTFChars(language, nullptr) : nullptr;
    std::string lang = raw_lang ? raw_lang : "en";
    if (language) env->ReleaseStringUTFChars(language, raw_lang);
    if (lang == "zh") lang = "zh";
    if (lang == "pt") lang = "pt";

    whisper_full_params params = whisper_full_default_params(WHISPER_SAMPLING_GREEDY);
    params.print_progress = false;
    params.print_special = false;
    params.print_realtime = false;
    params.print_timestamps = false;
    params.translate = translate == JNI_TRUE;
    params.language = lang.c_str();
    params.n_threads = std::max(2, std::min(4, static_cast<int>(std::thread::hardware_concurrency())));
    params.single_segment = false;
    params.no_context = true;

    const int result = whisper_full(value->ctx, params, pcm.data(), static_cast<int>(pcm.size()));
    if (result != 0) {
        pushLog(std::string("whisper: transcription failed, code=") + std::to_string(result));
        return env->NewStringUTF("");
    }

    std::string text;
    const int n_segments = whisper_full_n_segments(value->ctx);
    for (int i = 0; i < n_segments; ++i) {
        const char * segment = whisper_full_get_segment_text(value->ctx, i);
        if (segment != nullptr) text += segment;
    }

    // Trim whitespace
    const auto start = text.find_first_not_of(" \t\n\r");
    const auto end = text.find_last_not_of(" \t\n\r");
    if (start == std::string::npos) text.clear();
    else text = text.substr(start, end - start + 1);

    return env->NewStringUTF(text.c_str());
}

JNIEXPORT jstring JNICALL
Java_io_github_jonatasgoncalves_parley_WhisperEngine_nativeInfo(JNIEnv * env, jclass) {
    std::lock_guard<std::mutex> lock(g_whisper_info_mutex);
    return env->NewStringUTF(g_whisper_info.c_str());
}

} // extern "C"
