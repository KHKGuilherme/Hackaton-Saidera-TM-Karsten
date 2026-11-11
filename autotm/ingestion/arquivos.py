# Despachante: olha o tipo do arquivo e escolhe o leitor certo. É a única porta de entrada de arquivos de demanda.
from __future__ import annotations

import json

from ..domain.models import Cadastros, ErroValidacao
from .demandas import ResultadoLeitura, _df_para_rascunhos, ler_abas, ler_json, ler_txt_chave_valor
from .ficha_po import ler_ficha_po, parece_ficha_po
from .normalizacao import decodificar
from .texto_livre import extrair_texto_livre

# Formatos aceitos; usados também na tela (upload) e na mensagem de erro.
EXTENSOES = (".txt", ".json", ".csv", ".xlsx", ".xls", ".ods")


# Escolhe o leitor pela extensão. Cada demanda lida vira um ResultadoLeitura com a origem para rastrear.
def _ler(conteudo: bytes, nome: str, cadastros: Cadastros) -> list[ResultadoLeitura]:
    n = nome.lower()
    if n.endswith(".json"):
        return [ResultadoLeitura(r, f"{nome} #{i}") for i, r in enumerate(ler_json(decodificar(conteudo)), 1)]
    if n.endswith((".csv", ".xlsx", ".xls", ".ods")):
        leituras = []
        # Lê todas as abas: uma planilha pode ter uma ficha PO pronta ou uma tabela de várias demandas.
        for aba, df in ler_abas(conteudo, nome).items():
            # Se a aba tem o layout da ficha PO, lê como ficha (permite regerar/auditar uma PO existente).
            if parece_ficha_po(df):
                leituras.append(ResultadoLeitura(ler_ficha_po(df).rascunho, f"{nome} (ficha PO, aba {aba})"))
                continue
            rascunhos = _df_para_rascunhos(df)
            rotulo = "linha" if len(rascunhos) > 1 else "demanda"
            leituras += [ResultadoLeitura(r, f"{nome} {rotulo} {i}") for i, r in enumerate(rascunhos, 1)]
        return leituras
    texto = decodificar(conteudo)
    # .txt: primeiro tenta o formato "Campo: valor"...
    rascunho, _ = ler_txt_chave_valor(texto)
    # ...com 3 campos ou mais reconhecidos, considera que é esse formato.
    if len(rascunho) >= 3:
        return [ResultadoLeitura(rascunho, nome)]
    # Senão, trata como texto livre (pedido escrito como mensagem).
    rascunho, avisos = extrair_texto_livre(texto, cadastros)
    return [ResultadoLeitura(rascunho, f"{nome} (texto livre)", avisos)]


# Função pública: lê o arquivo e transforma qualquer falha em ErroValidacao com mensagem clara (sem traceback).
def ler_arquivo_demandas(conteudo: bytes, nome: str, cadastros: Cadastros) -> list[ResultadoLeitura]:
    if not nome.lower().endswith(EXTENSOES):
        raise ErroValidacao([("Arquivo", f"formato não suportado: '{nome}'. Use {', '.join(EXTENSOES)}.")])
    try:
        leituras = _ler(conteudo, nome, cadastros)
    # Erro já explicado: repassa sem mexer.
    except ErroValidacao:
        raise
    # JSON quebrado: informa linha e coluna do problema.
    except json.JSONDecodeError as e:
        raise ErroValidacao([("Arquivo", f"JSON inválido em '{nome}' (linha {e.lineno}, coluna {e.colno}): {e.msg}.")]) from e
    # Qualquer outro erro inesperado vira mensagem amigável; "from e" preserva a causa original para depuração.
    except Exception as e:
        raise ErroValidacao([("Arquivo", f"não foi possível ler '{nome}': {type(e).__name__}: {e}")]) from e
    if not leituras:
        raise ErroValidacao(
            [("Arquivo", f"nenhuma demanda encontrada em '{nome}'. Verifique se há um cabeçalho com campos como "
                         "Perímetro, Cód. Eqp e Elementos.")]
        )
    return leituras
