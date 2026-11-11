# Gera o Excel da ficha no layout do gabarito oficial (aba PO) e uma aba de análise complementar.
from __future__ import annotations

import io
import re
import zipfile
from ..relogio import agora
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.workbook.properties import CalcProperties
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from ..domain.analise import checagem_agulha, comparar_maquinas, pecas_por_hora
from ..domain.models import Cadastros, FichaPO

# Cores, bordas, fontes e alinhamento copiados do gabarito PO-SL-000.
CINZA = PatternFill("solid", fgColor="D9D9D9")
AMARELO = PatternFill("solid", fgColor="FFFF00")
_LADO = Side(style="thin", color="000000")
BORDA = Border(left=_LADO, right=_LADO, top=_LADO, bottom=_LADO)
CENTRO = Alignment(horizontal="center", vertical="center", wrap_text=True)

F_TITULO = Font(name="Arial", size=16, bold=True)
F_ROTULO = Font(name="Arial", size=10, bold=True)
F_NORMAL = Font(name="Arial", size=10)

# Larguras e alturas medidas no gabarito (em polegadas), para a ficha sair com as mesmas proporções.
LARGURAS_POL = {"A": 1.5311, "B": 2.0102, "C": 1.3854, "D": 1.1146, "E": 1.7083}
ALTURA_TITULO_POL, ALTURA_LINHA_POL, ALTURA_CABECALHO_POL = 0.5417, 0.178, 0.3189

FMT_2 = "0.00"
FMT_4 = "0.0000"


# O Excel não conhece Decimal: inteiro vira int, o resto vira float.
def _num(v: Decimal) -> int | float:
    return int(v) if v == v.to_integral_value() else float(v)


# Escreve uma célula já com o estilo do gabarito (fonte, borda, centralizado e, se for o caso, cor e formato).
def _cel(ws, ref, valor, fonte=F_NORMAL, fill=None, fmt=None):
    c = ws[ref]
    c.value = valor
    c.font, c.border, c.alignment = fonte, BORDA, CENTRO
    if fill:
        c.fill = fill
    if fmt:
        c.number_format = fmt
    return c


# Mescla células aplicando a borda em todas elas; senão o Excel desenha a borda só na primeira.
def _mesclar(ws, intervalo, valor, fonte=F_NORMAL, fill=None):
    primeira = intervalo.split(":")[0]
    _cel(ws, primeira, valor, fonte, fill)
    for linha in ws[intervalo]:
        for c in linha:
            c.border = BORDA
            if fill:
                c.fill = fill
    ws.merge_cells(intervalo)


