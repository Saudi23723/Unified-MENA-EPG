# 📺 قناة المعلومات — MENA Sports Info

قناة بث حي **24/7** تعرض المباريات المباشرة والقادمة، مبنية من دليل
`unified_mena_epg.xml` الموجود في هذا المستودع.

النتيجة رابط `.m3u8` عادي — تضيفه في TiviMate أو أي مشغل IPTV **مثل أي قناة**،
وتظهر في قائمة قنواتك جنب اشتراكك.

```
unified_mena_epg.xml  ──▶  Pillow يرسم الشاشة  ──▶  ffmpeg  ──▶  HLS  ──▶  مشغل IPTV
   (GitHub يحدّثه كل 15 د)      (بدون متصفح)          (H.264)      (.m3u8)
```

**لماذا بدون متصفح؟** الطريقة الشائعة (Chromium + تسجيل شاشة) تحتاج جهازًا
قويًا. هنا تُرسم الشاشة مباشرة كصور، فالتكلفة **1.8 مللي ثانية للإطار
(~1% من نواة معالج واحدة)** — يعني تشتغل على Raspberry Pi أو أصغر سيرفر مجاني.

---

## 🚀 التشغيل السريع

```bash
git clone https://github.com/Saudi23723/Unified-MENA-EPG.git
cd Unified-MENA-EPG/infochannel

pip install -r requirements.txt
sudo apt install ffmpeg fonts-dejavu-core        # ديبيان / أوبنتو / راسبيان

python3 stream.py
```

سيطبع لك:

```
[stream] playlist : http://192.168.1.50:8080/playlist.m3u   <- add this to your IPTV app
[stream] stream   : http://192.168.1.50:8080/info.m3u8
```

**تبي تشوف الشكل قبل ما تشغّل البث؟** (ما يحتاج ffmpeg):

```bash
python3 stream.py --preview shot.png --preview-pages 3
```

---

## 📲 الإضافة إلى تطبيق الـ IPTV

> ملاحظة مهمة: لا يمكن إضافة قناة **داخل** اشتراكك — قائمة الاشتراك يتحكم بها
> المزوّد. لكن كل مشغلات IPTV تسمح بإضافة **مصدر إضافي** يظهر جنب قنوات
> اشتراكك في نفس الواجهة. وهذي هي الطريقة:

### TiviMate

1. `Settings` ← `Playlists` ← `Add playlist` ← `Enter URL`
2. الصق: `http://<عنوان-الجهاز>:8080/playlist.m3u`
3. `Next` ← اختر اسمًا ← `Done`

القناة تظهر باسم **MENA Sports Info** ضمن مجموعة `INFO`.

### تطبيقات أخرى

| التطبيق | المكان |
|---|---|
| IBO Player / IBO Pro | Add Playlist ← M3U URL |
| XCIPTV | Add Playlist ← M3U |
| IPTV Smarters | Login with M3U URL |
| VLC / MX Player | افتح رابط الشبكة `info.m3u8` مباشرة |

---

## 💰 وين تشغّلها مجانًا للأبد؟

أي بث 24/7 يحتاج **شيء يشتغل باستمرار**. هذا لا يعني أن تدفع — لكنه يعني أن
GitHub Actions غير مناسب (الوظيفة تنتهي بعد 6 ساعات، والاستخدام للبث المستمر
مخالف لشروط الخدمة). الخياران المجانيان الحقيقيان:

### الخيار أ — جهاز عندك أصلاً ✅ الأنسب

أي جهاز يشتغل على أي حال: راوتر لينكس، **Raspberry Pi**، أندرويد بوكس
(عبر Termux)، لابتوب قديم، أو كمبيوتر شغّال.

- **التكلفة: صفر** — لا حساب ولا بطاقة ولا تسجيل.
- يعمل داخل الشبكة المنزلية مباشرة (المشغّل والجهاز على نفس الواي فاي).
- الاستهلاك ~1% معالج و~60 ميجابايت رام.

```bash
python3 stream.py --out /run/mena-info      # على Pi: اكتب المقاطع في الرام
```

للتشغيل التلقائي عند الإقلاع: استخدم `mena-info.service` المرفق.

### الخيار ب — Oracle Cloud Always Free 🌍 بدون أي جهاز عندك

> 📘 **الدليل الكامل خطوة بخطوة (من متصفح الجوال، بدون كمبيوتر ولا SSH):**
> [`ORACLE.md`](ORACLE.md) — مع سكربت إعداد تلقائي يركّب كل شي بنفسه.

Oracle تقدّم أجهزة **مجانية للأبد** (وليست تجربة 30 يوم):

| المورد | المتاح مجانًا |
|---|---|
| المعالج | 4 أنوية ARM + 24 جيجا رام (أو جهازين AMD صغيرين) |
| النقل الصادر | **10 تيرابايت شهريًا** |
| المدة | دائم — لا ينتهي |

بمعدل 900 kbps، المشاهد الواحد المستمر 24 ساعة يستهلك ~9.7 جيجا يوميًا
(~292 جيجا شهريًا) — أي أن 10 تيرابايت تكفي **~34 مشاهدًا متواصلين**.

> ⚠️ للأمانة: التسجيل في Oracle يتطلب بطاقة للتحقق من الهوية فقط (بدون خصم)،
> وأحيانًا تكون أجهزة ARM غير متوفرة في منطقتك فتحتاج تجربة منطقة أخرى.

بعد إنشاء الجهاز:

```bash
sudo apt update && sudo apt install -y python3-pip ffmpeg fonts-dejavu-core
git clone https://github.com/Saudi23723/Unified-MENA-EPG.git
cd Unified-MENA-EPG/infochannel && pip install -r requirements.txt

sudo cp mena-info.service /etc/systemd/system/
sudo systemctl enable --now mena-info
```

