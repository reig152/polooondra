import logging
from typing import List, Dict, Any, Union, Tuple
from datetime import datetime
from mysql.connector import connect, Error
from interface.settings import (
    OFHOST, OFDATABASE, OFPASS, OFUSER
)

from actualising_report.models import (
    ForPost, PrescriptionControl,
    NoPhotos, OnlyMulti
)
from actualising_report.sql_tempates.templates import SQLTemplates
from .add_to_db_class import AddToDb


logger = logging.getLogger(__name__)


class Reports:
    """Класс для отработки отчетов актуализации."""

    def __init__(
        self, task: str,
        model_class: Union[
            ForPost, PrescriptionControl,
            NoPhotos, OnlyMulti
        ],
        table_name: str, table_param: str,
        market: str = None
    ) -> None:
        self.task = task
        self.model_class = model_class
        self.table_name = table_name
        self.table_param = table_param
        self.offer_key = self.table_name.split('_')[0]
        self.offer_type = self.get_offer_params("offer_type")
        self.money_gt = self.get_offer_params("money_gt")
        self.market = market

    def get_offer_params(self, key) -> Union[str, int, None]:
        """Метод получающий параметры типа сделки."""
        # словарь для опеределения типа сделки и нижнего порога ставки
        # если задача по поиску активных блоков, то нижний порог аренды
        # равен 600 тыс.
        of_type: Dict[str, Dict[str, Union[str, int]]] = {
            "rent": {
                "offer_type": "Аренда",
                "money_gt": (
                    400000 if self.task
                    not in ["only_active"] else 600000
                ),
            },
            "sale": {
                "offer_type": "Продажа",
                "money_gt": 100000000,
            }
        }

        return of_type.get(self.offer_key).get(key)

    def add_to_db(self):
        """Метод добавления объектов в базу данных."""

        # получение данных
        data = self.get_data()

        # создание экзепляра класса добавления в БД
        for row in data:
            adder = AddToDb(
                model_class=self.model_class,
                update_field='block_id',
                update_offer_type='offer_type',
                **row
            )

            # Вызов метода в зависимости от переданных данных
            if self.market:
                adder.add_to_db(self.market)
            else:
                adder.add_to_db()

    def get_data(self) -> List[Dict[str, Any]]:
        """Метод получения обработанных данных."""

        # получение шаблона запроса к БД
        temp = SQLTemplates(
            self.table_name, self.table_param,
            self.money_gt, self.market
        )
        # определение метода с нужным шаблоном
        sql_method = getattr(temp, self.task + '_temp', None)
        if sql_method:
            sql_q = sql_method()
            # обработка данных
            return self.make_request(sql_q)
        # Обработка краевого случая
        else:
            logger.error(
                "Возникла ошибка при получении шаблона к базе данных!",
                exc_info=True
            )

    def make_request(self, sql_q) -> List[Dict[str, Any]]:
        """Метод выполняющий запрос к БД и обрабатывающий данные."""
        try:
            with connect(
                host=OFHOST,
                database=OFDATABASE,
                user=OFUSER,
                password=OFPASS,
            ) as connection:
                with connection.cursor(buffered=True) as cursor:
                    cursor.execute(sql_q)

                    rows: Tuple[Any] = cursor.fetchall()

                    # базовый шаблон возвращаемых данных
                    base_dicts = [{'block_id': row[0],
                                   'building_id': row[1],
                                   'address': row[2],
                                   'area_max': row[3],
                                   'rate': row[4],
                                   'price': (
                                       int(row[3] * row[4] / 12)
                                       if self.offer_key == "rent"
                                       else int(row[3] * row[4])
                                   ),
                                   'offer_type': self.offer_type}
                                  for row in rows]

                    # пополнение базового шаблона в зависимости
                    # от выполняемой задачи
                    if self.task == "prescription":
                        for i, base_dict in enumerate(base_dicts):
                            base_dict['resp_id'] = rows[i][5]
                            base_dict['resp_name'] = rows[i][6]
                            base_dict['owner_id'] = False \
                                if rows[i][7] == 35 else (
                                True if rows[i][7] is not None else False
                            )
                            base_dict['updated_at'] = rows[i][8]
                            time_difference = datetime.now() - rows[i][8]
                            base_dict['days_from_actualisation'] = (
                                time_difference.days
                            )
                            base_dict['outdated'] = time_difference.days < 30

                    if self.task in ["for_post", "for_post_not_active"]:
                        for base_dict in base_dicts:
                            base_dict['market'] = self.market

                    if self.task in ["no_photo", "only_multi"]:
                        for i, base_dict in enumerate(base_dicts):
                            floor = rows[i][5]
                            if floor.isdigit():
                                base_dict['floor'] = int(floor)
                            else:
                                base_dict['floor'] = 0
                            base_dict['block_type'] = rows[i][6]
                            if self.task == "no_photo":
                                base_dict['is_full_building'] = True \
                                    if rows[i][7] == 1 else False

                    if self.task == "only_active":
                        for i, base_dict in enumerate(base_dicts):
                            base_dict['is_available_block'] = rows[i][-3]
                            base_dict['is_export_building'] = rows[i][-2]
                            base_dict['is_export_block'] = rows[i][-1]

                    return base_dicts

        except Error as ex:
            logger.error(f"Возникла ошибка {ex} запросе к БД!")
