# Leitura dos cadastros de apoio (Matriz MTM e máquinas) a partir de planilha (.ods/.xlsx) ou JSON.
from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pandas as pd

from ..domain.models import Cadastros, ElementoMTM, ErroValidacao, Maquina
from .normalizacao import chave, codigo_mtm, codigo_simples, decodificar, inteiro_br, para_decimal

# Planilha oficial do kit, usada quando nenhum cadastro é enviado. parents[2] = raiz do projeto.
CAMINHO_PADRAO = Path(__file__).resolve().parents[2] / "kit_oficial" / "Entradas.ods"

# Títulos das colunas nas tabelas editáveis da tela.
COLUNAS_ELEMENTOS = ["Código", "Descrição", "Tempo (min)"]
COLUNAS_MAQUINAS = ["Código", "Tipo", "Descrição", "RPM", "Tempo/metro (min/m)"]


# Procura a linha do cabeçalho nas 15 primeiras linhas: planilhas reais costumam ter títulos e linhas em branco antes.
def _localizar_cabecalho(df: pd.DataFrame, obrigatorias: list[str]) -> pd.DataFrame:
    for i in range(min(len(df), 15)):
        linha = [chave(v) for v in df.iloc[i].tolist()]
        if all(any(ob in c for c in linha) for ob in obrigatorias):
            corpo = df.iloc[i + 1 :].copy()
            corpo.columns = [str(v) if pd.notna(v) else f"_col{j}" for j, v in enumerate(df.iloc[i].tolist())]
            # Remove colunas com nome repetido (mantém a primeira) para não confundir a leitura.
            corpo = corpo.loc[:, ~corpo.columns.duplicated()]
            return corpo.dropna(how="all")
    raise ErroValidacao([("Cadastros", f"cabeçalho com as colunas {obrigatorias} não encontrado nas 15 primeiras linhas.")])


# Acha a coluna pelo nome aproximado: primeiro quem COMEÇA com o candidato, depois quem o CONTÉM.
def _coluna(df: pd.DataFrame, *candidatos: str) -> str | None:
    chaves = [(col, chave(col)) for col in df.columns]
    for col, k in chaves:
        if any(k.startswith(c) for c in candidatos):
            return col
    for col, k in chaves:
        if any(c in k for c in candidatos):
            return col
    return None


# Célula vazia (None ou NaN) vira texto vazio; o resto vira texto sem espaços nas pontas.
def _texto(valor: object) -> str:
    return "" if valor is None or (isinstance(valor, float) and pd.isna(valor)) else str(valor).strip()


# Monta a Matriz MTM. Aceita o código numa coluna só ("2.1") ou separado em agrupador + elemento (2 e 1).
def elementos_de_df(df: pd.DataFrame) -> tuple[dict[str, ElementoMTM], list[str]]:
    c_desc = _coluna(df, "descricao")
    c_agr = _coluna(df, "codigodoagrupador", "agrupador")
    c_el = _coluna(df, "codigodoelemento")
    c_cod = _coluna(df, "elementoagrupador", "codigomtm", "codigo")
    c_tempo = _coluna(df, "tempo")
    if not (c_desc and c_tempo and (c_cod or (c_agr and c_el))):
        raise ErroValidacao([("Matriz MTM", "colunas esperadas: Código, Descrição, Tempo.")])
    elementos: dict[str, ElementoMTM] = {}
    erros, avisos = [], []
    # start=2: a linha 1 é o cabeçalho; assim o número bate com a linha que o usuário vê na planilha.
    for n, row in enumerate(df.to_dict("records"), start=2):
        if c_agr and c_el and pd.notna(row.get(c_agr)) and pd.notna(row.get(c_el)):
            cod = f"{codigo_simples(row[c_agr])}.{codigo_simples(row[c_el])}"
        elif c_cod and _texto(row.get(c_cod)):
            cod = codigo_mtm(row[c_cod])
        else:
            continue
        cod = codigo_mtm(cod)
        tempo = para_decimal(row.get(c_tempo))
        if tempo is None:
            erros.append(("Matriz MTM", f"linha {n}: tempo inválido para {cod}."))
            continue
        # Tempo zero é permitido (ex.: 1.1 "sem tempo"); negativo não.
        if tempo < 0:
            erros.append(("Matriz MTM", f"linha {n}: tempo negativo ({tempo}) para {cod}."))
            continue
        # Código repetido: fica a última linha e o usuário é avisado.
        if cod in elementos:
            avisos.append(f"Matriz MTM: o código {cod} aparece mais de uma vez; foi mantida a linha {n}.")
        elementos[cod] = ElementoMTM(cod, _texto(row.get(c_desc)) or f"Elemento {cod}", tempo)
    # Junta todos os erros da planilha antes de interromper.
    if erros:
        raise ErroValidacao(erros)
    if not elementos:
        raise ErroValidacao([("Matriz MTM", "nenhum elemento encontrado.")])
    return elementos, avisos


