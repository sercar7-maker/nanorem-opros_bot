import logging
import os
import json
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from pricing import calculate_treatment_cost  # расчёт материалов и цены

load_dotenv()

logging.basicConfig(level=logging.INFO)

def _clean_int(env_value: str, default: str) -> int:
    if not env_value:
        env_value = default
    if "=" in env_value:
        env_value = env_value.split("=", 1)[1]
    return int(env_value)

# Читаем настройки из .env / переменных окружения
ADMIN_CHAT_ID = _clean_int(os.getenv("ADMIN_CHAT_ID"), "0")

# Показывать ли цены клиенту в ответе бота
SHOW_PRICE_TO_CLIENT = os.getenv("SHOW_PRICE_TO_CLIENT", "false").lower() == "true"


# ===== Состояния диалога =====
(
    AGGREGATE,
    OVERHEAT,
    REPAIR,
    OIL_CONSUMPTION,
    SMOKE,
    ENGINE_VOLUME,
    CYLINDERS,
    OIL_VOLUME,
    VEHICLE_INFO,
    CLIENT_NAME,
    CLIENT_CONTACT,
    RESTART,
) = range(12)


# ===== /start =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(">>> Вызван /start от пользователя %s", update.effective_user.id)
    context.user_data.clear()

    keyboard = [
        ["Двигатель"],
        ["МКПП"],
        ["АКПП"],
        ["Редуктор (мост)"],
        ["ГУР"],
    ]

    await update.message.reply_text(
        "Здравствуйте!\n"
        "Я виртуальный помощник Петя по авто-продукции NANOREM.\n"
        "Сначала выберите агрегат, для которого хотите рассмотреть обработку NANOREM.\n\n"
        "Выберите агрегат:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )

    return AGGREGATE


# ===== /clean =====
async def clean(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Данные очищены. Начнём заново.\n\nВведите /start",
        reply_markup=ReplyKeyboardRemove(),
    )


# ===== Выбор агрегата =====
async def aggregate_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    context.user_data["aggregate"] = choice

    engine_keyboard = [
        ["Нет"],
        ["Был кратковременный"],
        ["Да, серьёзно"],
        ["Не знаю"],
    ]
    other_keyboard = [
        ["Нет"],
        ["Кратковременно"],
        ["Да, долго"],
        ["Не знаю"],
    ]
    aggregate_keyboard = [
        ["Двигатель"],
        ["МКПП"],
        ["АКПП"],
        ["Редуктор (мост)"],
        ["ГУР"],
    ]

    if choice == "Двигатель":
        await update.message.reply_text(
            "Задам несколько вопросов, чтобы понять, подходит ли обработка двигателя NANOREM.\n\n"
            "Перегревался ли двигатель?",
            reply_markup=ReplyKeyboardMarkup(
                engine_keyboard,
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return OVERHEAT

    if choice in ["МКПП", "АКПП", "Редуктор (мост)", "ГУР"]:
        await update.message.reply_text(
            "Задам несколько вопросов, чтобы понять, подходит ли обработка NANOREM "
            "для выбранного агрегата.\n\n"
            "Ездили ли вы без масла или с очень низким уровнем масла в этом агрегате?",
            reply_markup=ReplyKeyboardMarkup(
                other_keyboard,
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return OVERHEAT

    # Некорректный выбор агрегата
    await update.message.reply_text(
        "Пожалуйста, выберите один из вариантов на клавиатуре.",
        reply_markup=ReplyKeyboardMarkup(
            aggregate_keyboard,
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    return AGGREGATE


# ===== Перегрев / езда без масла =====
async def overheat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    aggregate = context.user_data.get("aggregate", "Двигатель")
    answer = update.message.text

    if aggregate == "Двигатель":
        valid_options_engine = ["Нет", "Был кратковременный", "Да, серьёзно", "Не знаю"]
        engine_keyboard = [
            ["Нет"],
            ["Был кратковременный"],
            ["Да, серьёзно"],
            ["Не знаю"],
        ]

        if answer not in valid_options_engine:
            await update.message.reply_text(
                "Пожалуйста, выберите один из вариантов на клавиатуре.",
                reply_markup=ReplyKeyboardMarkup(
                    engine_keyboard,
                    resize_keyboard=True,
                    one_time_keyboard=True,
                ),
            )
            return OVERHEAT

        context.user_data["overheat"] = answer

        if answer == "Нет":
            # Сразу переходим к расходу масла
            oil_keyboard = [
                ["До 0.5 л / 1000 км"],
                ["0.5–1 л / 1000 км"],
                ["Более 1 л / 1000 км"],
            ]
            await update.message.reply_text(
                "Какой расход масла?",
                reply_markup=ReplyKeyboardMarkup(
                    oil_keyboard,
                    resize_keyboard=True,
                    one_time_keyboard=True,
                ),
            )
            return OIL_CONSUMPTION

        # Если перегрев был — спрашиваем про ремонт
        repair_keyboard = [
            ["Нет"],
            ["Частичный ремонт"],
            ["Капитальный ремонт"],
            ["Не знаю"],
        ]
        await update.message.reply_text(
            "После перегрева двигатель ремонтировался?",
            reply_markup=ReplyKeyboardMarkup(
                repair_keyboard,
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return REPAIR

    # Для остальных агрегатов — вопрос про езду без масла
    valid_options_no_oil = ["Нет", "Кратковременно", "Да, долго", "Не знаю"]
    other_keyboard = [
        ["Нет"],
        ["Кратковременно"],
        ["Да, долго"],
        ["Не знаю"],
    ]

    if answer not in valid_options_no_oil:
        await update.message.reply_text(
            "Пожалуйста, выберите один из вариантов на клавиатуре.",
            reply_markup=ReplyKeyboardMarkup(
                other_keyboard,
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return OVERHEAT

    context.user_data["no_oil"] = answer

    symptoms_keyboard = [
        ["Нет"],
        ["Незначительные"],
        ["Сильные"],
        ["Не знаю"],
    ]
    await update.message.reply_text(
        "Есть ли посторонние шумы, вибрации или рывки в работе этого агрегата?",
        reply_markup=ReplyKeyboardMarkup(
            symptoms_keyboard,
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    return REPAIR


# ===== Ремонт / симптомы =====
async def repair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    aggregate = context.user_data.get("aggregate", "Двигатель")
    answer = update.message.text

    if aggregate == "Двигатель":
        valid_options_engine = ["Нет", "Частичный ремонт", "Капитальный ремонт", "Не знаю"]
        repair_keyboard = [
            ["Нет"],
            ["Частичный ремонт"],
            ["Капитальный ремонт"],
            ["Не знаю"],
        ]

        if answer not in valid_options_engine:
            await update.message.reply_text(
                "Пожалуйста, выберите один из вариантов на клавиатуре.",
                reply_markup=ReplyKeyboardMarkup(
                    repair_keyboard,
                    resize_keyboard=True,
                    one_time_keyboard=True,
                ),
            )
            return REPAIR

        context.user_data["repair"] = answer

        oil_keyboard = [
            ["До 0.5 л / 1000 км"],
            ["0.5–1 л / 1000 км"],
            ["Более 1 л / 1000 км"],
        ]
        await update.message.reply_text(
            "Какой расход масла?",
            reply_markup=ReplyKeyboardMarkup(
                oil_keyboard,
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return OIL_CONSUMPTION

    # Остальные агрегаты: симптомы
    valid_options_symptoms = ["Нет", "Незначительные", "Сильные", "Не знаю"]
    symptoms_keyboard = [
        ["Нет"],
        ["Незначительные"],
        ["Сильные"],
        ["Не знаю"],
    ]

    if answer not in valid_options_symptoms:
        await update.message.reply_text(
            "Пожалуйста, выберите один из вариантов на клавиатуре.",
            reply_markup=ReplyKeyboardMarkup(
                symptoms_keyboard,
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
    valid_options = [
        "До 0.5 л / 1000 км",
        "0.5–1 л / 1000 км",
        "Более 1 л / 1000 км",
    ]
    oil_keyboard = [
        ["До 0.5 л / 1000 км"],
        ["0.5–1 л / 1000 км"],
        ["Более 1 л / 1000 км"],
    ]

    if answer not in valid_options:
        await update.message.reply_text(
            "Пожалуйста, выберите один из вариантов на клавиатуре.",
            reply_markup=ReplyKeyboardMarkup(
                oil_keyboard,
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return OIL_CONSUMPTION

    context.user_data["oil_consumption"] = answer

    smoke_keyboard = [
        ["Нет"],
        ["Синий"],
        ["Белый"],
        ["Чёрный"],
    ]
    await update.message.reply_text(
        "Есть ли дым из выхлопной трубы?",
        reply_markup=ReplyKeyboardMarkup(
            smoke_keyboard,
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    return SMOKE


# ===== Дым =====
async def smoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.message.text
    valid_options = ["Нет", "Синий", "Белый", "Чёрный"]
    smoke_keyboard = [
        ["Нет"],
        ["Синий"],
        ["Белый"],
        ["Чёрный"],
    ]

    if answer not in valid_options:
        await update.message.reply_text(
            "Пожалуйста, выберите один из вариантов на клавиатуре.",
            reply_markup=ReplyKeyboardMarkup(
                smoke_keyboard,
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
        # Диапазон под себя, пример: 0.6–20.0
        if engine_volume_value < 0.6 or engine_volume_value > 20.0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "Пожалуйста, введите корректный объём двигателя в литрах, например: 1.6\n"
            "Допустимый диапазон: от 0.6 до 100.0 л."
        )
        return ENGINE_VOLUME

    context.user_data["engine_volume"] = engine_volume_value

    aggregate = context.user_data.get("aggregate", "Двигатель")
    if aggregate == "Двигатель":
        await update.message.reply_text(
            "Укажите количество цилиндров в двигателе (например: 4)"
        )
        return CYLINDERS

    # Для других агрегатов сразу переходим к объёму масла
    await update.message.reply_text(
        "Укажите объём масла в агрегате (например: 4)"
    )
    return OIL_VOLUME


# ===== Количество цилиндров =====
async def cylinders_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if not text.isdigit():
        await update.message.reply_text(
            "Пожалуйста, введите количество цилиндров цифрой, например: 4"
        )
        return CYLINDERS

    cylinders = int(text)

    # Допустимый диапазон, подправь под себя
    if cylinders < 2 or cylinders > 16:
        await update.message.reply_text(
            "Пожалуйста, введите реалистичное количество цилиндров (от 2 до 20)."
        )
        return CYLINDERS

    context.user_data["cylinders"] = cylinders

    await update.message.reply_text(
        "Укажите объём масла в двигателе (например: 4)"
    )
    return OIL_VOLUME




# ===== Объём масла + расчёт =====
async def oil_volume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(",", ".")
    aggregate = context.user_data.get("aggregate", "Двигатель")

    try:
        oil_volume_value = float(text)

        if aggregate == "Двигатель":
            if oil_volume_value < 2.0 or oil_volume_value > 70.0:
                raise ValueError
        else:
            if oil_volume_value < 0.3 or oil_volume_value > 100.0:
                raise ValueError

    except ValueError:
        if aggregate == "Двигатель":
            await update.message.reply_text(
                "Пожалуйста, введите корректный объём масла в двигателе, например: 4\n"
                "Допустимый диапазон: от 2 до 70 л."
            )
        else:
            await update.message.reply_text(
                "Пожалуйста, введите корректный объём масла в агрегате, например: 4\n"
                "Допустимый диапазон: от 0.3 до 100 л."
            )
        return OIL_VOLUME

    context.user_data["oil_volume"] = oil_volume_value

    engine_volume_value = context.user_data.get("engine_volume")
    cylinders = context.user_data.get("cylinders")

    logging.info(
        "DEBUG before calc: aggregate=%s, engine_volume=%s, oil_volume=%s, cylinders=%s",
        aggregate,
        engine_volume_value,
        oil_volume_value,
        cylinders,
    )

    try:
        (
            rvs_ml,
            accel_ml,
            material_cost,
            material_price_client,
            work_cost,
            total_price_client,
            profit,
        ) = calculate_treatment_cost(
            aggregate=aggregate,
            engine_volume=engine_volume_value,
            oil_volume=oil_volume_value,
            cylinders=cylinders,
        )

        context.user_data["rvs_ml"] = rvs_ml
        context.user_data["accel_ml"] = accel_ml
        context.user_data["material_cost"] = material_cost
        context.user_data["material_price_client"] = material_price_client
        context.user_data["work_cost"] = work_cost
        context.user_data["total_price_client"] = total_price_client
        context.user_data["profit"] = profit

        logging.info(
            "Расчёт обработки %s: объем двигателя=%s, масло=%s, цилиндров=%s, РВС=%.1f, ускоритель=%.1f, себестоимость=%.2f, цена=%.2f, прибыль=%.2f",
            aggregate,
            engine_volume_value,
            oil_volume_value,
            cylinders,
            rvs_ml,
            accel_ml,
            material_cost,
            total_price_client,
            profit,
        )

    except Exception as e:
        logging.error(f"Ошибка при расчёте стоимости: {e}")

    await update.message.reply_text(
        "Укажите марку и модель вашего транспортного средства (например: Toyota Camry 2.4)."
    )
    return VEHICLE_INFO




# ===== Марка и модель ТС =====
async def vehicle_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = update.message.text.strip()
    if len(info) < 2:
        await update.message.reply_text(
            "Пожалуйста, укажите марку и модель полностью, например: MAN TGS 18.440."
        )
        return VEHICLE_INFO

    context.user_data["vehicle_info"] = info

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


# ===== Контакт клиента, заключение, сохранение, уведомление админу =====
async def client_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.text.strip()

    # убираем всё, что не цифра
    phone_digits = re.sub(r"\D", "", contact)
    is_phone = len(phone_digits) >= 10  # пропускаем любые нормальные номера
    is_username = contact.startswith("@") and len(contact) >= 5

    if not (is_phone or is_username):
        await update.message.reply_text(
            "Пожалуйста, укажите номер телефона или @username для связи."
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
    material_cost = context.user_data.get("material_cost")
    material_price_client = context.user_data.get("material_price_client")
    work_cost = context.user_data.get("work_cost")
    total_price_client = context.user_data.get("total_price_client")
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

    # Клиенту — только заключение (согласно SHOW_PRICE_TO_CLIENT=false)
    # Если позже захочешь показывать цену — здесь можно будет условно добавить блок с ценами
    await update.message.reply_text(text)

    # ===== Сохранение заявки в файл =====
    printable_quote = None  # одна переменная и для файла, и для карточки

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
            "material_cost": material_cost,
            "material_price_client": material_price_client,
            "work_cost": work_cost,
            "total_price_client": total_price_client,
            "profit": profit,
            "vehicle_info": context.user_data.get("vehicle_info"),
        }

        # Текст для клиента (для печати/копирования)
        if (
            material_price_client is not None
            and work_cost is not None
            and total_price_client is not None
        ):
            printable_quote = (
                "Предварительный расчёт стоимости обработки NANOREM:\n\n"
                f"Материалы: {material_price_client:.2f} руб.\n"
                f"Работа: {work_cost:.2f} руб.\n"
                f"ИТОГО: {total_price_client:.2f} руб.\n\n"
                "Расчёт предварительный, окончательная стоимость может быть скорректирована "
                "по результатам диагностики и осмотра."
            )
            application_data["printable_quote"] = printable_quote


        filename = applications_dir / f"application_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(application_data, f, ensure_ascii=False, indent=2)

    except Exception as e:
        logging.error(f"Ошибка при сохранении заявки: {e}")

    # ===== Отправка карточки администратору =====
    if ADMIN_CHAT_ID:
        vehicle_info = context.user_data.get("vehicle_info")

        card_lines = [
            "📝 Новая заявка от клиента",
            "",
            f"👤 Ф.И.О.: {client_name_value or '-'}",
            f"📞 Контакт: {client_contact_value or '-'}",
            f"🔧 Агрегат: {aggregate}",
        ]

        if vehicle_info:
            card_lines.append(f"🚗 ТС: {vehicle_info}")

        card_lines.append("")

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

        # Блок материалов и финансов
        if rvs_ml is not None or accel_ml is not None:
            card_lines.append("")
            card_lines.append("🧪 Материалы:")
            if rvs_ml is not None:
                card_lines.append(f" • РВС: {rvs_ml:.1f} мл")
            if accel_ml is not None:
                card_lines.append(f" • Ускоритель: {accel_ml:.1f} мл")

        if (
            material_cost is not None
            and material_price_client is not None
            and work_cost is not None
            and total_price_client is not None
            and profit is not None
        ):
            card_lines.append("")
            card_lines.append("💰 Финансы:")
            card_lines.append(f" • Себестоимость материалов: {material_cost:.2f} руб.")
            card_lines.append(
                f" • Цена материалов для клиента: {material_price_client:.2f} руб."
            )
            card_lines.append(f" • Работа: {work_cost:.2f} руб.")
            card_lines.append(
                f" • ИТОГО для клиента: {total_price_client:.2f} руб."
            )
            card_lines.append(f" • Чистая прибыль: {profit:.2f} руб.")

        if printable_quote:
            card_lines.append("")
            card_lines.append("📄 Текст для клиента:")
            card_lines.append(printable_quote)

        card_text = "\n".join(card_lines)

        try:
            reply_markup = None
            if is_phone:
                normalized_digits = phone_digits
                if len(normalized_digits) == 11 and normalized_digits.startswith("8"):
                    normalized_digits = "7" + normalized_digits[1:]
                elif len(normalized_digits) == 10:
                    normalized_digits = "7" + normalized_digits

                tel_url = f"tel:+{normalized_digits}"
                reply_markup = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("📞 Позвонить клиенту", url=tel_url)]]
                )

            try:
                await context.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=card_text,
                    reply_markup=reply_markup,
                )
            except Exception as e:
                if reply_markup is not None:
                    logging.error(
                        "Ошибка при отправке карточки администратору с кнопкой: %s. "
                        "Повторяю отправку без кнопки.",
                        e,
                    )
                    await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=card_text)
                else:
                    raise
        except Exception as e:
            logging.error(f"Ошибка при отправке карточки администратору: {e}")

    # Предложение обработать ещё один агрегат
    restart_keyboard = [
        ["🔄 Выбрать ещё один агрегат"],
        ["❌ Завершить"],
    ]
    await update.message.reply_text(
        "Хотите выбрать обработку ещё одного агрегата?",
        reply_markup=ReplyKeyboardMarkup(
            restart_keyboard,
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )

    return RESTART


# ===== /help =====
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 Помощник Петя по авто-продукции NANOREM\n\n"
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


# ===== Повторный выбор =====
async def restart_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if "Выбрать" in text:
        context.user_data.clear()
        return await start(update, context)

    await update.message.reply_text(
        "Спасибо за обращение! Если понадобится выбор — нажмите /start.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


def _clean_str(env_value: str) -> str:
    if not env_value:
        return ""
    if "=" in env_value:
        env_value = env_value.split("=", 1)[1]
    return env_value.strip()

def main():
    raw_token = os.getenv("BOT_TOKEN")
    token = _clean_str(raw_token)
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
            CYLINDERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, cylinders_handler)],
            OIL_VOLUME: [MessageHandler(filters.TEXT & ~filters.COMMAND, oil_volume)],
            VEHICLE_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, vehicle_info)],
            CLIENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_name)],
            CLIENT_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_contact)],
            RESTART: [MessageHandler(filters.TEXT & ~filters.COMMAND, restart_choice)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
        ],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("clean", clean))
    app.add_handler(CommandHandler("help", help_command))

    logging.info("Бот запущен и готов к работе!")
    app.run_polling()


if __name__ == "__main__":
    main()
