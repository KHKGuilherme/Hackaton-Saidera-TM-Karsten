# Análises extras que reaproveitam o motor: comparação entre máquinas e checagem da agulha.
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from .engine import arredondar, calcular_po
from .models import Cadastros, Demanda, FichaPO


# 60 minutos ÷ TP, com 1 casa
def pecas_por_hora(tp: Decimal) -> Decimal:
    return arredondar(Decimal(60) / tp, Decimal("0.1")) if tp > 0 else Decimal(0)


# Resultado de um cenário "e se fosse em outra máquina?".
@dataclass(frozen=True)
class CenarioMaquina:
    codigo: str
    nome: str
    fixo: Decimal
    tp: Decimal
    pecas_hora: Decimal
    atual: bool


def comparar_maquinas(demanda: Demanda, cadastros: Cadastros) -> list[CenarioMaquina]:
    cenarios = []
    for cod, maq in cadastros.maquinas.items():
        # replace cria uma cópia da demanda trocando só a máquina; a original fica intacta.
        ficha = calcular_po(replace(demanda, cod_maquina=cod), cadastros)
        cenarios.append(
            CenarioMaquina(
                codigo=cod,
                nome=f"{cod} - {maq.tipo} {maq.descricao}",
                fixo=ficha.fixo,
                tp=ficha.tp,
                pecas_hora=pecas_por_hora(ficha.tp),
                atual=cod == demanda.cod_maquina,
            )
        )
    # Ordena do menor TP (mais rápida) para o maior.
    return sorted(cenarios, key=lambda c: c.tp)


# Leitura complementar: quanto do FIXO a agulha passa de fato costurando. Não altera o cálculo.
@dataclass(frozen=True)
class ChecagemAgulha:

    total_pontos: Decimal
    tempo_agulha_min: Decimal
    percentual_do_fixo: Decimal


def checagem_agulha(ficha: FichaPO) -> ChecagemAgulha | None:
    d = ficha.demanda
    if not d.pontos_cm or ficha.maquina.rpm <= 0 or ficha.fixo <= 0:
        return None
    # Total de pontos = perímetro em cm × pontos por cm.
    pontos = d.perimetro_m * Decimal(100) * d.pontos_cm
    # Minutos com a agulha em movimento = pontos ÷ RPM (pontos por minuto).
    tempo = arredondar(pontos / ficha.maquina.rpm)
    pct = arredondar(tempo / ficha.fixo * 100, Decimal("0.1"))
    return ChecagemAgulha(arredondar(pontos, Decimal("1")), tempo, pct)
