from data_cleaner import to_number


def correlation(first, second):
    pairs = [(a, b) for a, b in zip(first, second) if a is not None and b is not None]
    if len(pairs) < 3:
        return 0
    first_values = [pair[0] for pair in pairs]
    second_values = [pair[1] for pair in pairs]
    first_mean = sum(first_values) / len(first_values)
    second_mean = sum(second_values) / len(second_values)
    numerator = sum((a - first_mean) * (b - second_mean) for a, b in pairs)
    denominator_a = sum((a - first_mean) ** 2 for a in first_values) ** 0.5
    denominator_b = sum((b - second_mean) ** 2 for b in second_values) ** 0.5
    denominator = denominator_a * denominator_b
    return numerator / denominator if denominator else 0


def build_prediction(report):
    target = report.get("target_column")
    if not target:
        return {
            "available": False,
            "message": "No numeric target column was found. Upload a dataset with a numeric outcome column.",
            "model_name": "Not available",
            "predicted_value": None,
            "confidence": "Low",
            "confidence_score": 0,
            "top_factors": [],
            "trend": "Unknown",
        }

    target_values = [
        to_number(row.get(target, ""))
        for row in report.get("rows", [])
    ]
    target_values = [value for value in target_values if value is not None]
    if len(target_values) < 3:
        return {
            "available": False,
            "message": f'The target column "{target}" does not contain enough numeric values.',
            "model_name": "Not available",
            "predicted_value": None,
            "confidence": "Low",
            "confidence_score": 0,
            "top_factors": [],
            "trend": "Unknown",
        }

    recent_count = max(3, len(target_values) // 4)
    historical_average = sum(target_values) / len(target_values)
    recent_average = sum(target_values[-recent_count:]) / recent_count
    early_average = sum(target_values[:recent_count]) / recent_count
    change = recent_average - early_average
    predicted_value = recent_average + change * 0.35

    factors = []
    for column in report.get("numeric_columns", []):
        if column == target:
            continue
        feature_values = []
        outcome_values = []
        for row in report.get("rows", []):
            feature = to_number(row.get(column, ""))
            outcome = to_number(row.get(target, ""))
            if feature is not None and outcome is not None:
                feature_values.append(feature)
                outcome_values.append(outcome)
        strength = correlation(feature_values, outcome_values)
        factors.append({
            "name": column,
            "relationship": round(strength, 3),
            "direction": "Positive" if strength >= 0 else "Negative",
            "importance": round(abs(strength), 3),
        })

    factors.sort(key=lambda item: item["importance"], reverse=True)
    confidence_score = min(95, max(25, int(report.get("quality_score", 0) * 0.65 + min(len(target_values), 50) * 0.7)))
    confidence = "High" if confidence_score >= 75 else "Medium" if confidence_score >= 50 else "Low"
    trend = "Improving" if change > 0.01 else "Declining" if change < -0.01 else "Stable"

    return {
        "available": True,
        "target_column": target,
        "model_name": "Transparent trend baseline",
        "predicted_value": round(predicted_value, 3),
        "historical_average": round(historical_average, 3),
        "recent_average": round(recent_average, 3),
        "change_from_early_period": round(change, 3),
        "confidence": confidence,
        "confidence_score": confidence_score,
        "top_factors": factors[:5],
        "trend": trend,
        "note": "This first version uses an explainable historical-trend baseline. Upgrade it with validated machine-learning models before production use.",
    }
