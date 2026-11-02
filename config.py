import os

# Токен бота от @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_ТОКЕН_СЮДА")

# Telegram ID админа (узнать: @userinfobot)
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Реквизиты для оплаты — показываются покупателю
PAYMENT_DETAILS = os.getenv(
    "PAYMENT_DETAILS",
    "Карта: 0000 0000 0000 0000 (Имя Получателя)\nПосле оплаты пришлите чек/скриншот сюда.",
)

SHOP_NAME = os.getenv("SHOP_NAME", "Магазин цифровых товаров")
DB_PATH = os.getenv("DB_PATH", "shop.db")
