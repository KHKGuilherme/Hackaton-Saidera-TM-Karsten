# Interpreta um pedido escrito livremente (estilo WhatsApp) e preenche um rascunho.
# Determinístico e offline (expressões regulares, sem IA): o mesmo texto dá sempre o mesmo resultado.
# O resultado é só um rascunho: passa pelo formulário de revisão e pela mesma validação.
from __future__ import annotations

import re

from ..domain.models import Cadastros
from .cadastros import resolver_maquina
from .demandas import ROTULOS, formatar_roteiro, parse_roteiro
from .normalizacao import chave, sem_acentos

# Número com decimal opcional, com vírgula ou ponto.
NUM = r"\d+(?:[.,]\d+)?"

# Famílias de produto reconhecidas. Os nomes compostos vêm antes dos simples ("toalha de banho" antes de "toalha").
FAMILIAS = [
    "sobre-lençol",
    "protetor de colchão",
    "saia de cama",
    "toalha de banho",
    "toalha de rosto",
    "toalha de piso",
    "toalha de mesa",
    "jogo de cama",
    "lençol",
    "fronha",
    "toalha",
    "edredom",
    "colcha",
    "cobertor",
    "manta",
    "travesseiro",
    "roupão",
    "guardanapo",
]
# Mesma lógica: "super king" e "solteirão" antes de "king" e "solteiro".
TAMANHOS = ["super king", "solteirão", "solteiro", "casal", "queen", "king", "berço", "infantil", "baby"]


# Devolve o primeiro termo da lista que aparece como palavra inteira (\b) no texto.
def _achar_termo(texto_norm: str, termos: list[str]) -> str:
    for t in termos:
        tn = sem_acentos(t).lower()
        if re.search(rf"\b{re.escape(tn)}\b", texto_norm):
            return t[0].upper() + t[1:]
    return ""


# Volta o número ao formato brasileiro (vírgula) para exibir no formulário.
def _br(valor: str) -> str:
    return valor.replace(".", ",")