# Desenha a ficha célula por célula nas mesmas posições do gabarito (o teste golden confere isso). Devolve a linha do TP.
def preencher_aba_po(ws, ficha: FichaPO) -> int:
    d, m = ficha.demanda, ficha.maquina
    ws.title = "PO"
    for col, pol in LARGURAS_POL.items():
        # Conversão aproximada de polegadas para a unidade de largura do Excel.
        ws.column_dimensions[col].width = round(pol * 13.2, 2)

    _mesclar(ws, "A1:D1", d.titulo, F_TITULO)
    _cel(ws, "E1", f"Rev. {d.revisao}", F_TITULO)
    _cel(ws, "A2", "Operação", F_ROTULO, CINZA)
    _mesclar(ws, "B2:E2", d.operacao)
    for col, txt in zip("ABCDE", ["Agrupamento família", "Tamanho", "Medidas da peça (em m)", "Pontos/cm", "Perímetro costura\n(em m)"]):
        _cel(ws, f"{col}3", txt, F_ROTULO, CINZA)
    _cel(ws, "A4", d.familia)
    _cel(ws, "B4", d.tamanho)
    _cel(ws, "C4", d.medidas)
    _cel(ws, "D4", _num(d.pontos_cm) if d.pontos_cm is not None else None, fmt=FMT_2)
    _cel(ws, "E4", _num(d.perimetro_m), fmt=FMT_2)
    for col, txt in zip("ABCDE", ["Cód. Eqp.", "Equipamento", "RPM - limite inferior", "RPM - padrão", "RPM - limite superior"]):
        _cel(ws, f"{col}5", txt, F_ROTULO, CINZA)
    _cel(ws, "A6", _num(Decimal(m.codigo)) if m.codigo.isdigit() else m.codigo)
    _cel(ws, "B6", m.tipo or m.descricao)
    # RPM inferior e superior como fórmula, igual ao gabarito: se alguém mudar o RPM padrão, os limites acompanham.
    _cel(ws, "C6", "=D6*0.9")
    _cel(ws, "D6", _num(m.rpm))
    _cel(ws, "E6", "=D6*1.1")
    _cel(ws, "A7", "Código do elemento", F_ROTULO, CINZA)
    _mesclar(ws, "B7:C7", "Elementos", F_ROTULO, CINZA)
    _cel(ws, "D7", "Frequência", F_ROTULO, CINZA)
    _cel(ws, "E7", "Tempos (em minutos)", F_ROTULO, CINZA)
    linha = 8
    # Uma linha por elemento; a linha FIXO fica amarela como no gabarito.
    for l in ficha.linhas:
        fill = AMARELO if l.fixo else None
        _cel(ws, f"A{linha}", l.codigo, F_ROTULO, fill)
        _mesclar(ws, f"B{linha}:C{linha}", l.descricao, F_NORMAL, fill)
        _cel(ws, f"D{linha}", _num(l.frequencia), F_NORMAL, fill)
        _cel(ws, f"E{linha}", float(l.tempo), F_NORMAL, fill, FMT_4)
        linha += 1
    ultima = linha - 1
    _cel(ws, f"A{linha}", "TP", F_ROTULO, CINZA)
    _mesclar(ws, f"B{linha}:D{linha}", "Tempo total da operação (min)", F_ROTULO, CINZA)
    # TP como fórmula SUMPRODUCT (soma de frequência × tempo): o regulamento exige o TP e o gabarito não tinha essa linha.
    _cel(ws, f"E{linha}", f"=SUMPRODUCT(D8:D{ultima},E8:E{ultima})", F_ROTULO, CINZA, FMT_4)

    ws.row_dimensions[1].height = ALTURA_TITULO_POL * 72
    ws.row_dimensions[3].height = ALTURA_CABECALHO_POL * 72
    for r in [2, *range(4, linha + 1)]:
        ws.row_dimensions[r].height = max(ALTURA_LINHA_POL * 72, 15)
    # Configura a impressão: sem linhas de grade, retrato e caber numa página de largura.
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.print_area = f"A1:E{linha}"
    return linha


