import logging
import os
import sys
import requests
import json
import telegram
import time

from http import HTTPStatus
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

logging.basicConfig(
    level=logging.DEBUG,
    filemname='main.log',
    format='%(asctime)s, %(levelname)s, %(message)s',
    filemode='w'
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stderr)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
handler.setFormatter(formatter)


def check_tokens() -> None:
    """Проверка доступности переменных окружения."""
    logger.debug('Проверка переменных')
    return all((PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID))


def send_message(bot, message: str) -> bool:
    """Отправка сообщения в Telegram чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, text=message)
        logger.debug('Сообщение отправлено')
    except Exception as error:
        logger.error(f'Ошибка отправки сообщения: {error}')


def get_api_answer(timestamp):
    """Запрос к API."""
    try:
        response_status = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
    except requests.RequestException as error:
        logger.error(f'Ошибка при запросе к API: {error}')
        raise Exception('Ошибка при запросе')

    if response_status.status_code != HTTPStatus.OK:
        logger.error('Отсутствует доступ к эндпоинту')
        raise Exception('Отсутствует доступ к эндпоинту')

    try:
        response = response_status.json()
    except json.decoder.JSONDecodeError as error:
        logger.error(f'Ошибка формата JSON: {error}')
        raise Exception('Ошибка формата JSON')
    return response


def check_response(response):
    """Проверка ответа API на соответсвие документации."""
    if response is None:
        logger.error('Ошибка: Получен пустой ответ от API')
        raise Exception('Получен пустой ответ от API')
    if not isinstance(response, dict):
        logger.error('Ошибка: Полученный ответ не является словаря')
        raise TypeError('Ожидается словарь в ответе')
    if not isinstance(response.get('homeworks'), list):
        logger.error('Ошибка: Ответ не содежит списка домашних работ')
        raise TypeError('Ожидается список домашних работ')
    if not isinstance(response.get('current_date'), int):
        logger.error('Ошибка: Ответ не содежит UNIX-метки времени')
        raise TypeError('Ожидается UNIX-метки времени')


def parse_status(homework):
    """Извлекает статус о конкретной домашней работе."""
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
        raise KeyError('Отсутствует ключ в словаре HOMEWORK_VERDICTS')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logger.critical('Ошибка: Отсутствуют необходимые переменные окружения')
        return

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())

    while True:
        try:
            response = get_api_answer(timestamp)
            check_response(response)
            for homework in response.get('homeworks'):
                message = parse_status(homework)
                send_message(bot, message)

        except Exception as error:
            logger.error(f'Ошибка при запросе к API: {error}')
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)

        finally:
            if response.get('current_date') is not None:
                timestamp = response.get('current_date')
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
