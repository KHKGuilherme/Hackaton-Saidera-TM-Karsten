# Interface web (Streamlit). Rodar com: streamlit run app.py
# Importante: o Streamlit reexecuta este arquivo inteiro de cima a baixo a cada clique.
# Por isso, tudo que precisa sobreviver entre cliques fica em st.session_state (apelidado de ss).
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from html import escape
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from autotm.domain import ErroValidacao, FichaPO, ItemRoteiro, calcular_po
from autotm.domain.analise import checagem_agulha, comparar_maquinas, pecas_por_hora
from autotm.export import gerar_json, gerar_pdf, gerar_xlsx, gerar_zip, nome_arquivo
from autotm.export.html import ficha_html
from autotm.relogio import agora
from autotm.servicos import auditar_arquivo, processar_lote
from autotm.ingestion import (
    EXTENSOES,
    ROTULOS,
    cadastros_de_dfs,
    cadastros_para_dfs,
    cadastros_para_json,
    carregar_cadastros,
    demanda_para_rascunho,
    extrair_texto_livre,
    formatar_roteiro,
    ler_arquivo_demandas,
    montar_demanda,
    parse_roteiro,
    rascunho_vazio,
)
from autotm.ingestion.cadastros import CAMINHO_PADRAO, resolver_maquina
from interface.componentes import FONTE_UI, aplicar_estilo, citacao, etapas, fatos, html, lista_erros, masthead, nota, secao

# Configuração da página: precisa ser o primeiro comando do Streamlit. layout="wide" usa a largura toda.
ICONE = Path(__file__).parent / "interface" / "icone.png"
st.set_page_config(
    page_title="Auto-T&M · Ficha de Processo Operacional",
    page_icon=str(ICONE) if ICONE.exists() else None,
    layout="wide",
)
# Injeta o CSS dos temas claro/escuro e o script de sincronização (interface/componentes.py).
aplicar_estilo()

# Texto de exemplo já preenchido na opção "Texto livre": a demo funciona sem digitar nada.
EXEMPLO_TEXTO = (
    'Preciso da PO-SL-002 para a operação "Bainhar no corpo do SL - 1 lado": '
    "sobre-lençol casal 2,30 x 2,50, perímetro 7,96 m, 2,5 pontos/cm, na Siruba. "
    "Elementos: 2.1, 1.1, 3.1"
)
FONTE_GRAFICO = FONTE_UI
# As quatro formas de entrada da Etapa 1: nome da opção -> legenda explicativa.
ORIGENS = {
    "Cenário oficial": "Carrega a demanda do kit do evento",
    "Arquivo": "TXT, JSON, CSV, Excel, ODS ou ficha PO",
    "Texto livre": "Cole um e-mail ou mensagem",
    "Preencher à mão": "Digite os campos na etapa 2",
}


# Cria o estado da sessão na primeira execução. setdefault só cria se ainda não existir.
# cad = cadastros em uso; draft = rascunho do formulário; v = versão do formulário (ver painel_revisao);
# ficha = ficha atual; historico = fichas geradas; avisos_entrada e erros = mensagens para a tela.
def _init():
    ss = st.session_state
    if "cad" not in ss:
        ss.cad = carregar_cadastros()
    ss.setdefault("draft", rascunho_vazio())
    ss.setdefault("v", 0)
    ss.setdefault("ficha", None)
    ss.setdefault("historico", [])
    ss.setdefault("avisos_entrada", [])
    ss.setdefault("erros", [])


_init()
ss = st.session_state


# O st.file_uploader quer as extensões sem o ponto.
TIPOS_ARQUIVO = [e.lstrip(".") for e in EXTENSOES]


# Coloca um rascunho no formulário (vindo de arquivo, texto livre, histórico...) e, por padrão, já gera a ficha.
def carregar_rascunho(rascunho: dict, avisos: list[str] | None = None, gerar: bool = True, registrar: bool = True):
    ss.draft = rascunho_vazio() | {k: ("" if v is None else v) for k, v in rascunho.items()}
    # Muda a versão do formulário: os campos ganham chaves novas e o Streamlit os redesenha com os valores novos.
    ss.v += 1
    ss.avisos_entrada = avisos or []
    ss.erros = []
    ss.ficha = None
    if gerar:
        gerar_ficha(ss.draft, registrar=registrar)


# Rascunho -> Demanda -> FichaPO. Em caso de erro, guarda a lista para mostrar na Etapa 3.
def gerar_ficha(rascunho: dict, registrar: bool = True):
    try:
        ficha = calcular_po(montar_demanda(rascunho, ss.cad), ss.cad)
    except ErroValidacao as e:
        ss.erros, ss.ficha = e.erros, None
        return
    ss.erros, ss.ficha = [], ficha
    if registrar:
        ss.historico.insert(0, (agora(), ficha))
        # Mantém só as 30 fichas mais recentes no histórico.
        del ss.historico[30:]


# Troca os cadastros e recalcula a ficha aberta, para ela refletir os valores novos na hora.
def trocar_cadastros(novo) -> None:
    ss.cad = novo
    if ss.ficha is not None or ss.erros:
        gerar_ficha(ss.draft, registrar=False)
    st.rerun()


