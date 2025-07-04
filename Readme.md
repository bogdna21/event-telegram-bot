🧩 Telegram Event Manager Bot

A Telegram bot designed to manage game events (ігротеки) with features for creating, editing, registering, and exporting player lists. Built using Python, Flask, SQLAlchemy, and pyTelegramBotAPI, it supports full event lifecycle management, including real-time updates and webhook deployment.
🚀 Features

    📅 Create, edit, and delete events (game sessions).

    👥 Register and unregister users for specific events.

    📊 Export registrations to Excel.

    🔄 Automatically updates event messages and a general overview.

    🖼 Attach and send event images in announcements.

    📬 Webhook-based Flask server for reliable hosting.

    🔐 Admin-only commands for managing content securely.

🛠 Tech Stack

    Python 3

    Flask

    SQLAlchemy

    pyTelegramBotAPI (telebot)

    SQLite / PostgreSQL (configurable)

    Pandas (for export)

    dotenv (for config)

    Threading (for periodic updates)

📦 Installation

    Clone the repository:

git clone https://github.com/yourusername/your-repo-name.git
cd your-repo-name

    Install dependencies:

pip install -r requirements.txt

    Create a .env file:

API_TOKEN=your_telegram_bot_token
DATABASE_URL=sqlite:///events.db
ADMIN_IDS=12345678,87654321  # Comma-separated Telegram user IDs
GROUP_CHAT_ID=-1001234567890  # Target group chat ID
WEBHOOK_URL=https://yourdomain.com
PORT=5000

    Run the bot:

python bot.py

Or deploy it to a cloud hosting provider with webhook support.
📚 Bot Commands
User Commands

    /start — View list of available events and register.

    Inline buttons to join or leave events.

Admin Commands
Command	Description
/admin	Show all admin commands.
/create_event	Create a new event (`Name
/edit_event	Rename an event (`OldName
/delete_event	Delete an event by name.
/delete_all	Remove all events and registrations.
/list_event	List registered users for a given event.
/export_event	Export registered users to Excel.
/events	Post all upcoming events in the group.
/set_event_image	Save image for the next announcement.
📤 Webhook

The bot uses Flask to handle incoming webhook requests:

POST /<API_TOKEN>

To deploy with webhook, set:

bot.set_webhook(url=f"{WEBHOOK_URL}/{API_TOKEN}")

📈 Database Models

    User — Stores Telegram users.

    Event — Stores events.

    Registration — Links users to events.

    EventsOverviewMessage — Tracks the latest event message for live updates.

🌐 Hosting Suggestions

    🆓 Render, Railway, or Fly.io for free-tier Flask deployment.

    🐘 Use PostgreSQL or stick with SQLite for low-volume usage.

🔒 Admin Access

Only Telegram user IDs listed in ADMIN_IDS are allowed to use management commands.
📸 Screenshots

    (You can optionally add screenshots of your bot in action here.)

🧪 Testing

You can test the bot locally using Flask’s default server and Telegram’s setWebhook method. For development, consider using ngrok to tunnel to localhost.
📄 License

MIT License — free to use and modify.