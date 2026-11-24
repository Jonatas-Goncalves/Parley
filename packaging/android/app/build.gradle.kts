plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "io.github.jonatasgoncalves.parley"
    compileSdk = 34
    ndkVersion = "27.2.12479018"

    defaultConfig {
        // Separate install identity so both Parley variants can be tested side by side.
        applicationId = "io.github.jonatasgoncalves.parley.llama"
        minSdk = 26
        targetSdk = 34
        versionCode = 10000
        versionName = "1.0.0"

        externalNativeBuild {
            cmake {
                abiFilters += listOf("arm64-v8a")
            }
        }
    }

    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.31.6"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    packaging {
        jniLibs {
            // GGML CPU backends are loaded by path at runtime (GGML_BACKEND_DL).
            useLegacyPackaging = true
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("org.apache.commons:commons-compress:1.26.2")
}