# Guarda o Excel já gerado para não refazer a cada clique. O "_" em _cad diz ao Streamlit para não usá-lo na chave do cache;
# origem_cad entra na chave para o cache mudar quando os cadastros mudarem.
@st.cache_data(max_entries=64, show_spinner=False)
def xlsx_em_cache(ficha: FichaPO, _cad, origem_cad: str) -> bytes:
    return gerar_xlsx(ficha, _cad)


# Tabela de leitura com as colunas de tempo formatadas em 4 casas.
def tabela_numerica(df: pd.DataFrame, colunas_4_casas: list[str]):
    st.dataframe(
        df,
        hide_index=True,
        width="stretch",
        column_config={c: st.column_config.NumberColumn(format="%.4f") for c in colunas_4_casas},
    )


# As funções de cadastros abaixo são usadas em dois lugares (barra lateral e janela ampla).
# O parâmetro "onde" deixa as chaves dos componentes diferentes, porque o Streamlit não aceita chaves repetidas.
def _resumo_cadastros():
    cad = ss.cad
    html(
        f"<div class='estat'><div><b>{len(cad.elementos)}</b>elementos MTM</div>"
        f"<div><b>{len(cad.maquinas)}</b>máquinas</div></div>"
        f"<div class='fonte'>Fonte: {escape(cad.origem)}</div>"
    )
    for aviso in cad.avisos:
        nota(escape(aviso), "alerta")


# Envio de uma nova planilha/JSON de cadastros.
def _upload_cadastros(onde: str):
    up = st.file_uploader(
        "Substituir cadastros",
        type=["ods", "xlsx", "xls", "json"],
        key=f"cad_up_{onde}",
        help="Planilha com as abas MATRIZ DE ELEMENTOS e TEMPO-CM, ou o JSON exportado por este sistema.",
    )
    # Só processa quando chega um arquivo NOVO; sem isso, o mesmo arquivo seria recarregado a cada clique.
    if up is not None and ss.get("cad_file_id") != up.file_id:
        ss.cad_file_id = up.file_id
        try:
            trocar_cadastros(carregar_cadastros(up.getvalue(), up.name))
        except ErroValidacao as e:
            ss.erro_cadastro = e.erros
    if ss.get("erro_cadastro"):
        lista_erros("Não foi possível carregar os cadastros", ss.erro_cadastro)
        if up is None:
            ss.erro_cadastro = None


# Tabelas editáveis de elementos e máquinas. As alterações só valem depois de "Aplicar alterações".
def _editores_cadastros(onde: str, lado_a_lado: bool):
    el_df, mq_df = cadastros_para_dfs(ss.cad)
    col_el, col_mq = st.columns([3, 2], gap="medium") if lado_a_lado else (st.container(), st.container())
    with col_el:
        st.caption(f"Matriz de Elementos (MTM) · {len(el_df)} elementos")
        # A origem dos cadastros faz parte da chave: ao trocar a base, o editor recomeça com os dados novos.
        el_ed = st.data_editor(el_df, num_rows="dynamic", hide_index=True, key=f"ed_el_{onde}_{ss.cad.origem}", width="stretch")
    with col_mq:
        st.caption(f"Máquinas (TEMPO-CM) · {len(mq_df)} máquinas")
        mq_ed = st.data_editor(mq_df, num_rows="dynamic", hide_index=True, key=f"ed_mq_{onde}_{ss.cad.origem}", width="stretch")
    if st.button("Aplicar alterações", width="stretch", type="primary", key=f"aplicar_{onde}"):
        try:
            # As tabelas editadas passam pela mesma validação de uma planilha enviada.
            trocar_cadastros(cadastros_de_dfs(el_ed, mq_ed, f"editado na tela às {agora():%H:%M}"))
        except ErroValidacao as e:
            lista_erros("Alterações não aplicadas", e.erros)


# Botões para voltar ao kit oficial e baixar a base atual em JSON.
def _acoes_cadastros(onde: str):
    c1, c2 = st.columns(2)
    if c1.button("Kit oficial", width="stretch", key=f"kit_{onde}", help="Restaura os cadastros de Entradas.ods"):
        ss.pop("cad_file_id", None)
        ss.erro_cadastro = None
        trocar_cadastros(carregar_cadastros())
    c2.download_button(
        "Exportar", cadastros_para_json(ss.cad), "cadastros_autotm.json", "application/json",
        width="stretch", key=f"exp_{onde}", help="Baixa a base em JSON",
    )


# Resumo das fórmulas, sempre visível junto dos cadastros.
def _regras_calculo():
    html(
        "<div class='regras'><b>Regras do cálculo</b><br>"
        "<code>FIXO = perímetro × tempo/metro</code><br>"
        "<code>TP = FIXO + Σ tempo MTM × freq.</code><br>"
        "RPM: limites de 90% e 110% do padrão</div>"
    )


# Versão ampla dos cadastros em janela (st.dialog): mesmas funções da barra lateral, com mais espaço para as tabelas.
@st.dialog("Cadastros de apoio", width="large")
def janela_cadastros():
    esquerda, direita = st.columns([1, 2.6], gap="large")
    with esquerda:
        _resumo_cadastros()
        _upload_cadastros("janela")
        _acoes_cadastros("janela")
        _regras_calculo()
    with direita:
        _editores_cadastros("janela", lado_a_lado=False)


