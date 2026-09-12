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
        versionCode = 7
        versionName = "0.5.0-canonical-phone-interface"
    }
    buildTypes { release { isMinifyEnabled = false } }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}
