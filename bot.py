import asyncio
import random
import html
import aiohttp
import os

from deep_translator import GoogleTranslator
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

games = {}

categories = {
    "random": None,
    "it": 18,
    "history": 23,
    "sports": 21,
    "fun": 9
}


async def translate_text(text, target_lang="az"):
    try:
        return await asyncio.to_thread(
            GoogleTranslator(source="auto", target=target_lang).translate,
            text
        )
    except Exception:
        return text


async def get_random_question(category_id=None):
    url = "https://opentdb.com/api.php?amount=1&type=multiple"

    if category_id is not None:
        url += f"&category={category_id}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()

    if data.get("response_code") != 0:
        return None

    item = data["results"][0]

    question_en = html.unescape(item["question"])
    correct_en = html.unescape(item["correct_answer"])
    incorrect_en = [html.unescape(ans) for ans in item["incorrect_answers"]]

    # Burada dil seçilir:
    # "az" = Azərbaycan dili
    # "tr" = Türk dili
    target_lang = "az"

    question = await translate_text(question_en, target_lang)
    correct_answer = await translate_text(correct_en, target_lang)

    incorrect_answers = []
    for ans in incorrect_en:
        translated_ans = await translate_text(ans, target_lang)
        incorrect_answers.append(translated_ans)

    options = incorrect_answers + [correct_answer]
    random.shuffle(options)

    return {
        "question": question,
        "options": options,
        "correct_index": options.index(correct_answer),
        "answer": correct_answer
    }


def category_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Random", callback_data="gamecat_random")],
        [InlineKeyboardButton(text="💻 IT / Computer", callback_data="gamecat_it")],
        [InlineKeyboardButton(text="📜 History", callback_data="gamecat_history")],
        [InlineKeyboardButton(text="⚽ Sports", callback_data="gamecat_sports")],
        [InlineKeyboardButton(text="😂 Fun / General", callback_data="gamecat_fun")]
    ])


def question_count_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="10 Questions", callback_data="count_10")],
        [InlineKeyboardButton(text="15 Questions", callback_data="count_15")],
        [InlineKeyboardButton(text="20 Questions", callback_data="count_20")]
    ])


def join_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Join Game", callback_data="join_game")],
        [InlineKeyboardButton(text="🚀 Start Game", callback_data="start_game_now")]
    ])


def format_scoreboard(chat_id):
    game = games.get(chat_id)

    if not game or not game["players"]:
        return "🏆 Hələ heç kim xal yığmayıb."

    sorted_players = sorted(
        game["players"].values(),
        key=lambda player: player["score"],
        reverse=True
    )

    text = "🏆 Scoreboard:\n\n"

    for i, player in enumerate(sorted_players, start=1):
        text += f"{i}. {player['name']} — {player['score']} points\n"

    return text


async def finish_game(chat_id):
    game = games.get(chat_id)

    if not game:
        return

    game["active"] = False

    text = "🏁 Game Finished!\n\n"
    text += format_scoreboard(chat_id)

    await bot.send_message(chat_id, text)


