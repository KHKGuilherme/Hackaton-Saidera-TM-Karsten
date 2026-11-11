# Peças visuais da interface: paletas dos temas, CSS, sincronização do tema e funções que desenham blocos HTML.
# O app.py só chama estas funções; assim a aparência fica concentrada num arquivo.
from __future__ import annotations

import json
from html import escape

import streamlit as st
import streamlit.components.v1 as components

# Cores dos dois temas, com os mesmos nomes de token. O CSS usa só os nomes (var(--acento)), nunca a cor direta.
# Contraste de todos os pares texto/fundo conferido para WCAG 2.1 AA (4,5:1 para texto normal).
PALETAS = {
    # Tema claro: identidade Karsten, predominantemente branco, com azul (#005A7A) e um toque de amarelo.
    "light": {
        "fundo": "#FFFFFF",
        "sup": "#F4F7F9",
        "sup2": "#E8EFF3",
        "filete": "#D6E0E6",
        "borda": "#6F8694",
        "texto": "#0B2236",
        "sec": "#4B6070",
        "acento": "#005A7A",
        "acento_hover": "#00475F",
        "sobre_acento": "#FFFFFF",
        "destaque": "#FFE073",
        "sobre_destaque": "#0B2236",
        "faixa": "#F2B705",
        "selecionado": "#E6F1F5",
        "placeholder": "#5E7280",
        "neutro": "#5E7A8A",
        "erro": "#B3261E",
        "alerta": "#8A5A00",
        "ok": "#1B6E3E",
        "info": "#005A7A",
        "nota_erro": "#FDECEA",
        "nota_alerta": "#FFF5D6",
        "nota_ok": "#E8F5EC",
        "nota_info": "#EAF3F7",
        "div_fundo": "#FCE4E2",
        "div_texto": "#8C1D18",
        "sombra_folha": "0 6px 20px rgba(0,42,71,.12), 0 0 0 1px #D6E0E6",
    },
    # Tema escuro: marinho Karsten (#001521) com verde-água (#92CFCA) como acento.
    "dark": {
        "fundo": "#001521",
        "sup": "#04212F",
        "sup2": "#0A2D3E",
        "filete": "#133A4E",
        "borda": "#4F7385",
        "texto": "#F8F1E9",
        "sec": "#A7BEC8",
        "acento": "#92CFCA",
        "acento_hover": "#B4E0DC",
        "sobre_acento": "#001521",
        "destaque": "#92CFCA",
        "sobre_destaque": "#001521",
        "faixa": "#92CFCA",
        "selecionado": "#06323A",
        "placeholder": "#7F9AA6",
        "neutro": "#5FA3BF",
        "erro": "#FF8A80",
        "alerta": "#F2C46D",
        "ok": "#6FD8A6",
        "info": "#6FB7D6",
        "nota_erro": "#2A1519",
        "nota_alerta": "#241D10",
        "nota_ok": "#0B241B",
        "nota_info": "#06202B",
        "div_fundo": "#3A1D22",
        "div_texto": "#FFC4BE",
        "sombra_folha": "0 10px 30px rgba(0,0,0,.55), 0 0 0 1px rgba(255,255,255,.06)",
    },
}
# Fonte principal da interface (também configurada no .streamlit/config.toml).
FONTE_UI = "Instrument Sans"


# Converte {"acento_hover": "#00475F"} em "--acento-hover:#00475F;" (variáveis CSS).
def _variaveis(cores: dict[str, str]) -> str:
    return "".join(f"--{nome.replace('_', '-')}:{valor};" for nome, valor in cores.items())


# CSS de toda a interface, organizado em grupos: fontes, foco do teclado (contorno de 3px), cabeçalho (.mast),
# abas, etapas, cartões de origem, notas, ficha e tabelas. Todas as cores vêm das variáveis do tema.
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700;9..144,800&family=Instrument+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root{
  --serif:'Fraunces', Georgia, serif;
  --sans:'Instrument Sans', 'Helvetica Neue', Arial, sans-serif;
  --mono:'IBM Plex Mono', Consolas, monospace;
}

