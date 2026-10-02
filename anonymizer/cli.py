import argparse
import sys
from pathlib import Path
from .pipeline import anonymize_pdf


def main():
    parser = argparse.ArgumentParser(description="Redigir dados pessoais em PDFs localmente.")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", default="pt_core_news_lg")
    parser.add_argument("--ocr", choices=["auto", "always", "never"], default="auto")
    parser.add_argument("--language", default="por")
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--tessdata")
    parser.add_argument("--names-file", type=Path, help="UTF-8, um nome/alias por linha")
    parser.add_argument("--audit", type=Path)
    parser.add_argument("--include-originals", action="store_true", help="Auditoria conterá dados sensíveis")
    args = parser.parse_args()
    try:
        names = args.names_file.read_text(encoding="utf-8-sig").splitlines() if args.names_file else []
        report = anonymize_pdf(args.input, args.output, model=args.model, names=names,
                               ocr=args.ocr, language=args.language, dpi=args.dpi,
                               tessdata=args.tessdata, audit_path=args.audit,
                               include_originals=args.include_originals)
    except Exception as exc:
        # Don't print source text, detected values, or arbitrary library errors.
        print(f"Processamento falhou ({type(exc).__name__}). Verifique PDF, modelo, OCR e caminhos de saída.", file=sys.stderr)
        return 1
    print(f"PDF criado. Detecções: {len(report['entities'])}. Revisão visual obrigatória.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
