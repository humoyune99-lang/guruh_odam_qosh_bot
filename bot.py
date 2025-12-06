import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, ChatMemberUpdatedFilter, IS_MEMBER, IS_NOT_MEMBER
from aiogram.types import (
    Message,
    ChatMemberUpdated,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ========================
# KONFIGURATSIYA
# ========================
BOT_TOKEN = "8363504826:AAFNWiFZgXmRIoOmNY0is0n0gPAPPhXao48"
ADMIN_IDS = [7782143104]  # Admin ID'larni bu yerga qo'shing
REQUIRED_INVITES = 5

# ========================
# LOGGING
# ========================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========================
# MA'LUMOTLAR BAZASI (JSON)
# ========================
class Database:
    def __init__(self, filename='bot_data.json'):
        self.filename = filename
        self.data = self.load()
    
    def load(self) -> Dict:
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                'users': {},
                'groups': {},
                'invites': {}
            }
    
    def save(self):
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
    
    def add_user(self, user_id: int, username: str = None):
        user_id_str = str(user_id)
        if user_id_str not in self.data['users']:
            self.data['users'][user_id_str] = {
                'username': username,
                'invites_count': 0,
                'joined_at': datetime.now().isoformat()
            }
            self.save()
    
    def increment_invites(self, user_id: int):
        user_id_str = str(user_id)
        if user_id_str in self.data['users']:
            self.data['users'][user_id_str]['invites_count'] += 1
        else:
            self.data['users'][user_id_str] = {
                'username': None,
                'invites_count': 1,
                'joined_at': datetime.now().isoformat()
            }
        self.save()
    
    def get_user_invites(self, user_id: int) -> int:
        user_id_str = str(user_id)
        return self.data['users'].get(user_id_str, {}).get('invites_count', 0)
    
    def add_group(self, chat_id: int, title: str, invite_link: str = None):
        chat_id_str = str(chat_id)
        if chat_id_str not in self.data['groups']:
            self.data['groups'][chat_id_str] = {
                'title': title,
                'invite_link': invite_link,
                'added_at': datetime.now().isoformat()
            }
            self.save()
    
    def get_all_groups(self) -> Dict:
        return self.data['groups']
    
    def get_statistics(self) -> str:
        stats = "📊 **Statistika**\n\n"
        sorted_users = sorted(
            self.data['users'].items(),
            key=lambda x: x[1].get('invites_count', 0),
            reverse=True
        )
        
        for i, (user_id, data) in enumerate(sorted_users[:10], 1):
            username = data.get('username', 'Noma\'lum')
            invites = data.get('invites_count', 0)
            stats += f"{i}. @{username} — {invites} ta odam qo'shgan\n"
        
        return stats

# ========================
# FSM STATES
# ========================
class BroadcastStates(StatesGroup):
    choosing_group = State()
    entering_message = State()

# ========================
# BOT INITIALIZATION
# ========================
db = Database()
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