# Aba extra com indicadores, comparação entre máquinas e rastreabilidade. Não altera a aba PO.
def preencher_aba_analise(ws, ficha: FichaPO, cadastros: Cadastros | None) -> None:
    ws.title = "Análise"
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 16
    linhas: list[tuple] = [
        ("Indicadores (informativos, não alteram a PO)", None, None),
        ("TP - tempo total (min)", float(ficha.tp), FMT_4),
        ("Tempo FIXO (min)", float(ficha.fixo), FMT_4),
        ("Tempo manual MTM (min)", float(ficha.tempo_manual), FMT_4),
        ("Capacidade (peças/hora a 100%)", float(pecas_por_hora(ficha.tp)), "0.0"),
    ]
    chk = checagem_agulha(ficha)
    if chk:
        linhas += [
            ("Total de pontos (perímetro x pontos/cm)", int(chk.total_pontos), "0"),
            ("Tempo puro de agulha a RPM padrão (min)", float(chk.tempo_agulha_min), FMT_4),
            ("Agulha ativa / tempo FIXO (%)", float(chk.percentual_do_fixo), "0.0"),
        ]
    r = 1
    for rot, val, fmt in linhas:
        ws.cell(r, 1, rot).font = F_ROTULO if val is None else F_NORMAL
        if val is not None:
            ws.cell(r, 2, val).number_format = fmt
        r += 1

    # A comparação e a origem dos cadastros só aparecem quando os cadastros são informados.
    if cadastros:
        r += 1
        ws.cell(r, 1, "Comparação entre máquinas (mesmo roteiro)").font = F_ROTULO
        r += 1
        for col, txt in enumerate(["Máquina", "FIXO (min)", "TP (min)", "Peças/hora"], 1):
            c = ws.cell(r, col, txt)
            c.font, c.fill, c.border = F_ROTULO, CINZA, BORDA
        for cen in comparar_maquinas(ficha.demanda, cadastros):
            r += 1
            vals = [cen.nome + (" (selecionada)" if cen.atual else ""), float(cen.fixo), float(cen.tp), float(cen.pecas_hora)]
            for col, v in enumerate(vals, 1):
                c = ws.cell(r, col, v)
                c.border = BORDA
                c.number_format = FMT_4 if col in (2, 3) else "0.0"
        r += 2
        ws.cell(r, 1, "Rastreabilidade").font = F_ROTULO
        ws.cell(r + 1, 1, "Cadastros utilizados")
        ws.cell(r + 1, 2, cadastros.origem)
    ws.cell(r + 2, 1, "Gerado em")
    ws.cell(r + 2, 2, agora().strftime("%d/%m/%Y %H:%M"))
    ws.cell(r + 3, 1, "Gerado por")
    ws.cell(r + 3, 2, "Auto-T&M")
    for aviso_i, aviso in enumerate(ficha.avisos):
        ws.cell(r + 5 + aviso_i, 1, f"Aviso: {aviso}")


# O openpyxl grava fórmulas sem o valor calculado. Visualizadores, ERPs e o pandas mostrariam a célula vazia.
# Aqui o XML da planilha é editado para incluir o valor de cada fórmula (o mesmo calculado pelo motor).
def _gravar_valores_das_formulas(xlsx: bytes, planilha: str, valores: dict[str, Decimal]) -> bytes:
    entrada = zipfile.ZipFile(io.BytesIO(xlsx))
    xml = entrada.read(planilha).decode("utf-8")
    for ref, valor in valores.items():
        # Acha a célula da fórmula com o valor vazio (<v/>) e coloca o valor dentro.
        padrao = rf'(<c r="{ref}"[^>]*>\s*<f>[^<]*</f>\s*)<v\s*/>'
        xml, n = re.subn(padrao, rf"\g<1><v>{_num(valor)}</v>", xml)
        # Se o formato do arquivo mudar e a célula não for encontrada, falha alto em vez de gerar arquivo errado.
        if n != 1:
            raise RuntimeError(f"Célula de fórmula {ref} não encontrada ao gravar o cache.")
    saida = io.BytesIO()
    # O .xlsx é um ZIP: recria o arquivo copiando tudo e trocando só a planilha editada.
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as z:
        for item in entrada.infolist():
            z.writestr(item, xml.encode("utf-8") if item.filename == planilha else entrada.read(item.filename))
    return saida.getvalue()


# Função pública: monta as duas abas, salva em memória e grava os valores das fórmulas.
def gerar_xlsx(ficha: FichaPO, cadastros: Cadastros | None = None) -> bytes:
    wb = Workbook()
    linha_tp = preencher_aba_po(wb.active, ficha)
    preencher_aba_analise(wb.create_sheet(), ficha, cadastros)
    # Pede ao Excel para recalcular tudo ao abrir, garantindo que as fórmulas fiquem atualizadas.
    wb.calculation = CalcProperties(fullCalcOnLoad=True)
    buf = io.BytesIO()
    wb.save(buf)
    return _gravar_valores_das_formulas(
        buf.getvalue(),
        "xl/worksheets/sheet1.xml",
        {"C6": ficha.rpm_limite_inferior, "E6": ficha.rpm_limite_superior, f"E{linha_tp}": ficha.tp},
    )
