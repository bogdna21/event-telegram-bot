import os
import datetime
import locale
from flask import Flask, request
from telebot import TeleBot, types
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime
import pandas as pd
from io import BytesIO
import threading
import time
from telebot.apihelper import ApiTelegramException


# === Завантаження змінних з .env ===
load_dotenv()
API_TOKEN = os.getenv("API_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///events.db")
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

class Registration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))

class EventsOverviewMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.BigInteger)
    chat_id = db.Column(db.BigInteger)

with app.app_context():
    db.create_all()

# === Перевірка адміна ===
def is_admin(chat_id, user_id):
    return str(user_id) in ADMIN_IDS



def periodic_event_update():
    with app.app_context():
        while True:
            try:
                now = datetime.now()
                events = Event.query.filter(Event.date >= now).all()
                for event in events:
                    update_event_message(event)
                time.sleep(30)  # кожні 30 секунд
            except Exception as e:
                print(f"[❌ Помилка у циклі оновлення]: {e}")
                time.sleep(60)


# Запускаємо фоновий потік
update_thread = threading.Thread(target=periodic_event_update, daemon=True)
update_thread.start()


# === Оновлення повідомлення про ігротеку(кількість людей) ===
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


def update_overview_message():
    try:
        overview = EventsOverviewMessage.query.first()
        if not overview:
            print("❗ Немає повідомлення з ігротекою для оновлення.")
            return

        events = Event.query.filter(Event.date >= datetime.now()).order_by(Event.date).all()
        if not events:
            bot.edit_message_text("📭 Немає запланованих подій.", chat_id=overview.chat_id, message_id=overview.message_id)
            return

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
                f"👥 2–{event.max_players} гравців\n"
                f"⭐️ Для всіх бажаючих\n"
                f"<b>Заповненість:</b> {len(usernames)} / {event.max_players}\n"
                f"<b>Гравці:</b>\n" + ("\n".join(usernames) if usernames else "—")
            )
            text_blocks.append(block)

        full_text = "\n\n".join(text_blocks)
        bot.edit_message_text(full_text, chat_id=overview.chat_id, message_id=overview.message_id, parse_mode="HTML")
        print("✅ Оновлено загальне повідомлення з подіями")

    except Exception as e:
        print(f"❌ Помилка при оновленні огляду подій: {e}")


def update_event_message(event):
    try:
        registrations = Registration.query.filter_by(event_id=event.id).all()
        players = [db.session.get(User, r.user_id) for r in registrations if db.session.get(User, r.user_id)]

        text = f"🔔 Подія: {event.name}\n🕒 Дата: {event.date.strftime('%d.%m.%Y %H:%M')}\n"
        text += f"👥 Гравців: {len(players)} / {event.max_players}\n"
        if players:
            text += "Гравці: " + ", ".join(f"@{p.username}" if p.username else f"ID:{p.telegram_id}" for p in players) + "\n"

        reply_markup = InlineKeyboardMarkup()
        reply_markup.add(
            InlineKeyboardButton("✅ Я йду", callback_data=f"join_{event.id}"),
            InlineKeyboardButton("❌ Не йду", callback_data=f"leave_{event.id}")
        )

        bot.edit_message_text(
            chat_id=event.chat_id,
            message_id=event.message_id,
            text=text,
            reply_markup=reply_markup
        )

        update_overview_message()
        print(f"✅ Повідомлення події '{event.name}' оновлено")

    except ApiTelegramException as e:
        if "message is not modified" in str(e):
            print(f"ℹ️ '{event.name}': текст і кнопки не змінилися — пропущено оновлення.")
        else:
            print(f"❌ Інша помилка Telegram API для '{event.name}': {e}")
    except Exception as e:
        print(f"❌ Помилка оновлення '{event.name}': {e}")



