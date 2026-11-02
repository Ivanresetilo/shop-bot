import logging

from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import db
from config import ADMIN_ID, BOT_TOKEN, PAYMENT_DETAILS, SHOP_NAME

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())


class AddProduct(StatesGroup):
    name = State()
    description = State()
    price = State()


class AddStock(StatesGroup):
    product = State()
    content = State()


def is_admin(user_id):
    return user_id == ADMIN_ID


def catalog_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    for p in db.list_products():
        cnt = p["cnt"]
        label = f'{p["name"]} — {p["price"]}₽' + ("" if cnt else " (нет в наличии)")
        kb.add(InlineKeyboardButton(label, callback_data=f"product:{p['id']}"))
    if not kb.inline_keyboard:
        return None
    return kb


@dp.message_handler(commands=["start"])
async def cmd_start(m: types.Message):
    kb = catalog_kb()
    text = f"<b>{SHOP_NAME}</b>\n\nВыберите товар:"
    if kb:
        await m.answer(text, reply_markup=kb)
    else:
        await m.answer(text + "\n\nПока товаров нет — загляните позже.")


@dp.callback_query_handler(lambda c: c.data.startswith("product:"))
async def show_product(call: types.CallbackQuery):
    pid = int(call.data.split(":")[1])
    p = db.get_product(pid)
    if not p or not p["active"]:
        await call.answer("Товар недоступен", show_alert=True)
        return
    cnt = db.stock_count(pid)
    kb = InlineKeyboardMarkup()
    if cnt > 0:
        kb.add(InlineKeyboardButton("Купить", callback_data=f"buy:{pid}"))
    kb.add(InlineKeyboardButton("← Назад", callback_data="back"))
    desc = f"\n\n{p['description']}" if p["description"] else ""
    await call.message.edit_text(
        f"<b>{p['name']}</b> — {p['price']}₽{desc}\n\nВ наличии: {cnt} шт.",
        reply_markup=kb,
    )


@dp.callback_query_handler(lambda c: c.data == "back")
async def back(call: types.CallbackQuery):
    kb = catalog_kb()
    if kb:
        await call.message.edit_text("Выберите товар:", reply_markup=kb)
    else:
        await call.message.edit_text("Пока товаров нет.")


@dp.callback_query_handler(lambda c: c.data.startswith("buy:"))
async def buy(call: types.CallbackQuery):
    pid = int(call.data.split(":")[1])
    p = db.get_product(pid)
    if not p or db.stock_count(pid) == 0:
        await call.answer("Нет в наличии", show_alert=True)
        return
    oid = db.create_order(call.from_user.id, call.from_user.username or "", pid)
    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("Я оплатил(а) ✅", callback_data=f"paid:{oid}")
    )
    await call.message.edit_text(
        f"<b>Заказ №{oid}</b>: {p['name']} — {p['price']}₽\n\n"
        f"Оплатите по реквизитам:\n{PAYMENT_DETAILS}\n\n"
        "Затем нажмите кнопку ниже и пришлите чек/скриншот оплаты сообщением.",
        reply_markup=kb,
    )


@dp.callback_query_handler(lambda c: c.data.startswith("paid:"))
async def paid(call: types.CallbackQuery):
    oid = int(call.data.split(":")[1])
    order = db.get_order(oid)
    if not order or order["user_id"] != call.from_user.id:
        await call.answer("Заказ не найден", show_alert=True)
        return
    if order["status"] != "pending":
        await call.answer("Заказ уже обработан", show_alert=True)
        return
    await call.message.edit_text(
        "Пришлите скриншот или текст чека оплаты одним сообщением — админ проверит и товар придёт автоматически."
    )
    dp.current_state(chat=call.message.chat.id, user=call.from_user.id).update_data(
        awaiting_receipt=oid
    )


@dp.callback_query_handler(lambda c: c.data.startswith(("approve:", "reject:")), user_id=ADMIN_ID)
async def moderate(call: types.CallbackQuery):
    action, oid = call.data.split(":")
    oid = int(oid)
    order = db.get_order(oid)
    if not order or order["status"] != "pending":
        await call.answer("Уже обработан", show_alert=True)
        return
    if action == "approve":
        item = db.take_item(order["product_id"], oid)
        if not item:
            await call.answer("Нет товара на складе!", show_alert=True)
            return
        db.set_order_status(oid, "done")
        p = db.get_product(order["product_id"])
        await bot.send_message(
            order["user_id"],
            f"✅ Оплата подтверждена! Ваш товар «{p['name']}»:\n\n<code>{item}</code>",
        )
        await call.message.edit_reply_markup()
        await call.message.reply(f"Заказ №{oid} выдан ✅")
    else:
        db.set_order_status(oid, "rejected")
        await bot.send_message(order["user_id"], "❌ Оплата не подтверждена. Свяжитесь с продавцом.")
        await call.message.edit_reply_markup()
        await call.message.reply(f"Заказ №{oid} отклонён")


# ---------- Админка ----------