[data-testid="stDecoration"]{display:none}
header[data-testid="stHeader"]{background:transparent}
.block-container, [data-testid="stMainBlockContainer"]{padding-top:1.1rem !important; padding-bottom:4rem; max-width:1340px}
body, .stMarkdown, p, label, input, textarea, button{font-family:var(--sans)}
::selection{background:var(--acento); color:var(--sobre-acento)}

button:focus-visible, input:focus-visible, textarea:focus-visible, [role="tab"]:focus-visible,
[role="radio"]:focus-visible, a:focus-visible, label:focus-within{outline:3px solid var(--acento) !important; outline-offset:2px}

.mast{display:flex; justify-content:space-between; align-items:flex-end; gap:24px; flex-wrap:wrap;
      padding:26px 4px 18px; border-bottom:1px solid var(--filete); position:relative}
.mast::after{content:""; position:absolute; left:4px; bottom:-1px; width:72px; height:4px; background:var(--faixa)}
.mast .marca{font-family:var(--serif); font-weight:800; font-size:52px; line-height:.95; letter-spacing:-1.5px; color:var(--texto);
             font-variation-settings:"opsz" 144}
.mast .marca em{font-style:italic; font-weight:600; color:var(--acento)}
.mast .linha{font-family:var(--sans); font-size:16px; color:var(--sec); margin-top:10px}
.mast .meta{font-family:var(--mono); font-size:12.5px; color:var(--sec); text-align:right; line-height:1.7}
.mast .meta b{color:var(--texto); font-weight:500}

.stTabs [role="tablist"]{gap:34px; border-bottom:1px solid var(--filete); margin:6px 0 4px}
.stTabs [data-testid="stTab"]{height:auto; padding:16px 0 13px; background:transparent}
.stTabs [data-testid="stTab"] p{font-family:var(--serif) !important; font-weight:600; font-size:20px !important; color:var(--sec); line-height:1.2}
.stTabs [data-testid="stTab"]:hover p{color:var(--texto)}
.stTabs [data-testid="stTab"][aria-selected="true"] p{color:var(--texto)}
.stTabs .react-aria-SelectionIndicator{background:var(--acento) !important; height:3px !important}

.etapas{display:flex; gap:0; margin:18px 0 6px; border:1px solid var(--filete); border-radius:12px; overflow:hidden; background:var(--sup)}
.etapa{flex:1; display:flex; align-items:center; gap:12px; padding:12px 16px; border-left:1px solid var(--filete); min-width:0}
.etapa:first-child{border-left:none}
.etapa .n{flex:none; width:30px; height:30px; border-radius:50%; display:grid; place-items:center;
          font-family:var(--mono); font-weight:600; font-size:14px; border:2px solid var(--neutro); color:var(--sec)}
.etapa .t{font-weight:600; font-size:15px; color:var(--sec); white-space:nowrap; overflow:hidden; text-overflow:ellipsis}
.etapa .s{font-size:12.5px; color:var(--sec); opacity:.85}
.etapa.feita .n{background:var(--acento); border-color:var(--acento); color:var(--sobre-acento)}
.etapa.feita .t{color:var(--texto)}
.etapa.atual{background:var(--sup2)}
.etapa.atual .n{border-color:var(--acento); color:var(--acento)}
.etapa.atual .t{color:var(--texto)}
@media (max-width:700px){ .etapa .s{display:none} .etapa{padding:10px} }

.sec{margin:20px 0 14px}
.sec .kicker{font-family:var(--mono); font-weight:500; font-size:12.5px; color:var(--acento); text-transform:uppercase; letter-spacing:.12em}
.sec .titulo{font-family:var(--serif); font-weight:700; font-size:30px; line-height:1.1; color:var(--texto); margin:6px 0 0;
             letter-spacing:-.4px; font-variation-settings:"opsz" 72}
.sec .dek{color:var(--sec); font-size:15.5px; margin-top:8px; line-height:1.5; max-width:72ch}

