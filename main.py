import os
import datetime
import locale

import telebot
from flask import Flask, request
from sqlalchemy import Column
from sqlalchemy.sql.sqltypes import Boolean
from telebot import TeleBot, types
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime
import pandas as pd
from io import BytesIO
import threading
import time
from telebot.apihelper import ApiTelegramException, session
from flask_migrate import Migrate
import locale
from babel.dates import format_datetime, format_date
from telebot.apihelper import ApiTelegramException


# === Завантаження змінних з .env.prod ===
load_dotenv()
API_TOKEN = os.getenv("API_TOKEN")


env = os.getenv("FLASK_ENV", "development")
if env == "production":
    db_user = os.getenv("POSTGRES_USER")
    db_password = os.getenv("POSTGRES_PASSWORD")
    db_host = os.getenv("POSTGRES_HOST")
    db_name = os.getenv("POSTGRES_DB")
    db_port = os.getenv("POSTGRES_DB_PORT", "5432")
    DATABASE_URL = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
else:
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///events.db")

print(f"[✅ База даних] Підключено до: {DATABASE_URL}")


PORT = int(os.getenv("PORT", 5000))
ADMIN_IDS = os.getenv("ADMIN_IDS", "").split(",")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "-1001234567890"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")


# === Ініціалізація ===
bot = TeleBot(API_TOKEN, threaded=False)
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)



# === Завантаження фото для ігротеки ===
CURRENT_IMAGE_PATH = "current_event_image.jpg"

# === Кнопки подій ===
UKR_DAY_ABBR = {
    0: "Пн",
    1: "Вт",
    2: "Ср",
    3: "Чт",
    4: "Пт",
    5: "Сб",
    6: "Нд",
}


# === Моделі ===
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.String(50), nullable=False)
    username = db.Column(db.String(100))

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    date = db.Column(db.DateTime)
    max_players = db.Column(db.Integer)
    message_id = db.Column(db.BigInteger)
    chat_id = db.Column(db.BigInteger)
    description = db.Column(db.Text)
    last_rendered_text = db.Column(db.Text)
    is_simple = Column(Boolean, default=False)

class Registration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))

class EventsOverviewMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.BigInteger)
    chat_id = db.Column(db.BigInteger)
    last_rendered_text = db.Column(db.Text)

with app.app_context():
    db.create_all()


def format_uk_date(dt, with_time=True):
    if with_time:
        return format_datetime(dt, "EEEE, d MMMM yyyy о HH:mm", locale="uk")
    else:
        return format_datetime(dt, "EEEE, d MMMM yyyy", locale="uk")


# === Перевірка адміна ===
def is_admin(chat_id, user_id):
    return str(user_id) in ADMIN_IDS




def periodic_event_update():
#    with app.app_context():
 #       while True:
  #          try:
   #             now = datetime.now()
    #            events = Event.query.filter(Event.date >= now).all()
     #           for event in events:
      #              update_event_message(event)
       #         time.sleep(30)  # кожні 30 секунд
        #    except Exception as e:
         #       print(f"[❌ Помилка у циклі оновлення]: {e}")
          #      time.sleep(600)
    pass

# Запускаємо фоновий потік
#update_thread = threading.Thread(target=periodic_event_update, daemon=True)
#update_thread.start()


# === Оновлення повідомлення про ігротеку(кількість людей) ===
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


