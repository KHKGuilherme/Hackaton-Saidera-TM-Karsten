# Testes de casos difíceis do mundo real: nomes de coluna diferentes, unidades, codificações, cabeçalho deslocado, arquivos inválidos.
import io
import json
from decimal import Decimal

import pandas as pd
import pytest

from autotm.__main__ import main
from autotm.domain import ErroValidacao, ItemRoteiro, calcular_po
from autotm.ingestion import carregar_cadastros, extrair_texto_livre, ler_arquivo_demandas, montar_demanda, parse_roteiro

from .conftest import KIT

TXT_OFICIAL = (KIT / "demanda_000.txt").read_text(encoding="utf-8")


# Atalho: rascunho -> TP.
def _tp(rascunho, cad):
    return calcular_po(montar_demanda(rascunho, cad), cad).tp


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("4.1x2,3.1", [("4.1", 2), ("3.1", 1)]),
        ("2.1x2,1.1,3.1", [("2.1", 2), ("1.1", 1), ("3.1", 1)]),
        ("2,1; 1,1; 3,1", [("2.1", 1), ("1.1", 1), ("3.1", 1)]),
        ("4.1x1.5, 3.1", [("4.1", Decimal("1.5")), ("3.1", 1)]),
        ("2.1 -> 1.1 -> 3.1", [("2.1", 1), ("1.1", 1), ("3.1", 1)]),
    ],
)
def test_roteiro_formatos(texto, esperado):
    assert parse_roteiro(texto) == [ItemRoteiro(c, Decimal(f)) for c, f in esperado]


# Gera em memória uma planilha de cadastros com colunas e linhas à escolha do teste.
def _planilha_cadastros(el_cols, el_rows, mq_cols, mq_rows, titulo=True) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as w:
        for aba, cols, rows in [("MATRIZ DE ELEMENTOS", el_cols, el_rows), ("TEMPO-CM", mq_cols, mq_rows)]:
            linhas = ([["Cadastro oficial"] + [None] * (len(cols) - 1)] if titulo else []) + [cols] + rows
            pd.DataFrame(linhas).to_excel(w, sheet_name=aba, index=False, header=False)
    return buf.getvalue()


# Nomes de coluna exatamente como aparecem no regulamento.
EL_REG = ["Código MTM", "Descrição do Elemento", "Tempo Unitário (min)"]
MQ_REG = ["Código da Máquina", "Descrição/Modelo", "RPM Padrão", "Fator de Tempo por Metro (min/m)"]


def test_cadastro_com_nomes_de_coluna_do_regulamento():
    cad = carregar_cadastros(
        _planilha_cadastros(EL_REG, [["2.1", "Apanhar", 0.15]], MQ_REG, [[1, "Jack C4", "5.000", 0.0964]]), "base.xlsx"
    )
    assert cad.maquinas["1"].tempo_por_metro == Decimal("0.0964")
    assert cad.maquinas["1"].rpm == 5000
    assert cad.elementos["2.1"].tempo == Decimal("0.15")


def test_cadastro_avisa_duplicado_e_trata_descricao_vazia():
    cad = carregar_cadastros(
        _planilha_cadastros(EL_REG, [["2.1", "A", 0.15], ["2.1", None, 0.2]], MQ_REG, [[1, "X", 5000, 0.1]]), "b.xlsx"
    )
    assert cad.elementos["2.1"].descricao == "Elemento 2.1"
    assert any("mais de uma vez" in a for a in cad.avisos)


@pytest.mark.parametrize(
    "el,mq",
    [
        ([["2.1", "A", -0.1]], [[1, "X", 5000, 0.1]]),
        ([["2.1", "A", 0.1]], [[1, "X", 5000, 0]]),
        ([["2.1", "A", 0.1]], [[1, "X", 0, 0.1]]),
    ],
)
def test_cadastro_rejeita_valores_invalidos(el, mq):
    with pytest.raises(ErroValidacao):
        carregar_cadastros(_planilha_cadastros(EL_REG, el, MQ_REG, mq), "b.xlsx")


def test_cadastro_corrompido_vira_erro_legivel():
    with pytest.raises(ErroValidacao, match="não foi possível ler"):
        carregar_cadastros(b"isto nao e uma planilha", "base.xlsx")


# "696 cm" vira 6,96 m com aviso.
def test_perimetro_em_centimetros_e_convertido(cad):
    d = montar_demanda({"perimetro_m": "696 cm", "cod_maquina": "1", "roteiro": "2.1, 1.1, 3.1"}, cad)
    assert d.perimetro_m == Decimal("6.96") and any("centímetros" in a for a in d.avisos)
    assert calcular_po(d, cad).tp == Decimal("0.9409")


