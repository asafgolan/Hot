# Hot

entry point for HOT https://he.wikipedia.org/wiki/HOT

our entry point is the website as the customer interface for sevral services but the main fucntionality which is the application.

explaratory testing user facing application web application

## prerequisites

```bash
conda create -y -n hot-e2e python=3.12
conda activate hot-e2e && pip install -r requirements.txt
```

## running tests localy

```bash
python -m pytest
```

## vscode settings

```json
{
    "python.testing.pytestArgs": [
        "."
    ],
    "python.testing.unittestEnabled": false,
    "python.testing.pytestEnabled": true,
    "python.defaultInterpreterPath": "/opt/homebrew/Caskroom/miniforge/base/envs/hot-e2e/bin/python",
    "python.testing.pytestPath": "/opt/homebrew/Caskroom/miniforge/base/envs/hot-e2e/bin/pytest"
}
```