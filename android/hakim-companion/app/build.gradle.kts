plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "org.hakim.omega.companion"
    compileSdk = 35
    defaultConfig {
        applicationId = "org.hakim.omega.companion"
        minSdk = 26
        targetSdk = 35
        versionCode = 2
        versionName = "0.2.0-playprotect-safe"
    }
    buildTypes { release { isMinifyEnabled = false } }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}
