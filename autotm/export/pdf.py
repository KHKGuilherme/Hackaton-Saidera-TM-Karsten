# Gera a ficha em PDF (A4) com o mesmo layout do gabarito, usando a biblioteca fpdf2.
from __future__ import annotations

from ..relogio import agora
from decimal import Decimal

from fpdf import FPDF

from ..domain.analise import pecas_por_hora
from ..domain.models import FichaPO

# Mesmas proporções de coluna do Excel, distribuídas nos 190 mm úteis da folha A4.
_POL = [1.5311, 2.0102, 1.3854, 1.1146, 1.7083]
LARG = [round(p / sum(_POL) * 190, 2) for p in _POL]
H = 7.0
CINZA = (217, 217, 217)
AMARELO = (255, 255, 0)


# As fontes padrão do PDF só têm caracteres latin-1: troca travessões e substitui o que não existir.
def _latin1(texto: str) -> str:
    return str(texto).replace("—", "-").replace("–", "-").encode("latin-1", "replace").decode("latin-1")


def _fmt(v: Decimal | None, casas: int) -> str:
    return "" if v is None else f"{v:.{casas}f}"


def _inteiro(v: Decimal) -> str:
    return str(int(v)) if v == v.to_integral_value() else f"{v.normalize()}"


# Extensão do FPDF com dois atalhos: célula com borda e linha de cabeçalho cinza.
class _PDF(FPDF):
    def celula(self, w, txt, bold=False, fill=None, size=9, h=H):
        self.set_font("Helvetica", "B" if bold else "", size)
        if fill:
            self.set_fill_color(*fill)
        self.cell(w, h, _latin1(txt), border=1, align="C", fill=bool(fill))

    # Cabeçalho com quebra de linha manual ("\n") e texto centralizado na vertical, coisa que cell() sozinho não faz.
    def cabecalho(self, textos, h=H):
        y = self.get_y()
        x = self.l_margin
        for w, t in zip(LARG, textos):
            self.set_xy(x, y)
            self.set_font("Helvetica", "B", 8)
            self.set_fill_color(*CINZA)
            self.rect(x, y, w, h, style="DF")
            linhas = t.split("\n")
            lh = 3.6
            topo = y + (h - lh * len(linhas)) / 2
            for i, l in enumerate(linhas):
                self.set_xy(x, topo + i * lh)
                self.cell(w, lh, _latin1(l), align="C")
            x += w
        self.set_xy(self.l_margin, y + h)


# Desenha a ficha bloco a bloco: título, operação, peça, máquina e elementos.
def gerar_pdf(ficha: FichaPO) -> bytes:
    d, m = ficha.demanda, ficha.maquina
    pdf = _PDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(10, 12, 10)
    pdf.add_page()
    pdf.set_draw_color(0, 0, 0)
    a, b, c, dd, e = LARG

    pdf.celula(a + b + c + dd, d.titulo, bold=True, size=16, h=13)
    pdf.celula(e, f"Rev. {d.revisao}", bold=True, size=16, h=13)
    pdf.ln()
    pdf.celula(a, "Operação", bold=True, fill=CINZA)
    pdf.celula(b + c + dd + e, d.operacao)
    pdf.ln()
    pdf.cabecalho(["Agrupamento família", "Tamanho", "Medidas da peça\n(em m)", "Pontos/cm", "Perímetro costura\n(em m)"], h=10)
    for w, t in zip(LARG, [d.familia, d.tamanho, d.medidas, _fmt(d.pontos_cm, 2), _fmt(d.perimetro_m, 2)]):
        pdf.celula(w, t)
    pdf.ln()
    pdf.cabecalho(["Cód. Eqp.", "Equipamento", "RPM - limite\ninferior", "RPM - padrão", "RPM - limite\nsuperior"], h=10)
    for w, t in zip(
        LARG,
        [m.codigo, m.tipo or m.descricao, _inteiro(ficha.rpm_limite_inferior), _inteiro(m.rpm), _inteiro(ficha.rpm_limite_superior)],
    ):
        pdf.celula(w, t)
    pdf.ln()
    pdf.cabecalho(["Código do\nelemento", "Elementos", "", "Frequência", "Tempos\n(em minutos)"], h=10)
    # Redesenha "Elementos" ocupando as colunas B+C, imitando a célula mesclada do gabarito.
    y = pdf.get_y() - 10
    pdf.set_fill_color(*CINZA)
    pdf.rect(pdf.l_margin + a, y, b + c, 10, style="DF")
    pdf.set_xy(pdf.l_margin + a, y)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(b + c, 10, "Elementos", align="C")
    pdf.set_xy(pdf.l_margin, y + 10)

    for l in ficha.linhas:
        fill = AMARELO if l.fixo else None
        pdf.celula(a, l.codigo, bold=True, fill=fill)
        # Descrição longa usa fonte menor para caber na célula.
        pdf.celula(b + c, l.descricao, fill=fill, size=8 if len(l.descricao) > 45 else 9)
        pdf.celula(dd, _inteiro(l.frequencia), fill=fill)
        pdf.celula(e, _fmt(l.tempo, 4), fill=fill)
        pdf.ln()
    pdf.celula(a, "TP", bold=True, fill=CINZA)
    pdf.celula(b + c + dd, "Tempo total da operação (min)", bold=True, fill=CINZA)
    pdf.celula(e, _fmt(ficha.tp, 4), bold=True, fill=CINZA)
    pdf.ln(12)

    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(90, 90, 90)
    # Rodapé com a memória de cálculo (FIXO e TP) e a data de geração: quem lê o PDF entende de onde vêm os números.
    pdf.multi_cell(
        0,
        4,
        _latin1(
            f"FIXO = perímetro {d.perimetro_m} m x {m.tempo_por_metro} min/m ({m.tipo} {m.descricao}) = {ficha.fixo:.4f} min.  "
            f"TP = FIXO + soma(tempo x frequência) = {ficha.tp:.4f} min.  "
            f"Capacidade teórica: {pecas_por_hora(ficha.tp)} peças/hora.\n"
            f"Gerado por Auto-T&M em {agora():%d/%m/%Y %H:%M}."
        ),
    )
    return bytes(pdf.output())
