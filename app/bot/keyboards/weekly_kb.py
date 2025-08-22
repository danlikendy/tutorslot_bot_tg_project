from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

WD = [("Пн", 0), ("Вт", 1), ("Ср", 2), ("Чт", 3), ("Пт", 4)]
TIMES = ["15:00", "17:00", "19:00"]

def weekdays_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=f"wkday:{i}")] for t, i in WD]
    )

def times_kb_for_weekday(weekday: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=f"wktime:{weekday}:{t}")] for t in TIMES]
    )