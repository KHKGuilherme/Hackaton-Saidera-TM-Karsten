# Testes da auditoria: gabarito 100% conforme, detecção de valores alterados à mão e de fichas desatualizadas.
import io
from dataclasses import replace
from decimal import Decimal

from openpyxl import load_workbook

from autotm.__main__ import main
from autotm.domain import calcular_po
from autotm.export import gerar_xlsx
from autotm.ingestion import ler_arquivo_demandas, montar_demanda
from autotm.servicos import auditar_arquivo

from .conftest import KIT

GABARITO = (KIT / "PO-SL-000.ods").read_bytes()


# Excel do cenário oficial gerado pelo sistema, usado como base para simular alterações.
def _ficha_oficial(cad):
    r = ler_arquivo_demandas((KIT / "demanda_000.txt").read_bytes(), "d.txt", cad)[0].rascunho
    return calcular_po(montar_demanda(r, cad), cad)


def test_gabarito_oficial_confere_100_porcento(cad):
    [res] = auditar_arquivo(GABARITO, "PO-SL-000.ods", cad)
    assert not res.erros and not res.divergencias
    assert res.conformidade == 100
    itens = {c.item for c in res.conferencias}
    assert {"Equipamento", "RPM padrão", "FIXO (tempo de costura): tempo (min)", "Elemento 2.1: tempo (min)"} <= itens
    assert res.total == 11
    assert any("TP recalculado: 0.9409" in o for o in res.observacoes)


def test_ficha_gerada_pelo_sistema_confere_inclusive_tp(cad):
    [res] = auditar_arquivo(gerar_xlsx(_ficha_oficial(cad), cad), "gerada.xlsx", cad)
    assert res.conformidade == 100
    assert any(c.item.startswith("TP") and c.ok for c in res.conferencias)


# Simula alguém digitando um tempo errado: a auditoria aponta a célula.
def test_detecta_tempo_mtm_alterado_a_mao(cad):
    wb = load_workbook(io.BytesIO(gerar_xlsx(_ficha_oficial(cad), cad)))
    wb["PO"]["E9"] = 0.2
    buf = io.BytesIO()
    wb.save(buf)
    [res] = auditar_arquivo(buf.getvalue(), "editada.xlsx", cad)
    [div] = res.divergencias
    assert div.celula == "E9" and div.na_ficha == "0.2000" and div.calculado == "0.1500"


# Ficha antiga conferida com um cadastro novo: mostra quais valores ficaram desatualizados.
def test_detecta_ficha_desatualizada_apos_mudanca_de_cadastro(cad):
    maq = replace(cad.maquinas["1"], tempo_por_metro=Decimal("0.1"))
    novo = replace(cad, maquinas=cad.maquinas | {"1": maq})
    [res] = auditar_arquivo(GABARITO, "PO-SL-000.ods", novo)
    assert [d.item for d in res.divergencias] == ["FIXO (tempo de costura): tempo (min)"]
    assert res.divergencias[0].calculado == "0.6960"


def test_arquivo_sem_ficha_po(cad):
    [res] = auditar_arquivo((KIT / "Entradas.ods").read_bytes(), "Entradas.ods", cad)
    assert res.erros and "layout de ficha PO" in res.erros[0][1]


def test_cli_auditar(capsys):
    assert main(["--auditar", str(KIT / "PO-SL-000.ods")]) == 0
    assert "CONFORME" in capsys.readouterr().out
