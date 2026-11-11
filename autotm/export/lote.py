# Gera o ZIP do lote: uma ficha por demanda (Excel e, opcionalmente, PDF) mais uma planilha de resumo.
from __future__ import annotations

import io
import zipfile

from openpyxl import Workbook
from openpyxl.styles import Font

from ..domain.analise import pecas_por_hora
from ..domain.models import Cadastros
from ..servicos.lote import ResultadoLote
from .json_export import nome_arquivo
from .pdf import gerar_pdf
from .xlsx import gerar_xlsx


def gerar_zip(resultados: list[ResultadoLote], cadastros: Cadastros, incluir_pdf: bool = True) -> bytes:
    buf = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    # A planilha de resumo lista todas as demandas, inclusive as que deram erro, com o motivo.
    ws.title = "Resumo"
    ws.append(["Origem", "PO", "Operação", "Máquina", "FIXO (min)", "TP (min)", "Peças/hora", "Situação"])
    for c in ws[1]:
        c.font = Font(bold=True)
    # Nomes já usados no ZIP: duas demandas com o mesmo título viram PO_rev00 e PO_rev00_2, sem sobrescrever.
    usados: set[str] = set()
    # O ZIP é montado em memória (BytesIO), sem gravar arquivos temporários no disco.
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for r in resultados:
            if r.ficha:
                f = r.ficha
                base = nome_arquivo(f, "xlsx")[:-5]
                n, nome = 2, base
                while nome in usados:
                    nome, n = f"{base}_{n}", n + 1
                usados.add(nome)
                z.writestr(f"{nome}.xlsx", gerar_xlsx(f, cadastros))
                if incluir_pdf:
                    z.writestr(f"{nome}.pdf", gerar_pdf(f))
                ws.append(
                    [
                        r.origem,
                        f.demanda.titulo,
                        f.demanda.operacao,
                        f"{f.maquina.codigo} - {f.maquina.tipo} {f.maquina.descricao}",
                        float(f.fixo),
                        float(f.tp),
                        float(pecas_por_hora(f.tp)),
                        "Gerada",
                    ]
                )
            else:
                # Demanda com erro também aparece no resumo, para ninguém perder de vista o que faltou.
                ws.append([r.origem, "", "", "", None, None, None, "Erro: " + "; ".join(f"{c}: {m}" for c, m in r.erros)])
        for col, w in zip("ABCDEFGH", [26, 16, 34, 26, 11, 11, 11, 60]):
            ws.column_dimensions[col].width = w
        for row in ws.iter_rows(min_row=2, min_col=5, max_col=6):
            for c in row:
                c.number_format = "0.0000"
        resumo = io.BytesIO()
        wb.save(resumo)
        z.writestr("RESUMO_LOTE.xlsx", resumo.getvalue())
    return buf.getvalue()
