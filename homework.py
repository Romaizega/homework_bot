import logging
import os
import sys
import time
import json
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv
from contextlib import suppress


load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stderr)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
handler.setFormatter(formatter)
logger.addHandler(handler)


def check_tokens() -> None:
    """Проверка доступности переменных окружения."""
    logger.debug('Проверка переменных')

    token_names = ('PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID')
    missing_tokens = [
        name for name in token_names
        if globals()[name] in (None, '')
    ]

    if missing_tokens:
        logger.critical(
            'Отсутствуют'
            'переменная окружения: {", ".join(missing_tokens)}')
        sys.exit('Не удалось обнаружить значения для указанных токенов.')

    return True


def send_message(bot, message: str) -> bool:
    """Отправка сообщения в Telegram чат."""
    try:
        logger.debug('Отправка сообщения')
        bot.send_message(TELEGRAM_CHAT_ID, text=message)
        logger.debug('Сообщение отправлено')
        return True
    except telegram.TelegramError as error:
        logger.error(f'Ошибка отправки сообщения: {error}')
        return False


def get_api_answer(timestamp):
    """Запрос к API."""
    try:
        response_status = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
    except requests.RequestException as error:
        raise ConnectionError(f'Ошибка при запросе к API: {error}')

    if response_status.status_code != HTTPStatus.OK:
        raise ConnectionError(
            'Отсутствует доступ к эндпоинту. '
            'Код ответа: {response_status.status_code}')

    try:
        response = response_status.json()
    except json.decoder.JSONDecodeError as error:
        raise ValueError(f'Ошибка формата JSON: {error}')
    return response


def check_response(response):
    """Проверка ответа API на соответсвие документации."""
    logger.debug('Начало проверки ответа от API')
    if not isinstance(response, dict):
        logger.error('Ошибка: Полученный ответ не является словаря')
        raise TypeError(f'Ожидается словарь в ответе {type(response)}')
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        logger.error('Ошибка: Ответ не содежит списка домашних работ')
        raise TypeError(f'Ожидается список домашних работ {type(homeworks)}')


def parse_status(homework):
    """Извлекает статус о конкретной домашней работе."""
    logger.debug('Начало исполнение функции')
    homework_name = homework.get('homework_name')
    status = homework.get('status')
    verdict = HOMEWORK_VERDICTS.get(status)
    if homework_name is None:
        logger.error('Ошибка: Отсутствует название домашней работы')
        raise KeyError('Отсутствует название домашней работы')
    if status is None:
        logger.error('Ошибка: Отсутствует статус домашней работы')
        raise KeyError('Отсутствует статус домашней работы')
    if verdict is None:
        logger.error('Ошибка: Отсутствует ключ в словаре HOMEWORK_VERDICTS')
        raise ValueError('Отсутствует ключ в словаре HOMEWORK_VERDICTS')
    logger.debug('Завершение исполнения функции')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())

    while True:
        try:
            response = get_api_answer(timestamp)
            check_response(response)

            homeworks = response.get('homeworks', [])
            if homeworks:
                message = parse_status(homeworks[0])
                send_message(bot, message)
        except Exception as error:
            logger.error(f'Ошибка при запросе к API: {error}', exc_info=True)
            message = f'Сбой в работе программы: {error}'
            with suppress(Exception):
                send_message(bot, message)
        finally:
            timestamp = response.get('current_date', timestamp)
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