# Procura cada campo com uma expressão regular própria. norm = texto sem acento e minúsculo, para simplificar as buscas.
def extrair_texto_livre(texto: str, cadastros: Cadastros) -> tuple[dict, list[str]]:
    original = texto
    norm = sem_acentos(texto).lower()
    r: dict = {}
    # Trechos já usados por algum campo, para o mesmo número não ser lido duas vezes (ex.: medidas virando perímetro).
    usados: list[tuple[int, int]] = []

    def marcar(m: re.Match, grupo: int | str = 0):
        usados.append(m.span(grupo))

    # Título no padrão PO-SL-001 (também "po sl 1"). := atribui e testa na mesma linha.
    if m := re.search(r"\bPO[-\s]?[A-Z]{1,4}[-\s]?\d{1,4}\b", original, re.IGNORECASE):
        r["titulo"] = re.sub(r"\s", "-", m.group(0).upper())
        marcar(m)

    # Revisão: "rev 1", "revisão: 01"; zfill(2) completa com zero à esquerda.
    if m := re.search(r"\brev(?:isao)?\.?\s*[:#]?\s*(\d{1,3})\b", norm):
        r["revisao"] = m.group(1).zfill(2)
        marcar(m)

    # Operação: preferência pelo texto entre aspas; senão, o que vem depois de "operação:".
    if m := re.search(r"opera[çc][ãa]o\s*[:\-]?\s*[\"“](.+?)[\"”]", original, re.IGNORECASE) or re.search(
        r"[\"“](.+?)[\"”]", original
    ):
        r["operacao"] = m.group(1).strip()
    elif m := re.search(r"opera[çc][ãa]o\s*[:\-]\s*([^,;\n.]+)", original, re.IGNORECASE):
        r["operacao"] = m.group(1).strip()

    # Medidas "1,80 x 2,50": exige decimal dos dois lados para não confundir com um roteiro "4.1x2".
    dec = r"\d+[.,]\d+"
    if m := re.search(rf"({dec})\s*m?\s*[x×]\s*({dec})\s*m?\b", norm):
        r["medidas"] = f"{_br(m.group(1))} x {_br(m.group(2))}"
        marcar(m)

    # Pontos por cm: "2,5 pontos/cm" ou "densidade 2,5".
    if m := re.search(rf"({NUM})\s*(?:pontos|pts|pt)\s*(?:/|por)\s*cm", norm) or re.search(
        rf"(?:densidade|pontos/cm|pts/cm)[^0-9]{{0,20}}({NUM})", norm
    ):
        r["pontos_cm"] = _br(m.group(1))
        marcar(m)

    # Perímetro: primeiro procura a palavra "perímetro" seguida do número (com unidade opcional)...
    if m := re.search(rf"(?:perimetro|comprimento)[^0-9]{{0,30}}({NUM})\s*(cm|mm|centimetros?|milimetros?)?\b", norm):
        r["perimetro_m"] = _br(m.group(1)) + (f" {m.group(2)}" if m.group(2) else "")
        marcar(m, 1)
    else:
        # ...senão, o primeiro número com "m" que não tenha sido usado por outro campo.
        for m in re.finditer(rf"({NUM})\s*(?:m|metros?)\b", norm):
            if not any(a <= m.start() < b for a, b in usados):
                r["perimetro_m"] = _br(m.group(1))
                marcar(m)
                break

    # Máquina: "máquina 2", "eqp: 1"; senão procura o nome de uma máquina cadastrada no texto.
    if m := re.search(r"(?:maquina|maq\.?|eqp\.?|equipamento)\s*(?:n[ºo°]?\.?|#|:|=|cod(?:igo)?\.?)?\s*(\d+)\b", norm):
        r["cod_maquina"] = m.group(1)
        marcar(m)
    else:
        for maq in cadastros.maquinas.values():
            if chave(maq.descricao) and chave(maq.descricao) in chave(norm):
                r["cod_maquina"] = maq.codigo
                break
        else:
            cod = resolver_maquina(norm, cadastros)
            if cod in cadastros.maquinas:
                r["cod_maquina"] = cod

    avisos: list[str] = []
    # Roteiro: um item é "2.1", "4.1x2" ou "4.1(2)"; a lista são itens separados por , ; -> ou "e".
    item = r"\d+\.\d+(?:\s*[x×*]\s*\d+|\s*\(\s*\d+\s*\))?"
    lista = rf"{item}(?:\s*(?:,|;|->|>|\be\b)?\s*{item})*"
    # Preferência pela lista que vem depois de "elementos:" / "roteiro:"...
    if m := re.search(rf"(?:elementos?|roteiro|sequencia|operacoes|passos|mtm)\s*[:\-]?\s*({lista})", norm):
        trecho = m.group(1).strip(" .;")
    else:
        # ...senão, junta os códigos soltos no texto que existem na Matriz MTM.
        livres = [
            mm
            for mm in re.finditer(r"\b\d+\.\d+(?:\s*[x×*]\s*\d+)?\b", norm)
            if not any(a <= mm.start() < b for a, b in usados) and mm.group(0).split("x")[0].strip() in cadastros.elementos
        ]
        trecho = ", ".join(mm.group(0) for mm in livres)
    if trecho:
        try:
            r["roteiro"] = formatar_roteiro(parse_roteiro(trecho))
        # Se o roteiro não puder ser interpretado, mantém o texto cru e avisa: o usuário corrige na revisão.
        except Exception:
            r["roteiro"] = trecho
            avisos.append("Não consegui interpretar todo o roteiro; revise o campo Elementos.")

    if fam := _achar_termo(norm, FAMILIAS):
        r["familia"] = fam
    if tam := _achar_termo(norm, TAMANHOS):
        r["tamanho"] = tam

    # Avisa o que faltou: obrigatórios e opcionais em mensagens separadas.
    for campo in ("perimetro_m", "cod_maquina", "roteiro"):
        if not r.get(campo):
            avisos.append(f"Campo obrigatório não encontrado no texto: {ROTULOS[campo]}.")
    for campo in ("titulo", "operacao", "familia", "tamanho", "pontos_cm"):
        if not r.get(campo):
            avisos.append(f"Campo não identificado (opcional): {ROTULOS[campo]}.")
    return r, avisos
