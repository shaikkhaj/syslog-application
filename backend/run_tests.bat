@echo off
set DATABASE_URL=sqlite:///C:/temp/test_syslog.db
set SYSLOG_LISTENERS_ENABLED=false
set REDIS_URL=redis://127.0.0.1:6399/0
set LOG_LEVEL=WARNING
cd /d c:\Users\91991\Desktop\log-applica\backend
.venv\Scripts\python.exe -m pytest tests/test_api.py::test_health_endpoint -v -p no:cacheprovider 2>&1
pause