# ========================
# INLINE KEYBOARDS
# ========================
def get_main_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📢 Guruhga qo'shilish", callback_data="join_groups")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="statistics")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📢 Guruhga qo'shilish", callback_data="join_groups")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="statistics")],
        [InlineKeyboardButton(text="⚙️ Admin Panel", callback_data="admin_panel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_panel_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📨 Guruhga xabar yuborish", callback_data="broadcast_message")],
        [InlineKeyboardButton(text="📊 To'liq statistika", callback_data="full_stats")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_groups_keyboard() -> InlineKeyboardMarkup:
    groups = db.get_all_groups()
    buttons = []
    
    for chat_id, data in groups.items():
        title = data.get('title', 'Noma\'lum guruh')
        invite_link = data.get('invite_link')
        
        if invite_link:
            buttons.append([InlineKeyboardButton(text=f"👥 {title}", url=invite_link)])
        else:
            buttons.append([InlineKeyboardButton(text=f"👥 {title} (Link yo'q)", callback_data=f"group_{chat_id}")])
    
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_broadcast_groups_keyboard() -> InlineKeyboardMarkup:
    groups = db.get_all_groups()
    buttons = []
    
    for chat_id, data in groups.items():
        title = data.get('title', 'Noma\'lum guruh')
        buttons.append([InlineKeyboardButton(text=f"👥 {title}", callback_data=f"bc_{chat_id}")])
    
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ========================
# COMMAND HANDLERS
# ========================
@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    db.add_user(user_id, username)
    
    welcome_text = (
        "🤖 **Assalomu alaykum!**\n\n"
        "Botga xush kelibsiz! Bu bot guruhlarni monitoring qiladi va "
        "referral tizimini boshqaradi.\n\n"
        "📋 **Imkoniyatlar:**\n"
        "• Guruhlarga qo'shilish\n"
        "• Qo'shgan odamlaringiz sonini ko'rish\n"
        "• Statistikalarni kuzatish\n\n"
        "Quyidagi tugmalardan birini tanlang:"
    )
    
    if user_id in ADMIN_IDS:
        await message.answer(welcome_text, reply_markup=get_admin_keyboard())
    else:
        await message.answer(welcome_text, reply_markup=get_main_keyboard())

@router.message(Command("apanel"))
async def cmd_admin_panel(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Sizda admin huquqi yo'q.")
        return
    
    admin_text = (
        "⚙️ **Admin Panel**\n\n"
        "Quyidagi amallardan birini tanlang:"
    )
    
    await message.answer(admin_text, reply_markup=get_admin_panel_keyboard())

# ========================
# CALLBACK HANDLERS
# ========================
@router.callback_query(F.data == "join_groups")
async def show_groups(callback: CallbackQuery):
    groups = db.get_all_groups()
    
    if not groups:
        await callback.message.edit_text(
            "❌ Hozircha guruhlar mavjud emas.\n\n"
            "**Eslatma:** Bot to'liq ishlashi uchun uni guruhga admin "
            "sifatida qo'shishingiz kerak.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_main")]
            ])
        )
    else:
        await callback.message.edit_text(
            "📢 **Mavjud guruhlar**\n\n"
            "Quyidagi guruhlardan biriga qo'shiling:\n\n"
            "⚠️ **Muhim:** Bot to'liq ishlashi uchun uni guruhga "
            "**admin sifatida qo'shishingiz** kerak. Bu botga yangi "
            "a'zolarni aniqlash va statistikani yuritish imkonini beradi.",
            reply_markup=get_groups_keyboard()
        )
    
    await callback.answer()

@router.callback_query(F.data == "statistics")
async def show_statistics(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_invites = db.get_user_invites(user_id)
    
    stats_text = (
        f"📊 **Sizning statistikangiz**\n\n"
        f"Siz qo'shgan odamlar: **{user_invites}** ta\n"
        f"Yozish uchun kerak: **{max(0, REQUIRED_INVITES - user_invites)}** ta\n\n"
    )
    
    if user_invites >= REQUIRED_INVITES:
        stats_text += "✅ Siz guruhda yozishingiz mumkin!"
    else:
        stats_text += f"⚠️ Yozish uchun yana **{REQUIRED_INVITES - user_invites}** ta odam qo'shing."
    
    await callback.message.edit_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_main")]
        ])
    )
    await callback.answer()

