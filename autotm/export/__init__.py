# Reexporta os geradores de saída (Excel, PDF, JSON e ZIP) num só lugar.
from .xlsx import gerar_xlsx
from .pdf import gerar_pdf
from .json_export import ficha_para_dict, gerar_json, nome_arquivo
from .lote import gerar_zip

__all__ = ["ficha_para_dict", "gerar_json", "gerar_pdf", "gerar_xlsx", "gerar_zip", "nome_arquivo"]