# Barra lateral: cadastros de apoio e a explicação de como trocar o tema.
with st.sidebar:
    secao("Base de dados", "Cadastros de apoio")
    if st.button("Abrir em janela ampla", width="stretch", key="abrir_janela_lateral",
                 help="Mostra todos os cadastros num painel maior, com as tabelas completas"):
        janela_cadastros()
    _resumo_cadastros()
    _upload_cadastros("lateral")
    with st.expander("Ver e editar cadastros"):
        _editores_cadastros("lateral", lado_a_lado=False)
    _acoes_cadastros("lateral")
    _regras_calculo()
    html(
        "<div class='regras'><b>Aparência</b><br>Claro ou escuro: menu <b>⋮</b> no canto superior direito, "
        "opções System (segue o sistema), Light (claro) ou Dark (escuro). O padrão segue o seu sistema, e a escolha fica salva neste navegador.</div>"
    )


# Cabeçalho: marca e base em uso à esquerda; botão que abre a janela de cadastros à direita.
col_marca, col_botao = st.columns([5, 1.3], vertical_alignment="bottom")
with col_marca:
    masthead(len(ss.cad.elementos), len(ss.cad.maquinas), ss.cad.origem)
with col_botao:
    if st.button("Ver cadastros", width="stretch", key="abrir_janela_topo",
                 help="Abre os cadastros de apoio num painel maior"):
        janela_cadastros()
# As cinco abas do app.
aba_nova, aba_lote, aba_audit, aba_hist, aba_metodo = st.tabs(["Nova ficha", "Lote", "Auditoria", "Histórico", "Metodologia"])


# Etapa 1: escolher de onde vêm os dados. Toda opção termina em carregar_rascunho (mesmo caminho de validação).
def painel_entrada():
    secao("Etapa 1", "De onde vêm os dados?", "Escolha uma opção. Todas passam pela mesma validação antes de gerar a ficha.")
    modo = st.radio(
        "Origem dos dados",
        list(ORIGENS),
        captions=list(ORIGENS.values()),
        key="modo",
        label_visibility="collapsed",
    )
    # Carrega a demanda do kit oficial (kit_oficial/demanda_000.txt).
    if modo == "Cenário oficial":
        if st.button("Carregar cenário oficial", type="primary", width="stretch"):
            arq = CAMINHO_PADRAO.parent / "demanda_000.txt"
            leitura = ler_arquivo_demandas(arq.read_bytes(), arq.name, ss.cad)[0]
            carregar_rascunho(leitura.rascunho, leitura.avisos)
            # rerun redesenha a página na hora, já com o formulário preenchido.
            st.rerun()
    elif modo == "Arquivo":
        f = st.file_uploader(
            "Arquivo de demanda",
            type=TIPOS_ARQUIVO,
            help="TXT no formato do kit (Campo: valor), JSON, planilha (uma demanda por linha, ou Campo | Valor) "
            "ou uma ficha PO existente, para gerar nova revisão. Para várias demandas, use a aba Lote.",
        )
        if f is not None:
            try:
                leituras = ler_arquivo_demandas(f.getvalue(), f.name, ss.cad)
            except ErroValidacao as e:
                lista_erros("O arquivo não pôde ser lido.", e.erros)
                leituras = []
            if leituras:
                idx = 0
                # Arquivo com várias demandas: deixa escolher uma (para gerar todas, a aba Lote).
                if len(leituras) > 1:
                    nota(f"O arquivo contém <b>{len(leituras)} demandas</b>. Escolha uma, ou use a aba Lote para gerar todas.", "info")
                    idx = st.selectbox(
                        "Demanda",
                        range(len(leituras)),
                        format_func=lambda i: f"{leituras[i].origem} · {leituras[i].rascunho.get('titulo', '')}",
                    )
                if st.button("Usar este arquivo", type="primary", width="stretch"):
                    carregar_rascunho(leituras[idx].rascunho, leituras[idx].avisos)
                    st.rerun()
    elif modo == "Texto livre":
        texto = st.text_area(
            "Pedido em texto livre",
            value=EXEMPLO_TEXTO,
            height=118,
            help="Reconhece título PO-XX-000, operação entre aspas, família, tamanho, medidas, perímetro, pontos/cm, máquina (código ou nome) e a sequência de elementos. Use 4.1x2 para indicar frequência.",
        )
        st.caption("O resultado preenche a etapa 2 para você conferir antes de gerar.")
        if st.button("Interpretar texto", type="primary", width="stretch"):
            r, avisos = extrair_texto_livre(texto, ss.cad)
            carregar_rascunho(r, avisos)
            st.rerun()
    else:
        st.caption("Preencha os campos da etapa 2, logo abaixo, e clique em Gerar ficha PO.")
        if st.button("Limpar formulário", width="stretch"):
            carregar_rascunho(rascunho_vazio(), gerar=False)
            st.rerun()

    # Separa os avisos: obrigatórios em destaque, opcionais em texto discreto.
    obrig = [a for a in ss.avisos_entrada if "obrigatório" in a]
    opc = [a for a in ss.avisos_entrada if "obrigatório" not in a]
    if obrig:
        nota("<b>Faltam dados obrigatórios.</b><ul>" + "".join(f"<li>{escape(a)}</li>" for a in obrig) + "</ul>", "alerta")
    if opc:
        st.caption(" ".join(opc))


