# Anonimizador de PDF

Primeira versão de um anonimizador local de PDFs em português com spaCy e PyMuPDF. Detecta pessoas (`PER`/`PERSON`), CPF, telefone, e-mail, placa e, quando rotulados, RG, endereço e nascimento. Produz máscaras pretas definitivas nas regiões detectadas e uma auditoria JSON opcional.

**A detecção é probabilística: revise todas as páginas antes de compartilhar.** Ausência de texto extraível não prova ausência de dados pessoais nos pixels. Nomes, faces, assinaturas manuscritas, QR codes e identificadores não detectados podem permanecer. O projeto não certifica anonimização legal. Teste recall/precision com documentos representativos antes de uso operacional.

## Instalação (Python 3.10+, recomendado 3.12)

```powershell
# Dentro do clone do repositório
uv venv --python 3.12
uv pip install -e ".[dev]"
uv run python -m spacy download pt_core_news_lg
```

Alternativa sem uv:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m spacy download pt_core_news_lg
```

Para OCR, instale Tesseract e os dados `por.traineddata`. No Windows, informe a pasta `tessdata` com `--tessdata`; ela precisa conter esse arquivo. No Ubuntu:

```bash
sudo apt-get install tesseract-ocr tesseract-ocr-por
```

O OCR desta versão usa Tesseract integrado ao PyMuPDF, em CPU. PaddleOCR/GPU não está implementado. Após instalar o modelo e o OCR, os documentos são processados localmente, sem envio a serviços externos.

## Usar

```powershell
uv run python main.py entrada.pdf output/anonimizado.pdf --audit output/resultado.audit.json --tessdata "C:\Program Files\Tesseract-OCR\tessdata"
```

PDF somente com texto digital, sem imagens que contenham dados pessoais:

```powershell
uv run python main.py entrada.pdf output/anonimizado.pdf --ocr never
```

Forçar OCR em todas as páginas (inclusive texto convertido em curvas):

```powershell
uv run python main.py entrada.pdf output/anonimizado.pdf --ocr always --language por --dpi 300
```

Nomes conhecidos e aliases, um por linha em arquivo UTF-8:

```powershell
uv run python main.py entrada.pdf output/anonimizado.pdf --names-file nomes.txt --audit output/resultado.audit.json
```

Também há o comando `anonimizar-pdf` após instalação. PDFs protegidos por senha não são aceitos. Entrada e saídas existentes nunca são sobrescritas. Uma falha de OCR interrompe o processamento antes da publicação do PDF. Se a gravação da auditoria falhar, o PDF já gerado pode existir; verifique os caminhos antes de executar novamente.

## API Python

```python
from anonymizer import anonymize_pdf

report = anonymize_pdf(
    "entrada.pdf", "saida.pdf",
    names=["João da Silva", "João"],
    audit_path="resultado.audit.json",
    ocr="auto", language="por",
)
```

## Como funciona

1. Extrai caracteres e coordenadas nativas mantendo offsets; nomes podem atravessar linhas.
2. Em `auto`, executa OCR completo em páginas com imagens ou sem texto nativo. Analisa tanto a extração nativa quanto a OCR em páginas mistas. `always` inclui todas as páginas; `never` exige revisão específica de imagens/curvas.
3. Aplica NER spaCy, expressões regulares e nomes adicionais explícitos. Regras podem produzir falsos positivos: CPF tem formato, sem validação de dígito; endereço requer rótulo e vai até quebra de linha/ponto e vírgula; RG requer rótulo. Datas genéricas não são removidas.
4. Usa coordenadas de caracteres/palavras, com margem de 1 ponto, para remover pixels nas áreas detectadas. Não usa busca textual global para localizar ocorrências.
5. Renderiza novamente e cria um PDF novo contendo somente imagens já redigidas. Objetos, metadados, anexos, anotações e camadas de texto do PDF original não são copiados. Salva sem atualização incremental e verifica quantidade de páginas e ausência de camada textual.

A aparência e dimensões das páginas são mantidas, mas texto selecionável, acessibilidade, links, formulários e assinaturas digitais são perdidos. Anotações do original são omitidas. A rasterização pode aumentar o arquivo e reduzir nitidez; `--dpi` aceita 100 a 600. PDFs grandes exigem memória e tempo. As máscaras são pretas: os pseudônimos são usados na auditoria, não impressos sobre nomes.

## Auditoria e pseudônimos

Identificadores como `PESSOA_001` são consistentes **dentro do documento**, por tipo e texto normalizado (caixa, espaços e Unicode). Nomes curtos, nomes completos e grafias diferentes permanecem separados; não há resolução automática de identidade. Detecções sobrepostas ou extraídas pelos dois métodos podem aparecer em duplicidade na auditoria. Coordenadas registradas são do espaço original não rotacionado.

Por padrão, a auditoria contém página, tipo, identificador, método e coordenadas, sem nome original nem nome do arquivo. O uso de `--include-originals` inclui os valores originais: essa auditoria é sensível, reversível e deve ser protegida separadamente. Mesmo a auditoria padrão exige controle de acesso. Nenhum documento real ou auditoria deve ser commitado; mantenha resultados em `output/`, ignorado pelo Git.

## Testes

```powershell
uv run python -m pytest -q
```

Os testes usam documentos sintéticos, spaCy com EntityRuler e OCR real em inglês (disponível no CI). Cobrem offsets, regras, repetição, rotação, pixels redigidos, remoção de anexos/metadados/anotações, re-OCR da saída e interrupção quando OCR falha. Eles não medem a qualidade do NER em ROs reais. A integração com o modelo `pt_core_news_lg` exige o download separado e validação com seu corpus.

## Referências técnicas

- [Modelos de português do spaCy](https://spacy.io/models/pt/)
- [Coordenadas, OCR e redação no PyMuPDF](https://pymupdf.readthedocs.io/en/latest/page.html)
- [OCR no PyMuPDF](https://pymupdf.readthedocs.io/en/latest/recipes-ocr.html)

Verifique as licenças das dependências, em especial PyMuPDF/MuPDF (AGPL ou licença comercial), antes de integrar o projeto a produtos.
