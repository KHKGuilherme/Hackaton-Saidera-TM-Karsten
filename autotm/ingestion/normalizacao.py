# Funções pequenas de limpeza usadas por todos os leitores: acentos, números brasileiros, unidades e códigos.
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation


# Remove acentos: NFKD separa "ã" em "a" + "~" e o filtro descarta o sinal.
def sem_acentos(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# Versão "comparável" de um texto: sem acento, minúscula, só letras e números. "Cód. Eqp." vira "codeqp".
def chave(texto: object) -> str:
    return re.sub(r"[^a-z0-9]", "", sem_acentos(str(texto)).lower())


# Descobre a codificação do arquivo. Planilhas exportadas no Windows costumam vir em cp1252 ou UTF-16.
def decodificar(conteudo: bytes) -> str:
    if conteudo[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return conteudo.decode("utf-16")
    # Tenta da mais comum para a mais permissiva; utf-8-sig também remove o BOM do início.
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return conteudo.decode(enc)
        except UnicodeDecodeError:
            continue
    # Último recurso: nunca falha, troca o caractere ilegível por "?".
    return conteudo.decode("utf-8", errors="replace")


# Converte qualquer valor (texto "6,96", número, "6.96 m") em Decimal. Devolve None se não houver número.
def para_decimal(valor: object) -> Decimal | None:
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return valor
    # bool é subclasse de int no Python: sem esta linha, True viraria 1.
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        # Só NaN é diferente de si mesmo: é como o pandas representa célula vazia.
        if valor != valor:
            return None
        # str() antes do Decimal evita levar a imprecisão do float (Decimal(0.1) = 0.1000000000000000055...).
        return Decimal(str(valor))
    texto = str(valor).strip()
    # Pega o primeiro número do texto, ignorando unidades e palavras em volta.
    m = re.search(r"-?\d[\d.,]*", texto)
    if not m:
        return None
    num = m.group(0).rstrip(".,")
    # Com vírgula e ponto, o separador decimal é o que aparece por último: "1.234,5" (BR) ou "1,234.5" (EN).
    if "," in num and "." in num:
        num = num.replace(".", "").replace(",", ".") if num.rfind(",") > num.rfind(".") else num.replace(",", "")
    else:
        # Só vírgula ou só ponto: trata como decimal ("6,96" -> 6.96).
        num = num.replace(",", ".")
    try:
        return Decimal(num)
    except InvalidOperation:
        return None


# Para RPM: "5.000" no Brasil é cinco mil, não cinco. Só aceita o padrão de milhar com grupos de 3 dígitos.
def inteiro_br(valor: object) -> Decimal | None:
    if isinstance(valor, str) and re.fullmatch(r"\s*\d{1,3}(\.\d{3})+\s*", valor):
        return Decimal(valor.strip().replace(".", ""))
    return para_decimal(valor)


# Reconhece o número seguido da unidade (mm, cm, m, metros, centímetros...).
_UNIDADE = re.compile(r"(-?\d[\d.,]*)\s*(mm|cm|m|metros?|centimetros?|milimetros?)\b", re.IGNORECASE)


# Converte o perímetro para metros e devolve um aviso quando houve conversão (o usuário fica sabendo).
def comprimento_em_metros(valor: object) -> tuple[Decimal | None, str | None]:
    numero = para_decimal(valor)
    if numero is None or not isinstance(valor, str):
        return numero, None
    m = _UNIDADE.search(sem_acentos(valor))
    # Sem unidade explícita, assume metros (unidade do regulamento). [:2] une "cm" e "centimetros" em "cm"/"ce".
    unidade = (m.group(2).lower() if m else "m")[:2]
    if unidade in ("cm", "ce"):
        return numero / 100, f"Perímetro informado em centímetros ({valor.strip()}) convertido para {numero / 100} m."
    if unidade in ("mm", "mi"):
        return numero / 1000, f"Perímetro informado em milímetros ({valor.strip()}) convertido para {numero / 1000} m."
    return numero, None


# Planilhas leem o código 1 como 1.0; aqui ele volta a ser "1".
def codigo_simples(valor: object) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    texto = str(valor).strip()
    if re.fullmatch(r"\d+\.0+", texto):
        return texto.split(".")[0]
    return texto


# Padroniza o código MTM: "2,1", "02.01" e "2.1" viram todos "2.1".
def codigo_mtm(valor: object) -> str:
    texto = str(valor).strip().replace(",", ".")
    m = re.fullmatch(r"(\d+)\.(\d+)", texto)
    if m:
        return f"{int(m.group(1))}.{int(m.group(2))}"
    return texto


# Dicionário de sinônimos de cabeçalho: (campo interno, nomes exatos aceitos, prefixos aceitos).
# Permite ler planilhas com títulos diferentes ("Cód. Eqp.", "Máquina", "Equipamento"...).
_REGRAS_CAMPOS: list[tuple[str, set[str], tuple[str, ...]]] = [
    ("titulo", {"po", "title", "codigopo", "ficha"}, ("titulo",)),
    ("revisao", {"rev"}, ("revisao",)),
    ("operacao", set(), ("operacao", "descricaodaoperacao", "nomedaoperacao")),
    ("familia", {"peca", "produto"}, ("agrupamento", "familia", "nomedapeca")),
    ("tamanho", {"tam"}, ("tamanho",)),
    ("medidas", set(), ("medida", "dimens")),
    ("pontos_cm", {"pts", "pontos"}, ("pontoscm", "pontosporcm", "densidade")),
    ("perimetro_m", set(), ("perimetro", "comprimento")),
    ("cod_maquina", {"eqp", "maq"}, ("codeqp", "equipamento", "maquina", "codmaquina", "codigodamaquina", "codigomaquina")),
    ("roteiro", {"mtm"}, ("elemento", "roteiro", "sequencia", "operacoes", "codigosmtm", "codigomtm", "passo")),
]


# Traduz o título de uma coluna para o nome interno do campo, ou None se não reconhecer.
def campo_canonico(nome: object) -> str | None:
    k = chave(nome)
    if not k:
        return None
    for campo, exatos, prefixos in _REGRAS_CAMPOS:
        if k == chave(campo) or k in exatos or any(k.startswith(p) for p in prefixos):
            return campo
    return None