.fatos{display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:10px; margin:4px 0 18px}
.fato{background:var(--sup); border:1px solid var(--filete); border-radius:12px; padding:14px 16px 14px}
.fato .rot{font-size:13px; font-weight:600; color:var(--sec); text-transform:uppercase; letter-spacing:.06em;
           white-space:nowrap; overflow:hidden; text-overflow:ellipsis}
.fato .rot .un{font-family:var(--mono); text-transform:none; letter-spacing:0; font-weight:400; margin-left:6px}
.fato .val{font-family:var(--sans); font-weight:700; font-size:36px; line-height:1.05; color:var(--texto); letter-spacing:-.5px;
           font-variant-numeric:tabular-nums lining-nums; margin-top:8px; white-space:nowrap}
.fato .det{font-size:13px; color:var(--sec); margin-top:6px; line-height:1.35}
.fato.tp{background:var(--destaque); border-color:var(--destaque)}
.fato.tp .rot, .fato.tp .det, .fato.tp .val{color:var(--sobre-destaque)}
@media (max-width:480px){ .fatos{grid-template-columns:repeat(2,minmax(0,1fr))} .fato .val{font-size:28px} }

.nota{border:1px solid var(--filete); border-left:4px solid var(--info); background:var(--nota-info); border-radius:10px;
      padding:12px 16px; margin:10px 0; font-size:15.5px; line-height:1.5; color:var(--texto)}
.nota b{font-weight:700}
.nota ul{margin:6px 0 0 18px; padding:0}
.nota .rotulo{display:block; font-family:var(--mono); font-size:12px; letter-spacing:.1em; text-transform:uppercase; margin-bottom:4px}
.nota.erro{border-left-color:var(--erro); background:var(--nota-erro)} .nota.erro .rotulo{color:var(--erro)}
.nota.alerta{border-left-color:var(--alerta); background:var(--nota-alerta)} .nota.alerta .rotulo{color:var(--alerta)}
.nota.ok{border-left-color:var(--ok); background:var(--nota-ok)} .nota.ok .rotulo{color:var(--ok)}
.nota.info .rotulo{color:var(--info)}

.citacao{border-left:4px solid var(--faixa); padding:4px 0 4px 18px; margin:16px 0}
.citacao .q{font-family:var(--serif); font-size:22px; line-height:1.35; font-weight:500; color:var(--texto); font-style:italic}
.citacao .q b{font-style:normal; color:var(--acento); font-weight:700}
.citacao .a{font-size:13px; color:var(--sec); margin-top:8px}

.doc-cab{display:flex; justify-content:space-between; font-family:var(--mono); font-size:12px; color:var(--sec);
         text-transform:uppercase; letter-spacing:.1em; padding:0 2px 8px}

div[data-testid="stRadio"] [role="radiogroup"]{display:grid !important; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px}
div[data-testid="stRadio"] [role="radiogroup"] > div{position:relative; padding:14px 16px 14px; min-height:72px; border:1px solid var(--borda);
     border-radius:12px; background:var(--sup); cursor:pointer; transition:border-color .15s, background .15s}
div[data-testid="stRadio"] [role="radiogroup"] > div:hover{border-color:var(--sec)}
div[data-testid="stRadio"] [role="radiogroup"] > div[data-selected="true"]{border-color:var(--acento); background:var(--selecionado);
     box-shadow:inset 0 0 0 1px var(--acento)}
div[data-testid="stRadio"] [role="radiogroup"] > div:focus-within{outline:3px solid var(--acento); outline-offset:2px}
div[data-testid="stRadio"] label[data-testid="stRadioOption"]{margin:0 !important; padding:0 !important; position:static}
div[data-testid="stRadio"] label[data-testid="stRadioOption"]:focus-within{outline:none !important}
div[data-testid="stRadio"] label[data-testid="stRadioOption"]::after{content:""; position:absolute; inset:0; border-radius:12px}
div[data-testid="stRadio"] label[data-testid="stRadioOption"] p{font-weight:600; font-size:16px; color:var(--texto)}
div[data-testid="stRadio"] [data-testid="stRadioCaption"]{padding:2px 0 0 28px; margin:0}
div[data-testid="stRadio"] [data-testid="stRadioCaption"] p{font-size:13.5px; color:var(--sec); line-height:1.35}
@media (max-width:700px){ div[data-testid="stRadio"] [role="radiogroup"]{grid-template-columns:1fr} }