def test_texto_livre_perimetro_em_cm(cad):
    r, _ = extrair_texto_livre("fronha, perímetro 240 cm, máquina 2, elementos 2.1", cad)
    assert montar_demanda(r, cad).perimetro_m == Decimal("2.40")


def test_avisos_de_plausibilidade(cad):
    d = montar_demanda({"perimetro_m": "150", "medidas": "1,80 x 2,50", "cod_maquina": "1", "roteiro": "2.1"}, cad)
    f = calcular_po(d, cad)
    assert any("contorno da peça" in a for a in f.avisos)
    assert any("FIXO" in a for a in f.avisos)


@pytest.mark.parametrize("valor", ["01", "Máquina 2", "maq. 02", "Siruba", "2 - Interlock Siruba"])
def test_maquina_por_codigo_com_zero_ou_texto(valor, cad):
    esperado = "1" if valor == "01" else "2"
    assert montar_demanda({"perimetro_m": "1", "cod_maquina": valor, "roteiro": "2.1"}, cad).cod_maquina == esperado


def test_texto_livre_maquina_com_igual(cad):
    r, _ = extrair_texto_livre("perimetro 6,96 m maquina=1 elementos 2.1, 1.1, 3.1", cad)
    assert _tp(r, cad) == Decimal("0.9409")


# O Bloco de Notas pode salvar em UTF-16; o arquivo continua legível.
def test_txt_utf16_do_bloco_de_notas(cad):
    r = ler_arquivo_demandas(TXT_OFICIAL.encode("utf-16"), "d.txt", cad)[0].rascunho
    assert _tp(r, cad) == Decimal("0.9409")


def test_txt_elementos_em_varias_linhas(cad):
    texto = TXT_OFICIAL.replace("Elementos: 2.1, 1.1, 3.1", "Elementos:\n2.1\n1.1\n3.1")
    r = ler_arquivo_demandas(texto.encode(), "d.txt", cad)[0].rascunho
    assert _tp(r, cad) == Decimal("0.9409")


# Linhas de título antes do cabeçalho não atrapalham a leitura.
def test_planilha_com_titulo_acima_do_cabecalho(cad):
    linhas = [
        ["Demandas da semana", None, None],
        [None, None, None],
        ["Perímetro costura (em m)", "Cód. Eqp", "Elementos"],
        [6.96, 1, "2.1, 1.1, 3.1"],
        [7.96, 2, "2.1, 1.1, 3.1"],
    ]
    buf = io.BytesIO()
    pd.DataFrame(linhas).to_excel(buf, index=False, header=False)
    leituras = ler_arquivo_demandas(buf.getvalue(), "semana.xlsx", cad)
    assert [_tp(l.rascunho, cad) for l in leituras] == [Decimal("0.9409"), Decimal("0.9347")]


def test_varias_colunas_de_elementos(cad):
    csv = "Perímetro;Máquina;Elemento 1;Elemento 2;Elemento 3\n6,96;1;2.1;1.1;3.1\n"
    r = ler_arquivo_demandas(csv.encode(), "d.csv", cad)[0].rascunho
    assert _tp(r, cad) == Decimal("0.9409")


def test_json_aninhado(cad):
    dados = {"titulo": "PO-1", "produto": {"perimetro_m": 6.96}, "equipamento": {"maquina": 1}, "elementos": ["2.1", "1.1", "3.1"]}
    r = ler_arquivo_demandas(json.dumps(dados).encode(), "d.json", cad)[0].rascunho
    assert _tp(r, cad) == Decimal("0.9409")


def test_ficha_po_existente_serve_de_entrada(cad):
    leituras = ler_arquivo_demandas((KIT / "PO-SL-000.ods").read_bytes(), "PO-SL-000.ods", cad)
    assert len(leituras) == 1 and "ficha PO" in leituras[0].origem
    assert _tp(leituras[0].rascunho, cad) == Decimal("0.9409")


@pytest.mark.parametrize(
    "conteudo,nome,trecho",
    [
        (b'{"titulo": ', "d.json", "JSON inválido"),
        (b"", "d.csv", "nenhuma demanda"),
        (b"a;b\n1;2\n", "d.csv", "nenhuma demanda"),
        (b"PK\x03\x04lixo", "d.xlsx", "não foi possível ler"),
        (b"x", "d.pdf", "formato não suportado"),
    ],
)
# Arquivos quebrados geram mensagem em português, nunca traceback.
def test_arquivos_invalidos_viram_erro_legivel(conteudo, nome, trecho, cad):
    with pytest.raises(ErroValidacao, match=trecho):
        ler_arquivo_demandas(conteudo, nome, cad)


def test_cli_arquivo_inexistente(capsys):
    assert main(["nao_existe.txt"]) == 2
    assert "não encontrado" in capsys.readouterr().err
