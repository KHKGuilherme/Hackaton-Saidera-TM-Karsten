# Leitura das demandas e a ponte rascunho -> Demanda. O "rascunho" é um dict de textos, como o formulário da tela.
from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal

import pandas as pd

from ..domain.models import Cadastros, Demanda, ErroValidacao, ItemRoteiro
from .cadastros import resolver_maquina
from .normalizacao import campo_canonico, chave, codigo_mtm, comprimento_em_metros, decodificar, para_decimal

# Ordem oficial dos campos da demanda (a mesma da ficha e do formulário).
CAMPOS = [
    "titulo",
    "revisao",
    "operacao",
    "familia",
    "tamanho",
    "medidas",
    "pontos_cm",
    "perimetro_m",
    "cod_maquina",
    "roteiro",
]

# Nomes amigáveis de cada campo, iguais aos da ficha; usados nas mensagens de erro.
ROTULOS = {
    "titulo": "Título",
    "revisao": "Rev.",
    "operacao": "Operação",
    "familia": "Agrupamento família",
    "tamanho": "Tamanho",
    "medidas": "Medidas da peça (em m)",
    "pontos_cm": "Pontos/cm",
    "perimetro_m": "Perímetro costura (em m)",
    "cod_maquina": "Cód. Eqp.",
    "roteiro": "Elementos",
}


# O que um leitor devolve: o rascunho, de onde veio (arquivo/linha) e avisos da leitura.
@dataclass
class ResultadoLeitura:
    rascunho: dict
    origem: str
    avisos: list[str] = field(default_factory=list)


# Formulário em branco; revisão começa em "00". O operador | junta dois dicionários.
def rascunho_vazio() -> dict:
    return {c: "" for c in CAMPOS} | {"revisao": "00"}


# Frequência: inteiro ou decimal. O (?![.\d]) impede que "4.1x2,3.1" leia a frequência como "2,3".
_FREQ = r"\d+(?:[.,]\d+(?![.\d]))?"
# Um item do roteiro: código "2.1" seguido, opcionalmente, de frequência "x2", "×2", "*2" ou "(2)".
_ITEM = re.compile(
    rf"(?P<cod>\d+\s*\.\s*\d+)(?:\s*(?:[x×*]\s*(?P<f1>{_FREQ})|\(\s*(?P<f2>{_FREQ})\s*\)))?",
    re.IGNORECASE,
)


# Transforma o roteiro (texto, lista ou lista de dicts do JSON) em lista de ItemRoteiro.
def parse_roteiro(valor: object) -> list[ItemRoteiro]:
    if valor is None:
        return []
    # Lista (vinda de JSON): cada item pode ser {"codigo": .., "frequencia": ..} ou um texto.
    if isinstance(valor, (list, tuple)):
        itens = []
        for v in valor:
            if isinstance(v, dict):
                cod = next((v[k] for k in v if chave(k) in ("codigo", "cod", "elemento")), "")
                freq = next((v[k] for k in v if chave(k).startswith("freq")), 1)
                itens.append(ItemRoteiro(codigo_mtm(cod), para_decimal(freq) or Decimal(1)))
            else:
                itens.extend(parse_roteiro(str(v)))
        return itens
    texto = str(valor).strip()
    if not texto:
        return []
    # Quem digita "2,1; 3,1" usa vírgula como ponto do código: converte para "2.1; 3.1".
    if "." not in texto and re.search(r"\d,\d", texto):
        texto = re.sub(r"(\d),(\d)", r"\1.\2", texto)
    itens, pos, sobras = [], 0, []
    # Percorre os itens guardando o que sobrou entre eles, para detectar texto não reconhecido.
    for m in _ITEM.finditer(texto):
        sobras.append(texto[pos : m.start()])
        pos = m.end()
        freq = para_decimal(m.group("f1") or m.group("f2")) or Decimal(1)
        itens.append(ItemRoteiro(codigo_mtm(m.group("cod").replace(" ", "")), freq))
    sobras.append(texto[pos:])
    # Separadores aceitos entre itens: espaço , ; / | - > e "e". Qualquer outra sobra é erro.
    lixo = [s.strip() for s in sobras if re.sub(r"[\s,;/|\-–>e]+", "", s)]
    if lixo:
        # Melhor recusar e mostrar o trecho do que ignorar silenciosamente um elemento digitado errado.
        raise ErroValidacao([("Elementos", f"trecho não reconhecido no roteiro: '{lixo[0]}'. Use, por exemplo: 2.1, 4.1x2, 3.1")])
    return itens


# Caminho inverso: lista -> texto "2.1, 4.1x2". normalize() mostra 2 em vez de 2.00.
def formatar_roteiro(itens: list[ItemRoteiro]) -> str:
    return ", ".join(i.codigo if i.frequencia == 1 else f"{i.codigo}x{i.frequencia.normalize()}" for i in itens)