ثم افتح المنفذ 8080 في **Security List** داخل لوحة Oracle **و** في جدار
الجهاز نفسه:

```bash
sudo iptables -I INPUT -p tcp --dport 8080 -j ACCEPT
sudo netfilter-persistent save
```

### وسط بين الاثنين — جهازك + نفق مجاني

تبي تشغّلها على جهازك بالبيت لكن توصل لها من خارج المنزل؟ استخدم
**Cloudflare Tunnel** (خطة مجانية) بدل فتح منافذ الراوتر:

```bash
cloudflared tunnel --url http://localhost:8080
```

> ⚠️ شروط Cloudflare المجانية تقيّد بث كميات كبيرة من الفيديو. للاستخدام
> الشخصي الخفيف عادةً لا مشكلة، لكنها ليست الطريقة المخصصة لذلك — للاستخدام
> الجاد الخيار (ب) أسلم.

---

## ⚙️ الخيارات

```bash
python3 stream.py --help
```

| الخيار | الافتراضي | الوصف |
|---|---|---|
| `--epg` | رابط GitHub | مسار ملف XMLTV أو رابط |
| `--refresh` | `300` | كل كم ثانية يُعاد تحميل الدليل |
| `--port` | `8080` | منفذ خادم الويب المدمج |
| `--out` | `hls` | مجلد مقاطع HLS |
| `--width` `--height` | `1280` `720` | الدقة (جرّب `854x480` لجهاز ضعيف) |
| `--fps` | `5` | كافية تمامًا — الساعة وحدها تتحرك |
| `--bitrate` | `900` | كيلوبت/ثانية |
| `--rotate` | `12` | ثوانٍ لكل صفحة قبل التبديل |
| `--tz` | `Asia/Riyadh` | المنطقة الزمنية المعروضة |
| `--title` | `MENA SPORTS INFO` | اسم القناة في الأعلى وفي قائمة M3U |
| `--channels` | — | Regex: اعرض القنوات المطابقة فقط |
| `--exclude-channels` | — | Regex: أخفِ القنوات المطابقة |
| `--all-programmes` | مطفأ | اعرض كل البرامج لا الرياضة فقط |
| `--no-serve` | مطفأ | اكتب ملفات HLS فقط (لو عندك nginx) |
| `--preview` | — | احفظ صورة واخرج (بدون ffmpeg) |

أمثلة:

```bash
# قناة beIN فقط، بدقة 1080p
python3 stream.py --channels 'beIN' --width 1920 --height 1080 --bitrate 1600

# جهاز ضعيف
python3 stream.py --width 854 --height 480 --fps 4 --bitrate 500 --preset ultrafast
```

---

## 🐳 Docker

```bash
docker build -t mena-info infochannel/
docker run -d --restart unless-stopped -p 8080:8080 \
  --tmpfs /tmp/hls --name mena-info mena-info
```

---

## 🧪 الفحوصات

```bash
python3 test_render.py ../unified_mena_epg.xml
```

تفحص الأشياء التي تنكسر **بصمت** على الهواء:

- **الرموز المفقودة** — الخطوط العربية لا تحتوي حروفًا لاتينية ولا `·` `—` `…` `|`،
  فأي نص مختلط كان يظهر مربعات فارغة. الآن يُختار الخط حسب تغطيته الفعلية
  للنص (Noto للعربي الصرف، وDejaVu — الذي يغطي اللغتين — لما عداه).
- **اتجاه العربي** — التأكد أن أول كلمة تقع في أقصى اليمين.
- **الأبعاد** — الرسم على `854×480` و`720p` و`1080p` ومع دليل فارغ.
- **مسار الإطار السريع** — أن الثانية الواحدة تُعيد رسم الساعة فقط.

---

## 🔧 حل المشاكل

| العَرَض | السبب والحل |
|---|---|
| القناة سوداء أو لا تفتح | تأكد أن `ffmpeg` مثبّت: `ffmpeg -version` |
| مربعات فارغة مكان النص | خطوط ناقصة: `sudo apt install fonts-dejavu-core` |
| العربي مقلوب | Pillow مبني بدون Raqm — ثبّت `arabic-reshaper` و`python-bidi` |
| تظهر داخل الشبكة فقط | طبيعي — راجع الخيار (ب) أو نفق Cloudflare |
| `Address already in use` | غيّر المنفذ: `--port 8090` |
| تقطيع في البث | قلّل الحمل: `--fps 4 --bitrate 500 --preset ultrafast` |
| لا تظهر مباريات | جرّب `--all-programmes`، أو تحقق أن `--epg` صحيح |

مراقبة السجل عند التشغيل كخدمة:

```bash
journalctl -u mena-info -f
```

---

## 📁 الملفات

| الملف | الوظيفة |
|---|---|
| `stream.py` | التشغيل الرئيسي: ffmpeg + HLS + خادم الويب + M3U |
| `renderer.py` | رسم الشاشة (البطاقات، الساعة، الصفحات) |
| `epg_source.py` | قراءة XMLTV وتحديثه في الخلفية |
| `theme.py` | الألوان والخطوط وتغطية الرموز |
| `test_render.py` | فحوصات الرسم |
| `mena-info.service` | وحدة systemd |
| `Dockerfile` | صورة جاهزة |

---

## ⚖️ ملاحظة

هذه القناة تعرض **بيانات دليل البرامج فقط** — لا تبث أي محتوى رياضي ولا
تعيد بث أي قناة. الأسماء والعلامات التجارية تعود لأصحابها.