async def send_question(chat_id):
    game = games.get(chat_id)

    if not game or not game["active"]:
        return

    if game["current_number"] > game["question_count"]:
        await finish_game(chat_id)
        return

    q = await get_random_question(game["category_id"])

    if q is None:
        await bot.send_message(chat_id, "Sual tapılmadı. Yenidən cəhd edilir...")
        await asyncio.sleep(1)
        await send_question(chat_id)
        return

    game["current_question"] = q
    game["answers"] = {}

    buttons = []

    for index, option in enumerate(q["options"]):
        buttons.append([
            InlineKeyboardButton(
                text=option,
                callback_data=f"answer|{index}"
            )
        ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await bot.send_message(
        chat_id,
        f"❓ Question {game['current_number']}/{game['question_count']}\n\n"
        f"{q['question']}\n\n"
        f"⏰ Time: 10 seconds",
        reply_markup=keyboard
    )

    asyncio.create_task(question_timer(chat_id, game["current_number"]))


async def question_timer(chat_id, question_number):
    await asyncio.sleep(10)

    game = games.get(chat_id)

    if not game or not game["active"]:
        return

    if game["current_number"] != question_number:
        return

    q = game["current_question"]
    correct_index = q["correct_index"]

    correct_players = []

    for user_id, selected_index in game["answers"].items():
        if selected_index == correct_index:
            game["players"][user_id]["score"] += 10
            correct_players.append(game["players"][user_id]["name"])

    if correct_players:
        names = ", ".join(correct_players)
        text = (
            f"✅ Correct answer: {q['answer']}\n\n"
            f"+10 points: {names}"
        )
    else:
        text = (
            f"❌ Heç kim düzgün cavab vermədi.\n\n"
            f"Correct answer: {q['answer']}"
        )

    await bot.send_message(chat_id, text)

    game["current_number"] += 1

    await asyncio.sleep(2)
    await send_question(chat_id)


@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "🎮 Welcome to QuizRush Bot!\n\n"
        "Qrupda oyun başlatmaq üçün yaz:\n"
        "/startgame\n\n"
        "Xallara baxmaq üçün:\n"
        "/score\n\n"
        "Oyunu bitirmək üçün:\n"
        "/endgame"
    )


@dp.message(Command("startgame"))
async def startgame(message: types.Message):
    chat_id = message.chat.id

    if chat_id in games and games[chat_id].get("active"):
        await message.answer("⚠️ Bu qrupda oyun artıq davam edir.")
        return

    games[chat_id] = {
        "active": False,
        "players": {},
        "category_id": None,
        "question_count": None,
        "current_number": 1,
        "current_question": None,
        "answers": {}
    }

    await message.answer(
        "🎮 Yeni oyun yaradıldı!\n\n"
        "Əvvəlcə kateqoriya seç:",
        reply_markup=category_keyboard()
    )


@dp.callback_query(lambda c: c.data.startswith("gamecat_"))
async def choose_category(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    category_name = callback.data.replace("gamecat_", "")

    if chat_id not in games:
        await callback.message.answer("Əvvəl /startgame yaz 🙂")
        await callback.answer()
        return

    games[chat_id]["category_id"] = categories.get(category_name)

    await callback.message.answer(
        "✅ Kateqoriya seçildi.\n\n"
        "İndi sual sayını seç:",
        reply_markup=question_count_keyboard()
    )

    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("count_"))
async def choose_question_count(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    count = int(callback.data.replace("count_", ""))

    if chat_id not in games:
        await callback.message.answer("Əvvəl /startgame yaz 🙂")
        await callback.answer()
        return

    games[chat_id]["question_count"] = count

    await callback.message.answer(
        f"✅ {count} suallıq oyun seçildi.\n\n"
        "İndi hamı Join Game düyməsinə bassın.\n"
        "Hamı qoşulandan sonra Start Game basın.",
        reply_markup=join_keyboard()
    )

    await callback.answer()


@dp.callback_query(lambda c: c.data == "join_game")
async def join_game(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    user_name = callback.from_user.first_name

    if chat_id not in games:
        await callback.answer("Əvvəl oyun başladılmalıdır.", show_alert=True)
        return

    if games[chat_id]["active"]:
        await callback.answer("Oyun artıq başlayıb.", show_alert=True)
        return

    games[chat_id]["players"][user_id] = {
        "name": user_name,
        "score": 0
    }

    await callback.answer("Oyuna qoşuldun ✅", show_alert=True)


@dp.callback_query(lambda c: c.data == "start_game_now")
async def start_game_now(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id

    if chat_id not in games:
        await callback.message.answer("Əvvəl /startgame yaz 🙂")
        await callback.answer()
        return

    game = games[chat_id]

    if game["question_count"] is None:
        await callback.message.answer("Əvvəl sual sayını seç 🙂")
        await callback.answer()
        return

    if not game["players"]:
        await callback.message.answer("Əvvəl oyunçular Join Game bassın 🙂")
        await callback.answer()
        return

    game["active"] = True
    game["current_number"] = 1

    await callback.message.answer(
        "🚀 Game started!\n\n"
        f"❓ Questions: {game['question_count']}\n"
        "⏰ Each question: 10 seconds\n"
        "✅ Every correct player gets +10 points"
    )

    await send_question(chat_id)

    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("answer|"))
async def answer(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    if chat_id not in games or not games[chat_id]["active"]:
        await callback.answer("Aktiv oyun yoxdur.", show_alert=True)
        return

    game = games[chat_id]

    if user_id not in game["players"]:
        await callback.answer("Əvvəl Join Game bas 🙂", show_alert=True)
        return

    if user_id in game["answers"]:
        await callback.answer("Bu suala artıq cavab vermisən 🙂", show_alert=True)
        return

    selected_index = int(callback.data.split("|")[1])
    game["answers"][user_id] = selected_index

    await callback.answer("Cavabın qəbul edildi ✅", show_alert=True)


@dp.message(Command("score"))
async def score(message: types.Message):
    chat_id = message.chat.id
    await message.answer(format_scoreboard(chat_id))


@dp.message(Command("endgame"))
async def endgame(message: types.Message):
    chat_id = message.chat.id

    if chat_id not in games or not games[chat_id].get("active"):
        await message.answer("Aktiv oyun yoxdur.")
        return

    await finish_game(chat_id)


async def main():
    print("Bot is running...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
