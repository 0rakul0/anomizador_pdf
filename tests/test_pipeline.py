import pymupdf as fitz
import pytest
import spacy
from anonymizer.detection import Detector
from anonymizer.pipeline import anonymize_pdf

@pytest.fixture
def detector():
    nlp = spacy.blank('pt')
    ruler = nlp.add_pipe('entity_ruler')
    ruler.add_patterns([{'label': 'PER', 'pattern': 'Maria Souza'}])
    return Detector(nlp=nlp, names=['João da Silva'])

def make_pdf(path, rotation=0):
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((50, 70), 'Maria Souza encontrou João da Silva.', fontsize=14)
        page.insert_text((50, 100), 'Maria Souza: CPF 123.456.789-00; teste@example.com', fontsize=12)
        page.insert_text((50, 150), 'Texto publico preservado.', fontsize=14)
        page.set_rotation(rotation)
        doc.set_metadata({'author': 'Maria Souza'})
        doc.embfile_add('private.txt', b'Maria Souza')
        page.add_text_annot((50, 200), 'Maria Souza')
        doc.save(path)

def test_offsets(detector):
    text = 'João\nda Silva; Maria Souza; CPF 123.456.789-00; (21) 99999-9999; teste@example.com; RG: 12.345.678-9; ABC1D23; endereço: Rua A, 123; nascimento: 01/01/1990'
    entities = detector.detect(text)
    assert {e.kind for e in entities} == {'PESSOA','CPF','TELEFONE','EMAIL','RG','PLACA','ENDERECO','NASCIMENTO'}
    assert any(text[e.start:e.end] == 'João\nda Silva' for e in entities)

@pytest.mark.parametrize('rotation', [0,90,180,270])
def test_hidden_content_and_pixels(tmp_path, detector, rotation):
    src, out, audit = [tmp_path/p for p in ['in.pdf','out.pdf','audit.json']]
    make_pdf(src, rotation)
    report = anonymize_pdf(src, out, detector=detector, ocr='never', audit_path=audit)
    assert len({e['replacement'] for e in report['entities'] if e['type']=='PESSOA'}) == 2
    assert 'Maria' not in audit.read_text()
    with fitz.open(out) as doc, fitz.open(src) as original:
        assert not doc[0].get_text().strip()
        assert doc.embfile_count()==0
        assert not list(doc[0].annots() or [])
        assert not doc.metadata.get('author')
        rect = original[0].search_for('Maria Souza')[0] * original[0].rotation_matrix
        pix = doc[0].get_pixmap()
        for x,y in [(rect.x0+2,rect.y0+2),(rect.x1-2,rect.y1-2)]:
            assert pix.pixel(int(x),int(y))==(0,0,0)
    assert b'Maria Souza' not in out.read_bytes()

def test_scan_ocr(tmp_path, detector):
    native,scan,out=[tmp_path/p for p in ['native.pdf','scan.pdf','out.pdf']]
    make_pdf(native)
    with fitz.open(native) as original, fitz.open() as doc:
        page=doc.new_page()
        page.insert_image(page.rect,stream=original[0].get_pixmap(dpi=200).tobytes('png'))
        doc.save(scan)
    report=anonymize_pdf(scan,out,detector=detector,language='eng')
    assert report['pages'][0]['ocr_used']
    assert any(e['type']=='EMAIL' for e in report['entities'])
    with fitz.open(out) as doc:
        page=doc[0]
        tp=page.get_textpage_ocr(language='eng',dpi=200,full=True)
        text=page.get_text(textpage=tp)
        assert 'Maria Souza' not in text
        assert 'example.com' not in text
        assert 'preservado' in text

def test_failure(tmp_path,detector,monkeypatch):
    src,out=tmp_path/'in.pdf',tmp_path/'out.pdf'
    make_pdf(src)
    def broken(*args,**kwargs): raise RuntimeError('OCR unavailable')
    monkeypatch.setattr('anonymizer.pipeline.ocr_text',broken)
    with pytest.raises(RuntimeError,match='OCR falhou'):
        anonymize_pdf(src,out,detector=detector,ocr='always')
    assert not out.exists()
    with pytest.raises(ValueError): anonymize_pdf(src,src,detector=detector)

def test_originals_opt_in(tmp_path,detector):
    src,out=tmp_path/'in.pdf',tmp_path/'out.pdf'
    make_pdf(src)
    report=anonymize_pdf(src,out,detector=detector,ocr='never',include_originals=True)
    assert any(e.get('original')=='Maria Souza' for e in report['entities'])