# Etapa 2: formulário de revisão. Todos os campos usam chaves com a versão v (função k).
def painel_revisao():
    secao("Etapa 2", "Confira os parâmetros", "Ajuste o que precisar. Os campos com * são obrigatórios.")
    d, v, cad = ss.draft, ss.v, ss.cad
    # Ex.: "titulo_3". Quando v muda, o Streamlit cria campos novos com os valores do novo rascunho.
    k = lambda c: f"{c}_{v}"

    c1, c2 = st.columns([4, 1])
    c1.text_input(ROTULOS["titulo"], d.get("titulo", ""), key=k("titulo"), placeholder="PO-SL-001")
    c2.text_input(ROTULOS["revisao"], d.get("revisao", "00"), key=k("revisao"))
    st.text_input(ROTULOS["operacao"], str(d.get("operacao", "")).strip('"'), key=k("operacao"), placeholder="Bainhar no corpo do SL - 1 lado")
    c1, c2, c3 = st.columns(3)
    c1.text_input("Família", d.get("familia", ""), key=k("familia"), placeholder="Sobre-lençol")
    c2.text_input(ROTULOS["tamanho"], d.get("tamanho", ""), key=k("tamanho"), placeholder="Solteiro")
    c3.text_input("Medidas (m)", d.get("medidas", ""), key=k("medidas"), placeholder="1,80 x 2,50")
    c1, c2, c3 = st.columns(3)
    c1.text_input("Perímetro (m) *", str(d.get("perimetro_m", "")), key=k("perimetro_m"), placeholder="6,96")
    c2.text_input(ROTULOS["pontos_cm"], str(d.get("pontos_cm", "")), key=k("pontos_cm"), placeholder="2,50")
    opcoes = list(cad.maquinas)
    atual = str(d.get("cod_maquina", "")).strip()
    # Aceita nome da máquina vindo do arquivo/texto e converte para o código da lista.
    atual = resolver_maquina(atual, cad) if atual else atual
    c3.selectbox(
        "Máquina *",
        opcoes,
        index=opcoes.index(atual) if atual in opcoes else None,
        format_func=lambda c: f"{c} · {cad.maquinas[c].descricao}",
        help="Código e modelo da máquina (TEMPO-CM). O tipo aparece na ficha como Equipamento.",
        key=k("cod_maquina"),
        placeholder="Selecione",
    )
    if atual and atual not in opcoes:
        nota(f"A máquina informada (<b>{escape(atual)}</b>) não está cadastrada. Selecione uma das disponíveis.", "alerta")

    try:
        itens = parse_roteiro(d.get("roteiro", ""))
    except ErroValidacao:
        itens = []
    # O roteiro vira uma tabela editável (Seq., Código MTM, Frequência).
    df = pd.DataFrame(
        {
            "Seq.": list(range(1, len(itens) + 1)),
            "Código MTM": [i.codigo for i in itens],
            "Frequência": [float(i.frequencia) for i in itens],
        }
    )
    html(
        "<div class='rotulo-campo'><b>Roteiro de elementos *</b>"
        "<span> &nbsp;na ordem de execução. Clique na última linha para adicionar; altere Seq. para reordenar.</span></div>"
    )
    rot = st.data_editor(
        df,
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        key=k("roteiro_ed"),
        column_config={
            "Seq.": st.column_config.NumberColumn(min_value=1, step=1, width="small"),
            # Código escolhido de uma lista: impede digitar um código que não existe na Matriz MTM.
            "Código MTM": st.column_config.SelectboxColumn(options=list(cad.elementos), required=True),
            "Frequência": st.column_config.NumberColumn(min_value=0.01, step=1.0, default=1.0, format="%g"),
        },
    )
    with st.expander("Consultar a Matriz de Elementos (MTM)"):
        tabela_numerica(cadastros_para_dfs(cad)[0], [])

    # Ao gerar: descarta linhas sem código, ordena pela coluna Seq. e remonta o roteiro em texto.
    if st.button("Gerar ficha PO", type="primary", width="stretch"):
        rot = rot.dropna(subset=["Código MTM"]).copy()
        # Linha nova sem Seq. vai para o fim; kind="stable" mantém a ordem original em caso de empate.
        rot["Seq."] = rot["Seq."].fillna(10_000)
        rot = rot.sort_values("Seq.", kind="stable")
        roteiro = formatar_roteiro(
            [
                ItemRoteiro(str(r["Código MTM"]), Decimal(str(r["Frequência"] if pd.notna(r["Frequência"]) else 1)).normalize())
                for _, r in rot.iterrows()
            ]
        )
        campos = ["titulo", "revisao", "operacao", "familia", "tamanho", "medidas", "perimetro_m", "pontos_cm", "cod_maquina"]
        # Lê o valor atual de cada campo do formulário pelo nome da chave.
        rascunho = {c: ss.get(k(c), "") or "" for c in campos}
        rascunho["roteiro"] = roteiro
        ss.draft = rascunho
        gerar_ficha(rascunho)


