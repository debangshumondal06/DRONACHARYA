def build_recommendations(report, prediction):
    if not prediction.get("available"):
        return []

    target = prediction.get("target_column", "the target outcome")
    predicted = prediction.get("predicted_value")
    factors = prediction.get("top_factors", [])
    strongest_factor = factors[0]["name"] if factors else "the strongest available factor"
    trend = prediction.get("trend", "Stable")
    confidence = prediction.get("confidence", "Medium")

    return [
        {
            "title": "Maximum outcome strategy",
            "type": "Performance",
            "description": f"Prioritize the factors most strongly associated with {target}, especially {strongest_factor}.",
            "expected_outcome": f"The target may move toward the predicted level of {predicted}.",
            "risk_level": "Medium",
            "resource_level": "High",
            "confidence": confidence,
            "tradeoff": "May require more resources, monitoring, or operational effort.",
        },
        {
            "title": "Lowest-resource strategy",
            "type": "Efficiency",
            "description": "Maintain essential activity while avoiding large changes to resource usage.",
            "expected_outcome": f"Protects against unnecessary cost while monitoring the {trend.lower()} trend.",
            "risk_level": "Medium",
            "resource_level": "Low",
            "confidence": confidence,
            "tradeoff": "The expected outcome may be lower than the maximum-outcome strategy.",
        },
        {
            "title": "Balanced strategy",
            "type": "Balanced",
            "description": "Combine the strongest available factor with gradual changes and regular measurement.",
            "expected_outcome": "Attempts to improve the outcome without committing all available resources.",
            "risk_level": "Low–Medium",
            "resource_level": "Medium",
            "confidence": confidence,
            "tradeoff": "Usually provides a compromise rather than the best result in one category.",
        },
    ]
