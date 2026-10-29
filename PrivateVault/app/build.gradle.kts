plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.saudi.privatevault"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.saudi.privatevault"
        minSdk = 26
        targetSdk = 35
        versionCode = 2
        versionName = "1.1"
    }

    // Builds are signed with the key from the VAULT_KEYSTORE* environment
    // variables (GitHub secrets in CI). Keeping one key means a newer APK
    // installs over the old one and everything saved in the vault stays.
    // Without them the standard debug key is used.
    val keystorePath = System.getenv("VAULT_KEYSTORE")
    signingConfigs {
        if (keystorePath != null && file(keystorePath).exists()) {
            create("vault") {
                storeFile = file(keystorePath)
                storePassword = System.getenv("VAULT_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("VAULT_KEY_ALIAS") ?: "vault"
                keyPassword = System.getenv("VAULT_KEY_PASSWORD") ?: System.getenv("VAULT_KEYSTORE_PASSWORD")
            }
        }
    }
    val vaultSigning = signingConfigs.findByName("vault") ?: signingConfigs.getByName("debug")

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = vaultSigning
        }
        debug {
            signingConfig = vaultSigning
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        viewBinding = true
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.activity:activity-ktx:1.9.3")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.recyclerview:recyclerview:1.3.2")
    implementation("androidx.lifecycle:lifecycle-process:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.biometric:biometric:1.1.0")
    implementation("androidx.media3:media3-exoplayer:1.4.1")
    implementation("androidx.media3:media3-ui:1.4.1")
}
