"""Vocabulary for the major scientific-publishing languages.

The audit started with English and Turkish terms. A manuscript is not obliged to
be written in either, and a rule that silently does nothing on a Spanish or
Japanese paper is worse than no rule: the report looks clean. This module holds
the terms for the languages that publish most of the literature, so the existing
rules can recognise them.

Scope is deliberate: only vocabulary the rules already use — section headings,
increase/decrease, absolute wording, association, causal verbs, multiplicity
correction, group counts, rate ratios, paired designs and test names. Nothing here
adds a rule, and nothing here guesses semantics: a term is listed only when it is
the standard word for that concept in the language.
"""

from __future__ import annotations

import re

#: Section headings. Matching is a prefix test on the normalised heading, so it
#: works for scripts without word separators as well.
SECTIONS: dict[str, tuple[str, ...]] = {
    "methods": (
        "métodos", "metodos", "materiales y métodos", "metodología", "metodologia",
        "méthodes", "matériel et méthodes", "methoden", "material und methoden",
        "metodi", "materiali e metodi", "methoden en materialen",
        "методы", "материалы и методы", "metody", "materiały i metody",
        "metode", "bahan dan metode", "الطرق", "المنهجية",
        "विधियाँ", "विधि", "方法", "实验方法", "手法", "방법", "연구방법",
    ),
    "results": (
        "resultados", "résultats", "ergebnisse", "risultati", "resultaten",
        "результаты", "wyniki", "hasil", "النتائج", "परिणाम", "结果", "結果", "결과",
    ),
    "conclusion": (
        "conclusión", "conclusión y discusión", "conclusões", "conclusão",
        "conclusion", "discussion", "schlussfolgerung", "diskussion",
        "conclusione", "discussione", "conclusie", "discussie",
        "выводы", "обсуждение", "wnioski", "dyskusja", "kesimpulan", "pembahasan",
        "الاستنتاج", "المناقشة", "निष्कर्ष", "结论", "讨论", "結論", "考察", "결론", "고찰",
    ),
    "limitations": (
        "limitaciones", "limitações", "limites", "limitationen", "einschränkungen",
        "limiti", "beperkingen", "ограничения", "ograniczenia", "keterbatasan",
        "القيود", "सीमाएँ", "局限性", "研究局限", "限界", "한계",
    ),
    "references": (
        "referencias", "referências", "références", "literaturverzeichnis",
        "literatur", "riferimenti", "bibliografia", "referenties",
        "литература", "список литературы", "piśmiennictwo", "referensi", "daftar pustaka",
        "المراجع", "संदर्भ", "参考文献", "參考文獻", "참고문헌",
    ),
}

#: Outcome direction. ``\b`` does not work around CJK characters, so those terms
#: are matched as plain substrings and kept unambiguous (升/増/증 only mean "rise").
INCREASE_LATIN: tuple[str, ...] = (
    "aumentó", "aumento", "aumentaron", "incrementó", "incremento", "mayor",
    "aumentou", "aumentaram", "maior",
    "augmentation", "augmenté", "augmenta", "supérieur", "plus élevé",
    "erhöht", "erhöhte", "anstieg", "höher", "gestiegen",
    "aumentato", "aumentata", "aumento", "maggiore", "più alto",
    "toegenomen", "steeg", "hoger",
    "увеличился", "увеличилась", "возрос", "возросла", "выше",
    "wzrósł", "wzrosła", "zwiększył", "wyższy",
    "meningkat", "naik", "lebih tinggi",
    "ارتفع", "ارتفعت", "زاد", "أعلى",
)
INCREASE_CJK: tuple[str, ...] = (
    "升高", "增加", "上升", "增高", "上昇", "増加", "증가", "상승", "높았",
    "बढ़ा", "बढ़ी", "वृद्धि", "अधिक",
)

DECREASE_LATIN: tuple[str, ...] = (
    "disminuyó", "disminuyeron", "redujo", "reducción", "menor",
    "diminuiu", "reduziu", "menor",
    "diminution", "diminué", "réduit", "inférieur", "plus faible",
    "verringert", "sank", "niedriger", "reduziert",
    "diminuito", "ridotto", "minore", "più basso",
    "afgenomen", "daalde", "lager",
    "уменьшился", "уменьшилась", "снизился", "снизилась", "ниже",
    "spadł", "spadła", "zmniejszył", "niższy",
    "menurun", "turun", "lebih rendah",
    "انخفض", "انخفضت", "قل", "أقل",
)
DECREASE_CJK: tuple[str, ...] = (
    "降低", "减少", "下降", "减低", "低下", "減少", "감소", "하락", "낮았",
    "घटा", "घटी", "कमी", "कम",
)

