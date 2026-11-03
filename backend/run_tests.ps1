$env:DATABASE_URL = "sqlite:///$env:TEMP/test_syslog.db"
$env:SYSLOG_LISTENERS_ENABLED = "false"
$env:REDIS_URL = "redis://127.0.0.1:6399/0"
$env:LOG_LEVEL = "WARNING"

& .venv\Scripts\python.exe -m pytest tests/ -x -v --timeout=30 -p no:cacheprovider 2>&1