def update_overview_message():
    try:
        overview = EventsOverviewMessage.query.first()
        if not overview:
            print("❗ Немає повідомлення з ігротекою для оновлення.")
            return


        events = Event.query.order_by(Event.date).all()
        if not events:
            full_text = "📭 Немає запланованих подій."
        else:
            weekday_map = {0: "ПН", 1: "ВТ", 2: "СР", 3: "ЧТ", 4: "ПТ", 5: "СБ", 6: "НД"}
            text_blocks = []

            for event in events:
                regs = Registration.query.filter_by(event_id=event.id).all()
                users = [db.session.get(User, r.user_id) for r in regs]
                usernames = [f"@{u.username}" if u.username else f"ID:{u.telegram_id}" for u in users if u]
                weekday = weekday_map[event.date.weekday()]
                date_str = event.date.strftime("%d.%m")


                block = (
                    f"<b>🗓 {weekday}, {date_str} – {event.name}</b>\n"
                    f"{event.description.strip()}\n"
                )
                if getattr(event, "is_simple", False) is False:
                    block += f"<b>Заповненість:</b> {len(usernames)} / {event.max_players}\n"
                    block += f"<b>Гравці:</b> " + (", ".join(usernames) if usernames else "—")
                text_blocks.append(block)

            full_text = "\n\n".join(text_blocks)

        # 🧠 Якщо текст не змінився — не оновлюємо
        if overview.last_rendered_text == full_text:
            print("ℹ️ Текст огляду не змінився — оновлення пропущено.")
            return

        # 🔁 Оновлення повідомлення
        bot.edit_message_text(
            full_text,
            chat_id=overview.chat_id,
            message_id=overview.message_id,
            parse_mode="HTML"
        )

        # 💾 Збереження нового тексту
        overview.last_rendered_text = full_text
        db.session.commit()
        print("✅ Оновлено загальне повідомлення з подіями")

    except ApiTelegramException as e:
        if "message is not modified" in str(e):
            print("ℹ️ Telegram: нічого не змінилось — пропущено.")
        else:
            print(f"❌ Telegram API помилка: {e}")
    except Exception as e:
        print(f"❌ Помилка при оновленні огляду подій: {e}")


def update_event_message(event):
    try:
        if not event.message_id or not event.chat_id:
            print(f"⚠️ Подія '{event.name}' не має message_id або chat_id — пропущено оновлення.")
            return

        registrations = Registration.query.filter_by(event_id=event.id).all()
        players = [db.session.get(User, r.user_id) for r in registrations if db.session.get(User, r.user_id)]

        text = f"🔔 Подія: {event.name}\n🕒 Дата: {format_uk_date(event.date)}\n"
        text += f"👥 Гравців: {len(players)} / {event.max_players}\n"
        if players:
            text += "Гравці: " + ", ".join(f"@{p.username}" if p.username else f"ID:{p.telegram_id}" for p in players) + "\n"


        # ⏳ Перевіряємо, чи текст змінився
        if event.last_rendered_text == text:
            print(f"ℹ️ '{event.name}': текст не змінився — оновлення пропущено.")
            return

        bot.edit_message_text(
            chat_id=event.chat_id,
            message_id=event.message_id,
            text=text
        )

        # 💾 Зберігаємо новий текст
        event.last_rendered_text = text
        db.session.commit()

        update_overview_message()
        print(f"✅ Повідомлення події '{event.name}' оновлено")

    except ApiTelegramException as e:
        if "message is not modified" in str(e):
            print(f"ℹ️ '{event.name}': текст і кнопки не змінилися — пропущено оновлення.")
        else:
            print(f"❌ Telegram API помилка для '{event.name}': {e}")
    except Exception as e:
        print(f"❌ Помилка оновлення '{event.name}': {e}")


def generate_event_buttons(events=None):
    """
    Повертає InlineKeyboardMarkup для переданого списку events.
    Якщо events is None — дістане всі події з реєстрацією з БД.
    (Сумісно з попередніми викликами без аргументів.)
    """
    if events is None:
        # Беремо тільки події з реєстрацією
        events = Event.query.filter_by(is_simple=False).order_by(Event.date).all()

    markup = types.InlineKeyboardMarkup()
    if not events:
        markup.add(types.InlineKeyboardButton("Подій ще немає", callback_data="none"))
        return markup

    for event in events:
        # Безпечний weekday / date label
        weekday_abbr = UKR_DAY_ABBR.get(event.date.weekday(), "")
        date_label = format_date(event.date, format="dd.MM", locale="uk") if event.date else ""
        label = f"{weekday_abbr}, {date_label} | {event.name}"
        markup.add(types.InlineKeyboardButton(label, callback_data=f"toggle_{event.id}"))

    return markup

# === Старт ===
@bot.message_handler(commands=['start'])
def start_handler(message):
    telegram_id = str(message.from_user.id)
    username = message.from_user.username or 'Без імені'
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id, username=username)
        db.session.add(user)
        db.session.commit()
    bot.send_message(message.chat.id, "Привіт! Обери подію для реєстрації:", reply_markup=generate_event_buttons())


