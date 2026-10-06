"""La hora de la clínica.

El servidor corre en UTC. A las ocho de la noche en Santo Domingo ya es el día
siguiente en UTC: un pago registrado a esa hora con `date.today()` llevaría la
fecha de mañana. Todo lo que sea «hoy» o «a qué hora» para la clínica pasa por
aquí.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import settings

ZONA = ZoneInfo(settings.zona_horaria)


def hoy() -> date:
    """El día de hoy en la clínica."""
    return datetime.now(ZONA).date()


def local(momento: datetime) -> datetime:
    """Un instante, en la hora de la clínica."""
    return momento.astimezone(ZONA)
