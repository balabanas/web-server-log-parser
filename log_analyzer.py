#!/usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import configparser
import gzip
import logging
import os
import re
import string
import sys
from collections import namedtuple, defaultdict, OrderedDict
from datetime import datetime
from statistics import mean, median
from string import Template
from typing import Union, Generator

config: dict = {
    "REPORT_SIZE": 1000,
    "REPORT_DIR": "./reports",
    "LOG_DIR": "./log",

    "ACCEPTABLE_PARSED_SHARE": 0.333,
}


def get_config(args: argparse.Namespace, current_config: dict) -> dict:
    """
    Takes CLI args. If --config option provided there, tries to read config file, parse parameters from it,
    and alters the default `current_config` dict. Raises exceptions if file contains unreadable parameters or not
    exists.
    :param args: CLI args dict
    :param current_config: current config dict
    :return: updated config dict
    """
    current_config: dict = current_config.copy()  # avoiding updating global config
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
    in the `path` dir. If nothing found returns None
    :param path: relative path to the target dir
    :param pattern: target regexp pattern. Must include `date` named group to discover yyyymmdd date format
    :return: named tuple with str `file_path` (name of the file found) and extracted `date` as datetime.date.
    """
    file_name_pattern: re.Pattern = re.compile(pattern, re.IGNORECASE)
    files: list = os.listdir(path)
    latest_file: str = ''
    latest_date: datetime.date = datetime(1970, 1, 1).date()
    for file in files:
        match: Union[re.Match, None] = file_name_pattern.search(file)
        if match:
            date: Union[str, datetime.date] = match.group('date')
            date = datetime.strptime(date, '%Y%m%d').date()
            if date > latest_date:
                latest_file = file
                latest_date = date
    LogFile = namedtuple('LogFile', ['file_path', 'date'])
    return LogFile(file_path=os.path.join(path, latest_file), date=latest_date) if latest_file else None


def get_url_time_from_record(file_name: str, pattern: str) -> Generator[tuple, None, None]:
    """
    Generates next parsed line from `file_name` (log file), yielding requested url and request processing time.
    If pattern didn't match, url = '-', time = 0.0.
    :param file_name: Full path to a file
    :param pattern: Regexp patter, required to include `url` and `time` named groups
    :return: url:str, time:float
    """
    file_opener = gzip.open if file_name.endswith('.gz') else open
    url_pattern: re.Pattern = re.compile(pattern, re.IGNORECASE)
    with file_opener(file_name, 'rt') as f:
        record_count: int = sum(1 for _ in f)
        f.seek(0)
        record_processed: int = 0
        for i, line in enumerate(f):
            url: str = '-'
            time: float = 0.0
            match = url_pattern.search(line)
            if match:
                url: str = match.group('url')
                time: float = float(match.group('time'))
                record_processed += 1
            if i % 100000 == 0:
                progress: float = (i + 1) / record_count * 100
                print(f'Progress: {progress:.0f}%', end='\r')
            yield url, time


def get_validated_path(path_chunks: list, path_descr: str = None) -> str:
    """
    Join path chuncks into normalized path, checks path (directory or file) existence and returns path str.
    If not exists raises IOError exception
    :param path_chunks: list of path components. Some components might include slashes
    :param path_descr: str to write to log if path not exists
    :return path str with valid normalized path
    """
    path: str = os.path.join(*path_chunks)
    path = os.path.normpath(path)  # avoiding mix slashes
    if not os.path.exists(path):
        logging.error(f'The path {path} is not found ({path_descr}). Exiting...')
        raise IOError
    return path


def main():
    # Check if --config provided, updating config
    parser: argparse.ArgumentParser = argparse.ArgumentParser()
    parser.add_argument('--config', default='', const='./config.ini', nargs='?', help='Path to a config file')
    args: argparse.Namespace = parser.parse_args()
    working_config: dict = get_config(args, config)

    # Setting up logging
    log_format: str = '%(asctime)s %(levelname).1s %(message)s'
    logging.basicConfig(format=log_format, filename=working_config['SCRIPT_LOG'],
                        level=getattr(logging, working_config['SCRIPT_LOG_LEVEL'], 'INFO'),
                        datefmt='%Y.%m.%d %H:%M:%S')
    if working_config['SCRIPT_LOG']:
        print(f"Writing log to {working_config['SCRIPT_LOG']}")
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            logging.exception("Interrupted by user", exc_info=(exc_type, exc_value, exc_traceback))
        logging.exception("Unknown exception, check trace", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

    logging.info('Log analyzer started')
    logging.debug(f'Default configuration: {config}')
    logging.debug(f'Current configuration: {working_config}')

    logging.debug('Checking paths and files to work with')
    report_template_file: str = get_validated_path(['./templates', 'report.html'], "Report template")
    log_dir: str = get_validated_path([working_config['LOG_DIR'], ], 'Log directory')
    report_dir: str = get_validated_path([working_config['REPORT_DIR'], ], 'Report directory')

    logging.debug('Finding the latest log to parse')
    log_file_pattern: str = r"^nginx-access-ui\.log-(?P<date>\d{8})($|\.gz$)"
    log_file: namedtuple = get_latest_log(log_dir, log_file_pattern)
    if not log_file:
        logging.info('Log file is not found! Nothing to do. Exiting...')
        sys.exit(0)
    logging.info(f'Found log file to process: {log_file.file_path}')

    logging.debug('Setting up future report file. If already exists - exit')
    report_file: str = os.path.join(report_dir, f"report-{log_file.date.strftime('%Y.%m.%d')}.html")
    if os.path.exists(report_file):
        logging.info(f'The report for the latest date already exists: {report_file}. Exiting...')
        sys.exit(0)

    logging.debug('Set up pattern to parse log records')
    # Note `url` and `time` named groups
    url_pattern: str = r'"GET (?P<url>.+?(?=\ http\/1.1")) http\/1.1"\s+.*?(?P<time>\d+\.\d{3})$'
    url_times: defaultdict = defaultdict(list)

    logging.debug('Go parsing')
    for url, time in get_url_time_from_record(log_file.file_path, url_pattern):
        url_times[url].append(time)
    logging.debug('Finished parsing')

    logging.debug('Finding the proportion of the successfully parsed records. Exit if proportion is too small')
    records_processed: int = sum(map(len, url_times.values()))
    if '-' in url_times:
        del url_times['-']
    records_parsed: int = sum(map(len, url_times.values()))
    records_parsed_share: float = round(records_parsed / records_processed, 3)
    logging.debug(f"The share of records parsed: {records_parsed_share}, "
                  f"threshold: {working_config['ACCEPTABLE_PARSED_SHARE']}")
    if records_parsed_share < working_config['ACCEPTABLE_PARSED_SHARE']:
        logging.error(
            f"Less then {working_config['ACCEPTABLE_PARSED_SHARE']} of log records where successfully parsed. "
            f"({records_parsed_share}). Check if log format corresponds script expectations. Exiting...")
        sys.exit(0)

    logging.debug(f"Crop top {working_config['REPORT_SIZE']} of urls with slowest total time")
    # Use OrderedDict, so to preserve initial records' sort order in the report
    top_url_times: OrderedDict = OrderedDict(sorted(url_times.items(),
                                                    key=lambda x: -sum(x[1]))[:working_config['REPORT_SIZE']])

    times_sum: float = sum(map(sum, top_url_times.values()))
    logging.debug(f"Total processing time of `slowest` {working_config['REPORT_SIZE']} urls: {times_sum}")
    times_count: int = sum(map(len, top_url_times.values()))
    logging.debug(f"Total N of requests for `slowest` {working_config['REPORT_SIZE']} urls: {times_count}")

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
    first_row: dict = next(iter(table))
    logging.debug(
        f"First row statistics: {first_row['url']}, count {first_row['count']}, count_perc {first_row['count_perc']}"
        f", time_avg {first_row['time_avg']}, time_max {first_row['time_max']}, time_med {first_row['time_med']}"
        f", time_perc {first_row['time_perc']}, time_sum {first_row['time_sum']}")
    logging.debug('Rendering report template')
    with open(report_template_file, 'rt') as f:
        template: string.Template = Template(f.read())
    logging.debug('Writing the report')
    with open(report_file, 'w') as f:
        f.write(template.safe_substitute({'table_json': table}))

    logging.info("Log analyzer finished")
    logging.shutdown()


if __name__ == "__main__":
    main()
