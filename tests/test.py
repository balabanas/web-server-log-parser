import argparse
import configparser
import os
import unittest
from datetime import datetime
from unittest.mock import patch

import log_analyzer
from log_analyzer import get_latest_log, get_validated_path, get_config

TMPDIR = os.path.join('tests', 'tmpdir')


class FindLatestLogTest(unittest.TestCase):
    tmpfiles = [
        'nginx-access-ui.log-20170630.gz',
        'nginx-access-ui.log-20170630.gz'
        'nginx-access-ui.log-20170630',
        'nginx-access-ui.log-20230630.bz2',  # latest w/wrong naming
        'nginx-access-ui.log-20220112.gz',  # latest w/target naming
        'nginx-access-ui.log-2017063gz',
        'nginx-access-.log-20170630.gz',
        'nginx-access-ui.log-20170630.гз',
        'nginx-access-ui.log-20170630',
        'nginx-access-ui.log-20170901',
    ]

    def setUp(self):
        os.mkdir(TMPDIR)
        for tmpfile in self.tmpfiles:
            with open(os.path.join(TMPDIR, tmpfile), 'w') as f:
                f.write('test')

    def tearDown(self):
        for tmpfile in os.listdir(TMPDIR):
            os.remove(os.path.join(TMPDIR, tmpfile))
        os.rmdir(TMPDIR)

    def test_return_latest_w_date(self):
        log_file_latest = os.path.join(TMPDIR, 'nginx-access-ui.log-20220112.gz')
        log_file_pattern = r"^nginx-access-ui\.log-(?P<date>\d{8})($|\.gz$)"
        log_file = get_latest_log(TMPDIR, log_file_pattern)
        self.assertEqual(log_file_latest, log_file.file_path)
        self.assertEqual(datetime(2022, 1, 12).date(), log_file.date)

        # new latest w/correct naming, plaintext
        filename = os.path.join(TMPDIR, 'nginx-access-ui.log-20220113')
        with open(filename, 'w') as f:
            f.write('test')
        log_file = get_latest_log(TMPDIR, log_file_pattern)
        self.assertEqual(filename, log_file.file_path)
        os.remove(filename)

        # new latest w/wrong naming
        filename = os.path.join(TMPDIR, 'access-ui.log-20220114')
        with open(filename, 'w') as f:
            f.write('test')
        log_file = get_latest_log(TMPDIR, log_file_pattern)
        self.assertEqual(log_file_latest, log_file.file_path)
        os.remove(filename)


class ValidatePathTest(unittest.TestCase):
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


class ReadConfigTest(unittest.TestCase):
    @patch('log_analyzer.sys.argv', ['log_analyzer.py', '--config'])
    def setUp(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('--config', default='', const='./config.ini', nargs='?', help='Path to a config file')
        self.args = parser.parse_args()

        os.mkdir(TMPDIR)
        with open(os.path.join(TMPDIR, 'temp_config.ini'), 'w') as f:
            f.write('[config]\nSCRIPT_LOG = ./test_log.txt')
        with open(os.path.join(TMPDIR, 'temp_corrupted_config.ini'), 'w') as f:
            f.write('Corrupted config')
        with open(os.path.join(TMPDIR, 'temp_not_int_config.ini'), 'w') as f:
            f.write('[config]\nREPORT_SIZE = not an integer value')

    def tearDown(self):
        for tmpfile in os.listdir(TMPDIR):
            os.remove(os.path.join(TMPDIR, tmpfile))
        os.rmdir(TMPDIR)

    def test_get_default_config(self):
        config = get_config(self.args, log_analyzer.config)
        self.assertEqual(1001, config['REPORT_SIZE'])

    def test_get_custom_config(self):
        self.args.config = os.path.join(TMPDIR, 'temp_config.ini')
        config = get_config(self.args, log_analyzer.config)
        self.assertEqual('./test_log.txt', config['SCRIPT_LOG'])
        self.assertEqual(1000, config['REPORT_SIZE'])  # report size remained untouched

    def test_get_nonexistent_config(self):
        self.args.config = os.path.join(TMPDIR, 'temp_nonexistent_config.ini')
        with self.assertRaises(Exception):
            _ = get_config(self.args, log_analyzer.config)

    def test_get_corrupted_config(self):
        self.args.config = os.path.join(TMPDIR, 'temp_corrupted_config.ini')
        with self.assertRaises(configparser.MissingSectionHeaderError):
            _ = get_config(self.args, log_analyzer.config)

    def test_get_not_int_config(self):
        self.args.config = os.path.join(TMPDIR, 'temp_not_int_config.ini')
        with self.assertRaises(ValueError):
            _ = get_config(self.args, log_analyzer.config)


class GeneratorURLTimeTest(unittest.TestCase):
    log_file = 'tests/nginx-access-ui.log-20240301'
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
        if os.path.exists('tests/main_test/report-2023.02.28.html'):
            os.remove('tests/main_test/report-2023.02.28.html')
        pass

    @patch('log_analyzer.sys.argv', ['log_analyzer.py', '--config', 'tests/main_test_config.ini'])
    def test_main(self) -> None:
        # the /url-with-largest-times in a sample file should be the first in the report
        # and give 14.333 for time average, 22 as time max, 11 for time med, counted 3, time sum 43, etc...
        # We take this info from the log
        with self.assertLogs(level='DEBUG') as captured:
            log_analyzer.main()
        self.assertTrue(os.path.exists('tests/main_test/report-2023.02.28.html'))
        self.assertIn(
            'DEBUG:root:First row statistics: /url-with-largest-times, count 3, count_perc 0.136, time_avg 14.333,'
            'time_max 22.0, time_med 11.0, time_perc 0.867, time_sum 43.0',
            captured.output)

    @patch('log_analyzer.sys.argv', ['log_analyzer.py', '--config', 'tests/main_test_empty_log_dir_config.ini'])
    def test_main_empty_log_dir(self):
        with self.assertRaises(SystemExit):
            log_analyzer.main()

    @patch('log_analyzer.sys.argv', ['log_analyzer.py', '--config', 'tests/main_test_unparsable_logs_config.ini'])
    def test_main_unparsable_logs(self):
        with self.assertRaises(SystemExit):
            log_analyzer.main()

    @patch('log_analyzer.sys.argv', ['log_analyzer.py', '--config', 'tests/main_report_exists_config.ini'])
    def test_main_report_exists(self):
        with self.assertRaises(SystemExit):
            log_analyzer.main()


if __name__ == '__main__':
    unittest.main()
