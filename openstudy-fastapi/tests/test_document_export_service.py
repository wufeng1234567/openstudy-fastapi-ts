"""资料正文导出：Word 公式必须走原生 OMML，而不是保留 LaTeX 源码。"""

import io
import zipfile

from app.services.document_export_service import export_document


def test_docx_export_renders_latex_as_omml():
    body, filename, media_type = export_document(
        "公式测试.docx",
        "这是公式：$P(A)=0.4$，还有 $\\frac{1}{2}$。",
        {},
        "docx",
    )
    assert filename == "公式测试.docx"
    assert media_type.endswith("wordprocessingml.document")
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    assert "<m:oMath" in xml
    assert "P(A)=0.4" in xml or "0.4" in xml


def test_markdown_export_returns_text_without_huge_image_embedding():
    body, filename, media_type = export_document(
        "资料.md",
        "一段正文 $x^2$。",
        {},
        "markdown",
    )
    assert filename == "资料.md"
    assert media_type.startswith("text/markdown")
    assert "$x^2$" in body.decode("utf-8")
    assert len(body) < 10000
