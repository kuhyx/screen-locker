import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Release signing key, kept out of the repo. CI writes key.properties from
// repository secrets; locally the file is absent and the build falls back to
// the debug key so `flutter run --release` still works. Every release APK is
// signed with the one shared key, so updates install over each other instead
// of forcing an uninstall.
val keystoreProperties = Properties().apply {
    val f = rootProject.file("key.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}

android {
    namespace = "com.kuhy.workout_app"
    // Pinned above `flutter.compileSdkVersion` (36 on Flutter 3.47.2):
    // flutter_secure_storage 11.0.0, which arrives with crdt_sync_flutter
    // v0.3.1, publishes AAR metadata demanding API 37 or later. That in
    // turn needs AGP > 9.1.0, which needs Gradle >= 9.5.0 -- see
    // settings.gradle.kts and gradle-wrapper.properties.
    compileSdk = 37
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
        // Required by flutter_local_notifications 22.x, which uses java.time
        // APIs that only exist from API 26. minSdk here is 24, so they have to
        // be backported. The plugin's README says to enable this even when the
        // app schedules no notifications -- we don't, and it is still needed:
        // without it the Android build fails outright.
        isCoreLibraryDesugaringEnabled = true
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.kuhy.workout_app"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (keystoreProperties.getProperty("storeFile") != null) {
            create("release") {
                storeFile = file(keystoreProperties.getProperty("storeFile"))
                storePassword = keystoreProperties.getProperty("storePassword")
                keyAlias = keystoreProperties.getProperty("keyAlias")
                keyPassword = keystoreProperties.getProperty("keyPassword")
            }
        }
    }

    // Two installs of the same code, side by side. The sandbox flavor has its
    // own package name, so Android gives it its own app data: it physically
    // cannot read or write the daily build's database, secure storage or
    // notification channels, which is what makes it safe to poke at during a
    // real training block. Everything else the sandbox must not touch (the
    // LAN server the PC pulls from, Firebase/GitHub, the /sdcard mirrors) is
    // switched off in Dart from BuildConfig.FLAVOR via MainActivity.
    flavorDimensions += "store"
    productFlavors {
        create("daily") {
            dimension = "store"
            manifestPlaceholders["appLabel"] = "workout_app"
        }
        create("sandbox") {
            dimension = "store"
            applicationIdSuffix = ".sandbox"
            versionNameSuffix = "-sandbox"
            manifestPlaceholders["appLabel"] = "Workout SANDBOX"
        }
    }

    buildFeatures {
        buildConfig = true
    }

    buildTypes {
        release {
            // Falls back to the debug key only when key.properties is absent
            // (a fresh clone or a local run), so `flutter run --release` works.
            signingConfig = signingConfigs.findByName("release")
                ?: signingConfigs.getByName("debug")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}

dependencies {
    // Backports java.time for minSdk 24; see isCoreLibraryDesugaringEnabled.
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.5")
}
