import os

# Дозировки
RVS_DOSE_ML_PER_L_ENGINE = 10.0
ACCEL_DOSE_ML_PER_L_OIL = 2.5

# Цены (берём из .env)
RVS_PRICE_PER_ML = float(os.getenv("RVS_PRICE_PER_ML", "70"))
ACCEL_PRICE_PER_ML = float(os.getenv("ACCEL_PRICE_PER_ML", "30"))
MARKUP_COEF = float(os.getenv("MARKUP_COEF", "2.0"))

# Базовая работа (подправь под себя)
BASE_WORK_COST = {
    "Двигатель": 3000,   # база без учёта цилиндров
    "МКПП": 5000,
    "АКПП": 6000,
    "Вариатор": 6500,
    "ГУР": 3000,
}

# Стоимость за цилиндр
WORK_PER_CYL = 1000  # выкрутить свечу + 2 компрессометра + АГЦ

# Множитель для тяжёлой техники
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

    # --- Материалы ---
    rvs_ml = 0
    accel_ml = 0

    if aggregate == "Двигатель" and engine_volume and oil_volume:
        rvs_ml = engine_volume * RVS_DOSE_ML_PER_L_ENGINE
        accel_ml = oil_volume * ACCEL_DOSE_ML_PER_L_OIL
    elif oil_volume:
        rvs_ml = oil_volume * 5
        accel_ml = oil_volume * 2.5

    material_cost = rvs_ml * RVS_PRICE_PER_ML + accel_ml * ACCEL_PRICE_PER_ML

    # --- Работа ---
    base_work = BASE_WORK_COST.get(aggregate, 0)

    if aggregate == "Двигатель":
        cyl = cylinders or 4

        # Для 2‑цилиндровых двигателей фиксированная цена работы
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

