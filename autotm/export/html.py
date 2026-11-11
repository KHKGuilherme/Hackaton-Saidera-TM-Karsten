# Desenha a ficha em HTML para a pré-visualização na tela, imitando o layout do gabarito.
from __future__ import annotations

from decimal import Decimal
from html import escape

from ..domain.models import FichaPO

# Estilo da ficha: fundo branco e bordas pretas como no papel, nos dois temas; cinza nos rótulos e amarelo no FIXO.
# --sombra-folha vem do tema da interface (com valor padrão caso a variável não exista).
CSS = """
<style>
.po-wrap{background:#fff;padding:16px;border-radius:6px;box-shadow:var(--sombra-folha,0 6px 20px rgba(0,0,0,.2));box-sizing:border-box;width:100%}
.po{border-collapse:collapse;width:100%;table-layout:fixed;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#000}
.po td{border:1px solid #000;text-align:center;vertical-align:middle;padding:4px 3px;overflow-wrap:anywhere}
.po .tit{font-size:20px;font-weight:700;height:44px}
.po .rot{background:#d9d9d9;font-weight:700;font-size:12px}
.po .fixo{background:#ffff00}
.po .b{font-weight:700}
.po .tp td{background:#d9d9d9;font-weight:700;font-size:14px}
@media (max-width:560px){.po{font-size:10.5px}.po .tit{font-size:16px}.po-wrap{padding:6px}}
</style>
"""


# Número com casas fixas (vazio se não houver valor).
def _n(v: Decimal | None, casas: int) -> str:
    return "" if v is None else f"{v:.{casas}f}"


# Inteiro sem ".0"; se tiver decimais, mostra sem zeros sobrando.
def _i(v: Decimal) -> str:
    return str(int(v)) if v == v.to_integral_value() else str(v.normalize())


# Monta a tabela linha a linha na mesma ordem do gabarito.
def ficha_html(ficha: FichaPO) -> str:
    d, m = ficha.demanda, ficha.maquina
    # Segurança: escape impede que um texto digitado (ex.: "<script>") vire código na página.
    e = lambda s: escape(str(s or ""))
    linhas = []
    for l in ficha.linhas:
        cls = ' class="fixo"' if l.fixo else ""
        linhas.append(
            f"<tr{cls}><td class='b'>{e(l.codigo)}</td><td colspan='2'>{e(l.descricao)}</td>"
            f"<td>{_i(l.frequencia)}</td><td>{_n(l.tempo, 4)}</td></tr>"
        )
    return (
        CSS
        + "<div class='po-wrap'><table class='po'>"
        # Larguras proporcionais às colunas do gabarito oficial.
        + "<colgroup><col style='width:19%'><col style='width:26%'><col style='width:18%'><col style='width:15%'><col style='width:22%'></colgroup>"
        + f"<tr><td colspan='4' class='tit'>{e(d.titulo)}</td><td class='tit'>Rev. {e(d.revisao)}</td></tr>"
        + f"<tr><td class='rot'>Operação</td><td colspan='4'>{e(d.operacao)}</td></tr>"
        + "<tr><td class='rot'>Agrupamento família</td><td class='rot'>Tamanho</td><td class='rot'>Medidas da peça (em m)</td>"
        + "<td class='rot'>Pontos/cm</td><td class='rot'>Perímetro costura<br>(em m)</td></tr>"
        + f"<tr><td>{e(d.familia)}</td><td>{e(d.tamanho)}</td><td>{e(d.medidas)}</td>"
        + f"<td>{_n(d.pontos_cm, 2)}</td><td>{_n(d.perimetro_m, 2)}</td></tr>"
        + "<tr><td class='rot'>Cód. Eqp.</td><td class='rot'>Equipamento</td><td class='rot'>RPM - limite inferior</td>"
        + "<td class='rot'>RPM - padrão</td><td class='rot'>RPM - limite superior</td></tr>"
        + f"<tr><td>{e(m.codigo)}</td><td>{e(m.tipo or m.descricao)}</td><td>{_i(ficha.rpm_limite_inferior)}</td>"
        + f"<td>{_i(m.rpm)}</td><td>{_i(ficha.rpm_limite_superior)}</td></tr>"
        + "<tr><td class='rot'>Código do elemento</td><td class='rot' colspan='2'>Elementos</td>"
        + "<td class='rot'>Frequência</td><td class='rot'>Tempos (em minutos)</td></tr>"
        + "".join(linhas)
        + f"<tr class='tp'><td>TP</td><td colspan='3'>Tempo total da operação (min)</td><td>{_n(ficha.tp, 4)}</td></tr>"
        + "</table></div>"
    )
