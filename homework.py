import logging
import os
import sys
import time
import json
from http import HTTPStatus
from contextlib import suppress

import requests
import telegram
from dotenv import load_dotenv


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
        if not globals()[name]
    ]

    if missing_tokens:
        logger.critical(
            f'Отсутствуют'
            f'переменная окружения: {", ".join(missing_tokens)}')
        sys.exit('Не удалось обнаружить значения для указанных токенов.')


def send_message(bot, message: str) -> bool:
    """Отправка сообщения в Telegram чат."""
    logger.debug('Отправка сообщения')
    bot.send_message(TELEGRAM_CHAT_ID, text=message)
    logger.debug('Сообщение отправлено')


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
        raise ValueError(
            f'Отсутствует доступ к эндпоинту. '
            f'Код ответа: {response_status.status_code}'
        )

    try:
        response = response_status.json()
    except json.decoder.JSONDecodeError as error:
        raise ValueError(f'Ошибка формата JSON: {error}')
    return response


def check_response(response):
    """Проверка ответа API на соответсвие документации."""
    logger.debug('Начало проверки ответа от API')
    if not isinstance(response, dict):
        raise TypeError('Ожидается словарь в ответе "response"')
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError('Ожидается список домашних работ "homeworks"')


def parse_status(homework):
    """Извлекает статус о конкретной домашней работе."""
    logger.debug('Начало исполнение функции')
    homework_name = homework.get('homework_name')
    status = homework.get('status')
    verdict = HOMEWORK_VERDICTS.get(status)
    if homework_name is None:
        raise KeyError('Отсутствует название домашней работы')
    if status is None:
        raise KeyError('Отсутствует статус домашней работы')
    if verdict is None:
        raise ValueError('Неизвестный статус домашней работы')
    logger.debug('Завершение исполнения функции')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_sent_message = ''

    while True:
        try:
            response = get_api_answer(timestamp)
            check_response(response)
            homeworks = response.get('homeworks', [])
            if homeworks:
                message = parse_status(homeworks[0])
                if message != last_sent_message:
                    send_message(bot, message)
                    last_sent_message = message
                else:
                    logger.debug('Получено повторяющееся сообщение')
            else:
                logger.debug('Отсутствие обновлений статуса')
            timestamp = response.get('current_date', timestamp)
        except telegram.TelegramError as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message, exc_info=True)
            if message != last_sent_message:
                send_message(bot, message)
                last_sent_message = message
            with suppress(telegram.TelegramError):
                send_message(bot, message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