#: Absolute or conclusive wording.
ABSOLUTE: tuple[str, ...] = (
    "prueba de forma concluyente", "demuestra definitivamente", "prueba que",
    "prova de forma conclusiva", "demonstra definitivamente",
    "prouve de manière concluante", "démontre définitivement",
    "beweist schlüssig", "beweist eindeutig",
    "dimostra in modo conclusivo", "prova definitivamente",
    "bewijst overtuigend", "toont definitief aan",
    "доказывает окончательно", "доказывает убедительно",
    "dowodzi ostatecznie", "dowodzi jednoznacznie",
    "membuktikan secara meyakinkan", "terbukti secara pasti",
    "يثبت بشكل قاطع", "يثبت نهائيا",
    "निर्णायक रूप से सिद्ध करता है", "निश्चित रूप से सिद्ध",
    "确凿地证明", "彻底证明", "完全に証明", "確実に証明", "확실히 입증", "완전히 증명",
)

#: Association wording.
ASSOCIATION: tuple[str, ...] = (
    "asociado con", "asociada con", "correlación", "relación entre",
    "associado a", "associada a", "correlação", "relação entre",
    "associé à", "associée à", "corrélation", "relation entre",
    "assoziiert mit", "korreliert", "zusammenhang zwischen",
    "associato a", "associata a", "correlazione",
    "geassocieerd met", "gecorreleerd", "verband tussen",
    "связан с", "связана с", "корреляция", "связь между",
    "związany z", "związana z", "korelacja", "związek między",
    "berhubungan dengan", "berkorelasi", "hubungan antara",
    "مرتبط ب", "ارتباط", "علاقة بين",
    "से जुड़ा", "सहसंबंध", "संबंध",
    "相关", "相關", "相关性", "相関", "関連", "관련", "상관",
)

#: Causal verbs that the audit treats as claiming causation.
CAUSAL: tuple[str, ...] = (
    "causa", "causó", "provoca", "provocó", "conduce a",
    "causou", "provocou", "leva a",
    "cause", "provoque", "entraîne", "conduit à",
    "verursacht", "führt zu", "bewirkt",
    "causa", "provoca", "porta a",
    "veroorzaakt", "leidt tot",
    "вызывает", "приводит к",
    "powoduje", "prowadzi do",
    "menyebabkan", "mengakibatkan",
    "يسبب", "يؤدي إلى",
    "कारण बनता है", "के कारण",
    "导致", "導致", "引起", "引き起こす", "原因となる", "초래", "야기",
)

#: Multiplicity corrections.
CORRECTION: tuple[str, ...] = (
    "comparaciones múltiples", "corrección de bonferroni", "ajuste",
    "comparações múltiplas", "correção",
    "comparaisons multiples", "correction de bonferroni", "ajustement",
    "multiples vergleiche", "mehrfachvergleich", "korrektur",
    "confronti multipli", "correzione",
    "meervoudige vergelijking", "correctie",
    "множественные сравнения", "поправка",
    "porównania wielokrotne", "korekta",
    "perbandingan berganda", "koreksi",
    "مقارنات متعددة", "تصحيح",
    "बहु तुलना", "सुधार",
    "多重比较", "多重比較", "多重比較補正", "다중 비교", "다중비교",
)

#: Formally recognised test names, which the audit already treats as adjusting.
CORRECTION_PROPER_NOUNS: tuple[str, ...] = (
    "bonferroni", "holm", "sidak", "šidák", "tukey", "scheffé", "scheffe",
    "dunnett", "benjamini", "hochberg", "fdr", "false discovery",
)

#: Wording that describes a paired or repeated-measures design.
PAIRED_DESIGN: tuple[str, ...] = (
    "diseño apareado", "medidas repetidas", "antes y después", "emparejado",
    "desenho pareado", "medidas repetidas", "antes e depois", "emparelhado",
    "apparié", "mesures répétées", "avant et après",
    "gepaart", "verbunden", "messwiederholung", "vorher und nachher",
    "appaiato", "misure ripetute", "prima e dopo",
    "gepaard", "herhaalde metingen", "voor en na",
    "парный", "повторные измерения", "до и после",
    "powiązane", "pomiary powtarzane", "przed i po",
    "berpasangan", "pengukuran berulang", "sebelum dan sesudah",
    "مزدوج", "قياسات متكررة", "قبل وبعد",
    "युग्मित", "दोहराए गए माप", "पहले और बाद",
    "配对", "配對", "重复测量", "前後比較", "対応のある", "반복 측정", "대응",
)

#: Test names that assume independent groups.
INDEPENDENT_TEST: tuple[str, ...] = (
    "t student independiente", "prueba t independiente", "test t de muestras independientes",
    "teste t independente", "teste t para amostras independentes",
    "test t indépendant", "test t pour échantillons indépendants",
    "unabhängiger t-test", "t-test für unabhängige stichproben",
    "test t per campioni indipendenti",
    "onafhankelijke t-toets", "t-toets voor onafhankelijke",
    "критерий стьюдента для независимых", "t-критерий для независимых",
    "test t dla prób niezależnych",
    "uji t independen", "uji t dua sampel bebas",
    "اختبار t للعينات المستقلة",
    "स्वतंत्र नमूना t परीक्षण",
    "独立样本", "獨立樣本", "対応のないt検定", "독립표본",
)

