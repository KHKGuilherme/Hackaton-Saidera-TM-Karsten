# Linha de comando: python -m autotm <arquivos>. Gera fichas em lote ou audita fichas com --auditar.
# Útil para automação e integração (ERP, rotinas agendadas) sem abrir o navegador.
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .domain import ErroValidacao
from .export import gerar_json, gerar_pdf, gerar_xlsx, nome_arquivo
from .ingestion import carregar_cadastros, ler_arquivo_demandas
from .servicos import auditar_arquivo, processar_lote


# Erros vão para stderr, separados da saída normal.
def _erro(msg: str) -> None:
    print(f"[ERRO] {msg}", file=sys.stderr)


# Imprime o relatório de auditoria. Devolve 1 se houver divergência ou erro (útil em scripts automáticos).
def _auditar(arquivos: list[Path], cad) -> int:
    falhas = 0
    for arq in arquivos:
        for res in auditar_arquivo(arq.read_bytes(), arq.name, cad):
            if res.erros:
                falhas += 1
                print(f"[ERRO] {res.origem}")
                for campo, msg in res.erros:
                    print(f"       - {campo}: {msg}")
                continue
            situacao = "CONFORME" if not res.divergencias else f"{len(res.divergencias)} DIVERGÊNCIA(S)"
            print(f"[{situacao}] {res.origem}: {res.total - len(res.divergencias)}/{res.total} itens conferem ({res.conformidade}%)")
            for c in res.conferencias:
                marca = "ok " if c.ok else "XX "
                print(f"   {marca}{c.celula:<5} {c.item:<42} ficha={c.na_ficha:<12} calculado={c.calculado} {c.motivo}")
            for obs in res.observacoes:
                print(f"   obs: {obs}")
            falhas += bool(res.divergencias)
    return 1 if falhas else 0


# argv opcional permite chamar main() nos testes passando argumentos.
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="autotm", description="Gera ou audita a ficha de Processo Operacional (PO).")
    p.add_argument("arquivos", nargs="+", type=Path, help="demandas (.txt, .json, .csv, .xlsx, .ods) ou fichas PO com --auditar")
    p.add_argument("--cadastros", type=Path, help="planilha/JSON de cadastros (padrão: kit oficial)")
    p.add_argument("--saida", type=Path, default=Path("saidas"), help="pasta de saída (padrão: saidas/)")
    p.add_argument("--pdf", action="store_true", help="gera também o PDF")
    p.add_argument("--json", action="store_true", help="gera também o JSON")
    p.add_argument("--auditar", action="store_true", help="audita fichas PO existentes em vez de gerar novas")
    a = p.parse_args(argv)

    # Força UTF-8 no terminal: no Windows, os acentos sairiam trocados.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    # Confere antes se os arquivos existem, para dar um erro claro em vez de um traceback.
    faltando = [str(f) for f in [*a.arquivos, *([a.cadastros] if a.cadastros else [])] if not f.is_file()]
    if faltando:
        _erro("arquivo(s) não encontrado(s): " + ", ".join(faltando))
        return 2
    try:
        cad = carregar_cadastros(a.cadastros.read_bytes(), a.cadastros.name) if a.cadastros else carregar_cadastros()
    except ErroValidacao as e:
        _erro(f"cadastros inválidos: {e}")
        return 2
    for aviso in cad.avisos:
        print(f"[AVISO] {aviso}")

    if a.auditar:
        return _auditar(a.arquivos, cad)

    leituras, falhas = [], 0
    for arq in a.arquivos:
        try:
            leituras += ler_arquivo_demandas(arq.read_bytes(), arq.name, cad)
        except ErroValidacao as e:
            falhas += 1
            _erro(str(e))

    a.saida.mkdir(parents=True, exist_ok=True)
    # Gera os arquivos de cada ficha; demandas com erro são listadas com o motivo e não interrompem as outras.
    for r in processar_lote(leituras, cad):
        if not r.ficha:
            falhas += 1
            print(f"[ERRO] {r.origem}")
            for campo, msg in r.erros:
                print(f"       - {campo}: {msg}")
            continue
        f = r.ficha
        (a.saida / nome_arquivo(f, "xlsx")).write_bytes(gerar_xlsx(f, cad))
        if a.pdf:
            (a.saida / nome_arquivo(f, "pdf")).write_bytes(gerar_pdf(f))
        if a.json:
            (a.saida / nome_arquivo(f, "json")).write_bytes(gerar_json(f))
        print(f"[OK]   {r.origem} -> {f.demanda.titulo}  FIXO={f.fixo:.4f}  TP={f.tp:.4f} min")
        for l in f.linhas:
            print(f"         {l.codigo:<5} {l.descricao:<52} x{l.frequencia:<3} {l.tempo:.4f}")
        for aviso in f.avisos:
            print(f"         aviso: {aviso}")
    print(f"\nArquivos em: {a.saida.resolve()}")
    # Código de saída: 0 = tudo certo, 1 = alguma falha, 2 = problema de entrada (arquivo ou cadastros).
    return 1 if falhas else 0


if __name__ == "__main__":
    # Só roda quando chamado como programa; o código de saída vai para o sistema operacional.
    raise SystemExit(main())
