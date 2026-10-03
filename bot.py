import asyncio
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from dotenv import load_dotenv

import database
import parser
import worker  # Connect the parser for login verification

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class Registration(StatesGroup):
    waiting_for_login = State()
    waiting_for_password = State()

class OrderShift(StatesGroup):
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_type = State()
    waiting_for_force = State()  # NEW

# --- Helper function to validate credentials via Selenium ---
def verify_credentials_sync(login, password):
    """This function launches the browser and tries to log in. Returns True/False."""
    driver = parser.setup_driver()
    try:
        return parser.login(driver, login, password)
    except Exception as e:
        print(f"Login error: {e}")
        return False
    finally:
        driver.quit()

# ================= REGISTRATION =================
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await message.answer(
        "👋 Welcome to Shift Parser Bot!\n"
        "To start using the bot, please provide your portal credentials.\n\n"
        "Please enter your login (email):"
    )
    await state.set_state(Registration.waiting_for_login)

@dp.message(Registration.waiting_for_login)
async def process_login(message: types.Message, state: FSMContext):
    await state.update_data(login=message.text)
    await message.answer("🔒 Great. Now enter your password:")
    await state.set_state(Registration.waiting_for_password)

@dp.message(Registration.waiting_for_password)
async def process_password(message: types.Message, state: FSMContext):
    login = (await state.get_data())['login']
    password = message.text
    telegram_id = message.from_user.id
    
    # Send a placeholder message because verification takes time
    loading_msg = await message.answer("🔄 Checking your credentials on the portal. Please wait a few seconds...")
    
    # Run Selenium in a separate thread so the bot stays responsive
    is_valid = await asyncio.to_thread(verify_credentials_sync, login, password)
    
    if is_valid:
        database.add_user(telegram_id, login, password)
        await loading_msg.edit_text(
            "✅ Registration successful!\n\n"
            "Use /order to schedule a shift\n"
            "Use /myshifts to manage active orders\n"
            "Use /settings to configure timeouts"
        )
        await state.clear()
    else:
        await loading_msg.edit_text(
            "❌ Login failed. Please check your credentials or try again later.\n\n"
            "Please send your password again:"
        )
        # Keep the state waiting for the password again

# ================= SHIFT ORDER =================
@dp.message(Command("order"))
async def cmd_order(message: types.Message, state: FSMContext):
    if not database.user_exists(message.from_user.id):
        await message.answer("❌ You are not registered. Please use /start first.")
        return

    await message.answer(
        "📅 Please enter the date you want to work\n"
        "Format: DD.MM.YYYY (e.g., 03.08.2026):"
    )
    await state.set_state(OrderShift.waiting_for_date)

@dp.message(OrderShift.waiting_for_date)
async def process_date(message: types.Message, state: FSMContext):
    try:
        valid_date = datetime.strptime(message.text, "%d.%m.%Y").date()
        if valid_date < datetime.now().date():
            await message.answer("❌ The date cannot be in the past. Please enter a valid date (DD.MM.YYYY):")
            return
    except ValueError:
        await message.answer("❌ Invalid format! Please use strictly DD.MM.YYYY (e.g., 03.08.2026):")
        return

    await state.update_data(date=message.text)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌅 Morning (06:00 - 14:00)", callback_data="time_06-14")],
        [InlineKeyboardButton(text="🌇 Afternoon (14:00 - 22:00)", callback_data="time_14-22")],
        [InlineKeyboardButton(text="🌃 Night (22:00 - 06:00)", callback_data="time_22-06")],
        [InlineKeyboardButton(text="♾️ Any shift on this day", callback_data="time_ANY")]
    ])
    
    await message.answer("⏱ Please select the preferred shift time:", reply_markup=keyboard)
    await state.set_state(OrderShift.waiting_for_time)

# --- Replace the process_time function ---
@dp.callback_query(OrderShift.waiting_for_time)
async def process_time(call: CallbackQuery, state: FSMContext):
    time_type = call.data.split('_')[1] 
    await state.update_data(time_type=time_type)  # Save the time and continue
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 IMPORT", callback_data="type_IMPORT")],
        [InlineKeyboardButton(text="📤 EXPORT", callback_data="type_EXPORT")],
        [InlineKeyboardButton(text="♾️ ANY (Import/Export)", callback_data="type_ANY")]
    ])
    
    await call.message.edit_text("🏗 Please select the shift type:", reply_markup=keyboard)
    await state.set_state(OrderShift.waiting_for_type)

# --- Add the new process_type function ---
@dp.callback_query(OrderShift.waiting_for_type)
async def process_type(call: CallbackQuery, state: FSMContext):
    shift_type = call.data.split('_')[1] 
    await state.update_data(shift_type=shift_type)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 YES, Force Booking", callback_data="force_1")],
        [InlineKeyboardButton(text="✅ NO, Standard Booking", callback_data="force_0")],
        [InlineKeyboardButton(text="🔔 ONLY NOTIFY (Don't book)", callback_data="force_2")]  # <-- New button
    ])
    
    await call.message.edit_text(
        "⚠️ **Booking Mode?**\n\n"
        "• **Force:** Cancels conflicting shifts automatically.\n"
        "• **Standard:** Books only if there are no conflicts.\n"
        "• **Notify:** Doesn't book, just sends you a message.",
        reply_markup=keyboard, parse_mode="Markdown"
    )
    await state.set_state(OrderShift.waiting_for_force)

