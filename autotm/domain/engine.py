# Motor de cálculo: aplica a fórmula do regulamento.
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from .models import Cadastros, Demanda, ErroValidacao, FichaPO, LinhaPO

# Constantes da regra: 4 casas decimais (como no gabarito) e RPM ±10%.
CASAS_TEMPO = Decimal("0.0001")
FATOR_RPM_INFERIOR = Decimal("0.9")
FATOR_RPM_SUPERIOR = Decimal("1.1")
# Acima de 10 min de FIXO, provavelmente o perímetro veio em cm em vez de metros: gera aviso, não erro.
LIMITE_FIXO_PLAUSIVEL = Decimal(10)


# Arredondamento "meio para cima" (ROUND_HALF_UP), o mesmo da conta no papel e do Excel.
# O padrão do Python (ROUND_HALF_EVEN) arredondaria 0,00005 para baixo em alguns casos.
def arredondar(valor: Decimal, casas: Decimal = CASAS_TEMPO) -> Decimal:
    return valor.quantize(casas, rounding=ROUND_HALF_UP)


# Mostra 4500 em vez de 4500.0 quando o resultado do RPM é inteiro.
def _inteiro_se_possivel(valor: Decimal) -> Decimal:
    return valor.to_integral_value() if valor == valor.to_integral_value() else valor


# Confere tudo e devolve TODOS os erros de uma vez, em vez de parar no primeiro.
def validar(demanda: Demanda, cadastros: Cadastros) -> list[tuple[str, str]]:
    erros: list[tuple[str, str]] = []
    if demanda.perimetro_m is None or demanda.perimetro_m <= 0:
        erros.append(("Perímetro de costura", "deve ser maior que zero (em metros)."))
    if demanda.pontos_cm is not None and demanda.pontos_cm < 0:
        erros.append(("Pontos/cm", "não pode ser negativo."))
    # Máquina inexistente: a mensagem já lista as disponíveis, para o usuário corrigir sem procurar.
    if demanda.cod_maquina not in cadastros.maquinas:
        disponiveis = ", ".join(
            f"{m.codigo} ({m.tipo} {m.descricao})" for m in cadastros.maquinas.values()
        )
        erros.append(
            ("Cód. Eqp.", f"máquina '{demanda.cod_maquina}' não cadastrada. Disponíveis: {disponiveis}.")
        )
    if not demanda.roteiro:
        erros.append(("Elementos", "informe ao menos um código MTM no roteiro."))
    # start=1 porque a mensagem é para pessoas ("posição 1"), não para programadores.
    for pos, item in enumerate(demanda.roteiro, start=1):
        if item.codigo not in cadastros.elementos:
            erros.append(
                ("Elementos", f"posição {pos}: código MTM '{item.codigo}' não existe na Matriz de Elementos.")
            )
        if item.frequencia <= 0:
            erros.append(("Elementos", f"posição {pos}: frequência de '{item.codigo}' deve ser maior que zero."))
    return erros


# Função central do sistema: Demanda + Cadastros -> FichaPO.
def calcular_po(demanda: Demanda, cadastros: Cadastros) -> FichaPO:
    erros = validar(demanda, cadastros)
    if erros:
        # Nunca calcula com dado inválido: interrompe e entrega a lista completa de problemas.
        raise ErroValidacao(erros)

    maquina = cadastros.maquinas[demanda.cod_maquina]
    # FIXO = perímetro × tempo/metro (regulamento), arredondado ANTES de somar para o TP bater com o gabarito.
    fixo = arredondar(demanda.perimetro_m * maquina.tempo_por_metro)
    linhas = [LinhaPO("FIXO", "Tempo de costura", Decimal(1), fixo, fixo, fixo=True)]

    # Copia os avisos da demanda (list(...)) para não alterar a lista original.
    avisos: list[str] = list(demanda.avisos)
    vistos: set[str] = set()
    for item in demanda.roteiro:
        el = cadastros.elementos[item.codigo]
        # O tempo mostrado é o unitário; o total da linha multiplica pela frequência.
        tempo = arredondar(el.tempo)
        linhas.append(
            LinhaPO(el.codigo, el.descricao, item.frequencia, tempo, arredondar(tempo * item.frequencia))
        )
        # Elemento repetido no roteiro pode ser intencional, por isso é só aviso.
        if item.codigo in vistos:
            avisos.append(f"O elemento {item.codigo} aparece mais de uma vez no roteiro.")
        vistos.add(item.codigo)

    # TP = FIXO + Σ (tempo MTM × frequência). Soma de valores já arredondados: TP = soma do que aparece na ficha.
    tp = sum((l.tempo_total for l in linhas), Decimal(0))
    if fixo > LIMITE_FIXO_PLAUSIVEL:
        avisos.append(
            f"Tempo FIXO de {fixo} min é alto para uma operação de costura: confira se o perímetro "
            f"({demanda.perimetro_m} m) está em metros."
        )
    return FichaPO(
        demanda=demanda,
        maquina=maquina,
        rpm_limite_inferior=_inteiro_se_possivel(maquina.rpm * FATOR_RPM_INFERIOR),
        rpm_limite_superior=_inteiro_se_possivel(maquina.rpm * FATOR_RPM_SUPERIOR),
        linhas=linhas,
        tp=tp,
        avisos=avisos,
    )
