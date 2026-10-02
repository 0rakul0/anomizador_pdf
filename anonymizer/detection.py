"""Detection only: offsets always refer to the supplied, unmodified text."""
from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class Entity:
    start: int
    end: int
    kind: str
    source: str


PATTERNS = {
    "CPF": r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)",
    "EMAIL": r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
    "TELEFONE": r"(?<!\d)(?:\+55\s*)?\(?[1-9]\d\)?[ .-]*9?\d{4}[ .-]*\d{4}(?!\d)",
    "PLACA": r"\b[A-Z]{3}[- ]?\d[A-Z0-9]\d{2}\b",
    "RG": r"\bRG\s*[:=]?\s*(?P<value>\d[\d. -]{4,18}[\dXx])\b",
    "ENDERECO": r"\b(?:endere[çc]o|resid[eê]ncia)\s*[:=]\s*(?P<value>[^\n;]+)",
    "NASCIMENTO": r"\b(?:nascimento|nasc\.)\s*[:=]?\s*(?P<value>\d{2}[/.-]\d{2}[/.-]\d{4})",
}


def identity(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


class Detector:
    def __init__(self, model="pt_core_news_lg", names=(), nlp=None):
        if nlp is None:
            import spacy
            try:
                nlp = spacy.load(model)
            except OSError as exc:
                raise RuntimeError(
                    f"Modelo ausente. Execute: python -m spacy download {model}"
                ) from exc
            if "ner" not in nlp.pipe_names:
                raise ValueError("O modelo precisa conter o componente ner.")
        self.nlp = nlp
        self.names = tuple(name.strip() for name in names if name.strip())

    def detect(self, text):
        found = [Entity(e.start_char, e.end_char, "PESSOA", "spacy")
                 for e in self.nlp(text).ents if e.label_ in {"PER", "PERSON"}]
        for kind, pattern in PATTERNS.items():
            flags = 0 if kind == "PLACA" else re.IGNORECASE
            for match in re.finditer(pattern, text, flags):
                start, end = match.span("value") if "value" in match.re.groupindex else match.span()
                found.append(Entity(start, end, kind, "regex"))
        for name in self.names:
            pattern = r"(?<!\w)" + r"\s+".join(re.escape(x) for x in name.split()) + r"(?!\w)"
            found.extend(Entity(m.start(), m.end(), "PESSOA", "manual")
                         for m in re.finditer(pattern, text, re.IGNORECASE))
        # Keep overlapping detections: all involved coordinates must be removed.
        return sorted(set(found), key=lambda e: (e.start, e.end, e.kind))
