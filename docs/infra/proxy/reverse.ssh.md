 Create a simple HTTP server on Windows
powershell
python -m http.server 8000
Then set up SSH tunnel from Windows to Mac:

powershell
ssh -R 8000:localhost:8000 user@mac-ip-address
On Mac, check if you can access the server:

bash
curl http://localhost:8000

----------------------------------------------------------
on windows:

```powershell
.\mitmproxy.exe --mode regular --listen-host 0.0.0.0 --listen-port 8080 --ssl-insecure
```

on 2nd terminal:

```powershell
ssh -v -R 8081:localhost:8080 asafgolan@192.168.1.204 -N
```

On mac machine run:

```powershell
python mac_proxy_server.py --listen-port 8000 --tunnel-port 8081
```

