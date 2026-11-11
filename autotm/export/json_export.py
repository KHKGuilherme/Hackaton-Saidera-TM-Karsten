# Exporta a ficha em JSON (para integração com ERP) e define o padrão de nome dos arquivos gerados.
from __future__ import annotations

import json
import re

from ..domain.analise import pecas_por_hora
from ..domain.models import FichaPO


# Nome seguro para o arquivo: troca caracteres proibidos por "_". Ex.: PO-SL-001_rev00.xlsx.
def nome_arquivo(ficha: FichaPO, extensao: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", ficha.demanda.titulo).strip("_") or "PO"
    return f"{base}_rev{ficha.demanda.revisao}.{extensao}"


# Ficha -> dicionário organizado em blocos (produto, equipamento, elementos), espelhando a ficha impressa.
def ficha_para_dict(ficha: FichaPO) -> dict:
    d, m = ficha.demanda, ficha.maquina
    return {
        "titulo": d.titulo,
        "revisao": d.revisao,
        "operacao": d.operacao,
        "produto": {
            "familia": d.familia,
            "tamanho": d.tamanho,
            "medidas_m": d.medidas,
            # Números vão como texto (str) para não perder precisão: JSON só tem float.
            "pontos_cm": None if d.pontos_cm is None else str(d.pontos_cm),
            "perimetro_m": str(d.perimetro_m),
        },
        "equipamento": {
            "codigo": m.codigo,
            "tipo": m.tipo,
            "descricao": m.descricao,
            "rpm_limite_inferior": str(ficha.rpm_limite_inferior),
            "rpm_padrao": str(m.rpm),
            "rpm_limite_superior": str(ficha.rpm_limite_superior),
            "tempo_por_metro": str(m.tempo_por_metro),
        },
        "elementos": [
            {
                "codigo": l.codigo,
                "descricao": l.descricao,
                "frequencia": str(l.frequencia),
                "tempo_min": f"{l.tempo:.4f}",
                "tempo_total_min": f"{l.tempo_total:.4f}",
            }
            for l in ficha.linhas
        ],
        "tempo_fixo_min": f"{ficha.fixo:.4f}",
        "tp_min": f"{ficha.tp:.4f}",
        "pecas_hora": str(pecas_por_hora(ficha.tp)),
        "avisos": ficha.avisos,
    }


# ensure_ascii=False mantém os acentos legíveis; indent=2 deixa o arquivo legível por pessoas.
def gerar_json(ficha: FichaPO) -> bytes:
    return json.dumps(ficha_para_dict(ficha), ensure_ascii=False, indent=2).encode("utf-8")