# Monta o cadastro de máquinas; mesma lógica dos elementos.
def maquinas_de_df(df: pd.DataFrame) -> tuple[dict[str, Maquina], list[str]]:
    c_cod = _coluna(df, "codigodamaquina", "codigodemaquina", "codigo", "cod")
    c_tipo = _coluna(df, "tipo")
    c_desc = _coluna(df, "descricao", "modelo")
    c_rpm = _coluna(df, "rpm")
    c_tm = _coluna(df, "tempopormetro", "tempometro", "fatordetempo", "tempo", "minm")
    if not (c_cod and c_rpm and c_tm):
        raise ErroValidacao([("Máquinas", "colunas esperadas: Código, Tipo, Descrição, RPM, Tempo por metro (min/m).")])
    maquinas: dict[str, Maquina] = {}
    erros, avisos = [], []
    for n, row in enumerate(df.to_dict("records"), start=2):
        if not _texto(row.get(c_cod)):
            continue
        cod = codigo_simples(row[c_cod])
        # RPM usa inteiro_br porque "5.000" significa cinco mil.
        rpm, tm = inteiro_br(row.get(c_rpm)), para_decimal(row.get(c_tm))
        if rpm is None or tm is None:
            erros.append(("Máquinas", f"linha {n}: RPM ou tempo por metro inválido para a máquina {cod}."))
            continue
        if rpm <= 0 or tm <= 0:
            erros.append(("Máquinas", f"linha {n}: RPM e tempo por metro da máquina {cod} devem ser maiores que zero."))
            continue
        if cod in maquinas:
            avisos.append(f"Máquinas: o código {cod} aparece mais de uma vez; foi mantida a linha {n}.")
        maquinas[cod] = Maquina(
            codigo=cod,
            tipo=_texto(row.get(c_tipo)) if c_tipo else "",
            descricao=_texto(row.get(c_desc)) if c_desc else "",
            rpm=rpm,
            tempo_por_metro=tm,
        )
    if erros:
        raise ErroValidacao(erros)
    if not maquinas:
        raise ErroValidacao([("Máquinas", "nenhuma máquina encontrada.")])
    return maquinas, avisos


# Junta elementos e máquinas num único Cadastros, somando os avisos dos dois.
def _montar(el_df: pd.DataFrame, mq_df: pd.DataFrame, origem: str) -> Cadastros:
    elementos, av_el = elementos_de_df(el_df)
    maquinas, av_mq = maquinas_de_df(mq_df)
    return Cadastros(elementos, maquinas, origem=origem, avisos=tuple(av_el + av_mq))


# Lê a planilha do kit: localiza as abas pelo nome aproximado (MATRIZ DE ELEMENTOS e TEMPO-CM).
def _ler_planilha(conteudo: bytes, nome: str) -> Cadastros:
    # .ods precisa do leitor "odf"; para .xlsx o pandas escolhe sozinho. split(" ") ignora o sufixo "(kit oficial)".
    engine = "odf" if nome.lower().split(" ")[0].endswith(".ods") else None
    # sheet_name=None lê todas as abas; header=None porque o cabeçalho é localizado depois.
    abas = pd.read_excel(io.BytesIO(conteudo), sheet_name=None, header=None, engine=engine)
    aba_el = next((df for n, df in abas.items() if "elemento" in chave(n) or "mtm" in chave(n)), None)
    aba_maq = next((df for n, df in abas.items() if "tempocm" in chave(n) or "maquina" in chave(n)), None)
    if aba_el is None or aba_maq is None:
        encontradas = ", ".join(map(str, abas))
        raise ErroValidacao(
            [("Cadastros", f"a planilha deve ter as abas MATRIZ DE ELEMENTOS e TEMPO-CM (encontradas: {encontradas}).")]
        )
    return _montar(
        _localizar_cabecalho(aba_el, ["descricao", "tempo"]),
        _localizar_cabecalho(aba_maq, ["rpm", "tempo"]),
        nome,
    )


