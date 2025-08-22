# TutorSlot Bot

Телеграм-бот для записи учеников на занятия и управления расписанием;
Реализован на **Python 3.11 + aiogram 3 + SQLAlchemy + APScheduler** с интеграцией Google Calendar.

## Запуск проекта

1. Клонируем репозиторий:
   ```bash
   git clone https://github.com/<your-repo>/tutorslot_bot_tg_project.git
   cd tutorslot_bot_tg_project
   ```

2. Создаём окружение и ставим зависимости:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. Настраиваем переменные окружения в файле `.env`:
   ```
   BOT_TOKEN=ваш_токен_бота
   TZ=Europe/Moscow
   ADMINS=123456789,987654321
   ```

4. Настраиваем интеграцию Google Calendar:
   - Скачайте `credentials.json` из Google Cloud Console;
   - Запустите один раз:
     ```bash
     python -m app.integrations.google_oauth_setup
     ```
   - В результате появится `token.json`.

5. Запускаем бота:
   ```bash
   python -m app.main
   ```

## Основные команды

### Для пользователей
- `/start` — начать запись (выбор даты и времени);
- `/my` — показать мои записи;
- `/courses` — информация и материалы по курсам.

### Для администраторов
- `/admin` — панель управления всеми записями:
  - Просмотр всех слотов;
  - Кнопки **Изменить** и **Отменить** для каждой записи.

### Временно отключено
- `/weekly`, `/weekly_list`, `/weekly_del` — функционал еженедельных записей (закомментирован).

## Права доступа
- **Пользователь**:
  - Может создавать и просматривать только свои записи;
  - Может отменять только свои записи.
- **Админ**:
  - Видит все записи;
  - Может изменять/удалять любые записи;
  - Может создавать записи от имени любого пользователя.

## Технологии
- **aiogram 3** — обработка команд и сообщений;
- **SQLAlchemy (async)** — работа с базой данных (SQLite);
- **APScheduler** — напоминания о занятиях;
- **Google Calendar API** — интеграция календаря.

## Структура проекта
```
app/
 ├── bot/handlers/      # обработчики команд
 ├── bot/keyboards/     # клавиатуры
 ├── integrations/      # интеграция с Google API
 ├── scheduler/         # задачи APScheduler
 ├── services/          # бизнес-логика
 ├── storage/           # база данных и модели
 ├── utils/             # утилиты
 └── main.py            # точка входа
```
