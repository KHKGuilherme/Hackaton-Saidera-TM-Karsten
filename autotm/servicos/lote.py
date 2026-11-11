# Caso de uso: gerar várias fichas de uma vez.
from __future__ import annotations

from dataclasses import dataclass

from ..domain.engine import calcular_po
from ..domain.models import Cadastros, ErroValidacao, FichaPO
from ..ingestion.demandas import ResultadoLeitura, montar_demanda


# Resultado de cada demanda do lote: a ficha OU a lista de erros, nunca os dois.
@dataclass
class ResultadoLote:
    origem: str
    ficha: FichaPO | None
    erros: list[tuple[str, str]]


def processar_lote(leituras: list[ResultadoLeitura], cadastros: Cadastros) -> list[ResultadoLote]:
    resultados = []
    for leitura in leituras:
        try:
            ficha = calcular_po(montar_demanda(leitura.rascunho, cadastros), cadastros)
            resultados.append(ResultadoLote(leitura.origem, ficha, []))
        # Um erro numa demanda não derruba o lote: ela é registrada com os erros e as demais seguem.
        except ErroValidacao as e:
            resultados.append(ResultadoLote(leitura.origem, None, e.erros))
    return resultados