# Gráfico de barras (Altair) com o TP de cada máquina. Teto 16% acima do maior TP para caber o rótulo.
def grafico_maquinas(df: pd.DataFrame):
    teto = float(df["TP (min)"].max()) * 1.16
    base = alt.Chart(df).encode(
        y=alt.Y(
            "Rótulo:N",
            sort=list(df["Rótulo"]),
            title=None,
            axis=alt.Axis(labelLimit=400, labelFontSize=14, labelPadding=10, ticks=False, domain=False),
        ),
        x=alt.X(
            "TP (min):Q",
            title="TP (min)",
            scale=alt.Scale(domain=[0, teto], nice=False),
            axis=alt.Axis(grid=True, domain=False, ticks=False, format=".1f", tickCount=5),
        ),
    )
    barras = base.mark_bar(height=24, cornerRadiusEnd=4).encode(
        # Sem cores fixas: "Selecionada" e "Alternativa" usam as cores do tema ativo (chartCategoricalColors no config.toml),
        # assim o gráfico fica legível no claro e no escuro.
        color=alt.Color(
            "Situação:N", scale=alt.Scale(domain=["Selecionada", "Alternativa"]), legend=None
        ),
        tooltip=["Máquina", alt.Tooltip("TP (min):Q", format=".4f"), alt.Tooltip("FIXO (min):Q", format=".4f"), "Peças/hora"],
    )
    graf_padding = {"left": 28, "right": 8, "top": 4, "bottom": 4}
    # Valor do TP escrito ao lado de cada barra, na mesma cor da barra.
    rotulos = base.mark_text(align="left", dx=8, font="IBM Plex Mono", fontSize=13, fontWeight=600).encode(
        text=alt.Text("TP (min):Q", format=".4f"),
        color=alt.Color("Situação:N", scale=alt.Scale(domain=["Selecionada", "Alternativa"]), legend=None),
    )
    graf = (
        (barras + rotulos)
        .properties(height=54 * len(df), padding=graf_padding, background="transparent")
        .configure(font=FONTE_GRAFICO)
        .configure_view(strokeWidth=0)
        .configure_axis(titleFontWeight=600, titleFontSize=12)
    )
    st.altair_chart(graf, width="stretch")


# Etapa 3: a ficha pronta, os downloads, a comparação entre máquinas e a checagem da agulha.
def painel_saida():
    secao("Etapa 3", "Ficha de Processo Operacional", "No layout do gabarito oficial PO-SL-000, pronta para baixar.")
    if ss.erros:
        lista_erros("A ficha não pôde ser gerada. Corrija os campos da etapa 2:", ss.erros)
    ficha = ss.ficha
    if not ficha:
        if not ss.erros:
            nota(
                "A ficha aparece aqui assim que houver dados. O caminho mais rápido: em <b>Etapa 1</b>, deixe "
                "<b>Cenário oficial</b> selecionado e clique em <b>Carregar cenário oficial</b>.",
                "info",
            )
        return

    d, m = ficha.demanda, ficha.maquina
    # Cartões com FIXO, tempo manual, TP (destacado) e capacidade.
    fatos(
        [
            ("FIXO", f"{ficha.fixo:.4f}", "min", f"{d.perimetro_m} m × {m.tempo_por_metro}", False),
            ("Manual", f"{ficha.tempo_manual:.4f}", "min", f"{len(ficha.linhas) - 1} elementos MTM", False),
            ("TP", f"{ficha.tp:.4f}", "min", "tempo total da operação", True),
            ("Capacidade", f"{pecas_por_hora(ficha.tp)}", "pç/h", "60 / TP, a 100%", False),
        ]
    )
    html(f"<div class='doc-cab'><span>Pré-visualização</span><span>{escape(d.titulo)} · Rev. {escape(d.revisao)}</span></div>")
    # Pré-visualização no layout do gabarito.
    st.html(ficha_html(ficha))
    # Explica quando o TP não é a soma simples da coluna (há frequência diferente de 1).
    if any(l.frequencia != 1 for l in ficha.linhas):
        st.caption(
            "A coluna Tempos mostra o tempo unitário de cada elemento. Com frequência diferente de 1, "
            "o TP é a soma de frequência × tempo, e não a soma simples da coluna."
        )
    for a in ficha.avisos:
        nota(escape(a), "alerta")

    # Downloads: Excel (com cache), PDF e JSON.
    c1, c2, c3 = st.columns(3)
    c1.download_button(
        "Baixar Excel", xlsx_em_cache(ficha, ss.cad, ss.cad.origem), nome_arquivo(ficha, "xlsx"), type="primary", width="stretch"
    )
    c2.download_button("Baixar PDF", gerar_pdf(ficha), nome_arquivo(ficha, "pdf"), "application/pdf", width="stretch")
    c3.download_button("Baixar JSON", gerar_json(ficha), nome_arquivo(ficha, "json"), "application/json", width="stretch", help="Formato para integração com ERP/MES")

    secao("Análise", "Qual máquina executa este roteiro mais rápido?", "O mesmo roteiro simulado em todas as máquinas cadastradas. Informativo: não altera a ficha.")
    # Simula o mesmo roteiro em todas as máquinas (autotm/domain/analise.py).
    cen = comparar_maquinas(d, ss.cad)
    df = pd.DataFrame(
        {
            "Máquina": [c.nome for c in cen],
            "Rótulo": [f"{ss.cad.maquinas[c.codigo].descricao} · {ss.cad.maquinas[c.codigo].tipo}" for c in cen],
            "FIXO (min)": [float(c.fixo) for c in cen],
            "TP (min)": [float(c.tp) for c in cen],
            "Peças/hora": [float(c.pecas_hora) for c in cen],
            "Situação": ["Selecionada" if c.atual else "Alternativa" for c in cen],
        }
    )
    # Legenda escrita do gráfico: a informação não depende só da cor.
    html(
        f"<div class='legenda'><i style='background:var(--acento)'></i>máquina selecionada"
        f"<i style='background:var(--neutro);margin-left:18px'></i>alternativas</div>"
    )
    grafico_maquinas(df)
    # A lista vem ordenada pelo TP: a primeira é a mais rápida. Mostra o ganho em relação à selecionada.
    melhor = cen[0]
    if not melhor.atual:
        atual = next(c for c in cen if c.atual)
        ganho = (atual.tp - melhor.tp) / atual.tp * 100
        mq = ss.cad.maquinas[melhor.codigo]
        citacao(
            f"Na {escape(mq.descricao)}, o TP cai para <b>{melhor.tp:.4f} min</b>: {ganho:.1f}% menor, "
            f"com {melhor.pecas_hora} peças por hora contra {atual.pecas_hora}.",
            "Comparação com a máquina selecionada, mesmo roteiro e perímetro",
        )
    else:
        citacao("A máquina selecionada já tem o menor TP para este roteiro.")
    with st.expander("Tabela da comparação"):
        tabela_numerica(df.drop(columns=["Situação", "Rótulo"]), ["FIXO (min)", "TP (min)"])

    # Leitura complementar por RPM e pontos/cm; só aparece quando a demanda informa pontos/cm.
    chk = checagem_agulha(ficha)
    if chk:
        secao("Consistência", "Checagem por RPM e densidade de pontos")
        html(
            "<div class='texto-corrido'>"
            f"{d.perimetro_m} m × 100 × {d.pontos_cm} pontos/cm = <b>{chk.total_pontos} pontos</b>. "
            f"A {m.rpm:.0f} RPM, a agulha fica <b>{chk.tempo_agulha_min:.4f} min</b> em movimento, "
            f"o que corresponde a <b>{chk.percentual_do_fixo}%</b> do FIXO. O restante cobre aceleração, frenagem, "
            "condução do tecido e curvas, já embutidos no fator tempo/metro da máquina. "
            "<span class='sec-txt'>Indicador apenas informativo, para leitura da engenharia; não altera o FIXO "
            "oficial, que segue a fórmula do regulamento.</span></div>"
        )


