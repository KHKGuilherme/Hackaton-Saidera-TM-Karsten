# Auto-T&M: ficha de Processo Operacional automática

Projeto do Hackathon Auto-T&M Karsten. O sistema lê os cadastros de apoio (Matriz MTM e máquinas), recebe a
demanda em vários formatos e gera a ficha PO no layout do gabarito oficial, com exportação para Excel, PDF e JSON.
Também confere fichas PO que já existem, célula por célula.

Em resumo:

- Cenário oficial: `demanda_000.txt` gera FIXO 0,6709, TP 0,9409 min e RPM 4500 / 5000 / 5500.
- Validação: um teste compara o Excel gerado com o `PO-SL-000.ods` célula por célula (valores, fórmulas,
  mesclagens e cores). A auditoria do gabarito confere 11 de 11 itens.
- Entradas: formulário, TXT do kit, JSON, CSV/Excel/ODS em lote, planilha `Campo | Valor`, texto livre e ficha PO
  existente.
- Saídas: tela, Excel no layout do gabarito, PDF, JSON e ZIP para lotes.
- Aparência: tema claro e escuro. Segue o sistema por padrão e pode ser trocado no menu ⋮.

---

## Instalação e execução

Requisito: **Python 3.11 ou superior**. O CI roda os testes em 3.11, 3.12 e 3.13.

```bash
# 1. Criar o ambiente e instalar as dependências
python -m venv .venv
# Windows:  .venv\Scripts\activate      Linux/macOS:  source .venv/bin/activate
pip install -r requirements.txt

# 2. Abrir a interface web (abre em http://localhost:8501)
streamlit run app.py

# 3. (opcional) Rodar os testes, incluindo o teste golden contra o gabarito
python -m pytest -v
```

### Demonstração em 1 minuto
1. Abra o app. Na aba **Nova ficha**, clique em **Carregar cenário oficial**.
2. A ficha PO aparece na hora. Baixe em **Excel**, **PDF** ou **JSON**.
3. Na aba **Auditoria**, clique em **Auditar o gabarito oficial**: 11 de 11 itens conferem.
   Depois envie `exemplos/07_PO-SL-001_feita_a_mao.xlsx`, uma ficha com dois erros digitados à mão: o sistema aponta as células E8 e B11, mostra o valor certo e oferece a ficha corrigida com Rev. 01.
4. Em **Texto livre**, clique em **Interpretar texto** para ver um pedido em linguagem natural virar uma PO.
5. Na aba **Lote**, envie `exemplos/03_lote_demandas.csv`: saem 4 POs e 1 erro explicado.

### Linha de comando (automação e integração)
```bash
python -m autotm kit_oficial/demanda_000.txt                 # imprime a PO e salva saidas/PO-SL-001_rev00.xlsx
python -m autotm exemplos/03_lote_demandas.csv --pdf --json  # lote
python -m autotm demanda.txt --cadastros minha_base.xlsx      # outra base de cadastros
python -m autotm --auditar kit_oficial/PO-SL-000.ods          # audita fichas existentes
```

---

## Regras de cálculo

| Item | Regra |
|---|---|
| **FIXO** (costura de máquina) | `Perímetro (m) × Tempo/metro da máquina`, arredondado a **4 casas** (meio para cima). Ex.: 6,96 × 0,0964 = 0,670944 → **0,6709** |
| **Elementos manuais** | Descrição e tempo consultados na Matriz MTM pelo código `agrupador.elemento` (ex.: `2.1`) |
| **Frequência** | Cada elemento pode se repetir (`4.1x2` ou `4.1(2)`). A coluna Tempos mostra o tempo unitário; o TP multiplica pela frequência |
| **TP** | `FIXO + Σ(tempo MTM × frequência)` |
| **RPM** | Limite inferior = RPM × 0,9 e superior = RPM × 1,1. As fórmulas são mantidas no Excel, como no gabarito |

Os cálculos usam `Decimal`, uma aritmética decimal exata. Com `float`, por exemplo,
`0.6709 + 0.15 + 0.12 = 0.9409000000000001`.