# === Інлайн-кнопки: реєстрація + скасування ===
def handle_registration_logic(call, telegram_id, username, event_id):
    with app.app_context():
        try:
            user = User.query.filter_by(telegram_id=telegram_id).first()
            if not user:
                user = User(telegram_id=telegram_id, username=username)
                db.session.add(user)
            else:
                user.username = username  # Оновлюємо username
            db.session.commit()

            registration = Registration.query.filter_by(user_id=user.id, event_id=event_id).first()
            event = db.session.get(Event, event_id)

            if not event or not event.message_id:
                print(f"⚠️ Подія з id={event_id} не знайдена або не має message_id.")
                return

            if registration:
                db.session.delete(registration)
                db.session.commit()
                update_event_message(event)
            else:
                current_players = Registration.query.filter_by(event_id=event_id).count()
                if current_players >= event.max_players:
                    bot.send_message(call.message.chat.id, "⚠️ На жаль, всі місця зайняті.")
                    return
                reg = Registration(user_id=user.id, event_id=event_id)
                db.session.add(reg)
                db.session.commit()
                update_event_message(event)

        except Exception as e:
            print(f"❌ Помилка в handle_registration_logic: {e}")



@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_"))
def handle_toggle_registration(call):
    telegram_id = str(call.from_user.id)
    username = call.from_user.username or 'Без імені'
    event_id = int(call.data.split("_")[1])

    with app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            user = User(telegram_id=telegram_id, username=username)
            db.session.add(user)
            db.session.commit()
        else:
            if user.username != username:
                user.username = username
                db.session.commit()

        registration = Registration.query.filter_by(user_id=user.id, event_id=event_id).first()
        event = db.session.get(Event, event_id)
        if not event:
            bot.answer_callback_query(call.id, text="❌ Подія не знайдена.", show_alert=True)
            return

        if registration:
            db.session.delete(registration)
            db.session.commit()
            bot.answer_callback_query(call.id, text=f"❌ Ви скасували реєстрацію на '{event.name}'.")
        else:
            current_players = Registration.query.filter_by(event_id=event_id).count()
            if current_players >= event.max_players:
                bot.answer_callback_query(call.id, text="⚠️ Всі місця зайняті.", show_alert=True)
                return
            reg = Registration(user_id=user.id, event_id=event_id)
            db.session.add(reg)
            db.session.commit()
            bot.answer_callback_query(call.id, text=f"✅ Ви зареєструвались на '{event.name}'.")

        # 🔁 Оновлюємо повідомлення після будь-якої зміни
        update_event_message(event)
        update_overview_message()




# === Команди адміністратора ===
@bot.message_handler(commands=['admin'])
def admin_menu(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "⛔ Доступ заборонено.")
        return
    bot.send_message(message.chat.id, """📋 Адмін-команди:
/create_event - Створити ігротеку
/delete_event - Видалити ігротеку
/edit_event - Змінити ігротеку
/list_event - Люди, зареєстровані на ігротеку
/export_event - Люди, зареєстровані на ігротеку у файлі
/events — Загальний список ігротек
/delete_all - Видалити всі ігротеки
/set_event_image - При додаванні фото у примітках цю команду
/add_admin - Дати адмінку
/remove_admin - Видалити адмінку
/add_event - створити подію без реєстрації(D&D)
""")


def update_admin_ids_env(new_ids):
    env_path = ".env.prod"
    lines = []
    found = False
    new_line = f"ADMIN_IDS={','.join(new_ids)}"
    with open(env_path, "r") as f:
        for line in f:
            if line.startswith("ADMIN_IDS="):
                lines.append(new_line + "\n")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(new_line + "\n")
    with open(env_path, "w") as f:
        f.writelines(lines)


@bot.message_handler(commands=['add_admin'])
def add_admin_handler(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "⛔ Доступ лише для адміністраторів.")
        return

    telegram_id = str(message.reply_to_message.from_user.id if message.reply_to_message else message.from_user.id)
    username = message.reply_to_message.from_user.username if message.reply_to_message else message.from_user.username

    if telegram_id in ADMIN_IDS:
        bot.reply_to(message, f"ℹ️ @{username} вже є адміністратором.")
        return

    ADMIN_IDS.append(telegram_id)
    update_admin_ids_env(ADMIN_IDS)

    # Зберігаємо в базу (необов'язково)
    if not User.query.filter_by(telegram_id=telegram_id).first():
        user = User(username=username, telegram_id=telegram_id)
        db.session.add(user)
        db.session.commit()

    bot.reply_to(message, f"✅ @{username} додано до адміністраторів.")

