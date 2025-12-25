# guess_person_bot

### Бот для игры "Кто я?" с Yandex LLM 

## Подготовка к запуску и запуск
### Требования:
* git
* python
### Склонируйте репозиторий
```bash
git clone https://github.com/Nitor112221/guess_person_bot
cd guess_person_bot
```
### Создайте, а после заполните файл .env
```bash
copy template.env .env
```
### Подготовка окружения python
```bash
python -m venv .venv
```
#### Linux
```bash
source .venv/bin/activate
```
#### Windows
```bash
.\.venv\Scripts\activate
```
```bash
pip install -r requirements/requirements_prod.txt
````
### Запуск
```bash
python bot.py
```