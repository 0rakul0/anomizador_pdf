"""Raster-only export prevents copying hidden source objects into the result."""
import json
import os
from pathlib import Path
import tempfile

import pymupdf as fitz
from .detection import Detector, identity


def native_text(page):
    text, boxes = [], []
    for block in page.get_text("rawdict", sort=True)["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                for char in span["chars"]:
                    for letter in char["c"]:
                        text.append(letter)
                        boxes.append(char["bbox"])
            text.append("\n")
            boxes.append(None)
    return "".join(text), boxes


def ocr_text(page, language, dpi, tessdata):
    tp = page.get_textpage_ocr(language=language, dpi=dpi, full=True, tessdata=tessdata)
    text, boxes = [], []
    # OCR has word boxes, so redact the entire word for any matched character.
    for word in page.get_text("words", textpage=tp, sort=True):
        value = word[4]
        text.extend(value)
        boxes.extend([word[:4]] * len(value))
        text.append(" ")
        boxes.append(None)
    return "".join(text), boxes


def anonymize_pdf(input_path, output_path, *, model="pt_core_news_lg", names=(),
                  ocr="auto", language="por", dpi=200, tessdata=None,
                  audit_path=None, include_originals=False, detector=None):
    """Return an audit dict. Never overwrite input or existing outputs.

    auto: OCR pages containing images or lacking native text; always: all pages.
    OCR errors abort the entire operation before publishing an output.
    """
    source, target = Path(input_path), Path(output_path)
    audit = Path(audit_path) if audit_path else None
    if ocr not in {"auto", "always", "never"}:
        raise ValueError("ocr deve ser auto, always ou never")
    if not 100 <= dpi <= 600:
        raise ValueError("dpi deve estar entre 100 e 600")
    if target.resolve() == source.resolve() or target.exists():
        raise ValueError("A saída deve ser um arquivo novo, diferente da entrada.")
    if audit and (audit.exists() or audit.resolve() in {source.resolve(), target.resolve()}):
        raise ValueError("A auditoria deve ser um arquivo novo e separado.")
    detector = detector or Detector(model, names)
    report = {"version": 1, "model": model, "ocr": ocr, "dpi": dpi,
              "review_required": True, "pages": [], "entities": []}
    pseudonyms, counters = {}, {}
    with fitz.open(source) as original, fitz.open() as output:
        if not original.is_pdf or original.needs_pass:
            raise ValueError("É necessário um PDF válido e sem senha.")
        if len(original) == 0:
            raise ValueError("PDF sem páginas.")
        for number, page in enumerate(original, 1):
            text, boxes = native_text(page)
            has_image = bool(page.get_image_info())
            run_ocr = ocr == "always" or (ocr == "auto" and (has_image or not text.strip()))
            streams = [(text, boxes, "native")]
            if run_ocr:
                try:
                    streams.append((*ocr_text(page, language, dpi, tessdata), "ocr"))
                except Exception as exc:
                    raise RuntimeError(f"OCR falhou na página {number}. Verifique Tesseract/tessdata ({language}).") from exc
            if not any(t.strip() for t, _, _ in streams):
                raise RuntimeError(f"Página {number} sem texto detectável; revisar OCR antes de continuar.")
            # Render source without annotation appearances, then burn masks into
            # this independent image page. No original PDF objects are exported.
            pix = page.get_pixmap(dpi=dpi, alpha=False, annots=False)
            with fitz.open() as raster:
                clean = raster.new_page(width=page.rect.width, height=page.rect.height)
                clean.insert_image(clean.rect, stream=pix.tobytes("png"))
                for stream_text, stream_boxes, method in streams:
                    for entity in detector.detect(stream_text):
                        value = stream_text[entity.start:entity.end]
                        key = (entity.kind, identity(value))
                        if key not in pseudonyms:
                            counters[entity.kind] = counters.get(entity.kind, 0) + 1
                            pseudonyms[key] = f"{entity.kind}_{counters[entity.kind]:03d}"
                        areas = sorted(set(tuple(b) for b in stream_boxes[entity.start:entity.end] if b))
                        if not areas:
                            raise RuntimeError(f"Entidade sem coordenadas na página {number}.")
                        for area in areas:
                            rect = fitz.Rect(area)
                            # Extracted coordinates are unrotated; rendered page is rotated.
                            rect = rect * page.rotation_matrix
                            rect = (rect + (-1, -1, 1, 1)) & clean.rect
                            clean.add_redact_annot(rect, fill=(0, 0, 0))
                        record = {"page": number, "type": entity.kind,
                                  "replacement": pseudonyms[key], "source": entity.source,
                                  "extraction": method, "rectangles": areas}
                        if include_originals:
                            record["original"] = value
                        report["entities"].append(record)
                clean.apply_redactions(images=2, graphics=0, text=0)
                burned = clean.get_pixmap(dpi=dpi, alpha=False, annots=False)
                final = output.new_page(width=clean.rect.width, height=clean.rect.height)
                final.insert_image(final.rect, stream=burned.tobytes("png"))
            report["pages"].append({"page": number, "ocr_used": run_ocr,
                                    "review_required": True})
        target.parent.mkdir(parents=True, exist_ok=True)
        # Non-incremental save, fresh document, no metadata/attachments/forms.
        fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=target.parent)
        os.close(fd)
        try:
            output.save(tmp, garbage=4, deflate=True)
            with fitz.open(tmp) as verified:
                if len(verified) != len(original) or any(p.get_text().strip() for p in verified):
                    raise RuntimeError("Verificação estrutural da saída falhou.")
            # Exclusive creation avoids silently replacing a concurrently created file.
            with open(tmp, "rb") as src, target.open("xb") as dest:
                dest.write(src.read())
        finally:
            Path(tmp).unlink(missing_ok=True)
    if audit:
        audit.parent.mkdir(parents=True, exist_ok=True)
        with audit.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
    return report