#: Test names for paired data, whose presence clears the mismatch signal.
PAIRED_TEST: tuple[str, ...] = (
    "prueba t apareada", "t pareada", "rangos de wilcoxon",
    "teste t pareado", "teste de wilcoxon",
    "test t apparié", "test de wilcoxon",
    "t-test für gepaarte", "gepaarter t-test", "wilcoxon-vorzeichen",
    "test t appaiato", "wilcoxon per ranghi",
    "gepaarde t-toets", "wilcoxon rangtekentoets",
    "парный t-критерий", "критерий уилкоксона",
    "test t dla prób zależnych", "test wilcoxona",
    "uji t berpasangan", "uji wilcoxon",
    "اختبار t المزدوج", "اختبار ويلكوكسون",
    "युग्मित t परीक्षण", "विलकॉक्सन",
    "配对 t 检验", "配對t檢定", "対応のあるt検定", "대응표본", "윌콕슨",
)

#: How many groups a sentence says it compares.
GROUP_COUNT: tuple[str, ...] = (
    "tres grupos", "cuatro grupos", "cinco grupos", "seis grupos",
    "três grupos", "quatro grupos", "cinco grupos", "seis grupos",
    "trois groupes", "quatre groupes", "cinq groupes", "six groupes",
    "drei gruppen", "vier gruppen", "fünf gruppen", "sechs gruppen",
    "tre gruppi", "quattro gruppi", "cinque gruppi", "sei gruppi",
    "drie groepen", "vier groepen", "vijf groepen", "zes groepen",
    "три группы", "четыре группы", "пять групп", "шесть групп",
    "trzy grupy", "cztery grupy", "pięć grup", "sześć grup",
    "tiga kelompok", "empat kelompok", "lima kelompok", "enam kelompok",
    "ثلاث مجموعات", "أربع مجموعات", "خمس مجموعات", "ست مجموعات",
    "तीन समूह", "चार समूह", "पाँच समूह", "छह समूह",
    "三组", "三組", "四组", "四組", "五组", "五組", "六组", "六組",
    "3群", "4群", "5群", "6群", "세 그룹", "네 그룹", "다섯 그룹", "여섯 그룹",
)


#: Words that introduce a reported mean, for the mean-versus-interval check.
MEAN_WORD: tuple[str, ...] = (
    "media", "promedio", "média", "moyenne", "mittelwert", "mittel", "media",
    "gemiddelde", "среднее", "średnia", "rata-rata", "المتوسط", "औसत", "平均", "평균",
)

#: Words that introduce a difference or an effect, which makes a confidence
#: interval comparable with a p-value.
CONTRAST: tuple[str, ...] = (
    "diferencia", "efecto", "aumento", "disminución",
    "diferença", "efeito", "aumento", "redução",
    "différence", "effet", "augmentation", "diminution",
    "unterschied", "effekt", "anstieg", "rückgang",
    "differenza", "effetto", "aumento", "riduzione",
    "verschil", "effect", "toename", "afname",
    "разница", "эффект", "рост", "снижение",
    "różnica", "efekt", "wzrost", "spadek",
    "perbedaan", "efek", "kenaikan", "penurunan",
    "فرق", "تأثير", "زيادة", "انخفاض",
    "अंतर", "प्रभाव", "वृद्धि", "कमी",
    "差异", "差异", "效应", "增幅", "降幅", "差", "効果", "増加", "減少", "차이", "효과", "증가", "감소",
)

#: Ratio-style effect measures, whose null value is 1 rather than 0.
RATIO_STATEMENT: tuple[str, ...] = (
    "razón de momios", "razón de riesgo", "cociente de riesgos",
    "razão de chances", "razão de risco",
    "rapport de cotes", "rapport de risque", "risque relatif",
    "odds ratio", "risikoverhältnis", "relatives risiko",
    "rapporto di probabilità", "rischio relativo",
    "oddsratio", "relatief risico",
    "отношение шансов", "отношение рисков", "относительный риск",
    "iloraz szans", "ryzyko względne",
    "rasio odds", "risiko relatif",
    "نسبة الأرجحية", "نسبة الخطر",
    "ऑड्स अनुपात", "सापेक्ष जोखिम",
    "比值比", "相对风险", "優勢比", "相対リスク", "교차비", "상대 위험",
)


def _latin_alternation(terms: tuple[str, ...]) -> str:
    """Regex alternation for space-separated scripts, with word boundaries."""
    return "|".join(rf"\b{re.escape(term)}\w*\b" for term in terms)


def _script_alternation(terms: tuple[str, ...]) -> str:
    """Regex alternation for scripts without word boundaries."""
    return "|".join(re.escape(term) for term in terms)


def phrase_pattern(terms: tuple[str, ...]) -> str:
    """Alternation usable inside a larger regex, boundaries chosen per script."""
    return "|".join(re.escape(term) for term in terms)


def direction_patterns() -> tuple[str, str]:
    """(increase, decrease) alternations covering every listed language."""
    increase = "|".join(
        filter(None, [_latin_alternation(INCREASE_LATIN), _script_alternation(INCREASE_CJK)])
    )
    decrease = "|".join(
        filter(None, [_latin_alternation(DECREASE_LATIN), _script_alternation(DECREASE_CJK)])
    )
    return increase, decrease
