# Testes de leitura: cadastros, números brasileiros, sinônimos de campos, roteiro, TXT, JSON, CSV, Excel e texto livre.
import io
from decimal import Decimal

import pandas as pd
import pytest

from autotm.domain import ErroValidacao, ItemRoteiro, calcular_po
from autotm.export import gerar_zip
from autotm.servicos import processar_lote
from autotm.ingestion import (
    cadastros_de_dfs,
    cadastros_para_dfs,
    cadastros_para_json,
    carregar_cadastros,
    extrair_texto_livre,
    ler_arquivo_demandas,
    montar_demanda,
    parse_roteiro,
)
from autotm.ingestion.normalizacao import campo_canonico, para_decimal

from .conftest import EXEMPLOS, KIT


def test_cadastros_kit_oficial(cad):
    assert len(cad.elementos) == 9 and len(cad.maquinas) == 3
    assert cad.elementos["2.1"].tempo == Decimal("0.15")
    assert cad.elementos["2.1"].descricao == "Apanhar peça e posicionar na mesa"
    assert cad.maquinas["1"].tempo_por_metro == Decimal("0.0964")
    assert cad.maquinas["2"].descricao == "Siruba"


# Exportar e reimportar os cadastros (JSON e tabelas) não perde nem altera nada.
def test_cadastros_roundtrip_json_e_tabela(cad):
    cad_json = carregar_cadastros(cadastros_para_json(cad).encode(), "base.json")
    assert cad_json.elementos == cad.elementos and cad_json.maquinas == cad.maquinas
    el, mq = cadastros_para_dfs(cad)
    assert cadastros_de_dfs(el, mq, "editado").maquinas == cad.maquinas


def test_cadastros_xlsx(cad):
    el, mq = cadastros_para_dfs(cad)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as w:
        el.to_excel(w, sheet_name="MATRIZ DE ELEMENTOS", index=False)
        mq.to_excel(w, sheet_name="TEMPO-CM", index=False)
    assert carregar_cadastros(buf.getvalue(), "base.xlsx").elementos == cad.elementos


@pytest.mark.parametrize(
    "entrada,esperado",
    [("6,96", "6.96"), ("6.96 m", "6.96"), (6.96, "6.96"), ("1.234,5", "1234.5"), ("abc", None)],
)
def test_para_decimal(entrada, esperado):
    assert para_decimal(entrada) == (Decimal(esperado) if esperado else None)


@pytest.mark.parametrize(
    "nome,campo",
    [
        ("Perímetro costura (em m)", "perimetro_m"),
        ("Pontos/cm", "pontos_cm"),
        ("Cód. Eqp", "cod_maquina"),
        ("Agrupamento família", "familia"),
        ("Medidas da peça (em m)", "medidas"),
        ("Elementos", "roteiro"),
        ("Título", "titulo"),
        ("REV", "revisao"),
        ("qualquer", None),
    ],
)
def test_campo_canonico(nome, campo):
    assert campo_canonico(nome) == campo


def test_parse_roteiro_variantes():
    assert parse_roteiro("2.1, 1.1, 3.1") == [ItemRoteiro("2.1"), ItemRoteiro("1.1"), ItemRoteiro("3.1")]
    assert parse_roteiro("2.1; 4.1x2 3.1(3)") == [
        ItemRoteiro("2.1"),
        ItemRoteiro("4.1", Decimal(2)),
        ItemRoteiro("3.1", Decimal(3)),
    ]
    assert parse_roteiro(["2.1", {"codigo": "4.1", "frequencia": 2}]) == [ItemRoteiro("2.1"), ItemRoteiro("4.1", Decimal(2))]


# Texto não reconhecido no roteiro vira erro explicado, não é ignorado.
def test_parse_roteiro_lixo():
    with pytest.raises(ErroValidacao):
        parse_roteiro("2.1, banana, 3.1")


def test_txt_oficial(cad):
    r = ler_arquivo_demandas((KIT / "demanda_000.txt").read_bytes(), "demanda_000.txt", cad)[0].rascunho
    d = montar_demanda(r, cad)
    assert d.titulo == "PO-SL-001" and d.operacao == "Bainhar no corpo do SL - 1 lado"
    assert d.perimetro_m == Decimal("6.96") and d.pontos_cm == Decimal("2.50")
    assert d.familia == "Sobre-lençol" and d.medidas == "1,80 x 2,50"