# Aba Nova ficha: etapas no topo, entrada e revisão à esquerda, ficha à direita.
with aba_nova:
    # Etapa atual: 3 se já há ficha, 2 se já há rascunho carregado, senão 1.
    etapas(3 if ss.ficha else 2 if ss.v > 0 else 1)
    col_in, col_out = st.columns([9, 11], gap="large")
    with col_in:
        painel_entrada()
        painel_revisao()
    with col_out:
        painel_saida()


# Aba Lote: lê vários arquivos, gera todas as fichas válidas e lista as inválidas com o motivo.
with aba_lote:
    secao(
        "Lote",
        "Várias demandas de uma só vez",
        "Envie um ou mais arquivos: CSV, Excel ou ODS com uma demanda por linha, JSON com lista ou vários TXT. "
        "Cada demanda é validada separadamente; as válidas viram ficha e as inválidas aparecem com o motivo.",
    )
    arquivos = st.file_uploader("Arquivos de demandas", type=TIPOS_ARQUIVO, accept_multiple_files=True, key="lote_up")
    if arquivos:
        leituras = []
        for a in arquivos:
            try:
                leituras += ler_arquivo_demandas(a.getvalue(), a.name, ss.cad)
            except ErroValidacao as e:
                lista_erros(f"{a.name}: arquivo não lido", e.erros)
        # Cada demanda é validada separadamente: uma com erro não impede as outras.
        res = processar_lote(leituras, ss.cad)
        ok = [r for r in res if r.ficha]
        fatos(
            [
                ("Demandas lidas", str(len(res)), "", f"{len(arquivos)} arquivo(s)", False),
                ("Fichas geradas", str(len(ok)), "", "prontas para exportar", True),
                ("Com erro", str(len(res) - len(ok)), "", "ver motivos abaixo" if len(res) > len(ok) else "nenhuma", False),
                ("TP médio", f"{sum(r.ficha.tp for r in ok) / len(ok):.4f}" if ok else "-", "min" if ok else "", "fichas válidas", False),
            ]
        )
        tabela = pd.DataFrame(
            [
                {
                    "Situação": "Gerada" if r.ficha else "Erro",
                    "Origem": r.origem,
                    "PO": r.ficha.demanda.titulo if r.ficha else "",
                    "Operação": r.ficha.demanda.operacao if r.ficha else "",
                    "Máquina": f"{r.ficha.maquina.codigo} · {r.ficha.maquina.descricao}" if r.ficha else "",
                    "FIXO (min)": f"{r.ficha.fixo:.4f}" if r.ficha else "",
                    "TP (min)": f"{r.ficha.tp:.4f}" if r.ficha else "",
                }
                for r in res
            ]
        )
        st.dataframe(tabela, hide_index=True, width="stretch")
        for r in res:
            if r.erros:
                lista_erros(f"{r.origem}: ficha não gerada", r.erros)
        if ok:
            c1, c2 = st.columns([1, 2])
            pdf = c1.toggle("Incluir PDFs", value=True)
            c2.download_button(
                f"Baixar {len(ok)} fichas e resumo (.zip)",
                # ZIP com as fichas e a planilha RESUMO_LOTE.xlsx.
                gerar_zip(res, ss.cad, incluir_pdf=pdf),
                f"POs_lote_{agora():%Y%m%d_%H%M}.zip",
                "application/zip",
                type="primary",
            )
    else:
        nota("Para testar, use <b>exemplos/03_lote_demandas.csv</b>: são 5 demandas, uma delas com erro proposital.", "info")


