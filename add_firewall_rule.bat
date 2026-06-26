@echo off
netsh advfirewall firewall add rule name="Flask App" dir=in action=allow protocol=TCP localport=5000
echo Firewall rule added. Press any key to exit.
pause >nul