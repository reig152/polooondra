import aiohttp
import json
import logging
from typing import Final, List, Dict, Any
from asgiref.sync import sync_to_async
from tgbot.models import EndedChats
from interface.settings import (
    AVITO_KEY, AVITO_SECRET, AVITO_ID
)


logger = logging.getLogger(__name__)


class AvitoApi:
    """Класс с методами api Авито."""
    @staticmethod
    async def get_access_token():
        """Метод получает временный токен авторизации."""
        url = 'https://api.avito.ru/token'

        params = {
            'client_id': AVITO_KEY,
            'client_secret': AVITO_SECRET,
            'grant_type': 'client_credentials',
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, params=params) \
                    as response:
                data = await response.json()

        token = data.get('access_token')

        # возвращаем заголовки с полученным токеном
        return {
            'Authorization': f'Bearer {token}'
        }

    @staticmethod
    async def make_request(method, url, **kwargs):
        """Метод составляет get/post запрос к api."""
        async with aiohttp.ClientSession() as session:
            # словарь методов
            req_methods = {
                'get': session.get,
                'post': session.post
            }

            async with req_methods[method](
                    url,
                    headers=await AvitoApi.get_access_token(),
                    **kwargs
                ) \
                    as response:
                data = await response.json()
                code = response.status

            return data, code

    @staticmethod
    async def count_unread():
        """Метод высчитаывает количество непрочитанных сообщений."""
        chats: List[Dict[str, Any]] = \
            await AvitoApi.get_chats(unread=True)
        return len(chats.get('chats'))

    @staticmethod
    async def get_dialogs_list(unread=None):
        """Метод получает список прочитанных/непрочитанных диалогов."""
        # собираем id чатов и их тайтлы
        chats: List[Dict[str, Any]] = \
            await AvitoApi.get_chats(unread)

        # проверка на завершенные диалоги
        ended_chats_obj = await sync_to_async(list)(
            EndedChats.objects.all()
        )
        ended_chats = [chat.chat_id for chat in ended_chats_obj]

        # получаем тайтлы, исключая завершенные диалоги
        titles = [
            (
                title['id'],
                title['context']['value']['title']
            ) for title in chats.get('chats')
            if title['id'] not in ended_chats
        ]

        return titles

    @staticmethod
    async def get_all_messages(chat_id):
        """Метод получает все сообщения по chat_id."""
        url = (
            'https://api.avito.ru/messenger/v3/accounts/'
            f'{AVITO_ID}/chats/{chat_id}/messages/'
        )

        response = await AvitoApi.make_request(
            'get',
            url
        )

        # получаем сообщения
        messages_data = response[0].get('messages')

        # проверка на наличие данных
        if messages_data:
            messages = [
                (
                    "<b>OF RU:\n</b>"
                    f"<i>{message['content']['text']}</i>"
                    if message['author_id'] == int(AVITO_ID)
                    else f"Клиент:\n{message['content']['text']}"
                )
                for message in messages_data
            ][::-1]

            # составляем диалог для окна в телеге
            result_string = '\n\n'.join(messages)

            return result_string

        else:
            return False

    @staticmethod
    async def get_offer_link(chat_id):
        """Метод получает ссылку на объявление."""
        url = (
            'https://api.avito.ru/messenger/v2/accounts/'
            f'{AVITO_ID}/chats/{chat_id}'
        )

        response = await AvitoApi.make_request(
            'get',
            url
        )

        return response[0].get('context').get('value').get('url')

    @staticmethod
    async def send_api_message(chat_id, message):
        """Метод, отправляющий пользователю сообщение."""
        url = (
            'https://api.avito.ru/messenger/v1/accounts/'
            f'{AVITO_ID}/chats/{chat_id}/messages'
        )

        data = {
            "message": {
                "text": message
            },
            "type": "text"
        }

        # Преобразуем JSON-объект в строку
        data_json = json.dumps(data)

        response = await AvitoApi.make_request(
            'post',
            url,
            data=data_json
        )

        logger.info(
            f"Сообщение отправлено со статусом {response[-1]}!"
        )

    @staticmethod
    async def mark_as_read_dialog(chat_id):
        """Метод, завершающий диалог."""
        url = (
            'https://api.avito.ru/messenger/v1/accounts/'
            f'{AVITO_ID}/chats/{chat_id}/read'
        )

        response = await AvitoApi.make_request(
            'post',
            url
        )

        logger.info(
            f'Диалог {chat_id} был завершен '
            f'со статусом {response[-1]}!'
        )

        # добавляем диалог в завершенные, чтобы исключить из всех диалогов
        await EndedChats.objects.aget_or_create(
            chat_id=chat_id,
        )

    @staticmethod
    async def get_chats(unread=None) -> dict:
        """Метод получает список всех чатов."""
        url = f'https://api.avito.ru/messenger/v2/accounts/{AVITO_ID}/chats'

        # добавляем параметр если он передан
        params = {}
        if unread:
            params['unread_only'] = 'true'

        response = await AvitoApi.make_request(
            'get',
            url,
            params=params
        )

        return response[0]

    @staticmethod
    async def get_chat_title(chat_id):
        """Метод получает title чата."""
        url = (
            'https://api.avito.ru/messenger/v2/accounts/'
            f'{AVITO_ID}/chats/{chat_id}'
        )

        response = await AvitoApi.make_request(
            'get',
            url
        )

        return response[0].get('context').get('value').get('title')

    @staticmethod
    async def data_for_notification():
        """Данные для показа уведомления."""
        last_chat = await AvitoApi.get_chats()
        chatId = last_chat.get("chats")[0].get("id")
        offer_link = await AvitoApi.get_offer_link(chatId)
        messages = await AvitoApi.get_all_messages(chatId)

        return chatId, offer_link, messages


# инициализация экземпляра для вызова методов
AVITO_API_METHODS: Final[AvitoApi] = AvitoApi()
