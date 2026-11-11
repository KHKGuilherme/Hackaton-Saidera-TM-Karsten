# Caso de uso: auditar uma ficha existente. Lê a ficha, recalcula do zero e compara célula por célula.
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..domain.engine import calcular_po
from ..domain.models import Cadastros, ErroValidacao, FichaPO
from ..ingestion.demandas import ler_abas, montar_demanda
from ..ingestion.ficha_po import FichaLida, ler_ficha_po, parece_ficha_po
from ..ingestion.normalizacao import chave, para_decimal

# Meia unidade da 4ª casa: diferenças menores são só arredondamento de exibição, não erro.
TOLERANCIA = Decimal("0.00005")


# Uma linha do relatório: o item, a célula, o valor da ficha, o valor certo, se confere e o motivo.
@dataclass
class Conferencia:
    item: str
    celula: str
    na_ficha: str
    calculado: str
    ok: bool
    motivo: str = ""


# Resultado de uma ficha auditada: a ficha recalculada (que serve como versão corrigida) e as conferências.
@dataclass
class ResultadoAuditoria:
    origem: str
    ficha_recalculada: FichaPO | None
    conferencias: list[Conferencia] = field(default_factory=list)
    erros: list[tuple[str, str]] = field(default_factory=list)
    observacoes: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.conferencias)

    @property
    def divergencias(self) -> list[Conferencia]:
        return [c for c in self.conferencias if not c.ok]

    # Percentual de itens que conferem, com 1 casa.
    @property
    def conformidade(self) -> Decimal:
        if not self.conferencias:
            return Decimal(0)
        return (Decimal(self.total - len(self.divergencias)) / self.total * 100).quantize(Decimal("0.1"))


# Formata o valor para exibir no relatório: 4 casas para tempos, inteiro para RPM.
def _fmt(v: object, casas: int = 4) -> str:
    d = para_decimal(v)
    if d is None:
        return "" if v is None else str(v)
    return f"{d:.{casas}f}" if casas else (str(int(d)) if d == d.to_integral_value() else str(d))


# Compara números dentro da tolerância; texto que não é número conta como divergência.
def _num_ok(lido: object, esperado: Decimal) -> bool:
    d = para_decimal(lido)
    return d is not None and abs(d - esperado) <= TOLERANCIA


# Recalcula a ficha a partir dos dados que ela mesma traz e compara cada valor com o recálculo.
def auditar_ficha(lida: FichaLida, cadastros: Cadastros, origem: str) -> ResultadoAuditoria:
    try:
        ficha = calcular_po(montar_demanda(lida.rascunho, cadastros), cadastros)
    # Se nem dá para recalcular (ex.: máquina inexistente), devolve os erros em vez de conferências.
    except ErroValidacao as e:
        return ResultadoAuditoria(origem, None, erros=e.erros)

    res = ResultadoAuditoria(origem, ficha)
    add = res.conferencias.append
    m = ficha.maquina

    # Equipamento: aceita o tipo, a descrição ou os dois juntos.
    if v := lida.valores.get("equipamento"):
        ok = chave(v.valor) in {chave(m.tipo), chave(m.descricao), chave(f"{m.tipo} {m.descricao}")}
        add(Conferencia("Equipamento", v.celula, str(v.valor), m.tipo or m.descricao, ok,
                        "" if ok else "não corresponde à máquina do cadastro"))
    # RPMs da ficha contra o cadastro de máquinas.
    for chave_logica, rotulo, esperado in [
        ("rpm_inferior", "RPM limite inferior", ficha.rpm_limite_inferior),
        ("rpm_padrao", "RPM padrão", m.rpm),
        ("rpm_superior", "RPM limite superior", ficha.rpm_limite_superior),
    ]:
        if v := lida.valores.get(chave_logica):
            ok = _num_ok(v.valor, esperado)
            add(Conferencia(rotulo, v.celula, _fmt(v.valor, 0), _fmt(esperado, 0), ok,
                            "" if ok else "difere do cadastro de máquinas"))

    # Para cada linha da ficha, busca a linha recalculada do mesmo código e confere descrição e tempo.
    calculadas = {l.codigo: l for l in ficha.linhas}
    for lin in lida.linhas:
        calc = calculadas.get(lin["codigo"])
        if calc is None:
            continue
        nome = "FIXO (tempo de costura)" if calc.fixo else f"Elemento {calc.codigo}"
        if not calc.fixo:
            ok_desc = chave(lin["descricao"]) == chave(calc.descricao)
            add(Conferencia(f"{nome}: descrição", lin["cel_desc"], lin["descricao"], calc.descricao, ok_desc,
                            "" if ok_desc else "descrição diferente da Matriz MTM"))
        if lin["cel_tempo"]:
            ok_t = _num_ok(lin["tempo"], calc.tempo)
            motivo = ""
            if not ok_t:
                # O motivo mostra a conta certa, para o usuário entender de onde vem o valor correto.
                motivo = (f"perímetro × tempo/metro = {ficha.demanda.perimetro_m} × {m.tempo_por_metro}"
                          if calc.fixo else "tempo diferente da Matriz MTM")
            add(Conferencia(f"{nome}: tempo (min)", lin["cel_tempo"], _fmt(lin["tempo"]), f"{calc.tempo:.4f}", ok_t, motivo))

    # O gabarito oficial não tem linha de TP: nesse caso só registra o TP recalculado como observação.
    if v := lida.valores.get("tp"):
        ok = _num_ok(v.valor, ficha.tp)
        add(Conferencia("TP (tempo total)", v.celula, _fmt(v.valor), f"{ficha.tp:.4f}", ok,
                        "" if ok else "soma não confere"))
    else:
        res.observacoes.append(f"A ficha não traz linha de TP. TP recalculado: {ficha.tp:.4f} min.")
    return res


# Audita todas as abas do arquivo que tenham layout de ficha PO.
def auditar_arquivo(conteudo: bytes, nome: str, cadastros: Cadastros) -> list[ResultadoAuditoria]:
    try:
        abas = ler_abas(conteudo, nome)
    except Exception as e:
        return [ResultadoAuditoria(nome, None, erros=[("Arquivo", f"não foi possível ler '{nome}': {e}")])]
    resultados = [
        auditar_ficha(ler_ficha_po(df), cadastros, f"{nome}" + (f" (aba {aba})" if len(abas) > 1 else ""))
        for aba, df in abas.items()
        if parece_ficha_po(df)
    ]
    if not resultados:
        resultados.append(
            ResultadoAuditoria(nome, None, erros=[("Arquivo", f"'{nome}' não tem nenhuma aba no layout de ficha PO.")])
        )
    return resultados
