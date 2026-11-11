# Lê uma ficha PO já pronta (no layout do gabarito) e extrai o rascunho e os valores de cada célula.
# Usado para regerar uma PO existente e, principalmente, pela auditoria.
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from .normalizacao import chave, codigo_mtm, codigo_simples, para_decimal


# Um valor lido da ficha junto com o nome do item e a célula de origem (ex.: "E8"), para apontar onde está o erro.
@dataclass
class ValorLido:
    item: str
    celula: str
    valor: object


# Resultado da leitura: o rascunho (para recalcular), as linhas de elementos e os valores conferíveis.
@dataclass
class FichaLida:
    rascunho: dict
    linhas: list[dict] = field(default_factory=list)
    valores: dict[str, ValorLido] = field(default_factory=dict)


# Converte posição (linha, coluna) começando em 0 para referência de Excel: (7, 4) -> "E8".
def _ref(linha: int, coluna: int) -> str:
    letras = ""
    coluna += 1
    # Mesma lógica de números em base 26 (A..Z, AA..AZ...), com o ajuste -1 porque não existe "letra zero".
    while coluna:
        coluna, resto = divmod(coluna - 1, 26)
        letras = chr(65 + resto) + letras
    return f"{letras}{linha + 1}"


def _vazio(v: object) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or not str(v).strip()


# Procura uma célula cujo texto comece com o prefixo; achar pelo texto (e não por posição fixa) tolera fichas deslocadas.
def _achar(df: pd.DataFrame, *prefixos: str) -> tuple[int, int] | None:
    for i in range(min(len(df), 60)):
        for j in range(df.shape[1]):
            k = chave(df.iat[i, j]) if not _vazio(df.iat[i, j]) else ""
            if k and any(k.startswith(p) for p in prefixos):
                return i, j
    return None


# É ficha PO se tiver o cabeçalho "Código do elemento" e uma linha "FIXO".
def parece_ficha_po(df: pd.DataFrame) -> bool:
    return _achar(df, "codigodoelemento") is not None and _achar(df, "fixo") is not None


# Valor da primeira célula preenchida à direita do rótulo (células mescladas deixam vazias no meio).
def _proximo_a_direita(df: pd.DataFrame, i: int, j: int):
    for jj in range(j + 1, df.shape[1]):
        if not _vazio(df.iat[i, jj]):
            return df.iat[i, jj], jj
    return None, None


# Numa linha de rótulos, devolve {rótulo: (valor logo abaixo, coluna)}: é assim que o gabarito organiza os dados.
def _valores_abaixo(df: pd.DataFrame, i_cab: int) -> dict[str, tuple[object, int]]:
    out = {}
    for j in range(df.shape[1]):
        rot = df.iat[i_cab, j]
        if not _vazio(rot) and i_cab + 1 < len(df):
            out[chave(rot)] = (df.iat[i_cab + 1, j], j)
    return out


# Busca no mapa pelo início do rótulo.
def _pegar(mapa: dict, *prefixos: str):
    for k, v in mapa.items():
        if any(k.startswith(p) for p in prefixos):
            return v
    return (None, None)


