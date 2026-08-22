import os
import re
import smtplib
import threading
from datetime import date
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

BASE_URL = 'https://www.franceinfo.fr/'
JT20H_PATH_PREFIX = 'replay-jt/france-2/20-heures/'
JT20H_PATH_PATTERN = r'jt-de-20h-du-(?P<day>\w+)-(?P<date>\d{2})-(?P<month>\w+)-(?P<year>\d{4})_\d{7}\.html'

MONTHS_FRANCAIS = ['janvier', 'fevrier', 'mars', 'avril', 'mai', 'juin', 'juillet', 'aout', 'septembre', 'octobre',
                   'novembre', 'decembre']

DAYS_FRANCAIS = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']

SMTP_HOST = os.getenv('SMTP_HOST')
SMTP_PORT = os.getenv('SMTP_PORT')
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')

DATA_PATH = 'data/last-notified.txt'


class RepeatTimer(threading.Timer):
    def run(self):
        while not self.finished.wait(self.interval):
            self.function(*self.args, **self.kwargs)


def get_sitemap_url(target_date: date):
    return BASE_URL + f'sitemap/{target_date.year}-{target_date.month:02d}-direct_tv.xml'


def get_video_urls(target_date: date) -> Optional[List[str]]:
    sitemap_url = get_sitemap_url(target_date)
    response = requests.get(sitemap_url, headers={'User-Agent': 'Mozilla/5.0'})

    if response.status_code != 200:
        print(f'Failed to fetch sitemap: {response.status_code}')
        return None

    soup = BeautifulSoup(response.text, 'xml')
    urls = [url.text for url in soup.find_all('loc')]
    return urls


def notify(url: str, date: date):
    if url == get_last_notified_url():
        print('No new replays found.')
        return

    msg = EmailMessage()
    msg['Subject'] = f'New JT20H available: {date}'
    msg['From'] = SMTP_USER
    msg['To'] = SMTP_USER
    msg.set_content(f'New JT20H available: {url}')

    if not SMTP_HOST or not SMTP_PORT or not SMTP_USER or not SMTP_PASSWORD:
        print('SMTP credentials not found in environment variables')
        return

    try:
        with smtplib.SMTP(SMTP_HOST, int(SMTP_PORT)) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)

        write_last_notified_url(url)
        print(f'New replay available: {url}')
    except Exception as e:
        print(f'Failed to send email: {e}')


def get_date_from_url(url: str) -> Optional[date]:
    match = re.search(JT20H_PATH_PATTERN, url)
    if match is None:
        return None

    month = MONTHS_FRANCAIS.index(match.group('month')) + 1
    return date(int(match.group('year')), month, int(match.group('date')))


def get_last_notified_url() -> Optional[str]:
    if not os.path.exists(DATA_PATH):
        return None
    with open(DATA_PATH, 'r') as file:
        return file.read().strip()


def write_last_notified_url(url):
    Path(DATA_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_PATH, 'w') as file:
        file.write(url)


def check():
    today = datetime.now(ZoneInfo('Europe/Paris'))
    print(f'[{today}] Checking for new JT20H replays...')
    urls = get_video_urls(today)

    if urls is None:
        print('Failed to fetch video URLs')
        return

    jt20h_urls = [url for url in urls if url.startswith(BASE_URL + JT20H_PATH_PREFIX)]
    url_date = get_date_from_url(jt20h_urls[0])

    if url_date is None:
        print('Failed to parse date from URL')
        return

    notify(jt20h_urls[0], url_date)


def main():
    check()
    timer = RepeatTimer(15 * 60, check)
    timer.daemon = True
    timer.start()

    try:
        while timer.is_alive():
            timer.join(timeout=1)
    except KeyboardInterrupt:
        print('Stopping...')
        timer.cancel()
        timer.join()
        print('Stopped.')


if __name__ == '__main__':
    main()