# Contorno = 2 × (largura + comprimento), usado só para conferir se o perímetro é plausível.
def _contorno_da_peca(medidas: str) -> Decimal | None:
    nums = [para_decimal(n) for n in re.findall(r"\d+(?:[.,]\d+)?", str(medidas))]
    if len(nums) == 2 and all(nums):
        return 2 * (nums[0] + nums[1])
    return None


# Ponte entre o rascunho (textos) e o motor (Demanda com números). Valida tudo e junta todos os erros.
def montar_demanda(rascunho: dict, cadastros: Cadastros) -> Demanda:
    erros: list[tuple[str, str]] = []
    avisos: list[str] = []
    # Troca None por "" para não precisar testar None em cada campo.
    r = {k: ("" if v is None else v) for k, v in rascunho.items()}

    # Aceita "696 cm" e converte para metros, avisando o usuário.
    perimetro, aviso_unidade = comprimento_em_metros(r.get("perimetro_m"))
    if perimetro is None:
        erros.append((ROTULOS["perimetro_m"], "obrigatório (número em metros, por exemplo 6,96)."))
    elif aviso_unidade:
        avisos.append(aviso_unidade)

    pontos = None
    if str(r.get("pontos_cm", "")).strip():
        pontos = para_decimal(r.get("pontos_cm"))
        if pontos is None:
            erros.append((ROTULOS["pontos_cm"], f"valor inválido: '{r.get('pontos_cm')}'."))

    cod_maq = str(r.get("cod_maquina", "")).strip()
    if not cod_maq:
        erros.append((ROTULOS["cod_maquina"], "obrigatório (código ou nome da máquina)."))
    else:
        # Aceita código ou nome da máquina. Se não existir, o motor acusa com a lista das disponíveis.
        cod_maq = resolver_maquina(cod_maq, cadastros)

    try:
        roteiro = parse_roteiro(r.get("roteiro"))
    # Erro no roteiro entra na mesma lista dos outros erros, em vez de interromper aqui.
    except ErroValidacao as e:
        erros.extend(e.erros)
        roteiro = []

    if erros:
        raise ErroValidacao(erros)

    # Limpa campos de texto: espaços e aspas retas ou curvas que vêm de cópia do Word/WhatsApp.
    def txt(campo: str, padrao: str = "") -> str:
        return str(r.get(campo, "") or padrao).strip().strip('"').strip("“”").strip()

    medidas = txt("medidas")
    contorno = _contorno_da_peca(medidas)
    # Perímetro maior que o dobro do contorno da peça é suspeito: aviso, sem bloquear.
    if contorno and perimetro > 2 * contorno:
        avisos.append(
            f"O perímetro de costura ({perimetro} m) é mais que o dobro do contorno da peça "
            f"({medidas} m = {contorno} m). Confira o valor e a unidade."
        )

    return Demanda(
        perimetro_m=perimetro,
        cod_maquina=cod_maq,
        roteiro=roteiro,
        titulo=txt("titulo", "PO-SEM-TITULO"),
        revisao=txt("revisao", "00"),
        operacao=txt("operacao"),
        familia=txt("familia"),
        tamanho=txt("tamanho"),
        medidas=medidas,
        pontos_cm=pontos,
        avisos=avisos,
    )


# Caminho inverso: Demanda -> rascunho, para reabrir uma ficha do histórico no formulário.
def demanda_para_rascunho(d: Demanda) -> dict:
    return {
        "titulo": d.titulo,
        "revisao": d.revisao,
        "operacao": d.operacao,
        "familia": d.familia,
        "tamanho": d.tamanho,
        "medidas": d.medidas,
        "pontos_cm": "" if d.pontos_cm is None else str(d.pontos_cm),
        "perimetro_m": str(d.perimetro_m),
        "cod_maquina": d.cod_maquina,
        "roteiro": formatar_roteiro(d.roteiro),
    }


# Célula vazia em qualquer forma: None, NaN do pandas ou texto em branco.
def _vazio(v: object) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or not str(v).strip()


# Recebe pares (título, valor), reconhece cada título e monta o rascunho. Devolve também os títulos ignorados.
def _mapear(pares) -> tuple[dict, list[str]]:
    rascunho, ignorados = {}, []
    for k, v in pares:
        campo = campo_canonico(k)
        # Várias colunas de elementos (Elemento 1, Elemento 2...) são juntadas num roteiro só.
        if campo == "roteiro" and campo in rascunho:
            if not _vazio(v):
                rascunho["roteiro"] = f"{rascunho['roteiro']}, {v}" if not _vazio(rascunho["roteiro"]) else v
        # Para os demais campos vale a primeira ocorrência.
        elif campo and campo not in rascunho:
            rascunho[campo] = v
        elif not campo and str(k).strip():
            ignorados.append(str(k).strip())
    return rascunho, ignorados


