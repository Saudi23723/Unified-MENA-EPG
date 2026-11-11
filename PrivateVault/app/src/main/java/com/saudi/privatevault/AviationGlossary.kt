package com.saudi.privatevault

/**
 * The app's own aviation dictionary, English to Arabic, used by the captions: a term the general
 * translator gets wrong is put in its aviation Arabic first, with the English kept beside it.
 */
object AviationGlossary {
    val TERMS: Map<String, String> = linkedMapOf(
        "angle of attack" to "زاوية الهجوم", "traffic pattern" to "دائرة المطار", "downwind" to "الضلع المعاكس للريح",
        "base leg" to "الضلع الأساسي", "final approach" to "الاقتراب النهائي", "crosswind" to "ريح جانبية",
        "touch and go" to "لمس وإقلاع", "go around" to "إعادة المحاولة", "go-around" to "إعادة المحاولة",
        "slow flight" to "الطيران البطيء", "steep turn" to "الانعطاف الحاد", "steep turns" to "الانعطافات الحادة",
        "power off stall" to "انهيار بدون قدرة", "power on stall" to "انهيار مع قدرة", "stall" to "انهيار",
        "spin" to "دوران لولبي", "airspeed" to "السرعة الجوية", "altimeter" to "مقياس الارتفاع",
        "attitude indicator" to "مؤشر الوضعية", "heading indicator" to "مؤشر الاتجاه", "turn coordinator" to "منسق الانعطاف",
        "vertical speed indicator" to "مؤشر السرعة العمودية", "flaps" to "القلابات", "aileron" to "الجنيح", "ailerons" to "الجنيحات",
        "elevator" to "الرافع", "rudder" to "الدفة", "trim" to "الموازنة", "throttle" to "مقبض القدرة", "mixture" to "الخليط",
        "carburetor heat" to "تسخين المكربن", "magneto" to "المغناطيسي", "pitot tube" to "أنبوب بيتو", "static port" to "المنفذ الساكن",
        "lift" to "قوة الرفع", "drag" to "قوة السحب", "thrust" to "قوة الدفع", "weight and balance" to "الوزن والاتزان",
        "center of gravity" to "مركز الثقل", "density altitude" to "الارتفاع الكثافي", "pressure altitude" to "الارتفاع الضغطي",
        "runway" to "المدرج", "taxiway" to "ممر التدرج", "taxi" to "التدرج", "takeoff" to "الإقلاع", "landing" to "الهبوط",
        "flare" to "التسوية", "climb" to "الصعود", "descent" to "الهبوط التدريجي", "cruise" to "الطيران المستوي",
        "preflight" to "الفحص قبل الطيران", "checklist" to "قائمة التحقق", "clearance" to "التصريح", "tower" to "البرج",
        "ground control" to "المراقبة الأرضية", "approach control" to "مراقبة الاقتراب", "squawk" to "رمز المرسل",
        "transponder" to "المرسل المجيب", "airspace" to "المجال الجوي", "class bravo" to "المجال الجوي B", "class charlie" to "المجال الجوي C",
        "class delta" to "المجال الجوي D", "visibility" to "الرؤية", "ceiling" to "سقف الغيوم", "turbulence" to "المطبات الهوائية",
        "wind shear" to "قص الرياح", "icing" to "التجمد", "fuel" to "الوقود", "propeller" to "المروحة", "engine" to "المحرك",
        "yoke" to "عصا التحكم", "stick" to "عصا التحكم", "slip" to "الانزلاق", "forward slip" to "الانزلاق الأمامي",
        "coordinated" to "منسق", "uncoordinated" to "غير منسق", "load factor" to "عامل الحمل", "student pilot" to "الطالب الطيار",
        "instructor" to "المدرب", "solo" to "منفرد",
    )

    // One pass over every term, longest first, so "power off stall" is never touched again as "stall".
    private val ALL by lazy { Regex("(?i)\\b(" + TERMS.keys.sortedByDescending { it.length }.joinToString("|") { Regex.escape(it) } + ")\\b") }

    /** The terms in a line replaced by tokens the translator leaves alone (ZQ0, ZQ1…), and what each stands for. */
    fun protect(english: String): Pair<String, List<String>> {
        val found = ArrayList<String>()
        val out = ALL.replace(english) { m -> TERMS[m.value.lowercase()]?.let { found.add(it + " (" + m.value + ")"); "ZQ" + (found.size - 1) } ?: m.value }
        return out to found
    }

    /** The tokens put back as "Arabic (English)"; null when the translator lost one. */
    fun restore(arabic: String, found: List<String>): String? {
        var s = arabic
        for ((i, t) in found.withIndex()) { if (!s.contains("ZQ$i")) return null; s = s.replace("ZQ$i", t) }
        return s
    }

    /** "slow flight" → "الطيران البطيء (slow flight)". */
    fun mark(english: String): String = ALL.replace(english) { m -> (TERMS[m.value.lowercase()] ?: return@replace m.value) + " (" + m.value + ")" }
}
