# quickstart

* Pull docker image and run it in interactive mode:
  

```bash
docker run -it --rm -v tvdata:/home/developer vitalets/tizen-webos-sdk bash
```

* from inside the container run:

```bash
#validate dependencies
root@499ca5cc1ece:~sdb version
Smart Development Bridge version 4.2.16
root@499ca5cc1ece:~# 
root@499ca5cc1ece:~# ares-setup-device --version
Version: 1.11.0-j31-k
```

* connect to your tv

```bash
root@499ca5cc1ece:~# ares-setup-device
```

## entry point use case link
* [Login to LG TV](tv/LG/login.md)