# Arquivo salvo com a codificação antiga do Windows ainda é lido com os acentos certos.
def test_txt_em_cp1252(cad):
    texto = (KIT / "demanda_000.txt").read_text(encoding="utf-8").encode("cp1252")
    r = ler_arquivo_demandas(texto, "x.txt", cad)[0].rascunho
    assert montar_demanda(r, cad).familia == "Sobre-lençol"


def test_json(cad):
    r = ler_arquivo_demandas((EXEMPLOS / "02_demanda.json").read_bytes(), "02_demanda.json", cad)
    assert len(r) == 1
    assert calcular_po(montar_demanda(r[0].rascunho, cad), cad).tp == Decimal("1.4787")


# O CSV de exemplo tem 5 demandas e 1 erro proposital.
def test_csv_lote_com_erro(cad):
    leituras = ler_arquivo_demandas((EXEMPLOS / "03_lote_demandas.csv").read_bytes(), "lote.csv", cad)
    res = processar_lote(leituras, cad)
    assert len(res) == 5
    assert sum(r.ficha is not None for r in res) == 4
    assert res[0].ficha.tp == Decimal("0.9409")
    assert len(res[4].erros) == 2
    assert gerar_zip(res, cad)[:2] == b"PK"


# Planilha no formato vertical (Campo | Valor).
def test_xlsx_vertical_campo_valor(cad):
    df = pd.DataFrame(
        [["Perímetro costura (em m)", 6.96], ["Cód. Eqp", 1], ["Elementos", "2.1, 1.1, 3.1"]],
        columns=["Título", "PO-SL-001"],
    )
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    r = ler_arquivo_demandas(buf.getvalue(), "demanda.xlsx", cad)[0].rascunho
    assert calcular_po(montar_demanda(r, cad), cad).tp == Decimal("0.9409")
    assert r["titulo"] == "PO-SL-001"


def test_maquina_por_nome(cad):
    r = {"perimetro_m": "6,96", "cod_maquina": "Siruba", "roteiro": "2.1"}
    assert montar_demanda(r, cad).cod_maquina == "2"


def test_erros_de_campo_obrigatorio(cad):
    with pytest.raises(ErroValidacao) as e:
        montar_demanda({"perimetro_m": "", "cod_maquina": "", "roteiro": "2.1"}, cad)
    assert len(e.value.erros) == 2


def test_texto_livre_exemplo(cad):
    texto = (EXEMPLOS / "04_texto_livre.txt").read_text(encoding="utf-8")
    r, avisos = extrair_texto_livre(texto, cad)
    assert r["titulo"] == "PO-SL-004" and r["revisao"] == "01"
    assert r["operacao"] == "Bainhar no corpo do SL - 2 lados"
    assert r["familia"] == "Sobre-lençol" and r["tamanho"] == "Casal"
    assert r["medidas"] == "2,30 x 2,50"
    assert r["perimetro_m"] == "9,60" and r["pontos_cm"] == "2,5"
    assert r["cod_maquina"] == "2"
    assert r["roteiro"] == "2.1, 1.1, 2.3, 1.1, 3.1"
    assert not avisos


def test_texto_livre_cenario_oficial_em_uma_frase(cad):
    r, _ = extrair_texto_livre("Sobre-lençol solteiro, 6,96 m, 2,5 pontos/cm, máquina 1, elementos 2.1, 1.1, 3.1", cad)
    assert calcular_po(montar_demanda(r, cad), cad).tp == Decimal("0.9409")


def test_texto_livre_sem_palavra_chave_de_roteiro(cad):
    r, _ = extrair_texto_livre("Fronha 1.9 metros na Siruba: 2.1 4.1x2 3.1 6.1", cad)
    assert r["roteiro"] == "2.1, 4.1x2, 3.1, 6.1"
    assert calcular_po(montar_demanda(r, cad), cad).tp == Decimal("1.4787")


def test_texto_livre_avisa_campos_faltantes(cad):
    _, avisos = extrair_texto_livre("bainhar algo", cad)
    assert any("Perímetro" in a for a in avisos) and any("Elementos" in a for a in avisos)
