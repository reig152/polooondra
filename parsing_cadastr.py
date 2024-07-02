import asyncio
import aiohttp
import re
import json
from random import choice, uniform
from bs4 import BeautifulSoup
from cloudscraper import create_scraper

from aiogram.methods.send_message import SendMessage
from tgbot.config.config import bot

from interface.settings import (
    PROXY_LIST, PROXY_LOG, PROXY_PASS,
    DATA_T, DATA_S
)


class CadastreNumbers:
    url = "https://xn--80aaaaajm0cf1bvfgoh8r.xn--80asehdb/searchcad"
    floor_pattern = r'Этаж: <b>\n\t\t\t\t\t\t(\d+) </b>\n\t'
    square_pattern = r'Площадь: <b>\n\t\t\t\t\t\t(\d+(,\d+)?)кв.м'

    ip_list = PROXY_LIST

    log = PROXY_LOG
    password = PROXY_PASS

    token = DATA_T
    secret = DATA_S

    def __init__(
        self, address,
        square=None, floor=None,
        user_id=None
    ) -> None:
        self.address = address
        self.square = float(square) if square else None
        self.floor = float(floor) if floor else None
        self.user_id = user_id

    async def clean_address(self):
        """Метод, производящий стандартизацию адреса по dadata."""
        url = 'https://cleaner.dadata.ru/api/v1/clean/address'
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Token {self.token}',
            'X-Secret': self.secret
        }
        data = json.dumps([self.address])

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=data)\
                    as response:
                response_data = await response.json()
                return response_data[0].get('result', None)

    def get_proxy(self):
        """Метод, выбирающий случайный прокси."""
        random_element = choice(self.ip_list)
        proxy = {
            'http': f'http://{self.log}:{self.password}@{random_element}:8761',
            'https': f'http://{self.log}:{self.password}@{random_element}:8761'
        }
        return proxy

    def get_req_data(self, scraper):
        """Метод, получающий токен и кукисы."""
        response = scraper.get(self.url, proxies=self.get_proxy())
        cookies = response.cookies.get_dict()
        soup = BeautifulSoup(response.text, 'html.parser')
        meta_tag = soup.find('meta', {'name': 'csrf-token'})
        csrf_token = meta_tag['content']

        return csrf_token, cookies

    def get_data_numbers(self, session):
        """Метод, получающий информацию о всех номерах."""
        scraper = create_scraper(sess=session)
        csrf_token, cookies = self.get_req_data(scraper=scraper)

        data = {
            'address': self.address,
            '_token': csrf_token,
        }

        return scraper.post(
            self.url, cookies=cookies, data=data,
            proxies=self.get_proxy()
        ).json()

    async def find_all_numbers(self):
        """Метод выводит все номера объекта."""
        async with aiohttp.ClientSession() as session:
            html = await asyncio.to_thread(
                self.get_data_numbers, session=session
            )
            numbers = [x['Number'] for x in html]
            return numbers

    def parse_details(self, source, pattern):
        """Метод парсит площадь или этаж объекта."""
        match = re.search(pattern, source)
        res = None
        if match:
            res = match.group(1)
            res = float(res.replace(',', '.'))

        return res

    def parse_object_info(self, session, number):
        """Метод, выводящий информацию по номеру объекта."""
        scraper = create_scraper(sess=session)
        csrf_token, cookies = self.get_req_data(scraper=scraper)

        data = {
            'cadnum': str(number),
            '_token': csrf_token,
        }

        obj_info_url = (
            "https://xn--80aaaaajm0cf1bvfgoh8r.xn--80asehdb/searchcaddetails"
        )

        response = scraper.post(
            obj_info_url, cookies=cookies, data=data,
            proxies=self.get_proxy()
        ).json()

        source = response.get('html', None)
        square = None
        floor = None

        if source:
            square = self.parse_details(source, self.square_pattern)
            floor = self.parse_details(source, self.floor_pattern)

        return number, square, floor

    async def req_limit(self, number, semaphore, session):
        """Метод, задающий максимальное количество запросов."""
        async with semaphore:
            result = await asyncio.to_thread(
                self.parse_object_info, session=session, number=number
            )
            delay = uniform(5, 7)
            await asyncio.sleep(delay)
            return result

    async def process_numbers(self):
        """Метод, обрабатывающий полученные кадастровые номера."""
        # получение всех кадастровых номеров по адресу
        numbers = await self.find_all_numbers()
        print(len(numbers))

        # лимит в 10 запросов
        semaphore = asyncio.Semaphore(10)
        async with aiohttp.ClientSession() as session:
            tasks = [self.req_limit(
                number, semaphore, session
            ) for number in numbers]

            results = await asyncio.gather(*tasks)
            matches = []

            for number, square, floor in results:
                if isinstance(square, float):
                    # разница в 1%
                    if abs(self.square - square) <= self.square * 0.01:
                        if not self.floor:
                            if number not in matches:
                                matches.append(number)

                        if self.floor == floor:
                            if number not in matches:
                                matches.append(number)

            return matches

    async def send_result(self):
        """Метод, отправляющий результаты поиска номеров."""
        while True:
            # вызов функции process_numbers() в фоновом режиме
            print('Task started')
            result = await self.process_numbers()
            print(f'{result}')
            text = None

            if result:

                result_string = '\n'.join(result)

                text = (
                    'Результат поиска:\n'
                    f'<b>{result_string}</b>\n'
                    '<i>Нажмите на /start для перехода в меню</i>'
                )

            else:
                text = (
                    'Кадастровый номер по заданным параметрам <b>не найден</b>'
                    '<i>Нажмите на /start для перехода в меню</i>'
                )

            await bot(SendMessage(
                chat_id=self.user_id, text=text,
                parse_mode="HTML",
                disable_web_page_preview=True
            ))

            break