@bot.message_handler(commands=['remove_admin'])
def remove_admin_handler(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "⛔ Доступ лише для адміністраторів.")
        return

    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "📌 Формат: /remove_admin username (без @)")
        return

    username_to_remove = args[1].lstrip("@").strip()
    user = User.query.filter_by(username=username_to_remove).first()

    if not user:
        bot.reply_to(message, f"⚠️ Користувача @{username_to_remove} не знайдено у базі.")
        return

    telegram_id = str(user.telegram_id)
    if telegram_id not in ADMIN_IDS:
        bot.reply_to(message, f"ℹ️ @{username_to_remove} не є адміністратором.")
        return

    ADMIN_IDS.remove(telegram_id)
    update_admin_ids_env(ADMIN_IDS)
    bot.reply_to(message, f"✅ @{username_to_remove} видалено з адміністраторів.")


@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    if not is_admin(message.chat.id, message.from_user.id):
        return  # ігнорувати фото від неадмінів

    if message.caption and message.caption.strip().startswith("/set_event_image"):
        # Зберігаємо останнє фото з максимальною роздільною здатністю
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        with open(CURRENT_IMAGE_PATH, 'wb') as f:
            f.write(downloaded_file)

        bot.reply_to(message, "✅ Фото успішно збережено для подальших анонсів.")

#locale.setlocale(locale.LC_TIME, 'uk_UA.UTF-8')
#locale.setlocale(locale.LC_TIME, 'uk_UA.UTF-8')


