# Testes das saídas: ZIP do lote, PDF, JSON, HTML e a linha de comando.
import json
from decimal import Decimal

from autotm.__main__ import main
from autotm.domain import calcular_po
from autotm.export import gerar_json, gerar_pdf
from autotm.servicos import processar_lote
from autotm.export.html import ficha_html
from autotm.ingestion import ler_arquivo_demandas, montar_demanda

from .conftest import EXEMPLOS, KIT


def _ficha(cad):
    r = ler_arquivo_demandas((KIT / "demanda_000.txt").read_bytes(), "demanda_000.txt", cad)[0].rascunho
    return calcular_po(montar_demanda(r, cad), cad)


def test_lote_xlsx(cad):
    leituras = ler_arquivo_demandas((EXEMPLOS / "06_lote_demandas.xlsx").read_bytes(), "lote.xlsx", cad)
    res = processar_lote(leituras, cad)
    assert [r.ficha.tp for r in res] == [Decimal("0.9409"), Decimal("0.9347"), Decimal("1.9665"), Decimal("1.4787")]


def test_pdf_json_html(cad):
    f = _ficha(cad)
    assert gerar_pdf(f)[:4] == b"%PDF"
    dados = json.loads(gerar_json(f))
    assert dados["tp_min"] == "0.9409" and dados["elementos"][0]["codigo"] == "FIXO"
    html = ficha_html(f)
    assert "PO-SL-001" in html and "0.6709" in html and "0.9409" in html


# Segurança: texto com <script> aparece como texto na ficha, não é executado.
def test_html_escapa_entrada(cad):
    f = _ficha(cad)
    f.demanda.operacao = "<script>alert(1)</script>"
    assert "<script>" not in ficha_html(f)


def test_cli(tmp_path, capsys):
    assert main([str(KIT / "demanda_000.txt"), "--saida", str(tmp_path), "--pdf", "--json"]) == 0
    assert {p.suffix for p in tmp_path.iterdir()} == {".xlsx", ".pdf", ".json"}
    assert "TP=0.9409" in capsys.readouterr().out
