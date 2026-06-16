(function () {
    const MESSAGE = "El texto ingresado contiene lenguaje no permitido. Corrige el contenido para continuar.";

    const TERMS = [
        "conchatumadre", "ctm", "conchasumadre", "csm", "culiao", "culiado", "ql", "qla",
        "maraco", "maraca", "maricon", "chucha", "chuchatumadre",
        "weon", "weona", "huevon", "huevona", "wn", "wna", "aweonao", "aweonado", "aweona",
        "saco de weas", "sdw", "sacowea",
        "pico", "tula", "zorra", "poto", "raja", "tetas",
        "pelotudo", "aganao", "pajero", "pajera", "sarnoso", "cuma", "flaite", "flite",
        "perkin", "sapo", "bastardo",
        "idiot", "stupid", "asshole", "fuck", "shit", "bitch", "bastard", "dumb", "moron",
        "whore", "slut"
    ];

    const ALLOW_PHRASES = {
        pico: ["pico truncado", "pico y pala", "pico de loro"]
    };

    function normalizeText(text, oneReplacement) {
        return String(text || "")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .toLowerCase()
            .replace(/0/g, "o")
            .replace(/1/g, oneReplacement)
            .replace(/[!|]/g, "i")
            .replace(/3/g, "e")
            .replace(/4/g, "a")
            .replace(/5/g, "s")
            .replace(/7/g, "t")
            .replace(/[^a-z0-9]+/g, " ")
            .replace(/\s+/g, " ")
            .trim();
    }

    function variants(text) {
        return [normalizeText(text, "i"), normalizeText(text, "l")];
    }

    function compact(text) {
        return text.replace(/[^a-z0-9]+/g, "");
    }

    function containsTerm(value, term) {
        const normalizedTerm = normalizeText(term, "i");
        const compactTerm = compact(normalizedTerm);
        return variants(value).some((normalized) => {
            const allowed = ALLOW_PHRASES[term] || [];
            if (allowed.some((phrase) => normalized.includes(normalizeText(phrase, "i")))) {
                return false;
            }
            if (normalizedTerm.includes(" ")) {
                return normalized.includes(normalizedTerm) || compact(normalized).includes(compactTerm);
            }
            const wordMatch = new RegExp(`(^|[^a-z0-9])${normalizedTerm.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}([^a-z0-9]|$)`).test(normalized);
            return wordMatch || compact(normalized).includes(compactTerm);
        });
    }

    function containsProhibitedLanguage(value) {
        return TERMS.some((term) => containsTerm(value, term));
    }

    function isTextualField(field) {
        if (!field || field.disabled || field.readOnly) return false;
        if (field.matches("[data-content-filter-ignore]")) return false;
        if (field.tagName === "TEXTAREA") return true;
        if (field.tagName !== "INPUT") return false;
        const type = (field.getAttribute("type") || "text").toLowerCase();
        return ["text", "search"].includes(type);
    }

    function showMessage() {
        if (typeof window.dartToast === "function") {
            window.dartToast(MESSAGE, "error");
            return;
        }
        alert(MESSAGE);
    }

    document.addEventListener("submit", function (event) {
        const form = event.target;
        if (!(form instanceof HTMLFormElement)) return;
        const fields = Array.from(form.querySelectorAll("input, textarea")).filter(isTextualField);
        const blocked = fields.find((field) => containsProhibitedLanguage(field.value));
        if (!blocked) return;
        event.preventDefault();
        event.stopPropagation();
        showMessage();
        blocked.focus({ preventScroll: true });
        blocked.scrollIntoView({ behavior: "smooth", block: "center" });
    }, true);
})();
