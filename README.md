# Web server's log parser

TODO: description

` log_format ui_short '$remote_addr  $remote_user $http_x_real_ip [$time_local] "$request" '
                     '$status $body_bytes_sent "$http_referer" '
                     '"$http_user_agent" "$http_x_forwarded_for" "$http_X_REQUEST_ID" "$http_X_RB_USER" '
                     '$request_time';`

TODO: example runs (prod, tests)


## Configuration
By default, script uses the following hardcoded configuration:
* `REPORT_SIZE = 1000` - maximum number of urls with the largest sums of requests' processing times to be included into report
* `REPORT_DIR = ./reports` - directory to store reports
* `LOG_DIR = ./log` - directory to look for logs to parse
* `ACCEPTABLE_PARSED_SHARE = 0.333` - the acceptable minimum share of log records with known log pattern to create the report 

You can optionally provide an external config file, using command line `--config` option:

* `python log_analyzer.py --config` - the `config.ini` from the source is used
* `python log_analyzer.py --config myconfigs/myconfig.ini` - provided `myconfig.ini` is used

If provided, configuration file requires `[config]` section. Check `config.ini` for formatting guidelines. In addition to the hardcoded options, `SCRIPT_LOG` could be provided in configuration file to route script log messages to a file, ex.:

`[config]`

`SCRIPT_LOG = scriptlogs/log.txt`