import argparse
import configparser
import os
import unittest
from datetime import datetime
from unittest.mock import patch

import log_analyzer
from log_analyzer import get_latest_log, get_validated_path, get_config

TESTS_DIR = os.path.join('tests')


class GetLatestLogTest(unittest.TestCase):
    log_file_pattern = r"^nginx-access-ui\.log-(?P<date>\d{8})($|\.gz$)"

    def test_get_latest_gz_w_date(self):
        log_dir_mock = os.path.join(TESTS_DIR, 'get_latest_gz_log_20170630')
        log_file_latest = os.path.join(log_dir_mock, 'nginx-access-ui.log-20170630.gz')
        log_file = get_latest_log(log_dir_mock, self.log_file_pattern)
        self.assertEqual(log_file_latest, log_file.file_path)
        self.assertEqual(datetime(2017, 6, 30).date(), log_file.date)

    def test_get_latest_plain_w_date(self):
        log_dir_mock = os.path.join(TESTS_DIR, 'get_latest_plain_log_20170630')
        log_file_latest = os.path.join(log_dir_mock, 'nginx-access-ui.log-20170630')
        log_file = get_latest_log(log_dir_mock, self.log_file_pattern)
        self.assertEqual(log_file_latest, log_file.file_path)
        self.assertEqual(datetime(2017, 6, 30).date(), log_file.date)


class GetValidatedPathTest(unittest.TestCase):
    invalid_path = ['abrakadabra', 'foo']
    invalid_path_descr = 'Abrakadabra path'
    valid_path = ['/']
    valid_path_descr = 'Valid path'

    def test_get_validated_path(self):
        path = get_validated_path(self.valid_path, self.valid_path_descr)
        self.assertEqual(os.path.normpath('/'), path)

    def test_raise_exception_invalid_path(self):
        with self.assertRaises(IOError):
            _ = get_validated_path(self.invalid_path, self.invalid_path_descr)


class GetConfigTest(unittest.TestCase):
    @patch('log_analyzer.sys.argv', ['log_analyzer.py', '--config'])
    def setUp(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('--config', default='', const='./config.ini', nargs='?', help='Path to a config file')
        self.args = parser.parse_args()

    def test_get_default_config(self):
        config = get_config(self.args, log_analyzer.config)
        self.assertEqual(1001, config['REPORT_SIZE'])

    def test_get_good_config(self):
        self.args.config = os.path.join(TESTS_DIR, 'get_config', 'good_config.ini')
        config = get_config(self.args, log_analyzer.config)
        self.assertEqual('./test_log.txt', config['SCRIPT_LOG'])
        self.assertEqual(1000, config['REPORT_SIZE'])  # report size remained untouched

    def test_get_nonexistent_config(self):
        self.args.config = os.path.join(TESTS_DIR, 'get_config', 'nonexistent_config.ini')
        with self.assertRaises(Exception):
            _ = get_config(self.args, log_analyzer.config)

    def test_get_corrupted_config(self):
        self.args.config = os.path.join(TESTS_DIR, 'get_config', 'corrupted_config.ini')
        with self.assertRaises(configparser.MissingSectionHeaderError):
            _ = get_config(self.args, log_analyzer.config)

    def test_get_not_int_config(self):
        self.args.config = os.path.join(TESTS_DIR, 'get_config', 'not_int_config.ini')
        with self.assertRaises(ValueError):
            _ = get_config(self.args, log_analyzer.config)


class GetURLTimeFromRecordTest(unittest.TestCase):
    log_file = os.path.join(TESTS_DIR, 'get_url_time_from_record', 'nginx-access-ui.log-20240301')
    url_pattern = r'"GET (?P<url>.+?(?=\ http\/1.1")) http\/1.1"\s+.*?(?P<time>\d+\.\d{3})$'
    iter_reader = log_analyzer.get_url_time_from_record(log_file, url_pattern)

    def test_parse(self):
        url, time = next(self.iter_reader)
        self.assertEqual('/api/v2/banner/16852664', url)
        self.assertEqual(0.199, time)

        # on the second line log record is corrupted, pattern unreadable
        url, time = next(self.iter_reader)
        self.assertEqual('-', url)
        self.assertEqual(0, time)


class MainTest(unittest.TestCase):
    def tearDown(self) -> None:
        if os.path.exists(os.path.join(TESTS_DIR, 'main', 'report-2023.02.28.html')):
            os.remove(os.path.join(TESTS_DIR, 'main', 'report-2023.02.28.html'))

    @patch('log_analyzer.sys.argv', ['log_analyzer.py', '--config',
                                     os.path.join(TESTS_DIR, 'main', 'good_config.ini')])
    def test_main(self) -> None:
        # the /url-with-largest-times in a sample file should be the first in the report
        # and give 14.333 for time average, 22 as time max, 11 for time med, counted 3, time sum 43, etc...
        # We take this info from the log
        with self.assertLogs(level='DEBUG') as captured:
            log_analyzer.main()
        self.assertTrue(os.path.exists(os.path.join(TESTS_DIR, 'main', 'report-2023.02.28.html')))
        self.assertIn(
            'DEBUG:root:First row statistics: /url-with-largest-times, count 3, count_perc 0.136, time_avg 14.333, '
            'time_max 22.0, time_med 11.0, time_perc 0.867, time_sum 43.0',
            captured.output)

    @patch('log_analyzer.sys.argv', ['log_analyzer.py', '--config',
                                     os.path.join(TESTS_DIR, 'main', 'empty_log_dir_config.ini')])
    def test_main_empty_log_dir(self):
        with self.assertRaises(SystemExit):
            log_analyzer.main()

    @patch('log_analyzer.sys.argv', ['log_analyzer.py', '--config',
                                     os.path.join(TESTS_DIR, 'main_unparseable_logs', 'unparseable_logs_config.ini')])
    def test_main_unparseable_logs(self):
        with self.assertRaises(SystemExit):
            log_analyzer.main()

    @patch('log_analyzer.sys.argv', ['log_analyzer.py', '--config',
                                     os.path.join(TESTS_DIR, 'main_report_exists', 'report_exists_config.ini')])
    def test_main_report_exists(self):
        with self.assertRaises(SystemExit):
            log_analyzer.main()


if __name__ == '__main__':
    unittest.main()