# Lê o formato "Campo: valor" (como demanda_000.txt). Linha sem ":" continua o valor da linha anterior.
def ler_txt_chave_valor(texto: str) -> tuple[dict, list[str]]:
    pares: list[list[str]] = []
    for linha in texto.splitlines():
        if ":" in linha and campo_canonico(linha.split(":", 1)[0]):
            k, v = linha.split(":", 1)
            pares.append([k, v.strip()])
        elif pares and linha.strip():
            pares[-1][1] = f"{pares[-1][1]} {linha.strip()}".strip()
        elif ":" in linha:
            k, v = linha.split(":", 1)
            pares.append([k, v.strip()])
    return _mapear(pares)


# Aceita uma demanda, uma lista de demandas ou {"demandas": [...]}.
def ler_json(texto: str) -> list[dict]:
    dados = json.loads(texto)
    if isinstance(dados, dict):
        lista = next((v for k, v in dados.items() if chave(k) in ("demandas", "itens", "operacoes") and isinstance(v, list)), None)
        dados = lista if lista is not None else [dados]
    return [_mapear(_achatar(d).items())[0] for d in dados if isinstance(d, dict)]


# JSON aninhado ({"peca": {"tamanho": ..}}) vira um dict plano; o primeiro valor encontrado prevalece.
def _achatar(d: dict) -> dict:
    plano = {k: v for k, v in d.items() if not isinstance(v, dict)}
    for v in d.values():
        if isinstance(v, dict):
            for k2, v2 in _achatar(v).items():
                plano.setdefault(k2, v2)
    return plano


# Lê uma tabela de demandas em qualquer orientação.
def _df_para_rascunhos(bruto: pd.DataFrame) -> list[dict]:
    df = bruto.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
    if df.empty:
        return []
    # Para cada uma das 15 primeiras linhas, conta quantos títulos conhecidos ela tem: a campeã é o cabeçalho.
    # Isso resolve planilhas com linhas de título antes do cabeçalho.
    contagens = [sum(campo_canonico(v) is not None for v in df.iloc[i].tolist()) for i in range(min(len(df), 15))]
    linha_cab = max(range(len(contagens)), key=lambda i: contagens[i])
    # Conta também títulos conhecidos na primeira coluna (planilha "vertical": campo | valor).
    na_coluna = sum(campo_canonico(v) is not None for v in df.iloc[:, 0].tolist()) if df.shape[1] >= 2 else 0

    # Vertical: uma demanda só, lendo os pares da coluna A com a coluna B.
    if na_coluna >= 3 and na_coluna > contagens[linha_cab]:
        return [_mapear(zip(df.iloc[:, 0], df.iloc[:, 1]))[0]]
    # Menos de 2 títulos reconhecidos: não parece uma tabela de demandas.
    if contagens[linha_cab] < 2:
        return []
    cabecalho = [str(v) if not _vazio(v) else f"_col{j}" for j, v in enumerate(df.iloc[linha_cab].tolist())]
    rascunhos = []
    # Horizontal: cada linha abaixo do cabeçalho é uma demanda; linhas totalmente vazias são puladas.
    for _, linha in df.iloc[linha_cab + 1 :].iterrows():
        r, _ = _mapear((k, "" if _vazio(v) else v) for k, v in zip(cabecalho, linha.tolist()))
        if any(not _vazio(v) for v in r.values()):
            rascunhos.append(r)
    return rascunhos


# Lê CSV ou planilha como texto bruto (dtype=str/object, header=None): a interpretação fica para _df_para_rascunhos.
def ler_abas(conteudo: bytes, nome: str) -> dict[str, pd.DataFrame]:
    n = nome.lower()
    if n.endswith(".csv"):
        texto = decodificar(conteudo)
        if not texto.strip():
            return {}
        # sep=None com engine="python" detecta sozinho o separador (; ou ,).
        return {"csv": pd.read_csv(io.StringIO(texto), sep=None, engine="python", dtype=str, header=None)}
    engine = "odf" if n.endswith(".ods") else None
    return pd.read_excel(io.BytesIO(conteudo), sheet_name=None, dtype=object, engine=engine, header=None)


# Atalho: todas as demandas de todas as abas de uma planilha.
def ler_tabela(conteudo: bytes, nome: str) -> list[dict]:
    rascunhos = []
    for df in ler_abas(conteudo, nome).values():
        rascunhos.extend(_df_para_rascunhos(df))
    return rascunhos
