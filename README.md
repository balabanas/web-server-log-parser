# Web Server's Log Analyzer

Custom log analyzer that helps to extract URLs with the highest impact on the user experience with respect to time of request processing.

The analyzer takes the directory with web server's log files, finds the latest log, parse it against the pattern provided and calculates statistics per url (frequency of requests and time of processing). Then it takes the top URLs with respect to the total time of processing, finds percentages and output the report in HTML format.

If the report for a particular day already exists, log parsing is skipped.

## Expected Log File Format and Discovery
The code was created with NGINX log format in mind:
```
log_format ui_short '$remote_addr  $remote_user $http_x_real_ip [$time_local] "$request"
                     $status $body_bytes_sent "$http_referer"
                     "$http_user_agent" "$http_x_forwarded_for" "$http_X_REQUEST_ID"
                     "$http_X_RB_USER" '$request_time';
```
In case of minor log format change (say, the places for `request_time` or `request` are switched), you may alter regex pattern in the code (see `url_pattern` variable). Note `url` and `time` named groups there, they should persist.

Log files analyzed are expected to rotate on a daily basis.

Analyzer automatically discover the latest log file in the log directory (see parameters below) by the date in the file name. Filename pattern is expexted to be: `nginx-access-ui.log-YYYYMMDD` or `nginx-access-ui.log-YYYYMMDD.gz` (in case of zipped files). Files with different patterns are ignored.

## Report Fields*
* `url` - URL, extracted from the log
* `count` - request frequency for `url`
* `count_perc` - proportion `count` of total number of requests
* `time_avg` - mean `$request_time` for `url`
* `time_max` - max `$request_time` for `url`
* `time_med` - median `$request_time` for `url`
* `time_perc` - proportion `time_sum` of total `$request_time`
* `time_sum` - total `$request_time` for `url`

\* statistics computed based for top URLs by total `$request_time`. See `REPORT_SIZE` parameter below.

## Parameters and Config Files
By default, script uses the following hardcoded configuration:
* `REPORT_SIZE = 1000` - maximum number of urls with the largest sums of requests' processing times to be included into report
* `REPORT_DIR = ./reports` - directory to store reports
* `LOG_DIR = ./log` - directory to look for logs to parse
* `ACCEPTABLE_PARSED_SHARE = 0.333` - the acceptable minimum share of log records with known log pattern to create the report 

You can optionally provide an external config file, using command line `--config` option. If provided, configuration file requires `[config]` section. Check `config.ini` for formatting guidelines. In addition to the hardcoded parameters, you can specify:
* `SCRIPT_LOG` - path to a file, to route script log messages to 
* `SCRIPT_LOG_LEVEL` - to specify log level [`DEBUG`, `INFO`, `ERROR`]

## Run Log Parser from Command Line
* `python log_analyzer.py` - no config file, the hardcoded parameters are used. Script expects to find log for parsing in `./log` directory, and will put report generated into `./reports` directory. Script logs are streamed to stdout.
* `python log_analyzer.py --config` - config option is provided, but argument is empty. `config.ini` from the source is used
* `python log_analyzer.py --config myconfigs/myconfig.ini` - `myconfig.ini` is used

## Run Tests
* `python -m unittest discover -s tests`