> **Linha TP.** O gabarito `PO-SL-000` não traz a linha de total, mas o regulamento (item 3.3) exige
> o *Tempo Total da Operação (TP)*. A ficha reproduz o gabarito integralmente e acrescenta a linha **TP** ao final,
> com a fórmula `=SUMPRODUCT(Frequência; Tempos)`. O valor calculado também fica gravado no arquivo,
> de modo que leitores sem motor de cálculo (pandas, ERP, Excel em Modo Protegido) enxergam o TP.

---

## Formatos de entrada

Todos os formatos passam pela **mesma validação**. Os nomes de campos são reconhecidos com tolerância
a acentos, maiúsculas e sinônimos (por exemplo *Cód. Eqp*, *máquina*, *equipamento*, *Elemento 1*).

| Formato | Exemplo | Observação |
|---|---|---|
| TXT oficial `Campo: valor` | [exemplos/01_demanda_oficial.txt](exemplos/01_demanda_oficial.txt) | Formato do kit. UTF-8, UTF-16 ou Windows-1252. Elementos numa linha ou em várias |
| JSON | [exemplos/02_demanda.json](exemplos/02_demanda.json) | Objeto, lista, `{"demandas": [...]}` ou objetos aninhados. Roteiro como texto ou lista |
| CSV (`;` ou `,`) | [exemplos/03_lote_demandas.csv](exemplos/03_lote_demandas.csv) | Uma demanda por linha. A linha 5 tem erro proposital |
| Excel / ODS | [exemplos/06_lote_demandas.xlsx](exemplos/06_lote_demandas.xlsx) | Horizontal (uma por linha, cabeçalho em qualquer das 15 primeiras linhas) ou vertical (`Campo \| Valor`) |
| Texto livre | [exemplos/04_texto_livre.txt](exemplos/04_texto_livre.txt) | E-mail ou WhatsApp. O resultado é revisado antes de gerar |
| Ficha PO existente | [kit_oficial/PO-SL-000.ods](kit_oficial/PO-SL-000.ods) | Gera uma nova revisão a partir de uma PO antiga |
| Ficha PO com erro (auditoria) | [exemplos/07_PO-SL-001_feita_a_mao.xlsx](exemplos/07_PO-SL-001_feita_a_mao.xlsx) | FIXO e uma descrição alterados à mão, para testar a aba *Auditoria* |
| Formulário | aba *Nova ficha* | Roteiro em tabela ordenável com seleção dos códigos MTM |

**Tolerâncias e conversões:**
- **Números:** vírgula ou ponto decimal (`6,96`), e milhar brasileiro no RPM (`5.000`).
- **Perímetro em outra unidade:** `696 cm` ou `6960 mm` é convertido para metros, com aviso.
- **Máquina:** código (`1`, `01`), texto (`Máquina 2`) ou nome (*Siruba*, *Jack C4*, *Reta*).
- **Roteiro:** `2.1, 1.1, 3.1`, `4.1x2,3.1`, `2,1; 1,1; 3,1` ou `2.1 -> 1.1 -> 3.1`.

**Alertas de plausibilidade:**
- perímetro maior que o dobro do contorno da peça;
- FIXO acima de 10 minutos, o que sugere erro de unidade.

Os **cadastros** vêm por padrão de `kit_oficial/Entradas.ods`. Na barra lateral é possível substituí-los
(.ods, .xlsx ou .json), editá-los na tela ou exportá-los em JSON. Os nomes de coluna do regulamento
(*Código da Máquina*, *Descrição/Modelo*, *RPM Padrão*, *Fator de Tempo por Metro*) são reconhecidos. Também há tratamento para:
- **Cabeçalho deslocado:** é localizado mesmo com linhas de título acima.
- **Códigos duplicados:** geram aviso.
- **Tempos negativos ou tempo/metro zero:** são rejeitados.

Os **erros** aparecem todos de uma vez e indicam o campo e o motivo. Por exemplo:
*"Elementos: posição 2: código MTM '7.7' não existe na Matriz de Elementos."*
Arquivos corrompidos, JSON inválido ou planilhas sem demandas resultam em mensagem clara, nunca em traceback.

---

## Auditoria de fichas existentes