# Lê a ficha bloco a bloco, sempre localizando os rótulos pelo texto.
def ler_ficha_po(df: pd.DataFrame) -> FichaLida:
    r: dict = {}
    valores: dict[str, ValorLido] = {}

    # Título: a primeira célula preenchida da ficha; a revisão vem de "Rev. 00" na mesma linha.
    for i in range(min(len(df), 10)):
        cels = [(j, df.iat[i, j]) for j in range(df.shape[1]) if not _vazio(df.iat[i, j])]
        if cels:
            r["titulo"] = str(cels[0][1]).strip()
            for _, v in cels[1:]:
                if m := re.search(r"rev\.?\s*(\w+)", str(v), re.IGNORECASE):
                    r["revisao"] = m.group(1)
            break

    # Operação: o valor à direita do rótulo.
    if pos := _achar(df, "operacao"):
        v, _ = _proximo_a_direita(df, *pos)
        r["operacao"] = "" if v is None else str(v)

    # Bloco da peça: família, tamanho, medidas, pontos/cm e perímetro, cada um abaixo do seu rótulo.
    if pos := _achar(df, "agrupamentofamilia", "familia"):
        mapa = _valores_abaixo(df, pos[0])
        for campo, prefixos in [
            ("familia", ("agrupamento", "familia")),
            ("tamanho", ("tamanho",)),
            ("medidas", ("medidas",)),
            ("pontos_cm", ("pontos",)),
            ("perimetro_m", ("perimetro",)),
        ]:
            v, _ = _pegar(mapa, *prefixos)
            if not _vazio(v):
                r[campo] = v

    # Bloco da máquina: código, nome e RPMs; guarda as células para a auditoria conferir.
    if pos := _achar(df, "codeqp", "codigodamaquina", "equipamento"):
        i = pos[0]
        mapa = _valores_abaixo(df, i)
        cod, j = _pegar(mapa, "codeqp", "codigo")
        if not _vazio(cod):
            r["cod_maquina"] = codigo_simples(cod)
        for chave_logica, prefixos, rotulo in [
            ("equipamento", ("equipamento",), "Equipamento"),
            ("rpm_inferior", ("rpmlimiteinferior",), "RPM limite inferior"),
            ("rpm_padrao", ("rpmpadrao",), "RPM padrão"),
            ("rpm_superior", ("rpmlimitesuperior",), "RPM limite superior"),
        ]:
            v, jj = _pegar(mapa, *prefixos)
            if jj is not None and not _vazio(v):
                valores[chave_logica] = ValorLido(rotulo, _ref(i + 1, jj), v)

    linhas: list[dict] = []
    # Tabela de elementos: lê linha a linha até uma linha vazia ou a linha de TP.
    if pos := _achar(df, "codigodoelemento"):
        i_cab, j_cod = pos
        cab = {chave(df.iat[i_cab, j]): j for j in range(df.shape[1]) if not _vazio(df.iat[i_cab, j])}
        j_desc = next((j for k, j in cab.items() if k.startswith("elementos")), j_cod + 1)
        j_freq = next((j for k, j in cab.items() if k.startswith("freq")), None)
        j_tempo = next((j for k, j in cab.items() if k.startswith("tempo")), None)
        for i in range(i_cab + 1, len(df)):
            cod = df.iat[i, j_cod]
            if _vazio(cod):
                break
            # A linha de TP não é elemento: só guarda o valor para conferência.
            if chave(cod) == "tp":
                if j_tempo is not None and not _vazio(df.iat[i, j_tempo]):
                    valores["tp"] = ValorLido("TP (tempo total)", _ref(i, j_tempo), df.iat[i, j_tempo])
                break
            linhas.append(
                {
                    "codigo": "FIXO" if chave(cod) == "fixo" else codigo_mtm(cod),
                    "descricao": "" if _vazio(df.iat[i, j_desc]) else str(df.iat[i, j_desc]).strip(),
                    "frequencia": para_decimal(df.iat[i, j_freq]) if j_freq is not None else None,
                    "tempo": df.iat[i, j_tempo] if j_tempo is not None else None,
                    "cel_desc": _ref(i, j_desc),
                    "cel_tempo": _ref(i, j_tempo) if j_tempo is not None else "",
                }
            )
    # Remonta o roteiro em texto (sem o FIXO, que é calculado) para recalcular a ficha.
    manuais = [l for l in linhas if l["codigo"] != "FIXO"]
    r["roteiro"] = ", ".join(
        l["codigo"] if not l["frequencia"] or l["frequencia"] == 1 else f"{l['codigo']}x{l['frequencia'].normalize()}"
        for l in manuais
    )
    return FichaLida(rascunho=r, linhas=linhas, valores=valores)
