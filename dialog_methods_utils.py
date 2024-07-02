from typing import Dict, Any
from tgbot.windows.cian_api_methods import CIAN_API_METHODS
from tgbot.windows.avito_api_methods import AVITO_API_METHODS


# ключ cian/avito, значение: соответствующий экземляр
api_attrs_dict: Dict[str, Dict[str, Any]] = {
    "cian": {
        "class": CIAN_API_METHODS,
    },
    "avito": {
        "class": AVITO_API_METHODS,
    }
}


async def get_method_result(market: str, method_name: str, *args) -> Any:
    """Метод вызывает методы из классов по параметрам."""
    # получаем экземляр класса
    model_instance = api_attrs_dict.get(market)["class"]

    # получаем данные посредством вызова метода
    acquired_data = await getattr(
        model_instance, method_name
    )(*args)

    return acquired_data