A aba **Auditoria** (ou `python -m autotm --auditar`) lê fichas no layout PO, em .ods ou .xlsx, e as recalcula com
os cadastros em uso. Depois compara cada item:
- equipamento;
- RPM: padrão e limites;
- FIXO;
- descrição e tempo de cada elemento MTM;
- TP.

Cada divergência aparece com a **célula**, o valor da ficha, o valor recalculado e o motivo. É possível baixar a ficha
corrigida já com a revisão incrementada (Rev. 00 → 01).

Usos práticos:
- validar POs legadas feitas à mão;
- descobrir quais fichas ficaram desatualizadas depois que o tempo/metro de uma máquina ou um tempo MTM mudou.

---

## Indicadores extras (informativos, não alteram a PO)

- **Capacidade**: peças/hora = 60 / TP.
- **Comparação entre máquinas**: o mesmo roteiro é simulado em todas as máquinas cadastradas, com indicação da de menor TP.
  No cenário oficial, a Siruba reduz o TP em 9,5%.
- **Checagem por RPM e densidade de pontos**: total de pontos = perímetro × 100 × pontos/cm, e tempo de agulha = pontos / RPM.
  Mostra que parte do FIXO é agulha em movimento. É um indicador de leitura para a engenharia; o FIXO oficial
  segue a fórmula do regulamento.

---

## Arquitetura

```
auto-tm/
├── app.py                     # Interface web (Streamlit)
├── interface/                 # Estilos e componentes visuais da interface
├── autotm/
│   ├── domain/                # Núcleo puro, sem I/O
│   │   ├── models.py          #   Entidades: ElementoMTM, Maquina, Demanda, FichaPO...
│   │   ├── engine.py          #   Motor de cálculo T&M + validação + plausibilidade
│   │   └── analise.py         #   Indicadores: capacidade, comparação, checagem de agulha
│   ├── ingestion/             # Adaptadores de entrada
│   │   ├── arquivos.py        #   Ponto único: detecta o formato e trata erros de leitura
│   │   ├── cadastros.py       #   Matriz MTM + Máquinas (.ods/.xlsx/.json/tela)
│   │   ├── demandas.py        #   TXT, JSON, CSV/Excel/ODS -> rascunho -> Demanda
│   │   ├── ficha_po.py        #   Leitura de fichas PO existentes (layout do gabarito)
│   │   ├── texto_livre.py     #   Extração determinística de texto livre
│   │   └── normalizacao.py    #   Números BR, unidades, acentos, sinônimos de campos
│   ├── servicos/              # Casos de uso
│   │   ├── lote.py            #   Processamento em lote, um erro não derruba os demais
│   │   └── auditoria.py       #   Auditoria de fichas contra os cadastros
│   ├── export/                # Adaptadores de saída
│   │   ├── xlsx.py            #   Excel no layout do gabarito, com valores das fórmulas gravados
│   │   ├── pdf.py  html.py    #   PDF para impressão e HTML de tela
│   │   ├── json_export.py     #   JSON para integração (ERP/MES)
│   │   └── lote.py            #   ZIP com as fichas + resumo
│   ├── relogio.py             # Hora de Brasília (servidores em nuvem rodam em UTC)
│   └── __main__.py            # CLI
├── tests/                     # 92 testes (pytest): golden, motor, ingestão, casos de borda, auditoria, CLI
├── kit_oficial/               # Kit do evento: Entradas.ods, demanda_000.txt, PO-SL-000.ods
└── exemplos/                  # Arquivos de exemplo para cada formato
```

Fluxo: **qualquer entrada → rascunho → `montar_demanda` (validação) → `calcular_po` (motor) → exportadores**.
O domínio não depende de interface nem de arquivos. Por isso a mesma regra atende o app web, a CLI, a auditoria e
uma futura API.

---

## Publicação (Streamlit Community Cloud)

1. Suba o repositório no GitHub (público).
2. Em [share.streamlit.io](https://share.streamlit.io), crie um app com *Main file* `app.py`. [https://hackaton-saidera-tm-karsten.streamlit.app/]
   Em *Advanced settings*, escolha Python 3.12.
3. O `requirements.txt` já está pronto. O link gerado pode ser usado pela banca.

## Licença
Código de autoria de Guilherme Henrique Soeiro Fontes & Gabriel Abe Takeshi (regulamento, item 7.1).
