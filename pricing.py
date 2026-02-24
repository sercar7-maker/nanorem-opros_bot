import os
import logging


def _clean_number(env_value: str, default: str) -> float:
    if not env_value:
        env_value = default
    if "=" in env_value:
        env_value = env_value.split("=", 1)[1]
    return float(env_value)


# Цена материалов за мл (можно переопределить в .env)
RVS_PRICE_PER_ML = _clean_number(os.getenv("RVS_PRICE_PER_ML"), "70")
ACCEL_PRICE_PER_ML = _clean_number(os.getenv("ACCEL_PRICE_PER_ML"), "30")
MARKUP_COEF = _clean_number(os.getenv("MARKUP_COEF"), "2.0")
SHOW_PRICE_TO_CLIENT = os.getenv("SHOW_PRICE_TO_CLIENT", "false").lower() == "true"

# Дозировки по умолчанию (если не заданы во внешней среде)
RVS_DOSE_ML_PER_L_ENGINE = _clean_number(os.getenv("RVS_DOSE_ML_PER_L_ENGINE"), "10")
ACCEL_DOSE_ML_PER_L_OIL = _clean_number(os.getenv("ACCEL_DOSE_ML_PER_L_OIL"), "5")

# Базовая работа
BASE_WORK_COST = {
    "Двигатель": 3000,   # база без учёта цилиндров
    "МКПП": 5000,
    "АКПП": 6000,
    "Вариатор": 6500,
    "ГУР": 3000,
}

WORK_PER_CYL = 1000  # выкрутить свечу + 2 компрессометра + АГЦ

HEAVY_ENGINE_THRESHOLD_L = 8.0
HEAVY_ENGINE_COEF = 1.5


def calculate_treatment_cost(aggregate, engine_volume=None, oil_volume=None, cylinders=None):
    """
    Возвращает:
    rvs_ml,
    accel_ml,
    material_cost,
    material_price_client,
    work_cost,
    total_price_client,
    profit
    """

    logging.info(
        "DEBUG in calc: aggregate=%s, engine_volume=%s, oil_volume=%s, cylinders=%s",
        aggregate,
        engine_volume,
        oil_volume,
        cylinders,
    )

    logging.info(
        "DEBUG pricing env: RVS_PRICE_PER_ML=%s, ACCEL_PRICE_PER_ML=%s, MARKUP_COEF=%s, "
        "RVS_DOSE_ML_PER_L_ENGINE=%s, ACCEL_DOSE_ML_PER_L_OIL=%s",
        os.getenv("RVS_PRICE_PER_ML"),
        os.getenv("ACCEL_PRICE_PER_ML"),
        os.getenv("MARKUP_COEF"),
        os.getenv("RVS_DOSE_ML_PER_L_ENGINE"),
        os.getenv("ACCEL_DOSE_ML_PER_L_OIL"),
    )

    # --- Материалы ---
    rvs_ml = 0.0
    accel_ml = 0.0

    if aggregate == "Двигатель" and engine_volume and oil_volume:
        # Двигатель: дозировка от объёма двигателя и масла
        rvs_ml = engine_volume * RVS_DOSE_ML_PER_L_ENGINE
        accel_ml = oil_volume * ACCEL_DOSE_ML_PER_L_OIL
    elif oil_volume:
        # Остальные агрегаты: упрощённая схема от объёма масла
        rvs_ml = oil_volume * 5
        accel_ml = oil_volume * 2.5

    material_cost = rvs_ml * RVS_PRICE_PER_ML + accel_ml * ACCEL_PRICE_PER_ML

    # --- Работа ---
    base_work = BASE_WORK_COST.get(aggregate, 0)

    if aggregate == "Двигатель":
        cyl = cylinders or 4

        if cyl == 2:
            work_cost = 3000
        else:
            work_cost = base_work + WORK_PER_CYL * cyl
    else:
        work_cost = base_work

    if aggregate == "Двигатель" and engine_volume and engine_volume >= HEAVY_ENGINE_THRESHOLD_L:
        work_cost *= HEAVY_ENGINE_COEF

    # --- Итог ---
    material_price_client = material_cost * MARKUP_COEF
    total_price_client = material_price_client + work_cost
    profit = total_price_client - (material_cost + work_cost)

    return (
        rvs_ml,
        accel_ml,
        material_cost,
        material_price_client,
        work_cost,
        total_price_client,
        profit,
    )