.stButton button, .stDownloadButton button{min-height:46px; font-weight:600; font-size:15.5px; padding:0 22px; letter-spacing:.01em}
.stButton button p, .stDownloadButton button p{font-weight:650; font-size:15.5px}
button[data-testid="stBaseButton-primary"]{background:var(--acento) !important; border-color:var(--acento) !important; color:var(--sobre-acento) !important}
button[data-testid="stBaseButton-primary"] p{color:var(--sobre-acento) !important}
button[data-testid="stBaseButton-primary"]:hover{background:var(--acento-hover) !important; border-color:var(--acento-hover) !important}
button[data-testid="stBaseButton-secondary"]{background:transparent; border:1px solid var(--borda); color:var(--texto)}
button[data-testid="stBaseButton-secondary"]:hover{border-color:var(--acento); color:var(--acento)}
label[data-testid="stWidgetLabel"] p{font-weight:600; font-size:14.5px; color:var(--texto)}
[data-testid$="RootElement"], [data-testid="stSelectbox"] div:has(> input), [data-testid="stTextArea"] textarea{background:var(--sup) !important}
[data-testid$="RootElement"], [data-testid="stSelectbox"] div:has(> input){border-color:var(--borda) !important; min-height:44px}
input, textarea{font-size:16px !important; color:var(--texto) !important}
input::placeholder, textarea::placeholder{color:var(--placeholder) !important}
[data-testid="stExpander"] details{border-color:var(--filete); background:var(--sup)}
[data-testid="stExpander"] summary p{font-weight:600}
[data-testid="stFileUploaderDropzone"]{background:var(--sup); border:1px dashed var(--borda)}
[data-testid="stFileUploaderDropzone"] button{min-height:44px}
div[role="dialog"]{width:min(1240px,94vw) !important; max-width:none !important; background:var(--sup) !important;
     border:1px solid var(--filete); border-top:4px solid var(--faixa)}
div[role="dialog"] .estat b{font-size:44px}
[data-testid="stCaptionContainer"] p{color:var(--sec)}

section[data-testid="stSidebar"] .sec{margin-top:0}
.estat{display:flex; gap:26px; margin:6px 0 8px}
.estat div{font-size:13px; color:var(--sec); line-height:1.25}
.estat b{display:block; font-family:var(--serif); font-size:38px; font-weight:700; color:var(--texto)}
.fonte{font-family:var(--mono); font-size:12px; color:var(--sec); border-top:1px solid var(--filete); padding-top:10px; margin:6px 0 14px}
.regras{font-size:13.5px; color:var(--sec); line-height:1.65; border-top:1px solid var(--filete); padding-top:14px; margin-top:10px}
.regras b{color:var(--texto); font-weight:600}
.regras code{font-family:var(--mono); font-size:12.5px; color:var(--texto); background:transparent; padding:0}

.hist{border-top:1px solid var(--filete); padding:14px 0 4px}
.hist .t{font-family:var(--serif); font-weight:700; font-size:20px}
.hist .m{font-size:14px; color:var(--sec); margin-top:3px}
.hist .m code{font-family:var(--mono); color:var(--texto); background:transparent; padding:0}

.artigo .standfirst{font-family:var(--serif); font-size:22px; line-height:1.45; color:var(--texto); margin:4px 0 20px; font-weight:400}
.regra{display:grid; grid-template-columns:52px 1fr; gap:6px 14px; border-top:1px solid var(--filete); padding:16px 0}
.regra .n{font-family:var(--serif); font-weight:800; font-size:34px; color:var(--acento); line-height:1}
.regra .h{font-family:var(--serif); font-weight:700; font-size:20px}
.regra .c{font-size:15.5px; color:var(--texto); line-height:1.55; grid-column:2}
.formula{font-family:var(--mono); font-size:15px; background:var(--sup2); border:1px solid var(--filete); border-radius:8px;
         padding:10px 14px; margin:8px 0; display:inline-block; color:var(--texto)}