@router.callback_query(F.data == "admin_panel")
async def show_admin_panel(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Sizda admin huquqi yo'q.", show_alert=True)
        return
    
    admin_text = (
        "⚙️ **Admin Panel**\n\n"
        "Quyidagi amallardan birini tanlang:"
    )
    
    await callback.message.edit_text(admin_text, reply_markup=get_admin_panel_keyboard())
    await callback.answer()

@router.callback_query(F.data == "broadcast_message")
async def start_broadcast(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Sizda admin huquqi yo'q.", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📨 **Xabar yuborish**\n\n"
        "Qaysi guruhga xabar yuborishni xohlaysiz?",
        reply_markup=get_broadcast_groups_keyboard()
    )
    await state.set_state(BroadcastStates.choosing_group)
    await callback.answer()

@router.callback_query(F.data.startswith("bc_"))
async def choose_broadcast_group(callback: CallbackQuery, state: FSMContext):
    chat_id = callback.data.replace("bc_", "")
    await state.update_data(target_chat_id=chat_id)
    
    await callback.message.edit_text(
        "✍️ **Xabar matnini yuboring:**\n\n"
        "Guruhga yuboriladigan xabarni kiriting.\n"
        "Bekor qilish uchun /cancel yozing."
    )
    await state.set_state(BroadcastStates.entering_message)
    await callback.answer()

@router.message(BroadcastStates.entering_message)
async def send_broadcast(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await message.answer("❌ Bekor qilindi.")
        await state.clear()
        return
    
    data = await state.get_data()
    target_chat_id = int(data.get('target_chat_id'))
    
    try:
        await bot.send_message(target_chat_id, message.text)
        await message.answer("✅ Xabar muvaffaqiyatli yuborildi!")
    except Exception as e:
        await message.answer(f"❌ Xatolik: {str(e)}")
    
    await state.clear()

@router.callback_query(F.data == "full_stats")
async def show_full_stats(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Sizda admin huquqi yo'q.", show_alert=True)
        return
    
    stats = db.get_statistics()
    await callback.message.edit_text(
        stats,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_panel")]
        ])
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    welcome_text = (
        "🤖 **Asosiy menyu**\n\n"
        "Quyidagi tugmalardan birini tanlang:"
    )
    
    if user_id in ADMIN_IDS:
        await callback.message.edit_text(welcome_text, reply_markup=get_admin_keyboard())
    else:
        await callback.message.edit_text(welcome_text, reply_markup=get_main_keyboard())
    
    await callback.answer()

# ========================
# GROUP EVENT HANDLERS
# ========================
@router.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def on_user_join(event: ChatMemberUpdated):
    """Yangi foydalanuvchi guruhga qo'shilganda"""
    new_member = event.new_chat_member.user
    chat = event.chat
    inviter = event.from_user
    
    # Guruhni bazaga qo'shish
    try:
        invite_link = await bot.export_chat_invite_link(chat.id)
        db.add_group(chat.id, chat.title, invite_link)
    except:
        db.add_group(chat.id, chat.title)
    
    # Yangi foydalanuvchini bazaga qo'shish
    db.add_user(new_member.id, new_member.username)
    
    # Agar kimdir boshqa odamni qo'shgan bo'lsa
    if inviter.id != new_member.id:
        db.increment_invites(inviter.id)
        inviter_count = db.get_user_invites(inviter.id)
        
        # Qo'shgan odamga xabar
        try:
            await bot.send_message(
                inviter.id,
                f"✅ Siz yangi odam qo'shdingiz!\n\n"
                f"Jami qo'shgan odamlaringiz: **{inviter_count}** ta"
            )
        except:
            pass
    
    # Yangi kelgan odamga ogohlantirish
    remaining = max(0, REQUIRED_INVITES - db.get_user_invites(new_member.id))
    
    if remaining > 0:
        await bot.send_message(
            chat.id,
            f"👋 [{new_member.first_name}](tg://user?id={new_member.id}), guruhga xush kelibsiz!\n\n"
            f"⚠️ **Muhim:** Siz bu guruhda yozish uchun kamida **{REQUIRED_INVITES} ta** "
            f"odam qo'shishingiz kerak.\n\n"
            f"Sizning holatingiz: **{remaining} ta** odam qo'shish kerak.",
            parse_mode="Markdown"
        )
    else:
        await bot.send_message(
            chat.id,
            f"👋 [{new_member.first_name}](tg://user?id={new_member.id}), guruhga xush kelibsiz!\n\n"
            f"✅ Siz guruhda erkin yozishingiz mumkin!",
            parse_mode="Markdown"
        )

@router.message(F.chat.type.in_({"group", "supergroup"}))
async def check_message_permission(message: Message):
    """Guruhda yozilgan xabarlarni tekshirish"""
    user_id = message.from_user.id
    
    # Adminlarni tekshirmaydi
    if user_id in ADMIN_IDS:
        return
    
    # Bot o'z xabarlarini tekshirmaydi
    if message.from_user.is_bot:
        return
    
    user_invites = db.get_user_invites(user_id)
    
    if user_invites < REQUIRED_INVITES:
        remaining = REQUIRED_INVITES - user_invites
        await message.reply(
            f"⚠️ **Ogohlantirish!**\n\n"
            f"Siz bu guruhda yozish uchun **{remaining} ta** odam qo'shishingiz kerak.\n"
            f"Hozirgi holatingiz: **{user_invites}/{REQUIRED_INVITES}**",
            parse_mode="Markdown"
        )

# ========================
# MAIN FUNCTION
# ========================
async def main():
    dp.include_router(router)
    
    logger.info("🤖 Bot ishga tushmoqda...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())