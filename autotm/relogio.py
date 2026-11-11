# Relógio único do sistema, sempre no horário de Brasília.
# Motivo: o servidor (ex.: Streamlit Cloud) roda em UTC; sem isso as datas da ficha sairiam 3 horas adiantadas.
from datetime import datetime, timedelta, timezone

# Fuso fixo -03:00 (o Brasil não tem mais horário de verão), sem depender de biblioteca de fusos.
BRASILIA = timezone(timedelta(hours=-3), "BRT")


def agora() -> datetime:
    return datetime.now(BRASILIA)
