package com.saudi.privatevault

/**
 * Gemini writes formulas in LaTeX ($L = \frac{1}{2}\rho V^2 S C_L$); a phone shows them as typed.
 * This turns them into plain mathematics a pilot reads at a glance (L = ½ · ρ · V² · S · C_L), each
 * formula kept as one left-to-right island so an Arabic line around it stays in its order.
 */
object MathText {
    private const val LRI = '⁦'
    private const val PDI = '⁩'

    private val GREEK = mapOf(
        "alpha" to "α", "beta" to "β", "gamma" to "γ", "delta" to "δ", "Delta" to "Δ", "epsilon" to "ε", "varepsilon" to "ε",
        "theta" to "θ", "lambda" to "λ", "mu" to "μ", "pi" to "π", "rho" to "ρ", "sigma" to "σ", "Sigma" to "Σ", "tau" to "τ",
        "phi" to "φ", "varphi" to "φ", "omega" to "ω", "Omega" to "Ω", "eta" to "η", "nu" to "ν", "psi" to "ψ", "Phi" to "Φ",
    )
    private val SYMBOLS = mapOf(
        "cdot" to "·", "times" to "×", "div" to "÷", "pm" to "±", "approx" to "≈", "neq" to "≠", "ne" to "≠", "leq" to "≤", "le" to "≤",
        "geq" to "≥", "ge" to "≥", "infty" to "∞", "degree" to "°", "circ" to "°", "rightarrow" to "→", "to" to "→", "Rightarrow" to "⇒",
        "leftarrow" to "←", "propto" to "∝", "sqrt" to "√", "partial" to "∂", "sum" to "Σ", "quad" to "  ", "qquad" to "    ", "," to " ", ";" to " ", "!" to "",
        "%" to "%", "left" to "", "right" to "", "big" to "", "Big" to "", "displaystyle" to "", "%" to "%",
    )
    private val SUP = mapOf('0' to '⁰', '1' to '¹', '2' to '²', '3' to '³', '4' to '⁴', '5' to '⁵', '6' to '⁶', '7' to '⁷', '8' to '⁸', '9' to '⁹', '-' to '⁻', '+' to '⁺', 'n' to 'ⁿ')
    private val SUB = mapOf('0' to '₀', '1' to '₁', '2' to '₂', '3' to '₃', '4' to '₄', '5' to '₅', '6' to '₆', '7' to '₇', '8' to '₈', '9' to '₉')

    /** The whole answer: each formula (inline or display) made readable; the rest left alone. */
    fun clean(src: String): String {
        var s = src
        // Display maths first ($$…$$ and \[…\]), then inline ($…$ and \(…\)).
        s = Regex("\\$\\$([\\s\\S]+?)\\$\\$").replace(s) { "\n" + island(it.groupValues[1].trim()) + "\n" }
        s = Regex("\\\\\\[([\\s\\S]+?)\\\\\\]").replace(s) { "\n" + island(it.groupValues[1].trim()) + "\n" }
        s = Regex("\\\\\\((.+?)\\\\\\)").replace(s) { island(it.groupValues[1]) }
        // A single $ … $ on one line, not a price ("$5" alone stays).
        s = Regex("(?<![\\\\\\w])\\$(?!\\s)([^$\\n]{1,200}?)(?<!\\s)\\$(?!\\d)").replace(s) { m ->
            val body = m.groupValues[1]
            if (body.any { it == '\\' || it == '_' || it == '^' || it == '=' } || body.length <= 3) island(body) else m.value
        }
        // LaTeX outside any $: commands written bare.
        if (s.contains('\\')) s = Regex("\\\\(frac|rho|alpha|beta|theta|cdot|times|sqrt|approx|Delta|mu|pi|sigma|omega|leq|geq|text)\\b[^\\n]*").replace(s) { m ->
            island(m.value)
        }
        return s.replace(Regex("\n{3,}"), "\n\n")
    }

    private fun island(tex: String) = LRI + plain(tex).trim() + PDI

    /** One formula, LaTeX to plain text. */
    fun plain(tex: String): String {
        var s = tex
        // \text{...}, \mathrm{...}, \operatorname{...} → their words.
        s = Regex("\\\\(?:text|mathrm|mathbf|mathit|operatorname|textbf|rm|bf)\\s*\\{([^{}]*)\\}").replace(s) { it.groupValues[1] }
        // \frac{a}{b} → a/b (parenthesised when they are more than one thing); nested, from the inside out.
        val frac = Regex("\\\\[dt]?frac\\s*\\{([^{}]*)\\}\\s*\\{([^{}]*)\\}")
        repeat(6) { s = frac.replace(s) { m -> half(m.groupValues[1], m.groupValues[2]) } }
        s = Regex("\\\\sqrt\\s*\\{([^{}]*)\\}").replace(s) { "√(" + it.groupValues[1] + ")" }
        // Powers and indices.
        s = Regex("\\^\\{([^{}]*)\\}").replace(s) { sup(it.groupValues[1]) }
        s = Regex("\\^(\\w)").replace(s) { sup(it.groupValues[1]) }
        s = Regex("_\\{([^{}]*)\\}").replace(s) { sub(it.groupValues[1]) }
        s = Regex("_(\\w)").replace(s) { sub(it.groupValues[1]) }
        // Commands: Greek, symbols, anything else dropped to its name.
        s = Regex("\\\\([A-Za-z]+|[,;!%])").replace(s) { m -> val n = m.groupValues[1]; GREEK[n] ?: SYMBOLS[n] ?: n }
        s = s.replace("{", "").replace("}", "").replace("\\", "")
        s = s.replace(Regex("\\s*=\\s*"), " = ").replace(Regex("[ \\t]{2,}"), " ")
        return s
    }

    private fun half(a: String, b: String): String {
        if (a.trim() == "1" && b.trim() == "2") return "½"
        if (a.trim() == "1" && b.trim() == "4") return "¼"
        if (a.trim() == "3" && b.trim() == "4") return "¾"
        fun g(x: String) = x.trim().let { if (it.length > 1 && it.any { c -> c in " +-·×" }) "($it)" else it }
        return g(a) + "/" + g(b)
    }

    private fun sup(x: String) = if (x.all { it in SUP }) x.map { SUP[it] }.joinToString("") else "^($x)"
    private fun sub(x: String) = if (x.all { it in SUB }) x.map { SUB[it] }.joinToString("") else "_$x"
}
