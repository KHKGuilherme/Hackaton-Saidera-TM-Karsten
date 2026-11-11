# Modelagem de Dados
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

# Erro Validação
# Responsável por retornar todos os erros apontados.
class ErroValidacao(Exception):

    # Guarda a lista de (campo, mensagem) para a tela mostrar cada erro ao lado do campo certo.
    def __init__(self, erros: list[tuple[str, str]]):
        self.erros = erros
        # Também monta um texto único, usado quando o erro aparece no terminal (CLI) ou num log.
        super().__init__("; ".join(f"{c}: {m}" for c, m in erros))


# Um elemento da Matriz MTM (código, descrição e tempo padrão em minutos).
# Por se tratar de um Dado Referência, o mesmo é imutável
@dataclass(frozen=True)
class ElementoMTM:
    codigo: str
    descricao: str
    tempo: Decimal


# Uma máquina cadastrada. tempo_por_metro é o fator que gera o FIXO; rpm serve para os limites ±10%.
# Por se tratar de um Dado Referência, o mesmo é imutável
@dataclass(frozen=True)
class Maquina:
    codigo: str
    tipo: str
    descricao: str
    rpm: Decimal
    tempo_por_metro: Decimal


# Todos os dados de apoio juntos: elementos e máquinas indexados pelo código, para busca direta.
@dataclass(frozen=True)
class Cadastros:
    elementos: dict[str, ElementoMTM]
    maquinas: dict[str, Maquina]
    origem: str = "desconhecida"
    avisos: tuple[str, ...] = ()


# Qual elemento MTM e quantas vezes ele se repete ? O Padrão definido será 1.
@dataclass(frozen=True)
class ItemRoteiro:
    codigo: str
    frequencia: Decimal = Decimal(1)


# O pedido de ficha já validado. Mutável porque é montado aos poucos e recebe avisos no caminho.
@dataclass
class Demanda:

    perimetro_m: Decimal
    cod_maquina: str
    roteiro: list[ItemRoteiro]
    titulo: str = "PO-SEM-TITULO"
    revisao: str = "00"
    operacao: str = ""
    familia: str = ""
    tamanho: str = ""
    medidas: str = ""
    # Opcional: não entra no FIXO, serve só para a checagem complementar da agulha.
    pontos_cm: Decimal | None = None
    # default_factory cria uma lista nova para cada demanda; com "= []" todas compartilhariam a mesma lista.
    avisos: list[str] = field(default_factory=list)


# Uma linha pronta da ficha. tempo é o unitário (como no gabarito); tempo_total já multiplica pela frequência.
# fixo=True marca a primeira linha (tempo de costura), tratada à parte na exibição.
@dataclass(frozen=True)
class LinhaPO:
    codigo: str
    descricao: str
    frequencia: Decimal
    tempo: Decimal
    tempo_total: Decimal
    fixo: bool = False


# A ficha calculada: o pedido, a máquina, os limites de RPM, as linhas e o TP.
@dataclass
class FichaPO:
    demanda: Demanda
    maquina: Maquina
    rpm_limite_inferior: Decimal
    rpm_limite_superior: Decimal
    linhas: list[LinhaPO]
    tp: Decimal
    avisos: list[str] = field(default_factory=list)

    # O FIXO é sempre a primeira linha; a property evita guardar o mesmo valor em dois lugares.
    @property
    def fixo(self) -> Decimal:
        return self.linhas[0].tempo

    # Soma só os elementos manuais (tudo menos o FIXO). Decimal(0) como início para a soma não virar int.
    @property
    def tempo_manual(self) -> Decimal:
        return sum((l.tempo_total for l in self.linhas if not l.fixo), Decimal(0))
