# Leitor independente de .ods, feito só para os testes: lê o XML do gabarito direto, sem pandas nem openpyxl.
# Motivo: comparar o Excel gerado com o gabarito usando uma ferramenta diferente da que gerou o arquivo.
from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass

# Namespaces do formato OpenDocument (cada tag do XML tem um prefixo como table: ou office:).
NS = {
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
}
T, O, S, FO = (f"{{{NS[k]}}}" for k in ("table", "office", "style", "fo"))


# O que importa de cada célula para o teste: texto, valor numérico, fórmula, mesclagem e cor de fundo.
@dataclass
class CelulaODS:
    texto: str
    valor: float | None
    formula: str | None
    colspan: int
    fundo: str | None


# Índice -> letra da coluna (0 -> A). Basta para as colunas A a E da ficha.
def _col(i: int) -> str:
    return chr(ord("A") + i)


# Devolve {"E8": CelulaODS(...)} com todas as células preenchidas da aba.
def ler_aba(caminho, nome_aba: str, max_linhas: int = 60) -> dict[str, CelulaODS]:
    root = ET.fromstring(zipfile.ZipFile(caminho).read("content.xml"))
    fundos = {}
    # Primeiro mapeia os estilos que têm cor de fundo, para saber a cor de cada célula.
    for st in root.iter(S + "style"):
        props = st.find("style:table-cell-properties", NS)
        if props is not None and props.get(FO + "background-color"):
            fundos[st.get(S + "name")] = props.get(FO + "background-color").upper()
    aba = next(t for t in root.iter(T + "table") if t.get(T + "name") == nome_aba)
    celulas: dict[str, CelulaODS] = {}
    r = 0
    for row in aba.iter(T + "table-row"):
        r += 1
        if r > max_linhas:
            break
        c = 0
        for cell in row:
            if cell.tag not in (T + "table-cell", T + "covered-table-cell"):
                continue
            # O .ods compacta células vazias repetidas numa só tag; rep diz quantas colunas ela ocupa.
            rep = int(cell.get(T + "number-columns-repeated", "1"))
            if cell.tag == T + "table-cell":
                texto = "\n".join("".join(p.itertext()) for p in cell.findall("text:p", NS))
                valor = cell.get(O + "value")
                if texto or cell.get(T + "formula"):
                    celulas[f"{_col(c)}{r}"] = CelulaODS(
                        texto=texto,
                        valor=float(valor) if valor is not None else None,
                        formula=cell.get(T + "formula"),
                        colspan=int(cell.get(T + "number-columns-spanned", "1")),
                        fundo=fundos.get(cell.get(T + "style-name")),
                    )
            c += rep
    return celulas
