#!/usr/bin/env python
# -*- coding: utf-8 -*-


# log_format ui_short '$remote_addr  $remote_user $http_x_real_ip [$time_local] "$request" '
#                     '$status $body_bytes_sent "$http_referer" '
#                     '"$http_user_agent" "$http_x_forwarded_for" "$http_X_REQUEST_ID" "$http_X_RB_USER" '
#                     '$request_time';
import argparse
import configparser
import gzip
import logging
import os
import re
import sys
from collections import namedtuple, defaultdict, OrderedDict
from datetime import datetime
from statistics import mean, median
from string import Template
from typing import Union

config: dict = {
    "REPORT_SIZE": 1000,
    "REPORT_DIR": "./reports",
    "LOG_DIR": "./log",

    "ACCEPTABLE_PARSED_SHARE": 0.333,
}


def get_config(args, current_config: dict) -> None or dict:
    current_config = current_config.copy()  # avoiding updating global config
    current_config['SCRIPT_LOG'] = current_config.get('SCRIPT_LOG', None)
    current_config['SCRIPT_LOG_LEVEL'] = current_config.get('SCRIPT_LOG_LEVEL', 'INFO')
    if args.config:  # -- config argument is provided in CLI
        try:
            print(f'Reading config from {args.config}')
            config_from_file = configparser.ConfigParser()
            config_from_file.optionxform = str  # keep keys uppercase
            config_from_file.read(args.config)
            if config_from_file.sections():
                config_from_file = dict(config_from_file.items('config'))
                current_config.update(config_from_file)
            else:
                print(f'Unable to read from {args.config}. Exiting...')
                raise Exception

            # convert from str if provided in config file
            current_config['REPORT_SIZE'] = int(current_config['REPORT_SIZE'])
            current_config['ACCEPTABLE_PARSED_SHARE'] = float(current_config['ACCEPTABLE_PARSED_SHARE'])
        except configparser.MissingSectionHeaderError:
            print(f'Config file {args.config} seems to be incorrectly formatted.')
            raise
        except ValueError:  # possibly problem with type conversion from str
            print(
                f'Unable to parse parameters from config {args.config}. Check file against default config.ini.')
            raise
    return current_config


def get_latest_log(path: str, pattern: str) -> Union[namedtuple, None]:
    """
    Get plain text or .gz log file with the latest date in it's name,
    in the `path` dir.
    :param path: relative path to the target dir
    :param pattern: target regexp pattern. Must include `date` named group to discover yyyymmdd date format
    :return: named tuple with str `filename` (name of the file found) and extracted `date` as datetime.date.
    If nothing found `filename` is empty
    """
    file_name_pattern = re.compile(pattern, re.IGNORECASE)
    files = os.listdir(path)
    latest_file = ''
    latest_date = datetime(1970, 1, 1).date()
    for file in files:
        match = file_name_pattern.search(file)
        if match:
            date = match.group('date')
            date = datetime.strptime(date, '%Y%m%d').date()
            if date > latest_date:
                latest_file = file
                latest_date = date
    LogFile = namedtuple('LogFile', ['file_path', 'date'])
    return LogFile(file_path=os.path.join(path, latest_file), date=latest_date) if latest_file else None


def get_url_time_from_record(file_name: str, pattern: str):
    """
    Generates next parsed line from `file_name` (log file), yielding requested url and request processing time.
    If pattern didn't match, url = '-', time = 0.0.
    :param file_name: Full path to a file
    :param pattern: Regexp patter, required to include `url` and `time` named groups
    :return: url:str, time:float
    """
    file_opener = gzip.open if file_name.endswith('.gz') else open
    url_pattern = re.compile(pattern, re.IGNORECASE)
    with file_opener(file_name, 'rt') as f:
        record_count = sum(1 for _ in f)
        f.seek(0)
        record_processed: int = 0
        for i, line in enumerate(f):
            url: str = '-'
            time: float = 0.0
            match = url_pattern.search(line)
            if match:
                url = match.group('url')
                time = float(match.group('time'))
                record_processed += 1
            if i % 100000 == 0:
                progress = (i + 1) / record_count * 100
                print(f'Progress: {progress:.0f}%', end='\r')
            yield url, time


def get_validated_path(path_chunks: list, path_descr: str = None) -> str:
    path = os.path.join(*path_chunks)
    path = os.path.normpath(path)  # avoiding mix slashes
    if not os.path.exists(path):
        logging.error(f'The path {path} is not found ({path_descr}). Exiting...')
        raise IOError
    return path