.tab-simples, .tab-simples tr{border:none !important}
.tab-simples{width:100%; border-collapse:collapse; font-size:15px}
.tab-simples th{text-align:left; font-weight:700; border:none !important; border-bottom:1px solid var(--sec) !important; padding:8px 8px 8px 0; background:transparent !important}
.tab-simples td{border:none !important; border-bottom:1px solid var(--filete) !important; padding:9px 8px 9px 0; vertical-align:top}
.tab-simples code{font-family:var(--mono); font-size:13px}
.legenda{font-size:13.5px; color:var(--sec); margin:-2px 0 6px}
.legenda i{display:inline-block; width:11px; height:11px; border-radius:3px; margin:0 7px -1px 0}
.texto-corrido{font-size:15.5px; line-height:1.6}
.texto-corrido .sec-txt{color:var(--sec)}
.rotulo-campo{margin:12px 0 4px}
.rotulo-campo b{font-weight:600; font-size:14.5px}
.rotulo-campo span{color:var(--sec); font-size:14px}
</style>
"""

# Toda nota começa com um rótulo escrito: o estado nunca é indicado só pela cor (acessibilidade).
_ROTULO_NOTA = {"erro": "Erro", "alerta": "Atenção", "ok": "Tudo certo", "info": "Como usar"}


# JavaScript que roda na página principal: a cada 250 ms mede o brilho do fundo do app.
# Fundo escuro -> marca <html data-tema="escuro">; claro -> "claro". O CSS dos temas reage a essa marca.
# Motivo: trocar o tema no menu do Streamlit não reexecuta o Python, então o CSS precisa se ajustar sozinho.
_SINCRONIZAR_TEMA = """
(function () {
  function luminancia(cor) {
    var n = (cor.match(/\\d+/g) || [255, 255, 255]).map(Number);
    return (0.299 * n[0] + 0.587 * n[1] + 0.114 * n[2]) / 255;
  }
  function sincronizar() {
    var app = document.querySelector('.stApp');
    if (!app) return;
    var tema = luminancia(getComputedStyle(app).backgroundColor) < 0.5 ? 'escuro' : 'claro';
    if (document.documentElement.dataset.tema !== tema) document.documentElement.dataset.tema = tema;
  }
  sincronizar();
  setInterval(sincronizar, 250);
})();
"""

# Script executado uma vez: define o idioma da página como pt-BR (leitores de tela pronunciam certo),
# tira do Tab o iframe invisível que o Streamlit cria e instala o sincronizador de tema uma única vez (id autotm-tema).
# json.dumps transforma o código do sincronizador num texto JavaScript seguro para ser inserido.
_PAGINA_JS = """<script>
const d = window.parent.document;
d.documentElement.lang = 'pt-BR';
const f = window.frameElement;
if (f) { f.setAttribute('tabindex', '-1'); f.setAttribute('aria-hidden', 'true'); f.title = 'configuração da página'; }
if (!d.getElementById('autotm-tema')) {
  const s = d.createElement('script');
  s.id = 'autotm-tema';
  s.textContent = %s;
  d.head.appendChild(s);
}
</script>""" % json.dumps(_SINCRONIZAR_TEMA)


# Gera as variáveis das duas paletas. Ordem de prioridade:
# 1) padrão claro; 2) se o sistema estiver escuro e não houver escolha "claro", usa o escuro;
# 3) se a página estiver marcada como escura (escolha no menu), usa o escuro.
def _css_dos_temas() -> str:
    claro, escuro = _variaveis(PALETAS["light"]), _variaveis(PALETAS["dark"])
    return (
        f"<style>:root{{{claro}}}"
        f"@media (prefers-color-scheme: dark){{:root:not([data-tema='claro']){{{escuro}}}}}"
        f":root[data-tema='escuro']{{{escuro}}}</style>"
    )


# Aplica tudo no início de cada execução. O container de altura 1 esconde o iframe do script.
def aplicar_estilo() -> None:
    st.markdown(_css_dos_temas() + CSS, unsafe_allow_html=True)
    with st.container(height=1, border=False):
        components.html(_PAGINA_JS, height=0)


# Atalho para desenhar HTML. unsafe_allow_html só recebe textos já escapados pelas funções abaixo.
def html(conteudo: str) -> None:
    st.markdown(conteudo, unsafe_allow_html=True)


# Cabeçalho do app: marca à esquerda e, à direita, a base de cadastros em uso. role=heading ajuda leitores de tela.
def masthead(n_elementos: int, n_maquinas: int, origem: str) -> None:
    html(
        "<div class='mast'><div><div class='marca' role='heading' aria-level='1'>Auto-T<em>&amp;</em>M</div></div>"
        f"<div class='meta'>base <b>{escape(origem)}</b><br>{n_elementos} elementos MTM · {n_maquinas} máquinas</div></div>"
    )


# Barra de progresso Entrada -> Revisão -> Ficha PO. aria-label diz o estado de cada etapa em texto.
def etapas(atual: int) -> None:
    dados = [
        ("Entrada", "escolha a origem dos dados"),
        ("Revisão", "confira os parâmetros"),
        ("Ficha PO", "visualize e exporte"),
    ]
    blocos = []
    for i, (titulo, sub) in enumerate(dados, start=1):
        estado = "feita" if i < atual else "atual" if i == atual else ""
        rotulo = {"feita": "concluída", "atual": "etapa atual"}.get(estado, "pendente")
        blocos.append(
            f"<div class='etapa {estado}' aria-label='Etapa {i}: {titulo}, {rotulo}'>"
            f"<span class='n'>{i}</span><div><div class='t'>{titulo}</div><div class='s'>{sub}</div></div></div>"
        )
    html("<nav class='etapas' aria-label='Progresso'>" + "".join(blocos) + "</nav>")


# Título de seção no estilo editorial: chamada pequena (kicker), título e linha de apoio (dek).
def secao(kicker: str, titulo: str, dek: str = "") -> None:
    dek_html = f"<div class='dek'>{dek}</div>" if dek else ""
    html(
        f"<div class='sec'><div class='kicker'>{escape(kicker)}</div>"
        f"<div class='titulo' role='heading' aria-level='2'>{escape(titulo)}</div>{dek_html}</div>"
    )


# Cartões de números (FIXO, TP, RPM...). O último parâmetro de cada item destaca o cartão (usado no TP).
def fatos(itens: list[tuple[str, str, str, str, bool]]) -> None:
    blocos = []
    for rot, val, un, det, dest in itens:
        un_html = f"<span class='un'>{escape(un)}</span>" if un else ""
        det_html = f"<div class='det'>{escape(det)}</div>" if det else ""
        blocos.append(
            f"<div class='fato{' tp' if dest else ''}'><div class='rot'>{escape(rot)}{un_html}</div>"
            f"<div class='val'>{escape(val)}</div>{det_html}</div>"
        )
    html("<div class='fatos'>" + "".join(blocos) + "</div>")


# Caixa de aviso. role="alert" só para erro, para o leitor de tela anunciar na hora; os demais são "note".
def nota(texto_html: str, tipo: str = "info", rotulo: str | None = None) -> None:
    r = rotulo if rotulo is not None else _ROTULO_NOTA.get(tipo, "")
    r_html = f"<span class='rotulo'>{escape(r)}</span>" if r else ""
    html(f"<div class='nota {tipo}' role='{'alert' if tipo == 'erro' else 'note'}'>{r_html}{texto_html}</div>")


# Mostra a lista de erros de um ErroValidacao: cada linha com o campo em negrito e a mensagem.
def lista_erros(titulo: str, erros: list[tuple[str, str]]) -> None:
    itens = "".join(f"<li><b>{escape(c)}</b>: {escape(m)}</li>" for c, m in erros)
    nota(f"<b>{escape(titulo)}</b><ul>{itens}</ul>", "erro")


# Bloco de citação com destaque (usado na aba Metodologia).
def citacao(frase_html: str, atribuicao: str = "") -> None:
    a = f"<div class='a'>{escape(atribuicao)}</div>" if atribuicao else ""
    html(f"<div class='citacao'><div class='q'>{frase_html}</div>{a}</div>")
