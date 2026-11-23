plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.saudi1.tv"
    compileSdk = 34
    defaultConfig {
        applicationId = "com.saudi1.tv"
        // a side-by-side copy for screenshots of a brand-new install (saudi1_preview.yml); empty for the real app
        applicationIdSuffix = System.getenv("APP_SUFFIX") ?: ""
        minSdk = 23
        targetSdk = 34
        versionCode = (System.getenv("BUILD_NUMBER") ?: "1").toInt()
        versionName = "1.0." + (System.getenv("BUILD_NUMBER") ?: "1")
    }
    signingConfigs {
        create("release") {
            storeFile = file("../saudi1.keystore")
            storePassword = "saudi1-tv"
            keyAlias = "saudi1"
            keyPassword = "saudi1-tv"
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.getByName("release")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
        isCoreLibraryDesugaringEnabled = true   // needed by the FFmpeg sound decoder on older Android
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { buildConfig = true }
}

dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.0.4")
    // WireGuard VPN (the config comes from the owner's admin site, or a .conf file on phones)
    implementation("com.wireguard.android:tunnel:1.0.20230706")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.recyclerview:recyclerview:1.3.2")
    // the TV grid for Movies / Series (the one Google TV apps use): the focused row glides, held keys never stall
    implementation("androidx.leanback:leanback:1.0.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.4")
    implementation("androidx.media3:media3-exoplayer:1.3.1")
    implementation("androidx.media3:media3-exoplayer-hls:1.3.1")
    implementation("androidx.media3:media3-ui:1.3.1")
    implementation("androidx.media3:media3-datasource-okhttp:1.3.1")
    // AC3 / E-AC3 / MP2 / DTS sound on TVs and phones without those decoders
    // (the version that matches Media3 is looked up by the build; without one the app is built without it)
    System.getenv("FFMPEG_VER")?.takeIf { it.isNotBlank() }?.let { implementation("org.jellyfin.media3:media3-ffmpeg-decoder:$it") }
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("io.coil-kt:coil:2.6.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}