@dp.callback_query(OrderShift.waiting_for_force)
async def process_force(call: CallbackQuery, state: FSMContext):
    force_booking = int(call.data.split('_')[1])
    
    data = await state.get_data()
    target_date = data['date']
    time_type = data['time_type']
    shift_type = data['shift_type']
    
    database.add_shift_request(call.from_user.id, target_date, time_type, shift_type, force_booking)
    
    modes = {
        0: "✅ Standard (No conflict override)",
        1: "🚀 Force (Will cancel conflicts)",
        2: "🔔 Notify Only (No booking)"
    }
    
    await call.message.edit_text(
        f"✅ Request saved successfully!\n\n"
        f"📅 Date: {target_date}\n"
        f"⏱ Time: {time_type}\n"
        f"🏗 Type: {shift_type}\n"
        f"⚙️ Mode: {modes.get(force_booking)}\n\n"
        f"Use /myshifts to manage."
    )
    await state.clear()
    await call.answer()

# ================= MY SHIFTS (CANCEL) =================
# ================= MY SHIFTS (CANCEL) =================
@dp.message(Command("myshifts"))
async def cmd_myshifts(message: types.Message):
    if not database.user_exists(message.from_user.id):
        await message.answer("❌ You are not registered. Please use /start first.")
        return

    requests = database.get_active_requests(message.from_user.id)
    
    if not requests:
        await message.answer("📭 You don't have any active shift requests.")
        return
        
    modes = {
        0: "Standard",
        1: "Force",
        2: "Notify Only"
    }
        
    for req in requests:
        # Unpack all 5 values returned by the database
        req_id, date, time_type, shift_type, force_booking = req
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel Monitoring", callback_data=f"cancel_{req_id}")]
        ])
        
        mode_text = modes.get(force_booking, "Unknown")
        
        await message.answer(
            f"🔍 **Monitoring:** {date}\n"
            f"⏱ Time: {time_type}\n"
            f"🏗 Type: {shift_type}\n"
            f"⚙️ Mode: {mode_text}", 
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

@dp.callback_query(lambda c: c.data.startswith('cancel_'))
async def process_cancel(call: CallbackQuery):
    req_id = int(call.data.split('_')[1])
    database.delete_request(req_id, call.from_user.id)
    await call.message.edit_text("🛑 Monitoring cancelled for this shift.")
    await call.answer()

# ================= SETTINGS (TIMEOUT) =================
@dp.message(Command("settings"))
async def cmd_settings(message: types.Message):
    if not database.user_exists(message.from_user.id):
        await message.answer("❌ You are not registered. Please use /start first.")
        return

    current_timeout = database.get_user_timeout(message.from_user.id)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 Hour", callback_data="timeout_1"),
         InlineKeyboardButton(text="2 Hours", callback_data="timeout_2")],
        [InlineKeyboardButton(text="4 Hours", callback_data="timeout_4"),
         InlineKeyboardButton(text="8 Hours", callback_data="timeout_8")],
        [InlineKeyboardButton(text="24 Hours", callback_data="timeout_24")]
    ])
    
    await message.answer(
        f"⚙️ **Settings**\n\n"
        f"Stop monitoring shifts if less than: **{current_timeout} hours** left before it starts.\n"
        f"Select a new timeout below:", 
        reply_markup=keyboard, parse_mode="Markdown"
    )

@dp.callback_query(lambda c: c.data.startswith('timeout_'))
async def process_timeout(call: CallbackQuery):
    hours = int(call.data.split('_')[1])
    database.update_timeout(call.from_user.id, hours)
    
    await call.message.edit_text(
        f"✅ Settings updated!\n\n"
        f"Bot will stop looking for shifts {hours} hours before they start."
    )
    await call.answer()


# ================= NOTIFICATION TEMPLATES =================
async def notify_shift_booked(telegram_id: int, date: str, time_type: str):
    """This function will be called from the parser when a shift is booked."""
    await bot.send_message(
        telegram_id, 
        f"🎉 **SUCCESS!**\n\nI successfully booked a shift for you!\n📅 Date: {date}\n⏱ Type: {time_type}",
        parse_mode="Markdown"
    )

async def notify_monitoring_stopped(telegram_id: int, date: str, time_type: str, hours: int):
    """This function will be called when the waiting timeout expires."""
    await bot.send_message(
        telegram_id, 
        f"⚠️ **Monitoring Stopped**\n\n"
        f"Could not find the shift for {date} ({time_type}).\n"
        f"Stopped because there is less than {hours} hours left before it starts.",
        parse_mode="Markdown"
    )

async def notify_error(telegram_id: int, error_msg: str):
    """Send parser error notifications."""
    await bot.send_message(
        telegram_id, 
        f"⚠️ **Parser Alert**\n\n{error_msg}",
        parse_mode="Markdown"
    )


# === ADD THIS AT THE VERY END OF THE FILE (before async def main) ===
async def notify_shift_found(telegram_id: int, date: str, time_type: str):
    """Notification for Notify Only mode."""
    await bot.send_message(
        telegram_id, 
        f"🔔 **SHIFT FOUND!**\n\n"
        f"The shift you requested is now available on the portal!\n"
        f"📅 Date: {date}\n"
        f"⏱ Type: {time_type}\n\n"
        f"_I did not book it, because you selected 'Notify Only'._",
        parse_mode="Markdown"
    )


async def main():
    database.init_db()
    print("Bot is running...")

    # Start the background monitoring loop alongside the bot
    asyncio.create_task(worker.start_monitoring(bot))
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())