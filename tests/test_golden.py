# Teste "golden": compara o Excel gerado com o gabarito oficial PO-SL-000 célula por célula.
# É a prova de precisão do sistema: valores, textos, fórmulas, mesclagens, cores e formato.
import io
import re

import pytest
from openpyxl import load_workbook

from autotm.domain import calcular_po
from autotm.export import gerar_xlsx
from autotm.ingestion import ler_arquivo_demandas, montar_demanda

from .conftest import KIT
from .ods_reader import ler_aba

GABARITO = KIT / "PO-SL-000.ods"


# Gera a ficha do cenário oficial uma vez para todos os testes do arquivo (scope="module").
@pytest.fixture(scope="module")
def ficha(cad):
    leitura = ler_arquivo_demandas((KIT / "demanda_000.txt").read_bytes(), "demanda_000.txt", cad)[0]
    return calcular_po(montar_demanda(leitura.rascunho, cad), cad)


# Abre o Excel gerado, aba PO.
@pytest.fixture(scope="module")
def ws(ficha, cad):
    return load_workbook(io.BytesIO(gerar_xlsx(ficha, cad)))["PO"]


# Lê o gabarito com o leitor independente (ods_reader.py).
@pytest.fixture(scope="module")
def gabarito():
    return ler_aba(GABARITO, "PO")


# Calcula fórmulas simples como "=D6*0.9" para comparar com o valor numérico do gabarito.
def _avaliar(ws, valor):
    if isinstance(valor, str) and (m := re.fullmatch(r"=([A-Z]+\d+)\*([\d.]+)", valor)):
        return ws[m.group(1)].value * float(m.group(2))
    return valor


# Os números do motor (FIXO, tempos, TP e RPM) iguais aos do gabarito.
def test_valores_do_motor_batem_com_gabarito(ficha, gabarito):
    assert float(ficha.fixo) == gabarito["E8"].valor == 0.6709
    tempos = [float(l.tempo) for l in ficha.linhas]
    assert tempos == [gabarito[f"E{r}"].valor for r in range(8, 12)]
    assert float(ficha.tp) == pytest.approx(0.9409, abs=1e-12)
    assert float(ficha.rpm_limite_inferior) == gabarito["C6"].valor
    assert float(ficha.rpm_limite_superior) == gabarito["E6"].valor


# Cada célula preenchida do gabarito tem o mesmo conteúdo no Excel gerado. Junta todas as diferenças antes de falhar.
def test_todas_as_celulas_do_gabarito(ws, gabarito):
    divergencias = []
    for ref, esperado in gabarito.items():
        obtido = _avaliar(ws, ws[ref].value)
        if esperado.valor is not None:
            ok = isinstance(obtido, (int, float)) and abs(obtido - esperado.valor) < 1e-9
        else:
            ok = str(obtido).strip() == esperado.texto.strip()
        if not ok:
            divergencias.append(f"{ref}: esperado {esperado.texto!r}/{esperado.valor} obtido {obtido!r}")
    assert not divergencias, "\n".join(divergencias)


# As fórmulas de RPM são as mesmas, descontando a diferença de sintaxe entre ODS (of:=[.D6]) e Excel (=D6).
def test_formulas_rpm_iguais_ao_gabarito(ws, gabarito):
    for ref in ("C6", "E6"):
        ods = gabarito[ref].formula
        xlsx = ws[ref].value
        assert re.sub(r"of:=|\[\.|\]", "", ods) == xlsx.lstrip("=")


# Células mescladas no gabarito também estão mescladas no Excel.
def test_mesclagens_iguais_ao_gabarito(ws, gabarito):
    mescladas = {str(r) for r in ws.merged_cells.ranges}
    for ref, cel in gabarito.items():
        if cel.colspan > 1:
            col, lin = ref[0], ref[1:]
            fim = chr(ord(col) + cel.colspan - 1)
            assert f"{ref}:{fim}{lin}" in mescladas


# Cinza dos rótulos e amarelo do FIXO iguais.
def test_cores_iguais_ao_gabarito(ws, gabarito):
    for ref, cel in gabarito.items():
        if cel.fundo and cel.fundo != "#FFFFFF":
            cor = ws[ref].fill.fgColor.rgb[-6:].upper()
            assert f"#{cor}" == cel.fundo, ref


def test_formato_quatro_casas_nos_tempos(ws):
    for r in range(8, 12):
        assert ws[f"E{r}"].number_format == "0.0000"


# As fórmulas já trazem o valor gravado (data_only=True lê o valor, não a fórmula). Garante que ERPs e o pandas vejam o TP.
def test_formulas_tem_valor_gravado(ficha, cad):
    wb = load_workbook(io.BytesIO(gerar_xlsx(ficha, cad)), data_only=True)["PO"]
    assert (wb["C6"].value, wb["E6"].value) == (4500, 5500)
    assert wb["E12"].value == pytest.approx(0.9409, abs=1e-12)
    import pandas as pd

    df = pd.read_excel(io.BytesIO(gerar_xlsx(ficha, cad)), sheet_name="PO", header=None)
    assert df.iloc[11, 4] == pytest.approx(0.9409)


# A linha de TP, que o regulamento exige e o gabarito não tem, existe e soma frequência × tempo.
def test_linha_tp_exigida_pelo_regulamento(ws):
    assert ws["A12"].value == "TP"
    assert ws["E12"].value == "=SUMPRODUCT(D8:D11,E8:E11)"
    soma = sum(ws[f"D{r}"].value * ws[f"E{r}"].value for r in range(8, 12))
    assert soma == pytest.approx(0.9409)
