# calculator.py

def calculate_treatment_cost(
    aggregate,
    engine_volume,
    oil_volume,
    rvs_price_per_ml,
    accel_price_per_ml,
    markup_coef,
    rvs_dose_engine,
    accel_dose_oil,
):
    if aggregate == "Двигатель" and engine_volume is not None and oil_volume is not None:
        rvs_ml = engine_volume * rvs_dose_engine
        accel_ml = oil_volume * accel_dose_oil
    else:
        if oil_volume is not None:
            rvs_ml = oil_volume * 5
            accel_ml = oil_volume * 2.5
        else:
            rvs_ml = 0
            accel_ml = 0

    cost_rvs = rvs_ml * rvs_price_per_ml
    cost_accel = accel_ml * accel_price_per_ml
    cost_raw = cost_rvs + cost_accel

    client_price = cost_raw * markup_coef
    profit = client_price - cost_raw

    return rvs_ml, accel_ml, cost_raw, client_price, profit
