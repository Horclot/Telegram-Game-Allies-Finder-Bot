import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, Filters, \
    CallbackContext
import sqlite3
from datetime import datetime, timedelta

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

NICKNAME, GAME, RANK, DESCRIPTION, EDITING = range(5)
MAIN_MENU_BUTTON = "🏠 Главное меню"

# Инициализация базы данных
conn = sqlite3.connect('allies.db', check_same_thread=False)
cursor = conn.cursor()

# Создание таблиц
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        game TEXT,
        rank TEXT,
        description TEXT,
        is_searching BOOLEAN DEFAULT FALSE,
        is_banned BOOLEAN DEFAULT FALSE,
        ban_end DATETIME
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS invites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user_id INTEGER,
        to_user_id INTEGER,
        status TEXT DEFAULT 'pending',
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(from_user_id) REFERENCES users(user_id),
        FOREIGN KEY(to_user_id) REFERENCES users(user_id)
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reported_user_id INTEGER,
        reporter_user_id INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(reported_user_id) REFERENCES users(user_id),
        FOREIGN KEY(reporter_user_id) REFERENCES users(user_id)
    )
''')
conn.commit()


def main_menu_markup():
    return ReplyKeyboardMarkup([[MAIN_MENU_BUTTON]], resize_keyboard=True, one_time_keyboard=False)


def has_profile(user_id: int) -> bool:
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    return cursor.fetchone() is not None


def show_main_menu(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user if update.message else update.callback_query.from_user
    chat_id = update.effective_chat.id

    # Проверяем разблокировку аккаунта
    cursor.execute('SELECT is_banned, ban_end FROM users WHERE user_id = ?', (user.id,))
    user_data = cursor.fetchone()
    if user_data and user_data[0]:  # Если аккаунт заблокирован
        ban_end = datetime.strptime(user_data[1], "%Y-%m-%d %H:%M:%S")
        if datetime.now() > ban_end:
            # Разблокируем аккаунт
            cursor.execute('UPDATE users SET is_banned = FALSE, ban_end = NULL WHERE user_id = ?', (user.id,))
            conn.commit()
            context.bot.send_message(
                chat_id=chat_id,
                text="✅ Ваш профиль разблокирован! Теперь вы снова можете искать союзников.",
                reply_markup=main_menu_markup()
            )
        else:
            context.bot.send_message(
                chat_id=chat_id,
                text=f"⛔ Ваш профиль заблокирован до {user_data[1]}. Причина: получено много жалоб.",
                reply_markup=main_menu_markup()
            )
            return

    if has_profile(user.id):
        keyboard = [
            [InlineKeyboardButton("Продолжить поиск", callback_data='resume_search')],
            [InlineKeyboardButton("Изменить анкету", callback_data='edit_profile'),
             InlineKeyboardButton("Остановить поиск", callback_data='stop_search')],
            [InlineKeyboardButton("История инвайтов", callback_data='invite_history'),
             InlineKeyboardButton("Моя анкета", callback_data='show_my_profile')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.bot.send_message(
            chat_id=chat_id,
            text="Главное меню:",
            reply_markup=main_menu_markup()
        )
        context.bot.send_message(
            chat_id=chat_id,
            text="Выберите действие:",
            reply_markup=reply_markup
        )
    else:
        keyboard = [[InlineKeyboardButton("Создать анкету", callback_data='create_profile')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.bot.send_message(
            chat_id=chat_id,
            text="Главное меню будет доступно после создания анкеты!",
            reply_markup=main_menu_markup()
        )
        context.bot.send_message(
            chat_id=chat_id,
            text="Начните с создания анкеты:",
            reply_markup=reply_markup
        )


def start(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    show_main_menu(update, context)


def main_menu_handler(update: Update, context: CallbackContext):
    if update.message.text == MAIN_MENU_BUTTON:
        # Завершаем любые активные диалоги
        if context.user_data.get('editing'):
            context.user_data.clear()
            update.message.reply_text("Редактирование отменено")

        show_main_menu(update, context)
        return ConversationHandler.END


def create_profile(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    query.message.reply_text(
        "Введите ваш игровой никнейм:",
        reply_markup=main_menu_markup()
    )
    return NICKNAME


def nickname(update: Update, context: CallbackContext) -> int:
    context.user_data['nickname'] = update.message.text
    update.message.reply_text(
        "Введите название игры:",
        reply_markup=main_menu_markup()
    )
    return GAME


def game(update: Update, context: CallbackContext) -> int:
    # Если это редактирование профиля
    if context.user_data.get('editing'):
        new_game = update.message.text
        user_id = update.message.from_user.id

        # Обновляем данные в базе
        cursor.execute('''
            UPDATE users 
            SET game = ?
            WHERE user_id = ?
        ''', (new_game, user_id))
        conn.commit()

        update.message.reply_text(
            "✅ Игра успешно обновлена!",
            reply_markup=main_menu_markup()
        )
        show_main_menu(update, context)
        context.user_data.clear()
        return ConversationHandler.END
    # Если это создание профиля
    else:
        context.user_data['game'] = update.message.text
        update.message.reply_text(
            "Введите ваш ранг в игре:",
            reply_markup=main_menu_markup()
        )
        return RANK


def rank(update: Update, context: CallbackContext) -> int:
    # Если это редактирование профиля
    if context.user_data.get('editing'):
        new_rank = update.message.text
        user_id = update.message.from_user.id

        # Обновляем данные в базе
        cursor.execute('''
            UPDATE users 
            SET rank = ?
            WHERE user_id = ?
        ''', (new_rank, user_id))
        conn.commit()

        update.message.reply_text(
            "✅ Ранг успешно обновлен!",
            reply_markup=main_menu_markup()
        )
        show_main_menu(update, context)
        context.user_data.clear()
        return ConversationHandler.END
    # Если это создание профиля
    else:
        context.user_data['rank'] = update.message.text
        update.message.reply_text(
            "Напишите краткое описание о себе и кого ищете:",
            reply_markup=main_menu_markup()
        )
        return DESCRIPTION


def description(update: Update, context: CallbackContext) -> int:
    user = update.message.from_user

    # Если это редактирование профиля
    if context.user_data.get('editing'):
        new_description = update.message.text

        # Обновляем данные в базе
        cursor.execute('''
            UPDATE users 
            SET description = ?
            WHERE user_id = ?
        ''', (new_description, user.id))
        conn.commit()

        update.message.reply_text(
            "✅ Описание успешно обновлено!",
            reply_markup=main_menu_markup()
        )
        show_main_menu(update, context)
        context.user_data.clear()
        return ConversationHandler.END
    # Если это создание профиля
    else:
        context.user_data['description'] = update.message.text

        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, username, game, rank, description, is_searching)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            user.id,
            user.username,
            context.user_data['game'],
            context.user_data['rank'],
            context.user_data['description'],
            True
        ))
        conn.commit()

        update.message.reply_text(
            "Анкета создана! Начинаем поиск...",
            reply_markup=main_menu_markup()
        )
        show_next_profile(update, context, user.id)
        return ConversationHandler.END


def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text(
        'Создание анкеты отменено',
        reply_markup=main_menu_markup()
    )
    return ConversationHandler.END


def show_my_profile(update: Update, context: CallbackContext, user_id: int) -> None:
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    profile = cursor.fetchone()

    if profile:
        profile_text = f"""
        Ваша анкета:
        🎮 Игра: {profile[2]}
        👤 Никнейм: {profile[1]}
        🏆 Ранг: {profile[3]}
        📝 Описание: {profile[4]}
        """
        context.bot.send_message(
            chat_id=user_id,
            text=profile_text,
            reply_markup=main_menu_markup()
        )
    else:
        context.bot.send_message(
            chat_id=user_id,
            text="У вас еще нет анкеты!",
            reply_markup=main_menu_markup()
        )

    # Показываем главное меню после отображения анкеты
    show_main_menu(update, context)


def show_next_profile(update: Update, context: CallbackContext, user_id: int, offset: int = 0) -> None:
    # Проверяем не заблокирован ли пользователь
    cursor.execute('SELECT is_banned FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    if result and result[0]:
        context.bot.send_message(
            chat_id=user_id,
            text="⛔ Ваш профиль заблокирован. Вы не можете искать союзников.",
            reply_markup=main_menu_markup()
        )
        return

    cursor.execute('''
        SELECT * FROM users 
        WHERE game = (SELECT game FROM users WHERE user_id = ?)
        AND is_searching = TRUE
        AND is_banned = FALSE
        AND user_id != ?
        LIMIT 1 OFFSET ?
    ''', (user_id, user_id, offset))
    profile = cursor.fetchone()

    chat_id = update.effective_chat.id
    message = None

    if isinstance(update, Update) and update.message:
        message = update.message
    elif update.callback_query and update.callback_query.message:
        message = update.callback_query.message

    if profile:
        profile_text = f"""
        🎮 Игра: {profile[2]}
        👤 Никнейм: {profile[1]}
        🏆 Ранг: {profile[3]}
        📝 Описание: {profile[4]}
        """
        keyboard = [
            [InlineKeyboardButton("Следующая анкета", callback_data=f'next_{offset + 1}')],
            [
                InlineKeyboardButton("Отправить запрос", callback_data=f'invite_{profile[0]}'),
                InlineKeyboardButton("Перестать искать", callback_data='stop_search')
            ],
            [
                InlineKeyboardButton("Изменить анкету", callback_data='edit_profile'),
                InlineKeyboardButton("Пожаловаться на профиль", callback_data=f'report_{profile[0]}')
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        if message:
            message.reply_text(profile_text, reply_markup=reply_markup)
        else:
            context.bot.send_message(chat_id, profile_text, reply_markup=reply_markup)
    else:
        text = "Пока нет подходящих анкет. Попробуйте позже."
        reply_markup = main_menu_markup()
        if message:
            message.reply_text(text, reply_markup=reply_markup)
        else:
            context.bot.send_message(chat_id, text, reply_markup=reply_markup)


def show_invite_history(user_id: int) -> str:
    # Получаем историю отправленных инвайтов
    cursor.execute('''
        SELECT u.username, i.status 
        FROM invites i
        JOIN users u ON i.to_user_id = u.user_id
        WHERE i.from_user_id = ?
    ''', (user_id,))
    sent_invites = cursor.fetchall()

    # Получаем историю полученных инвайтов
    cursor.execute('''
        SELECT u.username, i.status 
        FROM invites i
        JOIN users u ON i.from_user_id = u.user_id
        WHERE i.to_user_id = ?
    ''', (user_id,))
    received_invites = cursor.fetchall()

    history_text = "📝 Ваша история инвайтов 🎮:\n\n"

    # Добавляем отправленные инвайты
    for username, status in sent_invites:
        status_text = "✅ Принята ✅" if status == 'accepted' else "❌ Отклонена ❌"
        history_text += f"Вы --> {username} ({status_text})\n"

    # Добавляем полученные инвайты
    for username, status in received_invites:
        status_text = "✅ Принята ✅" if status == 'accepted' else "❌ Отклонена ❌"
        history_text += f"{username} --> Вы ({status_text})\n"

    if not sent_invites and not received_invites:
        history_text += "У вас пока нет истории инвайтов."

    return history_text


def report_user(reported_user_id: int, reporter_user_id: int):
    # Добавляем жалобу в базу
    cursor.execute('''
        INSERT INTO reports (reported_user_id, reporter_user_id)
        VALUES (?, ?)
    ''', (reported_user_id, reporter_user_id))
    conn.commit()

    # Проверяем количество жалоб
    cursor.execute('SELECT COUNT(*) FROM reports WHERE reported_user_id = ?', (reported_user_id,))
    report_count = cursor.fetchone()[0]

    if report_count >= 5:
        # Блокируем пользователя на 2 недели
        ban_end = datetime.now() + timedelta(days=14)
        cursor.execute('''
            UPDATE users 
            SET is_banned = TRUE, ban_end = ?, is_searching = FALSE
            WHERE user_id = ?
        ''', (ban_end.strftime("%Y-%m-%d %H:%M:%S"), reported_user_id))
        conn.commit()

        # Уведомляем пользователя о блокировке
        return True, ban_end

    return False, None


def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == 'main_menu':
        show_main_menu(update, context)
        return

    if data.startswith('next_'):
        offset = int(data.split('_')[1])
        show_next_profile(update, context, user_id, offset)

    elif data == 'stop_search':
        cursor.execute('UPDATE users SET is_searching = FALSE WHERE user_id = ?', (user_id,))
        conn.commit()
        # Убираем клавиатуру из текущего сообщения
        query.edit_message_text(
            "Поиск остановлен.",
            reply_markup=None  # Важно: убираем инлайн-клавиатуру
        )
        # Отправляем главное меню как новое сообщение
        show_main_menu(update, context)

    elif data == 'resume_search':
        cursor.execute('UPDATE users SET is_searching = TRUE WHERE user_id = ?', (user_id,))
        conn.commit()
        show_next_profile(update, context, user_id, 0)

    elif data == 'edit_profile':
        keyboard = [
            [InlineKeyboardButton("Поменять игру", callback_data='change_game')],
            [InlineKeyboardButton("Поменять описание", callback_data='change_description')],
            [InlineKeyboardButton("Изменить ранг", callback_data='change_rank')],
            [InlineKeyboardButton("Заполнить заново", callback_data='create_profile')]
        ]
        # Используем reply_text вместо edit_message_text
        context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Что вы хотите изменить?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == 'show_my_profile':
        query.edit_message_text(
            "Ваша анкета:",
            reply_markup=None
        )
        show_my_profile(update, context, user_id)

    elif data.startswith('report_'):
        reported_user_id = int(data.split('_')[1])
        is_banned, ban_end = report_user(reported_user_id, user_id)

        if is_banned:
            # Уведомляем о блокировке пользователя
            context.bot.send_message(
                chat_id=reported_user_id,
                text=f"⛔ Ваш профиль заблокирован до {ban_end.strftime('%Y-%m-%d %H:%M:%S')} "
                     "из-за большого количества жалоб."
            )
            query.edit_message_text(
                "✅ Жалоба отправлена! Профиль заблокирован из-за большого количества жалоб.",
                reply_markup=None
            )
        else:
            query.edit_message_text(
                "✅ Жалоба отправлена! Спасибо за вашу бдительность.",
                reply_markup=None
            )

        # Отправляем главное меню как новое сообщение
        show_main_menu(update, context)

    elif data.startswith('invite_'):
        to_user_id = int(data.split('_')[1])
        cursor.execute('''
            SELECT * FROM invites 
            WHERE from_user_id = ? AND to_user_id = ? 
            AND status = 'pending'
        ''', (user_id, to_user_id))
        if cursor.fetchone():
            # Убираем клавиатуру из текущего сообщения
            query.edit_message_text(
                "Вы уже отправили запрос этому пользователю!",
                reply_markup=None  # Важно: убираем инлайн-клавиатуру
            )
            # Отправляем главное меню как новое сообщение
            show_main_menu(update, context)
            return

        cursor.execute('''
            INSERT INTO invites (from_user_id, to_user_id)
            VALUES (?, ?)
        ''', (user_id, to_user_id))
        conn.commit()

        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        inviter = cursor.fetchone()

        invite_text = f"""
        🎉 Тебе пришло приглашение!
        🎮 Игра: {inviter[2]}
        👤 Никнейм: {inviter[1]}
        🏆 Ранг: {inviter[3]}
        📝 Описание: {inviter[4]}
        """
        keyboard = [
            [
                InlineKeyboardButton("Принять", callback_data=f'accept_{user_id}'),
                InlineKeyboardButton("Отклонить", callback_data=f'decline_{user_id}')
            ],
            [InlineKeyboardButton("Главное меню", callback_data='main_menu')]
        ]

        context.bot.send_message(
            chat_id=to_user_id,
            text=invite_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        # Убираем клавиатуру из текущего сообщения
        query.edit_message_text(
            "✅ Запрос отправлен!",
            reply_markup=None  # Важно: убираем инлайн-клавиатуру
        )
        # Отправляем главное меню как новое сообщение
        show_main_menu(update, context)

    elif data.startswith('accept_'):
        from_user_id = int(data.split('_')[1])
        cursor.execute('''
            UPDATE invites SET status = 'accepted'
            WHERE from_user_id = ? AND to_user_id = ?
        ''', (from_user_id, user_id))
        conn.commit()

        cursor.execute('SELECT * FROM users WHERE user_id IN (?, ?)', (from_user_id, user_id))
        users = {row[0]: row for row in cursor.fetchall()}

        for u_id in [from_user_id, user_id]:
            partner_id = user_id if u_id == from_user_id else from_user_id
            partner_username = users[partner_id][1]
            if partner_username:
                link = f"https://t.me/{partner_username}"
                text = f"🎉 Взаимный инвайт! Свяжись с партнером: {link}"
            else:
                text = f"🎉 Взаимный инвайт! Партнер не имеет username. ID для связи: {partner_id}"

            context.bot.send_message(
                chat_id=u_id,
                text=text,
                reply_markup=main_menu_markup()
            )

        # Убираем клавиатуру из текущего сообщения
        query.edit_message_text(
            "✅ Вы приняли запрос!",
            reply_markup=None  # Важно: убираем инлайн-клавиатуру
        )
        # Отправляем главное меню как новое сообщение
        show_main_menu(update, context)

    elif data.startswith('decline_'):
        from_user_id = int(data.split('_')[1])
        cursor.execute('''
            UPDATE invites SET status = 'rejected'
            WHERE from_user_id = ? AND to_user_id = ?
        ''', (from_user_id, user_id))
        conn.commit()
        # Убираем клавиатуру из текущего сообщения
        query.edit_message_text(
            "❌ Вы отклонили запрос.",
            reply_markup=None  # Важно: убираем инлайн-клавиатуру
        )
        # Отправляем главное меню как новое сообщение
        show_main_menu(update, context)

    query.answer()


def edit_game(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    context.user_data['editing'] = True
    query.message.reply_text(
        "Введите новую игру:",
        reply_markup=main_menu_markup()
    )
    return GAME


def edit_rank(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    context.user_data['editing'] = True
    query.message.reply_text(
        "Введите новый ранг:",
        reply_markup=main_menu_markup()
    )
    return RANK


def edit_description(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    context.user_data['editing'] = True
    query.message.reply_text(
        "Введите новое описание:",
        reply_markup=main_menu_markup()
    )
    return DESCRIPTION


def main() -> None:
    updater = Updater("8196066669:AAHuIaa6zdac51tCUf4zwlw282vj-_SzPac")
    dispatcher = updater.dispatcher

    # Обработчик главного меню должен быть первым
    dispatcher.add_handler(MessageHandler(Filters.regex(f'^{MAIN_MENU_BUTTON}$'), main_menu_handler))
    dispatcher.add_handler(CommandHandler('start', start))

    # ConversationHandler для создания профиля
    create_profile_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(create_profile, pattern='^create_profile$')],
        states={
            NICKNAME: [
                MessageHandler(Filters.text & ~Filters.command, nickname),
                MessageHandler(Filters.regex(f'^{MAIN_MENU_BUTTON}$'), main_menu_handler)
            ],
            GAME: [
                MessageHandler(Filters.text & ~Filters.command, game),
                MessageHandler(Filters.regex(f'^{MAIN_MENU_BUTTON}$'), main_menu_handler)
            ],
            RANK: [
                MessageHandler(Filters.text & ~Filters.command, rank),
                MessageHandler(Filters.regex(f'^{MAIN_MENU_BUTTON}$'), main_menu_handler)
            ],
            DESCRIPTION: [
                MessageHandler(Filters.text & ~Filters.command, description),
                MessageHandler(Filters.regex(f'^{MAIN_MENU_BUTTON}$'), main_menu_handler)
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            MessageHandler(Filters.regex(f'^{MAIN_MENU_BUTTON}$'), main_menu_handler),
            CommandHandler('start', start)
        ]
    )

    # ConversationHandler для редактирования профиля
    edit_profile_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(edit_game, pattern='^change_game$'),
            CallbackQueryHandler(edit_rank, pattern='^change_rank$'),
            CallbackQueryHandler(edit_description, pattern='^change_description$')
        ],
        states={
            GAME: [
                MessageHandler(Filters.text & ~Filters.command, game),
                MessageHandler(Filters.regex(f'^{MAIN_MENU_BUTTON}$'), main_menu_handler)
            ],
            RANK: [
                MessageHandler(Filters.text & ~Filters.command, rank),
                MessageHandler(Filters.regex(f'^{MAIN_MENU_BUTTON}$'), main_menu_handler)
            ],
            DESCRIPTION: [
                MessageHandler(Filters.text & ~Filters.command, description),
                MessageHandler(Filters.regex(f'^{MAIN_MENU_BUTTON}$'), main_menu_handler)
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            MessageHandler(Filters.regex(f'^{MAIN_MENU_BUTTON}$'), main_menu_handler),
            CommandHandler('start', start)
        ]
    )

    dispatcher.add_handler(create_profile_handler)
    dispatcher.add_handler(edit_profile_handler)
    dispatcher.add_handler(CallbackQueryHandler(button_handler))

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()