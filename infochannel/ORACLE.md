# ☁️ التشغيل على Oracle Cloud — مجاني للأبد

سيرفر يشتغل 24/7 بدون أي جهاز عندك، ورابط تفتحه من أي مكان.
**كل الخطوات من متصفح جوالك** — ما تحتاج كمبيوتر ولا SSH.

---

## ⚠️ قبل ما تبدأ

كود القناة حاليًا على فرع `claude/sports-streaming-platform-e4xf26` وليس على
`main`. سكربت الإعداد يسحب من `main`، فلازم تدمج الفرع أولًا:

افتح المستودع على GitHub ← `Pull requests` ← ادمج الفرع في `main`.

*(أو غيّر سطر `git clone` في السكربت وأضف `--branch claude/sports-streaming-platform-e4xf26`)*

---

## 1️⃣ أنشئ الحساب

اذهب إلى **cloud.oracle.com** ← `Start for free`

| الحقل | ماذا تختار |
|---|---|
| Home Region | الأقرب لك — **Saudi Arabia Central (Riyadh)** أو **UAE East (Dubai)** |
| البطاقة | للتحقق من الهوية فقط — لا يوجد خصم |

> ⚠️ المنطقة **لا يمكن تغييرها لاحقًا**، فاخترها بعناية.

بعد التسجيل، تأكد أن الحساب **Always Free** وليس تجربة مدفوعة.

---

## 2️⃣ أنشئ السيرفر

القائمة (☰) ← `Compute` ← `Instances` ← **`Create instance`**

| الإعداد | القيمة |
|---|---|
| Name | `mena-info` |
| Image | `Canonical Ubuntu 24.04` |
| Shape | `VM.Standard.A1.Flex` — **1 OCPU / 6 GB** |
| Public IPv4 address | ✅ Assign |
| SSH keys | `No SSH keys` (السكربت يسوي كل شي) |

> 💡 إذا ظهر خطأ **"Out of host capacity"** فمعناه أن أجهزة ARM ممتلئة حاليًا.
> اختر بدلها `VM.Standard.E2.1.Micro` — أضعف لكنها تكفي هذي القناة تمامًا،
> ومتوفرة دائمًا.

**تأكد أن الشكل مكتوب عليه `Always Free-eligible`** قبل الإنشاء.

---

## 3️⃣ الصق سكربت الإعداد ⭐ الخطوة المهمة

في نفس صفحة الإنشاء:

`Show advanced options` ← تبويب `Management` ← `Initialization script`
← اختر **`Paste cloud-init script`**

الصق محتوى الملف [`oracle-cloud-init.yaml`](oracle-cloud-init.yaml) كاملًا.

هذا السكربت يركّب ffmpeg والخطوط والبرنامج، ويفتح المنفذ، ويشغّل القناة
كخدمة تعمل تلقائيًا عند كل إقلاع — بدون أي تدخل منك.

ثم اضغط **`Create`**.

---

## 4️⃣ افتح المنفذ في الشبكة

السكربت يفتح جدار الجهاز، لكن **شبكة Oracle لها جدار منفصل** لازم تفتحه يدويًا:

القائمة (☰) ← `Networking` ← `Virtual Cloud Networks` ← اختر الشبكة
← `Subnets` ← اختر الـ subnet ← `Security Lists` ← `Default Security List`
← **`Add Ingress Rules`**

| الحقل | القيمة |
|---|---|
| Source CIDR | `0.0.0.0/0` |
| IP Protocol | `TCP` |
| Destination Port Range | `8080` |

اضغط `Add Ingress Rules`.

> 🔓 هذا يجعل القناة مفتوحة لأي أحد يعرف عنوان السيرفر. المحتوى مجرد
> مواعيد مباريات (لا بيانات شخصية)، لكن انتبه أن الاستهلاك يُحسب عليك.

---

## 5️⃣ خذ الرابط

ارجع إلى `Compute` ← `Instances` ← `mena-info` وانسخ **Public IP address**.

انتظر **~4 دقائق** بعد الإنشاء (يركّب الحزم)، ثم رابطك:

```
http://<PUBLIC_IP>:8080/playlist.m3u
```

للتأكد أنه يعمل: افتح `http://<PUBLIC_IP>:8080/info.m3u8` في متصفح جوالك —
المفروض ينزّل ملف نصي يبدأ بـ `#EXTM3U`.

---

## 6️⃣ أضفه في TiviMate

على الـ Google TV Streamer:

```
Settings ← Playlists ← Add playlist ← Enter URL
```

الصق الرابط ← `Next` ← سمّها `Info` ← `Done`

تظهر القناة باسم **MENA SPORTS INFO** في مجموعة `INFO`.

> ⚠️ TiviMate المجاني يسمح بقائمة تشغيل **واحدة** فقط. إذا عندك اشتراك مضاف
> أصلًا فتحتاج TiviMate Premium، أو استخدم مشغّلًا يسمح بعدة قوائم مثل
> IBO Player أو XCIPTV.

---

## 📊 الاستهلاك مقابل الحد المجاني

| البند | الاستهلاك | الحد المجاني |
|---|---|---|
| المعالج | ~1% من نواة | 4 أنوية ARM |
| الذاكرة | ~60 ميجابايت | 24 جيجابايت |
| النقل الصادر | ~9.7 جيجا/يوم لكل مشاهد متواصل | **10 تيرابايت/شهر** |

يعني 10 تيرابايت تكفي **~34 مشاهدًا متواصلين 24 ساعة**. لاستخدامك الشخصي
لن تقترب من الحد إطلاقًا.

> ✅ Oracle تسترجع أجهزة **الخاملة** في الطبقة المجانية. قناتك تبث باستمرار،
> فهي ليست خاملة ولن تُسترجع.

لتقليل الاستهلاك أكثر، عدّل `ExecStart` في الخدمة:

```
--width 854 --height 480 --bitrate 500
```

---

## 🔧 إذا ما اشتغلت

افتح **Cloud Shell** من أعلى يمين لوحة Oracle (أيقونة `>_`) — طرفية داخل
المتصفح، تشتغل من الجوال:

```bash
# هل الخدمة شغالة؟
sudo systemctl status mena-info

# السجل
sudo journalctl -u mena-info -n 50

# هل السكربت التلقائي نجح؟
sudo cat /var/log/cloud-init-output.log | tail -40
```

| العَرَض | الحل |
|---|---|
| الرابط لا يفتح إطلاقًا | الخطوة 4️⃣ (Security List) غير مكتملة |
| يفتح لكن بدون صورة | انتظر 4 دقائق، أو راجع `journalctl` |
| `Out of host capacity` | استخدم `VM.Standard.E2.1.Micro` |
| القناة تتوقف بعد فترة | `sudo systemctl status mena-info` — المفروض `Restart=always` يعالجها |

---

## 🔄 التحديث لاحقًا

السكربت يثبّت مؤقّتًا يسحب آخر تحديث من GitHub **أسبوعيًا** ويعيد التشغيل
تلقائيًا. للتحديث فورًا من Cloud Shell:

```bash
sudo -u mena git -C /opt/mena-info pull
sudo systemctl restart mena-info
```
