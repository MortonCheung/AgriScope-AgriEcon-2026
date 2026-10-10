# forecast_v2

## system

只输出 JSON。使用给定 cutoff 前历史数值预测指定 target，不得加入外部历史记忆或改写事实。
target_type=cycle_market_average 表示周期整体均价；harvest_market_price 表示 target_window 内上市价格均值。
unit=ratio_to_current_price 时所有价格均为相对当前价格的比值，current_price=1，输出必须使用该单位。
confidence 是自报置信，不是校准概率。信息不足必须写 uncertainty。
JSON 必须包含 forecast_horizon, point_forecast, range_low, range_high, direction(up/down/flat),
confidence(0..1), drivers(字符串数组), downside_risks(字符串数组), assumptions(字符串数组), uncertainty, unit,
method 和 context_hash。价格有限且为正，range_low <= point_forecast <= range_high。

## user

METHOD: {method}
CONTEXT_HASH: {context_hash}
UNIT: {unit}
PACKET_JSON:
{packet_json}

严格回显 method={method}，context_hash={context_hash}，forecast_horizon={horizon}，unit={unit}。
