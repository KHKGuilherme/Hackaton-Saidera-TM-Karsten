# Porta de entrada da camada de ingestão: leitores de arquivo, cadastros e montagem da demanda.
from .arquivos import EXTENSOES, ler_arquivo_demandas
from .cadastros import (
    cadastros_de_dfs,
    cadastros_para_dfs,
    cadastros_para_json,
    carregar_cadastros,
    resolver_maquina,
)
from .demandas import (
    CAMPOS,
    ROTULOS,
    ResultadoLeitura,
    demanda_para_rascunho,
    formatar_roteiro,
    montar_demanda,
    parse_roteiro,
    rascunho_vazio,
)
from .ficha_po import FichaLida, ler_ficha_po, parece_ficha_po
from .texto_livre import extrair_texto_livre

__all__ = [
    "CAMPOS",
    "EXTENSOES",
    "ROTULOS",
    "FichaLida",
    "ResultadoLeitura",
    "cadastros_de_dfs",
    "cadastros_para_dfs",
    "cadastros_para_json",
    "carregar_cadastros",
    "demanda_para_rascunho",
    "extrair_texto_livre",
    "formatar_roteiro",
    "ler_arquivo_demandas",
    "ler_ficha_po",
    "montar_demanda",
    "parece_ficha_po",
    "parse_roteiro",
    "rascunho_vazio",
    "resolver_maquina",
]
