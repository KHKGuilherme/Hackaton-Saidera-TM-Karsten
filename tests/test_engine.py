# Testes do motor de cálculo: fórmula, arredondamento, frequência, RPM, erros e análises.
from dataclasses import replace
from decimal import Decimal

import pytest

from autotm.domain import Demanda, ErroValidacao, ItemRoteiro, calcular_po
from autotm.domain.analise import checagem_agulha, comparar_maquinas, pecas_por_hora


# Monta uma demanda de teste com valores padrão; cada teste muda só o que precisa.
def demanda(**kw):
    base = dict(
        perimetro_m=Decimal("6.96"),
        cod_maquina="1",
        roteiro=[ItemRoteiro("2.1"), ItemRoteiro("1.1"), ItemRoteiro("3.1")],
        pontos_cm=Decimal("2.5"),
    )
    return Demanda(**(base | kw))


def test_fixo_formula_oficial_e_arredondamento(cad):
    f = calcular_po(demanda(), cad)
    assert f.fixo == Decimal("0.6709")
    assert f.linhas[0].codigo == "FIXO" and f.linhas[0].fixo


# Com float, 0.6709 + 0.15 + 0.12 daria 0.9409000000000001; com Decimal dá exatamente 0.9409.
def test_decimal_evita_erro_de_float(cad):
    assert 0.6709 + 0.15 + 0.12 != 0.9409
    assert calcular_po(demanda(), cad).tp == Decimal("0.9409")


# Confirma ROUND_HALF_UP: o 5 na casa seguinte arredonda para cima.
def test_arredondamento_meio_para_cima(cad):
    assert calcular_po(demanda(perimetro_m=Decimal("1.9"), cod_maquina="2"), cad).fixo == Decimal("0.1587")


def test_tp_soma_fixo_e_mtm(cad):
    assert calcular_po(demanda(), cad).tp == Decimal("0.9409")


def test_frequencia_multiplica_tempo(cad):
    f = calcular_po(demanda(roteiro=[ItemRoteiro("4.1", Decimal(2))]), cad)
    assert f.linhas[1].tempo == Decimal("0.4000")
    assert f.linhas[1].tempo_total == Decimal("0.8000")
    assert f.tp == Decimal("0.6709") + Decimal("0.8")


def test_ordem_do_roteiro_preservada(cad):
    f = calcular_po(demanda(roteiro=[ItemRoteiro(c) for c in ["3.1", "2.1", "6.1"]]), cad)
    assert [l.codigo for l in f.linhas] == ["FIXO", "3.1", "2.1", "6.1"]


def test_rpm_limites(cad):
    f = calcular_po(demanda(), cad)
    assert (f.rpm_limite_inferior, f.maquina.rpm, f.rpm_limite_superior) == (4500, 5000, 5500)


# Vários erros na mesma demanda aparecem todos juntos.
def test_erros_acumulados(cad):
    with pytest.raises(ErroValidacao) as e:
        calcular_po(demanda(perimetro_m=Decimal(0), cod_maquina="9", roteiro=[ItemRoteiro("7.7")]), cad)
    campos = [c for c, _ in e.value.erros]
    assert len(e.value.erros) == 3
    assert "Cód. Eqp." in campos and "Elementos" in campos


def test_roteiro_vazio(cad):
    with pytest.raises(ErroValidacao):
        calcular_po(demanda(roteiro=[]), cad)


def test_aviso_elemento_duplicado(cad):
    f = calcular_po(demanda(roteiro=[ItemRoteiro("1.1"), ItemRoteiro("1.1")]), cad)
    assert any("mais de uma vez" in a for a in f.avisos)
    assert not calcular_po(demanda(), cad).avisos


def test_comparar_maquinas_ordena_por_tp(cad):
    cen = comparar_maquinas(demanda(), cad)
    assert [c.codigo for c in cen] == ["2", "1", "3"]
    assert next(c for c in cen if c.atual).codigo == "1"


def test_indicadores(cad):
    f = calcular_po(demanda(), cad)
    assert pecas_por_hora(f.tp) == Decimal("63.8")
    chk = checagem_agulha(f)
    assert chk.total_pontos == 1740 and chk.tempo_agulha_min == Decimal("0.3480")
    assert checagem_agulha(replace(f, demanda=demanda(pontos_cm=None))) is None