@dp.message_handler(commands=["admin"])
async def admin(m: types.Message):
    if not is_admin(m.from_user.id):
        return
    s = db.stats()
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("➕ Добавить товар", callback_data="adm:add"),
        InlineKeyboardButton("📦 Пополнить склад", callback_data="adm:stock"),
        InlineKeyboardButton("🗑 Убрать товар", callback_data="adm:remove"),
        InlineKeyboardButton("🕒 Заказы в ожидании", callback_data="adm:orders"),
    )
    await m.answer(
        f"<b>Админ-панель</b>\nПродано: {s['sold']} шт. на {s['revenue']}₽",
        reply_markup=kb,
    )


@dp.callback_query_handler(lambda c: c.data == "adm:add", user_id=ADMIN_ID)
async def adm_add(call: types.CallbackQuery):
    await AddProduct.name.set()
    await call.message.answer("Название товара:")


@dp.message_handler(state=AddProduct.name)
async def ap_name(m: types.Message, state: FSMContext):
    await state.update_data(name=m.text)
    await AddProduct.next()
    await m.answer("Описание (или «-»):")


@dp.message_handler(state=AddProduct.description)
async def ap_desc(m: types.Message, state: FSMContext):
    await state.update_data(description="" if m.text.strip() == "-" else m.text)
    await AddProduct.next()
    await m.answer("Цена в рублях (число):")


@dp.message_handler(state=AddProduct.price)
async def ap_price(m: types.Message, state: FSMContext):
    if not m.text.isdigit():
        await m.answer("Нужно число, например 499:")
        return
    d = await state.get_data()
    pid = db.add_product(d["name"], d["description"], int(m.text))
    await state.finish()
    await m.answer(f"Товар «{d['name']}» добавлен (id {pid}). Теперь пополни склад: /admin → 📦")


@dp.callback_query_handler(lambda c: c.data == "adm:stock", user_id=ADMIN_ID)
async def adm_stock(call: types.CallbackQuery):
    products = db.list_products()
    if not products:
        await call.answer("Сначала добавьте товар", show_alert=True)
        return
    kb = InlineKeyboardMarkup(row_width=1)
    for p in products:
        kb.add(InlineKeyboardButton(f"{p['name']} ({p['cnt']} шт.)", callback_data=f"stockfor:{p['id']}"))
    await call.message.answer("К какому товару пополнить склад?", reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data.startswith("stockfor:"), user_id=ADMIN_ID)
async def stock_for(call: types.CallbackQuery, state: FSMContext):
    pid = int(call.data.split(":")[1])
    await AddStock.content.set()
    await state.update_data(product_id=pid)
    await call.message.answer(
        "Отправьте товары — каждый с новой строки (ключи, аккаунты, ссылки и т.д.):"
    )


@dp.message_handler(state=AddStock.content)
async def stock_content(m: types.Message, state: FSMContext):
    d = await state.get_data()
    lines = [x.strip() for x in m.text.split("\n") if x.strip()]
    for line in lines:
        db.add_stock(d["product_id"], line)
    await state.finish()
    await m.answer(f"Добавлено {len(lines)} шт. на склад.")


@dp.callback_query_handler(lambda c: c.data == "adm:remove", user_id=ADMIN_ID)
async def adm_remove(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(row_width=1)
    for p in db.list_products():
        kb.add(InlineKeyboardButton(f"❌ {p['name']}", callback_data=f"del:{p['id']}"))
    await call.message.answer("Что убрать?", reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data.startswith("del:"), user_id=ADMIN_ID)
async def adm_del(call: types.CallbackQuery):
    db.deactivate_product(int(call.data.split(":")[1]))
    await call.message.edit_text("Товар убран из каталога.")


@dp.callback_query_handler(lambda c: c.data == "adm:orders", user_id=ADMIN_ID)
async def adm_orders(call: types.CallbackQuery):
    rows = db.pending_orders()
    if not rows:
        await call.message.answer("Ожидающих заказов нет.")
        return
    for o in rows:
        await call.message.answer(
            f"№{o['id']} — {o['product_name']} — @{o['username']} (id {o['user_id']})"
        )


# Универсальный хендлер — строго последним: ловит чек оплаты либо подсказывает /start
@dp.message_handler(content_types=types.ContentTypes.ANY)
async def receipt(m: types.Message):
    state = dp.current_state(chat=m.chat.id, user=m.from_user.id)
    data = await state.get_data()
    oid = data.get("awaiting_receipt")
    if not oid:
        await m.answer("Чтобы выбрать товар — /start")
        return
    order = db.get_order(oid)
    if not order or order["status"] != "pending":
        await m.answer("Этот заказ уже обработан.")
        await state.update_data(awaiting_receipt=None)
        return
    # Пересылаем чек админу с кнопками подтверждения
    p = db.get_product(order["product_id"])
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Выдать товар", callback_data=f"approve:{oid}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject:{oid}"),
    )
    await bot.send_message(
        ADMIN_ID,
        f"💰 Заказ №{oid}: «{p['name']}» — {p['price']}₽\n"
        f"Покупатель: @{order['username']} (id {order['user_id']})\nЧек ниже:",
        reply_markup=kb,
    )
    await bot.forward_message(ADMIN_ID, m.chat.id, m.message_id)
    await state.update_data(awaiting_receipt=None)
    await m.answer("Чек отправлен на проверку. Товар придёт сюда после подтверждения оплаты.")


if __name__ == "__main__":
    db.init_db()
    executor.start_polling(dp, skip_updates=True)
