import logging
import os
import json
import re
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)


# Стоимость обработки за 1 литр (в условных единицах/рублях) — базовая ставка,
# может использоваться для агрегатов, для которых нет детализированных дозировок.
MATERIAL_PRICE_PER_LITER = 1000.0

# ID администратора/владельца бота, куда будет отправляться карточка клиента.
# Сейчас здесь указан ваш Telegram ID.
ADMIN_CHAT_ID = 899738024

# Дозировки для обработки двигателя NANOREM
RVS_DOSE_ML_PER_L_ENGINE = 10.0     # РВС: 10 мл на 1 литр рабочего объёма двигателя
ACCEL_DOSE_ML_PER_L_OIL = 2.5       # Ускоритель: 2.5 мл на 1 литр масла

# Стоимость материалов и наценка (загружаются из .env)
RVS_PRICE_PER_ML = float(os.getenv("RVS_PRICE_PER_ML", "0.8"))      # Себестоимость РВС за 1 мл
ACCEL_PRICE_PER_ML = float(os.getenv("ACCEL_PRICE_PER_ML", "0.6")) # Себестоимость ускорителя за 1 мл
MARKUP_COEF = float(os.getenv("MARKUP_COEF", "2.0"))                # Коэффициент наценки для клиентской цены

# Коэффициенты для разных агрегатов (можно править под свою экономику)
AGGREGATE_COEFFICIENTS = {
    "Двигатель": 1.0,
    "МКПП": 1.1,
    "АКПП": 1.2,
    "Вариатор": 1.3,
    "ГУР": 0.8,
}


def calculate_treatment_cost(aggregate, engine_volume, oil_volume):
    """
    Возвращает:
    rvs_ml,
    accel_ml,
    cost_raw (себестоимость),
    client_price (цена клиенту),
    profit
    """

    if aggregate == "Двигатель" and engine_volume is not None and oil_volume is not None:
        rvs_ml = engine_volume * RVS_DOSE_ML_PER_L_ENGINE
        accel_ml = oil_volume * ACCEL_DOSE_ML_PER_L_OIL
    else:
        if oil_volume is not None:
            rvs_ml = oil_volume * 5
            accel_ml = oil_volume * 2.5
        else:
            rvs_ml = 0
            accel_ml = 0

    cost_rvs = rvs_ml * RVS_PRICE_PER_ML
    cost_accel = accel_ml * ACCEL_PRICE_PER_ML
    cost_raw = cost_rvs + cost_accel

    client_price = cost_raw * MARKUP_COEF
    profit = client_price - cost_raw

    return rvs_ml, accel_ml, cost_raw, client_price, profit



import logging
import os
import json
import re
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)

# Стоимость обработки за 1 литр (базовая ставка)
MATERIAL_PRICE_PER_LITER = 1000.0

# ID администратора
ADMIN_CHAT_ID = 899738024

# Дозировки
RVS_DOSE_ML_PER_L_ENGINE = 10.0
ACCEL_DOSE_ML_PER_L_OIL = 2.5

# Цены и наценка (из .env)
RVS_PRICE_PER_ML = float(os.getenv("RVS_PRICE_PER_ML", "0.8"))
ACCEL_PRICE_PER_ML = float(os.getenv("ACCEL_PRICE_PER_ML", "0.6"))
MARKUP_COEF = float(os.getenv("MARKUP_COEF", "2.0"))

AGGREGATE_COEFFICIENTS = {
    "Двигатель": 1.0,
    "МКПП": 1.1,
    "АКПП": 1.2,
    "Вариатор": 1.3,
    "ГУР": 0.8,
}