# Aba Histórico: fichas desta sessão, com download e opção de reabrir no formulário.
with aba_hist:
    secao("Histórico", "Fichas geradas nesta sessão", "As 30 mais recentes. Reabra uma ficha para revisá-la ou gerar uma nova revisão.")
    if not ss.historico:
        nota("Nenhuma ficha gerada ainda.", "info")
    for i, (quando, f) in enumerate(ss.historico):
        c1, c2, c3 = st.columns([6, 1.2, 1.2], vertical_alignment="center")
        with c1:
            html(
                f"<div class='hist'><div class='t'>{escape(f.demanda.titulo)} · Rev. {escape(f.demanda.revisao)}</div>"
                f"<div class='m'>{escape(f.demanda.operacao or 'Operação sem descrição')} · Máquina {escape(f.maquina.codigo)} "
                f"· TP {f.tp:.4f} min · gerada às {quando:%H:%M:%S}</div></div>"
            )
        c2.download_button("Excel", xlsx_em_cache(f, ss.cad, ss.cad.origem), nome_arquivo(f, "xlsx"), key=f"h_dl_{i}", width="stretch")
        if c3.button("Reabrir", key=f"h_open_{i}", width="stretch"):
            # registrar=False: reabrir não cria uma entrada duplicada no histórico.
            carregar_rascunho(demanda_para_rascunho(f.demanda), registrar=False)
            st.rerun()


# Aba Auditoria: confere fichas existentes contra o recálculo (autotm/servicos/auditoria.py).
def painel_auditoria():
    secao(
        "Auditoria",
        "Confira fichas PO já existentes",
        "Envie fichas feitas à mão ou por outro sistema. Cada uma é lida, recalculada com os cadastros em uso e comparada "
        "item a item: FIXO, tempos e descrições MTM, RPM e TP. Útil para validar POs antigas e para encontrar as fichas "
        "que ficaram desatualizadas depois de uma mudança no cadastro.",
    )
    c1, c2 = st.columns([2, 3], vertical_alignment="bottom")
    if c1.button("Auditar o gabarito oficial", type="primary", help="Audita kit_oficial/PO-SL-000.ods"):
        arq = CAMINHO_PADRAO.parent / "PO-SL-000.ods"
        # O resultado fica na sessão para não sumir no próximo clique.
        ss.auditoria = auditar_arquivo(arq.read_bytes(), arq.name, ss.cad)
    arquivos = c2.file_uploader("Fichas PO (.ods, .xlsx)", type=["ods", "xlsx", "xls"], accept_multiple_files=True, key="audit_up")
    if arquivos:
        ss.auditoria = [r for a in arquivos for r in auditar_arquivo(a.getvalue(), a.name, ss.cad)]

    resultados = ss.get("auditoria") or []
    if not resultados:
        nota("Clique em <b>Auditar o gabarito oficial</b> ou envie uma ou mais fichas PO.", "info")
        return

    validas = [r for r in resultados if not r.erros]
    total = sum(r.total for r in validas)
    diverg = sum(len(r.divergencias) for r in validas)
    fatos(
        [
            ("Fichas auditadas", str(len(resultados)), "", f"{len(resultados) - len(validas)} não lida(s)", False),
            ("Itens conferidos", str(total), "", "FIXO, MTM, RPM e TP", False),
            ("Divergências", str(diverg), "", "nenhuma" if not diverg else "ver detalhes", False),
            ("Conformidade", f"{(total - diverg) / total * 100:.1f}" if total else "-", "%", "itens que conferem", True),
        ]
    )
    for res in resultados:
        if res.erros:
            lista_erros(f"{res.origem}: não auditada", res.erros)
            continue
        f = res.ficha_recalculada
        if res.divergencias:
            nota(
                f"<b>{escape(res.origem)}</b> · {escape(f.demanda.titulo)}: <b>{len(res.divergencias)} divergência(s)</b> "
                f"em {res.total} itens ({res.conformidade}% conforme).",
                "erro",
            )
        else:
            nota(
                f"<b>{escape(res.origem)}</b> · {escape(f.demanda.titulo)}: todos os <b>{res.total} itens conferem</b> "
                "com os cadastros em uso.",
                "ok",
            )
        tabela = pd.DataFrame(
            [
                {
                    "Situação": "Confere" if c.ok else "Diverge",
                    "Célula": c.celula,
                    "Item": c.item,
                    "Na ficha": c.na_ficha,
                    "Recalculado": c.calculado,
                    "Observação": c.motivo,
                }
                for c in res.conferencias
            ]
        )
        # Linhas divergentes em vermelho translúcido e negrito; a coluna Situação também diz "Diverge" por escrito.
        estilo = tabela.style.apply(
            lambda linha: ["background-color:rgba(214,64,52,.22);font-weight:700" if linha["Situação"] == "Diverge" else ""]
            * len(linha),
            axis=1,
        )
        st.dataframe(
            estilo,
            hide_index=True,
            width="stretch",
            column_config={
                "Situação": st.column_config.TextColumn(width="small"),
                "Célula": st.column_config.TextColumn(width="small"),
                "Item": st.column_config.TextColumn(width="medium"),
            },
        )
        for obs in res.observacoes:
            st.caption(obs)
        # Ficha com divergência: oferece a versão corrigida já com a revisão seguinte (00 -> 01).
        proxima = f"{int(f.demanda.revisao) + 1:02d}" if f.demanda.revisao.isdigit() else f"{f.demanda.revisao}-1"
        revisada = replace(f, demanda=replace(f.demanda, revisao=proxima))
        st.download_button(
            f"Baixar ficha recalculada (Rev. {proxima})" if res.divergencias else "Baixar ficha regenerada no sistema",
            gerar_xlsx(revisada if res.divergencias else f, ss.cad),
            nome_arquivo(revisada if res.divergencias else f, "xlsx"),
            key=f"aud_dl_{res.origem}",
        )