def main():
    # Check if --config provided, updating config
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='', const='./config.ini', nargs='?', help='Path to a config file')
    args = parser.parse_args()
    conf = get_config(args, config)

    # Setting up logging
    log_format = '%(asctime)s %(levelname).1s %(message)s'
    logging.basicConfig(format=log_format, filename=conf['SCRIPT_LOG'],
                        level=getattr(logging, conf['SCRIPT_LOG_LEVEL'], 'INFO'),
                        datefmt='%Y.%m.%d %H:%M:%S')

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            logging.exception("Interrupted by user", exc_info=(exc_type, exc_value, exc_traceback))
        logging.exception("Unknown exception, check trace", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

    logging.info('Log analyzer started')
    logging.debug(f'Default configuration: {config}')
    logging.debug(f'Current configuration: {conf}')

    logging.debug('Checking paths and files to work with')
    report_template_file = get_validated_path(['./templates', 'report.html'], "Report template")
    log_dir = get_validated_path([conf['LOG_DIR'], ], 'Log directory')
    report_dir = get_validated_path([conf['REPORT_DIR'], ], 'Report directory')

    logging.debug('Finding the latest log to parse')
    log_file_pattern = r"^nginx-access-ui\.log-(?P<date>\d{8})($|\.gz$)"
    log_file: namedtuple = get_latest_log(log_dir, log_file_pattern)
    if not log_file:
        logging.info('Log file is not found! Nothing to do. Exiting...')
        sys.exit(0)
    logging.info(f'Found log file to process: {log_file.file_path}')

    logging.debug('Setting up future report file. If already exists - exit')
    report_file = os.path.join(report_dir, f"report-{log_file.date.strftime('%Y.%m.%d')}.html")
    if os.path.exists(report_file):
        logging.info(f'The report for the latest date already exists: {report_file}. Exiting...')
        sys.exit(0)

    logging.debug('Set up pattern to parse log records')
    # Note `url` and `time` named groups
    url_pattern = r'"GET (?P<url>.+?(?=\ http\/1.1")) http\/1.1"\s+.*?(?P<time>\d+\.\d{3})$'
    url_times = defaultdict(list)

    logging.debug('Go parsing')
    for url, time in get_url_time_from_record(log_file.file_path, url_pattern):
        url_times[url].append(time)
    logging.debug('Finished parsing')

    logging.debug('Finding the proportion of the successfully parsed records. Exit if proportion is too small')
    records_processed = sum(map(len, url_times.values()))
    if '-' in url_times:
        del url_times['-']
    records_parsed = sum(map(len, url_times.values()))
    records_parsed_share = round(records_parsed / records_processed, 3)
    logging.debug(f"The share of records parsed: {records_parsed_share}, threshold: {conf['ACCEPTABLE_PARSED_SHARE']}")
    if records_parsed_share < conf['ACCEPTABLE_PARSED_SHARE']:
        logging.error(
            f"Less then {conf['ACCEPTABLE_PARSED_SHARE']} of log records where successfully parsed. ({records_parsed_share}). "
            f"Check if log format corresponds script expectations. Exiting...")
        sys.exit(0)

    logging.debug(f"Crop top {conf['REPORT_SIZE']} of urls with slowest total time")
    # Use OrderedDict, so to preserve initial records' sort order in the report
    top_url_times = OrderedDict(sorted(url_times.items(), key=lambda x: -sum(x[1]))[:conf['REPORT_SIZE']])

    times_sum = sum(map(sum, top_url_times.values()))
    logging.debug(f"Total processing time of `slowest` {conf['REPORT_SIZE']} urls: {times_sum}")
    times_count = sum(map(len, top_url_times.values()))
    logging.debug(f"Total N of requests for `slowest` {conf['REPORT_SIZE']} urls: {times_count}")

    logging.debug(f'Populating the resulting JSON with url statistics')
    table: list = []
    for k, v in top_url_times.items():
        table.append({'url': k,
                      'count': len(v),
                      'time_avg': round(mean(v), 3),
                      'time_max': max(v),
                      'time_sum': round(sum(v), 3),
                      'time_med': round(median(v), 3),
                      'time_perc': round(sum(v) / times_sum, 3),
                      'count_perc': round(len(v) / times_count, 3),
                      })

    # Statistics in the first row:
    first_row = next(iter(table))
    logging.debug(
        f"First row statistics: {first_row['url']}, count {first_row['count']}, count_perc {first_row['count_perc']}, time_avg {first_row['time_avg']}, time_max {first_row['time_max']}, time_med {first_row['time_med']}, time_perc {first_row['time_perc']}, time_sum {first_row['time_sum']}")
    logging.debug('Rendering report template')
    with open(report_template_file, 'rt') as f:
        template = Template(f.read())
    logging.debug('Writing the report')
    with open(report_file, 'w') as f:
        f.write(template.safe_substitute({'table_json': table}))

    logging.info("Log analyzer finished")
    logging.shutdown()


if __name__ == "__main__":
    main()
