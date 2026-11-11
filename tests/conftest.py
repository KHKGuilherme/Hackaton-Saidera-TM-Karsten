# Configuração compartilhada pelo pytest: caminhos do projeto e a fixture com os cadastros oficiais.
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
# Coloca a raiz do projeto no caminho de importação para os testes acharem o pacote autotm.
sys.path.insert(0, str(RAIZ))

from autotm.ingestion import carregar_cadastros

KIT = RAIZ / "kit_oficial"
EXEMPLOS = RAIZ / "exemplos"


# scope="session": carrega os cadastros oficiais uma única vez para todos os testes (mais rápido).
@pytest.fixture(scope="session")
def cad():
    return carregar_cadastros()