def calculate_treatment_cost(aggregate, engine_volume, oil_volume):
    if aggregate == "Двигатель" and engine_volume is not None and oil_volume is not None:
        rvs_ml = engine_volume * RVS_DOSE_ML_PER_L_ENGINE
        accel_ml = oil_volume * ACCEL_DOSE_ML_PER_L_OIL
    else:
        if oil_volume is not None:
            rvs_ml = oil_volume * 5
            accel_ml = oil_volume * 2.5
        else:
            rvs_ml = 0
            accel_ml = 0

    cost_rvs = rvs_ml * RVS_PRICE_PER_ML
    cost_accel = accel_ml * ACCEL_PRICE_PER_ML
    cost_raw = cost_rvs + cost_accel

    client_price = cost_raw * MARKUP_COEF
    profit = client_price - cost_raw

    return rvs_ml, accel_ml, cost_raw, client_price, profit


# ===== Состояния диалога =====
(
    AGGREGATE,
    OVERHEAT,
    REPAIR,
    OIL_CONSUMPTION,
    SMOKE,
    ENGINE_VOLUME,
    OIL_VOLUME,
    CLIENT_NAME,
    CLIENT_CONTACT,
) = range(9)


# ===== /start =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(">>> Вызван /start от пользователя %s", update.effective_user.id)
    context.user_data.clear()

    await update.message.reply_text(
        "Здравствуйте!\n"
        "Я виртуальный помощник Петя по авто-продукции NANOREM.\n"
        "Сначала выберите агрегат, для которого хотите рассмотреть обработку NANOREM.\n\n"
        "Выберите агрегат:",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["Двигатель"],
                ["МКПП"],
                ["АКПП"],
                ["Вариатор"],
                ["ГУР"],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    return AGGREGATE


# ===== /clean =====
async def clean(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    await update.message.reply_text(
        "Данные очищены. Начнём заново.\n\nВведите /start"
    )


# ===== Выбор агрегата =====
async def aggregate_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    context.user_data["aggregate"] = choice

    if choice == "Двигатель":
        await update.message.reply_text(
            "Задам несколько вопросов, чтобы понять, подходит ли обработка двигателя NANOREM.\n\n"
            "Перегревался ли двигатель?",
            reply_markup=ReplyKeyboardMarkup(
                [
                    ["Нет"],
                    ["Был кратковременный"],
                    ["Да, серьёзно"],
                    ["Не знаю"],
                ],
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return OVERHEAT

    if choice in ["МКПП", "АКПП", "Вариатор", "ГУР"]:
        await update.message.reply_text(
            "Задам несколько вопросов, чтобы понять, подходит ли обработка NANOREM "
            "для выбранного агрегата.\n\n"
            "Ездили ли вы без масла или с очень низким уровнем масла в этом агрегате?",
            reply_markup=ReplyKeyboardMarkup(
                [
                    ["Нет"],
                    ["Кратковременно"],
                    ["Да, долго"],
                    ["Не знаю"],
                ],
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return OVERHEAT

    await update.message.reply_text(
        "Пожалуйста, выберите один из вариантов на клавиатуре.",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["Двигатель"],
                ["МКПП"],
                ["АКПП"],
                ["Вариатор"],
                ["ГУР"],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    return AGGREGATE


# ===== Перегрев =====
async def overheat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    aggregate = context.user_data.get("aggregate", "Двигатель")
    answer = update.message.text

    if aggregate == "Двигатель":
        valid_options_engine = ["Нет", "Был кратковременный", "Да, серьёзно", "Не знаю"]

        if answer not in valid_options_engine:
            await update.message.reply_text(
                "Пожалуйста, выберите один из вариантов на клавиатуре.",
                reply_markup=ReplyKeyboardMarkup(
                    [
                        ["Нет"],
                        ["Был кратковременный"],
                        ["Да, серьёзно"],
                        ["Не знаю"],
                    ],
                    resize_keyboard=True,
                    one_time_keyboard=True,
                ),
            )
            return OVERHEAT

        context.user_data["overheat"] = answer

        if answer == "Нет":
            await update.message.reply_text(
                "Какой расход масла?",
                reply_markup=ReplyKeyboardMarkup(
                    [
                        ["До 0.5 л / 1000 км"],
                        ["0.5–1 л / 1000 км"],
                        ["Более 1 л / 1000 км"],
                    ],
                    resize_keyboard=True,
                    one_time_keyboard=True,
                ),
            )
            return OIL_CONSUMPTION

        await update.message.reply_text(
            "После перегрева двигатель ремонтировался?",
            reply_markup=ReplyKeyboardMarkup(
                [
                    ["Нет"],
                    ["Частичный ремонт"],
                    ["Капитальный ремонт"],
                    ["Не знаю"],
                ],
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return REPAIR

    valid_options_no_oil = ["Нет", "Кратковременно", "Да, долго", "Не знаю"]

    if answer not in valid_options_no_oil:
        await update.message.reply_text(
            "Пожалуйста, выберите один из вариантов на клавиатуре.",
            reply_markup=ReplyKeyboardMarkup(
                [
                    ["Нет"],
                    ["Кратковременно"],
                    ["Да, долго"],
                    ["Не знаю"],
                ],
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return OVERHEAT

    context.user_data["no_oil"] = answer

    await update.message.reply_text(
        "Есть ли посторонние шумы, вибрации или рывки в работе этого агрегата?",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["Нет"],
                ["Незначительные"],
                ["Сильные"],
                ["Не знаю"],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    return REPAIR


# ===== Ремонт =====
async def repair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    aggregate = context.user_data.get("aggregate", "Двигатель")
    answer = update.message.text

    if aggregate == "Двигатель":
        valid_options_engine = ["Нет", "Частичный ремонт", "Капитальный ремонт", "Не знаю"]

        if answer not in valid_options_engine:
            await update.message.reply_text(
                "Пожалуйста, выберите один из вариантов на клавиатуре.",
                reply_markup=ReplyKeyboardMarkup(
                    [
                        ["Нет"],
                        ["Частичный ремонт"],
                        ["Капитальный ремонт"],
                        ["Не знаю"],
                    ],
                    resize_keyboard=True,
                    one_time_keyboard=True,
                ),
            )
            return REPAIR

        context.user_data["repair"] = answer

        await update.message.reply_text(
            "Какой расход масла?",
            reply_markup=ReplyKeyboardMarkup(
                [
                    ["До 0.5 л / 1000 км"],
                    ["0.5–1 л / 1000 км"],
                    ["Более 1 л / 1000 км"],
                ],
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return OIL_CONSUMPTION

    valid_options_symptoms = ["Нет", "Незначительные", "Сильные", "Не знаю"]

    if answer not in valid_options_symptoms:
        await update.message.reply_text(
            "Пожалуйста, выберите один из вариантов на клавиатуре.",
            reply_markup=ReplyKeyboardMarkup(
                [
                    ["Нет"],
                    ["Незначительные"],
                    ["Сильные"],
                    ["Не знаю"],
                ],
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return REPAIR

    context.user_data["symptoms"] = answer

    await update.message.reply_text(
        "Укажите объём масла в агрегате (например: 4)",
        reply_markup=ReplyKeyboardRemove(),
    )
    return OIL_VOLUME


# ===== Расход масла =====
async def oil_consumption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.message.text
    valid_options = ["До 0.5 л / 1000 км", "0.5–1 л / 1000 км", "Более 1 л / 1000 км"]

    if answer not in valid_options:
        await update.message.reply_text(
            "Пожалуйста, выберите один из вариантов на клавиатуре.",
            reply_markup=ReplyKeyboardMarkup(
                [
                    ["До 0.5 л / 1000 км"],
                    ["0.5–1 л / 1000 км"],
                    ["Более 1 л / 1000 км"],
                ],
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return OIL_CONSUMPTION

    context.user_data["oil_consumption"] = answer

    await update.message.reply_text(
        "Есть ли дым из выхлопной трубы?",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["Нет"],
                ["Синий"],
                ["Белый"],
                ["Чёрный"],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    return SMOKE


# ===== Дым =====
async def smoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.message.text
    valid_options = ["Нет", "Синий", "Белый", "Чёрный"]

    if answer not in valid_options:
        await update.message.reply_text(
            "Пожалуйста, выберите один из вариантов на клавиатуре.",
            reply_markup=ReplyKeyboardMarkup(
                [
                    ["Нет"],
                    ["Синий"],
                    ["Белый"],
                    ["Чёрный"],
                ],
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return SMOKE

    context.user_data["smoke"] = answer

    await update.message.reply_text(
        "Укажите объём двигателя в литрах (например: 1.6)",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ENGINE_VOLUME


# ===== Объём двигателя =====
async def engine_volume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(",", ".")
    try:
        engine_volume_value = float(text)
        if engine_volume_value <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "Пожалуйста, введите корректный объём двигателя в литрах, например: 1.6"
        )
        return ENGINE_VOLUME

    context.user_data["engine_volume"] = engine_volume_value

    await update.message.reply_text(
        "Укажите объём масла в двигателе (например: 4)"
    )
    return OIL_VOLUME


# ===== Объём масла =====
async def oil_volume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(",", ".")
    try:
        oil_volume_value = float(text)
        if oil_volume_value <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "Пожалуйста, введите корректный объём масла в литрах, например: 4"
        )
        return OIL_VOLUME

    context.user_data["oil_volume"] = oil_volume_value

    aggregate = context.user_data.get("aggregate", "Двигатель")
    engine_volume_value = context.user_data.get("engine_volume")

    try:
        if aggregate == "Двигатель" and engine_volume_value is not None and oil_volume_value is not None:
            rvs_ml = engine_volume_value * RVS_DOSE_ML_PER_L_ENGINE
            accel_ml = oil_volume_value * ACCEL_DOSE_ML_PER_L_OIL
        else:
            if oil_volume_value is not None:
                rvs_ml = oil_volume_value * 5
                accel_ml = oil_volume_value * 2.5
            else:
                rvs_ml = 0
                accel_ml = 0

        cost_rvs = rvs_ml * RVS_PRICE_PER_ML
        cost_accel = accel_ml * ACCEL_PRICE_PER_ML
        cost_raw = cost_rvs + cost_accel
        client_price = cost_raw * MARKUP_COEF
        profit = client_price - cost_raw

        context.user_data["rvs_ml"] = rvs_ml
        context.user_data["accel_ml"] = accel_ml
        context.user_data["cost_raw"] = cost_raw
        context.user_data["client_price"] = client_price
        context.user_data["profit"] = profit

        print(
            f"Расчёт обработки {aggregate}:\n"
            f"  Объём двигателя: {engine_volume_value}\n"
            f"  Объём масла: {oil_volume_value}\n"
            f"  РВС: {rvs_ml:.1f} мл\n"
            f"  Ускоритель: {accel_ml:.1f} мл\n"
            f"  Себестоимость: {cost_raw:.2f} руб.\n"
            f"  Цена для клиента: {client_price:.2f} руб.\n"
            f"  Прибыль: {profit:.2f} руб."
        )
    except Exception as e:
        logging.error(f"Ошибка при расчёте стоимости: {e}")

    await update.message.reply_text(
        "Спасибо. Теперь укажите, пожалуйста, ваше Ф.И.О."
    )
    return CLIENT_NAME


# ===== Ф.И.О. клиента =====
async def client_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()

    if len(name) < 2:
        await update.message.reply_text(
            "Пожалуйста, укажите ваше полное Ф.И.О. (минимум 2 символа)."
        )
        return CLIENT_NAME

    context.user_data["client_name"] = name

    await update.message.reply_text(
        "Укажите номер телефона или @username в Telegram для связи."
    )
    return CLIENT_CONTACT


# ===== Контакт клиента =====
async def client_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.text.strip()

    phone_digits = re.sub(r"\D", "", contact)

    is_phone = (
        (phone_digits.startswith("7") and len(phone_digits) == 11) or
        (phone_digits.startswith("8") and len(phone_digits) == 11)
    )

    is_username = re.fullmatch(r"@[A-Za-z0-9_]{5,32}", contact) is not None

    if not (is_phone or is_username):
        await update.message.reply_text(
            "Пожалуйста, укажите корректный номер телефона "
            "(пример: +79041234567 или 89041234567) "
            "или корректный @username в Telegram."
        )
        return CLIENT_CONTACT

    context.user_data["client_contact"] = contact

    aggregate = context.user_data.get("aggregate", "Двигатель")

    overheat = context.user_data.get("overheat")
    no_oil = context.user_data.get("no_oil")
    oil = context.user_data.get("oil_consumption")
    smoke = context.user_data.get("smoke")
    symptoms = context.user_data.get("symptoms")

    engine_volume_value = context.user_data.get("engine_volume")
    oil_volume_value = context.user_data.get("oil_volume")
    rvs_ml = context.user_data.get("rvs_ml")
    accel_ml = context.user_data.get("accel_ml")
    cost_raw = context.user_data.get("cost_raw")
    client_price = context.user_data.get("client_price")
    profit = context.user_data.get("profit")
    client_name_value = context.user_data.get("client_name")
    client_contact_value = context.user_data.get("client_contact")

    # Заключение для клиента
    if aggregate == "Двигатель":
        if (
            overheat == "Да, серьёзно"
            and oil == "Более 1 л / 1000 км"
            and smoke == "Синий"
        ):
            conclusion = (
                "⚠️ Заключение:\n\n"
                "По введённым данным применение NANOREM не рекомендуется.\n\n"
                "Рекомендуется предварительная диагностика агрегата."
            )
        else:
            conclusion = (
                "✅ Заключение:\n\n"
                "По предварительным данным применение NANOREM возможно.\n"
                "Рекомендуется консультация специалиста."
            )
    else:
        if no_oil == "Да, долго" and symptoms == "Сильные":
            conclusion = (
                "⚠️ Заключение:\n\n"
                "По введённым данным применение NANOREM не рекомендуется.\n\n"
                "Рекомендуется предварительная диагностика агрегата."
            )
        else:
            conclusion = (
                "✅ Заключение:\n\n"
                "По предварительным данным применение NANOREM возможно.\n"
                "Рекомендуется консультация специалиста."
            )

    text = (
        conclusion
        + f"\n\nВыбранный агрегат: {aggregate}."
        + "\n\nНаш специалист свяжется с вами для уточнения деталей."
    )

    await update.message.reply_text(text)

    # ===== Сохранение заявки в файл =====
    try:
        applications_dir = Path("applications")
        applications_dir.mkdir(exist_ok=True)

        application_data = {
            "timestamp": datetime.now().isoformat(),
            "client_name": client_name_value,
            "client_contact": client_contact_value,
            "aggregate": aggregate,
            "engine_volume": engine_volume_value,
            "oil_volume": oil_volume_value,
            "overheat": overheat,
            "no_oil": no_oil,
            "repair": context.user_data.get("repair"),
            "oil_consumption": oil,
            "smoke": smoke,
            "symptoms": symptoms,
            "rvs_ml": rvs_ml,
            "accel_ml": accel_ml,
            "cost_raw": cost_raw,
            "client_price": client_price,
            "profit": profit,
        }

        filename = applications_dir / f"application_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(application_data, f, ensure_ascii=False, indent=2)

    except Exception as e:
        logging.error(f"Ошибка при сохранении заявки: {e}")

    # ===== Отправка карточки администратору =====
    if ADMIN_CHAT_ID:
        card_lines = [
            "📝 Новая заявка от клиента",
            "",
            f"👤 Ф.И.О.: {client_name_value or '-'}",
            f"📞 Контакт: {client_contact_value or '-'}",
            f"🔧 Агрегат: {aggregate}",
            "",
        ]

        if engine_volume_value is not None:
            card_lines.append(f"⚙️ Объём двигателя: {engine_volume_value} л")
        if oil_volume_value is not None:
            card_lines.append(f"🛢️ Объём масла: {oil_volume_value} л")

        if aggregate == "Двигатель":
            if overheat:
                card_lines.append(f"🌡️ Перегрев: {overheat}")
            if context.user_data.get("repair"):
                card_lines.append(f"🔨 Ремонт: {context.user_data.get('repair')}")
            if oil:
                card_lines.append(f"📊 Расход масла: {oil}")
            if smoke:
                card_lines.append(f"💨 Дым: {smoke}")
        else:
            if no_oil:
                card_lines.append(f"⛽ Езда без масла: {no_oil}")
            if symptoms:
                card_lines.append(f"🔊 Симптомы: {symptoms}")

        # ВСЕГДА добавляем материалы и финансы, если они посчитаны
        if rvs_ml is not None or accel_ml is not None:
            card_lines.append("")
            card_lines.append("🧪 Материалы:")
            if rvs_ml is not None:
                card_lines.append(f"   • РВС: {rvs_ml:.1f} мл")
            if accel_ml is not None:
                card_lines.append(f"   • Ускоритель: {accel_ml:.1f} мл")

        if cost_raw is not None and client_price is not None and profit is not None:
            card_lines.append("")
            card_lines.append("💰 Финансы:")
            card_lines.append(f"   • Себестоимость: {cost_raw:.2f} руб.")
            card_lines.append(f"   • Цена для клиента: {client_price:.2f} руб.")
            card_lines.append(f"   • Прибыль: {profit:.2f} руб.")

        card_text = "\n".join(card_lines)

        try:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=card_text)
        except Exception as e:
            logging.error(f"Ошибка при отправке карточки администратору: {e}")

    # Предложение обработать ещё один агрегат
    await update.message.reply_text(
        "Если хотите рассчитать обработку ещё одного агрегата,\n"
        "нажмите /start."
    )

    print("Функция client_contact завершилась")
    return ConversationHandler.END



# ===== /help =====
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 Помощник по авто-продукции NANOREM\n\n"
        "Я помогу вам определить, подходит ли обработка NANOREM для вашего агрегата.\n\n"
        "📋 Доступные команды:\n"
        "• /start - начать консультацию\n"
        "• /help - показать эту справку\n"
        "• /cancel - прервать текущую консультацию\n\n"
        "Я задам вам несколько вопросов о состоянии агрегата, "
        "после чего дам рекомендацию по применению NANOREM."
    )
    await update.message.reply_text(help_text)


# ===== /cancel =====
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Консультация завершена.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


def main():
    token = os.getenv("BOT_TOKEN")

    if not token:
        logging.error("Токен бота не найден! Установите переменную окружения BOT_TOKEN.")
        return

    app = ApplicationBuilder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            AGGREGATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, aggregate_choice)],
            OVERHEAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, overheat)],
            REPAIR: [MessageHandler(filters.TEXT & ~filters.COMMAND, repair)],
            OIL_CONSUMPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, oil_consumption)],
            SMOKE: [MessageHandler(filters.TEXT & ~filters.COMMAND, smoke)],
            ENGINE_VOLUME: [MessageHandler(filters.TEXT & ~filters.COMMAND, engine_volume)],
            OIL_VOLUME: [MessageHandler(filters.TEXT & ~filters.COMMAND, oil_volume)],
            CLIENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_name)],
            CLIENT_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_contact)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
        ],
        allow_reentry=True,
    )

    app.add_handler(conv)

    # Отдельные команды
    app.add_handler(CommandHandler("clean", clean))
    app.add_handler(CommandHandler("help", help_command))

    logging.info("Бот запущен и готов к работе!")
    app.run_polling()


if __name__ == "__main__":
    main()