with aba_audit:
    painel_auditoria()


# Aba Metodologia: explica as regras do cálculo e os formatos de entrada aceitos.
with aba_metodo:
    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        secao("Metodologia", "Como a ficha é calculada")
        html(
            "<div class='artigo'><div class='standfirst'>O sistema reproduz o raciocínio do engenheiro de Tempos e Métodos: "
            "o tempo de máquina vem do perímetro de costura, os tempos manuais vêm da Matriz MTM e o total soma os dois.</div>"
            "<div class='regra'><div class='n'>1</div><div class='h'>Elemento FIXO: costura de máquina</div>"
            "<div class='c'><span class='formula'>FIXO = Perímetro de costura (m) × Tempo por metro da máquina (min/m)</span><br>"
            "Arredondado a 4 casas, meio para cima, como no gabarito: 6,96 × 0,0964 = 0,670944, registrado como <b>0,6709</b>.</div></div>"
            "<div class='regra'><div class='n'>2</div><div class='h'>Elementos manuais</div>"
            "<div class='c'>A descrição e o tempo de cada código (agrupador.elemento, por exemplo 2.1) são consultados na Matriz MTM, "
            "na ordem do roteiro.</div></div>"
            "<div class='regra'><div class='n'>3</div><div class='h'>Frequência</div>"
            "<div class='c'>Um elemento pode se repetir na operação (4.1x2). A ficha mostra o tempo unitário e o TP considera "
            "o tempo multiplicado pela frequência.</div></div>"
            "<div class='regra'><div class='n'>4</div><div class='h'>Tempo total da operação</div>"
            "<div class='c'><span class='formula'>TP = FIXO + Σ (tempo MTM × frequência)</span></div></div>"
            "<div class='regra'><div class='n'>5</div><div class='h'>Faixa de RPM</div>"
            "<div class='c'>Limite inferior de 90% e superior de 110% do RPM padrão, com as fórmulas mantidas no Excel.</div></div>"
            "<div class='regra'><div class='n'>6</div><div class='h'>Precisão verificada</div>"
            "<div class='c'>Os cálculos usam aritmética decimal exata, sem erro de ponto flutuante. Um teste automatizado compara "
            "o Excel gerado com o gabarito PO-SL-000 célula por célula: valores, fórmulas, mesclagens e cores.</div></div></div>"
        )
    with c2:
        secao("Entradas", "Formatos aceitos")
        html(
            "<table class='tab-simples'><tr><th>Formato</th><th>Exemplo</th></tr>"
            "<tr><td>TXT oficial (Campo: valor)</td><td><code>01_demanda_oficial.txt</code></td></tr>"
            "<tr><td>JSON (objeto ou lista)</td><td><code>02_demanda.json</code></td></tr>"
            "<tr><td>CSV, Excel ou ODS em lote</td><td><code>03_lote_demandas.csv</code></td></tr>"
            "<tr><td>Planilha Campo | Valor</td><td>qualquer .xlsx ou .ods</td></tr>"
            "<tr><td>Texto livre</td><td><code>04_texto_livre.txt</code></td></tr>"
            "<tr><td>Ficha PO existente</td><td><code>PO-SL-000.ods</code></td></tr>"
            "<tr><td>Formulário</td><td>aba Nova ficha</td></tr></table>"
            "<p class='texto-corrido' style='color:var(--sec);margin-top:12px'>Os nomes de campos são reconhecidos com tolerância "
            "a acentos, maiúsculas e sinônimos (Cód. Eqp, máquina, equipamento). A máquina pode ser indicada pelo código, "
            "com ou sem zero à esquerda, ou pelo nome. Os números aceitam vírgula ou ponto decimal, e o perímetro aceita "
            "cm e mm, com conversão avisada. O cabeçalho das planilhas é localizado mesmo com linhas de título acima.</p>"
        )
        secao("Cadastros", "Máquinas em uso")
        tabela_numerica(cadastros_para_dfs(ss.cad)[1], ["Tempo/metro (min/m)"])
