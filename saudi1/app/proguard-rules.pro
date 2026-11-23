-dontwarn okhttp3.**
-dontwarn okio.**

# The app's own code is renamed and shrunk by R8 (owner, 21 Nov 2026: protect the app). The crash report
# (Settings › App › Last error) keeps its line numbers; the build keeps mapping.txt to read it back.
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute S

# FFmpeg sound decoders are found by name at run time (DefaultRenderersFactory)
-keep class androidx.media3.decoder.ffmpeg.** { *; }

# WireGuard (native code calls back into these)
-keep class com.wireguard.** { *; }