@bot.message_handler(commands=['create_event'])
def create_event_handler(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Лише для адмінів.")
        return

    try:
        content = message.text[len('/create_event'):].strip()
        parts = [p.strip() for p in content.split("|")]
        if len(parts) < 4:
            bot.reply_to(message, "📌 Формат: /create_event Назва | Дата | МаксГравців | Опис")
            return

        name, date_str, max_players_str, description = parts[:4]

        try:
            event_date = datetime.strptime(date_str, "%d.%m")
            event_date = event_date.replace(year=datetime.now().year)
        except ValueError:
            bot.reply_to(message, "❗️ Невірний формат дати. Використовуйте DD.MM")
            return

        #if event_date < datetime.now():
         #   bot.reply_to(message, "⚠️ Дата вже минула.")
          #  return

        try:
            max_players = int(max_players_str)
        except ValueError:
            bot.reply_to(message, "⚠️ Кількість гравців має бути числом.")
            return

        event = Event(
            name=name,
            date=event_date,
            max_players=max_players,
            description=description,
            is_simple=False
        )
        db.session.add(event)
        db.session.commit()

        # ❗️ ТУТ ГОЛОВНЕ: публікуємо в тому ж чаті, де створено івент (особистий чат)
        publish_event_message(event, chat_id=message.chat.id)

        bot.send_chat_action(message.chat.id, "typing")
        time.sleep(0.3)
        bot.delete_message(message.chat.id, message.message_id)
        bot.send_message(message.chat.id, "✅ Івент створено.", disable_notification=True)

    except Exception as e:
        print(f"[ERROR /create_event]: {e}")
        bot.reply_to(message, "🚫 Помилка при створенні події.")


@bot.message_handler(commands=['add_event'])
def add_simple_event(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Лише для адмінів.")
        return

    try:
        parts = message.text[len("/add_event"):].strip().split("|")
        if len(parts) < 3:
            bot.reply_to(message, "📌 Формат: /add_event Назва | Дата | Опис")
            return

        name = parts[0].strip()
        date_str = parts[1].strip()
        description = parts[2].strip()

        try:
            event_date = datetime.strptime(date_str, "%d.%m")
            event_date = event_date.replace(year=datetime.now().year)
        except ValueError:
            bot.reply_to(message, "❗️ Невірний формат дати. Використовуйте DD.MM")
            return

        # Створюємо просту подію
        new_event = Event(
            name=name,
            date=event_date,
            description=description,
            is_simple=True
        )
        db.session.add(new_event)
        db.session.commit()

        # Публікуємо в групу без кнопок
        text = f"📅 {event_date.strftime('%d.%m.%Y')}\n<b>{name}</b>\n\n{description}"

        bot.reply_to(message, "✅ Подія додана як проста (без реєстрації).")

    except Exception as e:
        bot.reply_to(message, f"🚫 Помилка: {e}")



def publish_event_message(event, chat_id=GROUP_CHAT_ID):
    try:
        # Якщо подія проста — без блоку "Гравців" і кнопок
        if getattr(event, "is_simple", False):
            text = (
                f"🔔 Подія: {event.name}\n"
                f"🕒 Дата: {event.date.strftime('%d.%m.%Y %H:%M')}\n"
                f"{event.description}"
            )
            markup = None
        else:
            text = (
                f"🔔 Подія: {event.name}\n"
                f"🕒 Дата: {event.date.strftime('%d.%m.%Y %H:%M')}\n"
                f"👥 Гравців: 0 / {event.max_players}\n"
                f"{event.description}"
            )
            markup = InlineKeyboardMarkup()


        msg = bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)

        event.message_id = msg.message_id
        event.chat_id = msg.chat.id
        event.last_rendered_text = text
        db.session.commit()

        print(f"✅ Повідомлення про подію '{event.name}' опубліковано.")
    except Exception as e:
        print(f"❌ Не вдалося опублікувати повідомлення для '{event.name}': {e}")



@bot.message_handler(commands=['delete_event'])
def delete_event_handler(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Лише для адмінів.")
        return

    args = message.text.split(' ', 1)
    if len(args) < 2:
        bot.reply_to(message, "📌 Формат: /delete_event Назва події")
        return

    event_name = args[1].strip()
    event = Event.query.filter_by(name=event_name).first()
    if not event:
        bot.reply_to(message, f"⚠️ Подія '{event_name}' не знайдена.")
        return

    Registration.query.filter_by(event_id=event.id).delete()
    db.session.delete(event)
    db.session.commit()
    bot.send_message(message.chat.id, f"🗑 Подію '{event_name}' видалено з усіма реєстраціями.")

@bot.message_handler(commands=['delete_all'])
def delete_all_events_handler(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Лише для адмінів.")
        return
    Registration.query.delete()
    Event.query.delete()
    db.session.commit()
    bot.send_message(message.chat.id, "🗑 Усі події та реєстрації було очищено.")


@bot.message_handler(commands=['edit_event'])
def edit_event_handler(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Лише для адмінів.")
        return

    args = message.text.split(' ', 1)
    if len(args) < 2 or "|" not in args[1]:
        bot.reply_to(message, "📌 Формат: /edit_event СтараНазва | НоваНазва")
        return

    old_name, new_name = map(str.strip, args[1].split("|", 1))
    event = Event.query.filter_by(name=old_name).first()
    if not event:
        bot.reply_to(message, f"⚠️ Подія '{old_name}' не знайдена.")
        return

    event.name = new_name
    db.session.commit()
    bot.send_message(message.chat.id, f"✅ Подію перейменовано: '{old_name}' ➝ '{new_name}'")
import time
from telebot.apihelper import ApiTelegramException

@bot.message_handler(commands=['events'])
def send_events_to_group(message):
    # Тільки для адміністраторів
    if not is_admin(message.chat.id, message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Лише для адмінів.")
        return

    events = Event.query.order_by(Event.date).all()
    if not events:
        bot.send_message(message.chat.id, "📭 Наразі немає запланованих подій.")
        return

    intro_text = (
        "Ану до нас на ігротеку! 🎲\n"
        "Немає компанії? Знайдемо! \n"
        "Навчимо правилам — пригостимо кавою☕️\n"
        "Початок о 18:00 \n"
        "📍 Адреса: вул. Листопадового Чину, 3\n\n"
    )

    # Надсилаємо зображення (якщо є)
    if os.path.exists(CURRENT_IMAGE_PATH):
        try:
            with open(CURRENT_IMAGE_PATH, "rb") as photo:
                bot.send_photo(message.chat.id, photo, caption=intro_text)
                time.sleep(1)
        except ApiTelegramException as e:
            handle_too_many_requests(e)

    # Формування тексту подій
    weekday_map = {0: "ПН", 1: "ВТ", 2: "СР", 3: "ЧТ", 4: "ПТ", 5: "СБ", 6: "НД"}
    text_blocks = []
    events_for_buttons = []  # тільки ті, що мають реєстрацію

    for event in events:
        weekday = weekday_map.get(event.date.weekday(), "")
        date_str = format_date(event.date, format="dd.MM", locale="uk") if event.date else ""

        if getattr(event, "is_simple", False):
            block = (
                f"📅 {weekday}, {date_str} – {event.name}\n"
                f"{(event.description or '').strip()}"
            )
        else:
            regs = Registration.query.filter_by(event_id=event.id).all()
            users = [db.session.get(User, r.user_id) for r in regs]
            usernames = [f"@{u.username}" if u and u.username else f"ID:{u.telegram_id}" for u in users if u]

            players_text = ", ".join(usernames) if usernames else "поки ніхто"
            block = (
                f"📅 {weekday}, {date_str} – {event.name}\n"
                f"{(event.description or '').strip()}\n"
                f"Гравці: {players_text}"
            )
            events_for_buttons.append(event)

        text_blocks.append(block)

    full_text = "\n\n".join(text_blocks)

    # Надсилаємо опис подій
    try:
        desc_msg = bot.send_message(message.chat.id, full_text, parse_mode="HTML")
        time.sleep(1)
    except ApiTelegramException as e:
        handle_too_many_requests(e)
        return

    # Зберігаємо або оновлюємо overview у БД
    overview = EventsOverviewMessage.query.first()
    if not overview:
        overview = EventsOverviewMessage(
            chat_id=desc_msg.chat.id,
            message_id=desc_msg.message_id,
            last_rendered_text=full_text
        )
        db.session.add(overview)
    else:
        overview.chat_id = desc_msg.chat.id
        overview.message_id = desc_msg.message_id
        overview.last_rendered_text = full_text
    db.session.commit()

    # Кнопки — тільки якщо є події з реєстрацією
    if events_for_buttons:
        markup = generate_event_buttons(events_for_buttons)
        try:
            bot.send_message(message.chat.id, "Обери подію для реєстрації:", reply_markup=markup)
            time.sleep(1)
        except ApiTelegramException as e:
            handle_too_many_requests(e)



def handle_too_many_requests(e):
    if e.result.status_code == 429:
        retry_after = e.result_json.get("parameters", {}).get("retry_after", 5)
        print(f"[Rate Limit] Too Many Requests. Waiting for {retry_after} seconds...")
        time.sleep(retry_after)
    else:
        raise e


@bot.message_handler(commands=['list_event'])
def list_event_handler(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Лише для адмінів.")
        return
    args = message.text.split(' ', 1)
    if len(args) < 2:
        bot.reply_to(message, "📌 Формат: /list_event НазваПодії")
        return
    event_name = args[1].strip()
    event = Event.query.filter_by(name=event_name).first()
    if not event:
        bot.reply_to(message, f"⚠️ Подія '{event_name}' не знайдена.")
        return
    registrations = Registration.query.filter_by(event_id=event.id).all()
    if not registrations:
        bot.reply_to(message, f"👥 Ніхто ще не зареєстрований на '{event.name}'.")
        return
    usernames = []
    for reg in registrations:
        user = db.session.get(User, reg.user_id)
        if user:
            usernames.append(f"@{user.username}" if user.username else f"ID:{user.telegram_id}")
    reply = f"📋 Зареєстровані на '{event.name}':\n" + ", ".join(usernames)

    bot.send_message(message.chat.id, reply)


@bot.message_handler(commands=['export_event'])
def export_event_handler(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Лише для адмінів.")
        return
    args = message.text.split(' ', 1)
    if len(args) < 2:
        bot.reply_to(message, "📌 Формат: /export_event НазваПодії")
        return
    event_name = args[1].strip()
    event = Event.query.filter_by(name=event_name).first()
    if not event:
        bot.reply_to(message, f"⚠️ Подія '{event_name}' не знайдена.")
        return
    registrations = Registration.query.filter_by(event_id=event.id).all()
    data = []
    for reg in registrations:
        user = db.session.get(User, reg.user_id)
        if user:
            data.append({
                "Telegram ID": user.telegram_id,
                "Username": user.username or "",
            })
    if not data:
        bot.send_message(message.chat.id, f"⚠️ Немає зареєстрованих на '{event.name}'")
        return
    df = pd.DataFrame(data)
    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    bot.send_document(message.chat.id, output, visible_file_name=f"{event.name}.xlsx")


# === Вебхуки ===

@app.route('/', methods=['POST'])
def webhook_root():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return '', 200

@app.route('/ping')
def ping():
    return "✅ I'm alive", 200


@app.route('/')
def index():
    return '✅ Бот працює!'


# === Запуск із вебхуком ===
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{API_TOKEN}")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
#if __name__ == "__main__":
 #   print("[✅] Запуск у режимі polling")
  #  bot.remove_webhook()
   # bot.infinity_polling()