def generate_event_buttons():
    markup = types.InlineKeyboardMarkup()
    events = Event.query.filter(Event.date >= datetime.now()).order_by(Event.date).all()
    if not events:
        markup.add(types.InlineKeyboardButton("Подій ще немає", callback_data="none"))
    else:
        for event in events:
            weekday_abbr = UKR_DAY_ABBR[event.date.weekday()]
            date_label = event.date.strftime("%d.%m")
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
@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_"))
def handle_toggle_registration(call):
    telegram_id = str(call.from_user.id)
    username = call.from_user.username or 'Без імені'
    event_id = int(call.data.split("_")[1])

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

            if registration:
                db.session.delete(registration)
                db.session.commit()
                update_event_message(event)
                bot.answer_callback_query(call.id, "❌ Реєстрацію скасовано.")
            else:
                # Перевіряємо, чи є ще місця
                current_players = Registration.query.filter_by(event_id=event_id).count()
                if current_players >= event.max_players:
                    bot.answer_callback_query(call.id, "⚠️ На жаль, всі місця зайняті.")
                    return

                reg = Registration(user_id=user.id, event_id=event_id)
                db.session.add(reg)
                db.session.commit()
                update_event_message(event)
                bot.answer_callback_query(call.id, "✅ Реєстрація успішна!")

        except Exception as e:
            print(f"❌ Помилка в handle_toggle_registration: {e}")
            bot.answer_callback_query(call.id, "⚠️ Сталася помилка. Спробуйте пізніше.")



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
""")


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

locale.setlocale(locale.LC_TIME, 'uk_UA.UTF-8')
locale.setlocale(locale.LC_TIME, 'uk_UA.UTF-8')


@bot.message_handler(commands=['create_event'])
def create_event_handler(message):
    try:
        if not is_admin(message.chat.id, message.from_user.id):
            bot.reply_to(message, "❌ Лише для адмінів.")
            return
        text = message.text[len('/create_event'):].strip()
        if "|" not in text:
            bot.reply_to(message, "📌 Формат: /create_event Назва | Дата | МаксГравців | Опис")
            return
        parts = [p.strip() for p in text.split("|")]
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
        try:
            max_players = int(max_players_str)
        except ValueError:
            bot.reply_to(message, "⚠️ Кількість гравців має бути числом.")
            return

        # Створюємо подію
        event = Event(name=name, date=event_date, max_players=max_players, description=description)
        db.session.add(event)
        db.session.commit()
        bot.reply_to(message, "✅ Подію збережено! Щоб надіслати — скористайся /events")

    except Exception as e:
        print(f"[ERROR /create_event]: {e}")
        bot.reply_to(message, "🚫 Сталася помилка при створенні події.")


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
    bot.send_message(message.chat.id, f"🗑 Подію '{event_name}' видалено разом із реєстраціями.")

@bot.message_handler(commands=['delete_all'])
def delete_all_events_handler(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Лише для адмінів.")
        return
    Registration.query.delete()
    Event.query.delete()
    db.session.commit()
    bot.send_message(message.chat.id, "🗑 Усі події та реєстрації було успішно видалено.")


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


@bot.message_handler(commands=['events'])
def send_events_to_group(message):

    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "⛔ Лише для адмінів.")
        return
    events = Event.query.filter(Event.date >= datetime.now()).order_by(Event.date).all()
    if not events:
        bot.send_message(message.chat.id, "📭 Наразі немає запланованих подій.")
        return
    if os.path.exists(CURRENT_IMAGE_PATH):
        try:
            with open(CURRENT_IMAGE_PATH, 'rb') as photo:
                bot.send_photo(message.chat.id, photo, caption="🧩 Ігротека — не пропусти подію!")
        except Exception as e:
            print(f"❌ Помилка при надсиланні фото: {e}")
    text_blocks = []
    weekday_map = {0: "ПН", 1: "ВТ", 2: "СР", 3: "ЧТ", 4: "ПТ", 5: "СБ", 6: "НД"}
    for event in events:
        regs = Registration.query.filter_by(event_id=event.id).all()
        users = [db.session.get(User, r.user_id) for r in regs]
        usernames = [f"@{u.username}" if u.username else f"ID:{u.telegram_id}" for u in users if u]
        weekday = weekday_map[event.date.weekday()]
        date_str = event.date.strftime("%d.%m")
        block = (
            f"<b>🗓 {weekday}, {date_str} – {event.name}</b>\n"
            f"👥 2–{event.max_players} гравців\n"
            f"⭐️ Для всіх бажаючих\n"
            f"<b>Заповненість:</b> {len(usernames)} / {event.max_players}\n"
            f"<b>Гравці:</b>\n" + ("\n".join(usernames) if usernames else "—")
        )
        text_blocks.append(block)
    try:
        full_text = "\n\n".join(text_blocks)
        EventsOverviewMessage.query.delete()
        db.session.commit()
        sent = bot.send_message(message.chat.id, full_text, parse_mode="HTML")
        overview = EventsOverviewMessage(message_id=sent.message_id, chat_id=message.chat.id)
        db.session.add(overview)
        db.session.commit()
        bot.send_message(message.chat.id, "Обери подію для реєстрації:", reply_markup=generate_event_buttons())
    except Exception as e:
        print(f"❌ Помилка при надсиланні подій: {e}")


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
    reply = f"📋 Зареєстровані на '{event.name}':\n" + "\n".join(usernames)
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
@app.route(f'/{API_TOKEN}', methods=['POST'])
def webhook():
    update = types.Update.de_json(request.data.decode("utf-8"))
    bot.process_new_updates([update])
    return "ok", 200

@app.route('/')
def index():
    return '✅ Бот працює!'


# === Запуск із вебхуком ===
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{API_TOKEN}")
    app.run(host="0.0.0.0", port=PORT, threaded=True)