# Lê cadastros em JSON (o mesmo formato que o botão Exportar gera).
def _ler_json(conteudo: bytes, nome: str) -> Cadastros:
    dados = json.loads(decodificar(conteudo))
    if not isinstance(dados, dict):
        raise ErroValidacao([("Cadastros", 'o JSON deve ter o formato {"elementos": [...], "maquinas": [...]}.')])
    return _montar(pd.DataFrame(dados.get("elementos", [])), pd.DataFrame(dados.get("maquinas", [])), nome)


# Função pública: sem argumentos carrega o kit oficial; com arquivo, decide entre JSON e planilha.
def carregar_cadastros(conteudo: bytes | None = None, nome: str | None = None) -> Cadastros:
    if conteudo is None:
        conteudo, nome = CAMINHO_PADRAO.read_bytes(), f"{CAMINHO_PADRAO.name} (kit oficial)"
    nome = nome or "cadastros"
    try:
        if nome.lower().split(" ")[0].endswith(".json"):
            return _ler_json(conteudo, nome)
        return _ler_planilha(conteudo, nome)
    except ErroValidacao:
        raise
    except Exception as e:
        raise ErroValidacao([("Cadastros", f"não foi possível ler '{nome}': {type(e).__name__}: {e}")]) from e


# Caminho inverso: Cadastros -> tabelas, para exibir e editar na tela. float porque o editor não trabalha com Decimal.
def cadastros_para_dfs(cad: Cadastros) -> tuple[pd.DataFrame, pd.DataFrame]:
    el = pd.DataFrame(
        [[e.codigo, e.descricao, float(e.tempo)] for e in cad.elementos.values()], columns=COLUNAS_ELEMENTOS
    )
    mq = pd.DataFrame(
        [[m.codigo, m.tipo, m.descricao, float(m.rpm), float(m.tempo_por_metro)] for m in cad.maquinas.values()],
        columns=COLUNAS_MAQUINAS,
    )
    return el, mq


# Tabelas editadas na tela -> Cadastros novo (passa pela mesma validação da planilha).
def cadastros_de_dfs(el: pd.DataFrame, mq: pd.DataFrame, origem: str) -> Cadastros:
    return _montar(el, mq, origem)


# Exporta os cadastros em JSON. Números como texto (str) para não perder casas decimais.
def cadastros_para_json(cad: Cadastros) -> str:
    return json.dumps(
        {
            "elementos": [
                {"Código": e.codigo, "Descrição": e.descricao, "Tempo": str(e.tempo)} for e in cad.elementos.values()
            ],
            "maquinas": [
                {
                    "Código": m.codigo,
                    "Tipo": m.tipo,
                    "Descrição": m.descricao,
                    "RPM": str(m.rpm),
                    "Tempo/metro": str(m.tempo_por_metro),
                }
                for m in cad.maquinas.values()
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


# Descobre a máquina mesmo quando o usuário escreve diferente: "1", "01", "Siruba", "Interlock Siruba", "máq. 2".
# Tenta do mais exato ao mais tolerante; se nada servir, devolve o código como veio (a validação acusa depois).
def resolver_maquina(valor: str, cad: Cadastros) -> str:
    cod = codigo_simples(valor)
    if cod in cad.maquinas:
        return cod
    # "01" vira "1".
    if cod.isdigit() and cod.lstrip("0") in cad.maquinas:
        return cod.lstrip("0")
    k = chave(valor)
    if not k:
        return cod
    # Procura pelo nome: só aceita se exatamente UMA máquina combinar (evita adivinhar errado).
    for campo in ("descricao", "tipo"):
        hits = [m.codigo for m in cad.maquinas.values() if chave(getattr(m, campo)) and chave(getattr(m, campo)) in k]
        if len(hits) == 1:
            return hits[0]
    hits = [m.codigo for m in cad.maquinas.values() if k in chave(f"{m.tipo} {m.descricao}")]
    if len(hits) == 1:
        return hits[0]
    # Último recurso: um único número no texto ("máquina 2").
    numeros = re.findall(r"\d+", str(valor))
    if len(numeros) == 1 and numeros[0].lstrip("0") in cad.maquinas:
        return numeros[0].lstrip("0")
    return cod
