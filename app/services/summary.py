"""Human-readable classification summaries + explanations.

Adds a plain-language `summary` to every fire alongside the machine fields so
judges and viewers understand a classification without reading raw numbers.

Fields added to each fire's properties:
- `summary_headline` — short label ("Industrial Fire", "Forest Fire", …)
- `summary_detail` — the distance/context phrase ("≈340 m from a known
  industrial zone", "deep within a vegetation zone", …)
- `summary_persistent` — only when `persistent_thermal_source`; a recurrence note
- `summary` — headline + detail + (persistent note), the string used on the UI
- `summary_icon` — emoji hint for the frontend
- `explanation` — one-line "why we think this" (the rule that fired)
"""

from ..config import settings
from .spatial import NEAR_BUFFER_METERS, VEGETATION_BUFFER_METERS

NEAR_KM = NEAR_BUFFER_METERS / 1000  # industrial: 1 km
VEGETATION_KM = VEGETATION_BUFFER_METERS / 1000  # forest: 3 km

HEADLINES = {
    "industrial": "Industrial Fire",
    "forest": "Forest Fire",
    "other_natural": "Crop/Agricultural Burning",
}

ICONS = {
    "industrial": "\U0001f3ed",  # factory
    "forest": "\U0001f332",  # evergreen tree
    "other_natural": "\U0001f33e",  # ear of rice
}


def _format_distance(meters: float | None) -> str:
    """ "≈340 m" or "≈1.2 km"; empty when unknown."""
    if meters is None:
        return ""
    if meters >= 1000:
        return f"\u2248{meters / 1000:.1f} km"
    return f"\u2248{round(meters)} m"


def _industrial_detail(props: dict) -> str:
    """Distance/source phrase for the industrial headline."""
    plant_name = props.get("power_plant_name")
    source = props.get("industrial_match_source")
    d = props.get("distance_m")
    if d is not None and d < 10:
        base = "burning inside a mapped industrial facility"
    else:
        base = (
            f"{_format_distance(d)} from a known industrial zone"
            if d
            else "near a known industrial zone"
        )
    if source == "power_plant_db" and plant_name:
        return f"\u2248{_format_distance(props.get('power_plant_distance_m'))} from the {plant_name} power plant"
    if source == "both":
        suffix = (
            f" and the {plant_name} power plant"
            if plant_name
            else " and a mapped power plant"
        )
        return base + suffix
    return base


def _explanation(props: dict) -> str:
    """One line saying why the rule picked this class."""
    rule = props.get("fire_type_rule")
    source = props.get("industrial_match_source")
    plant_name = props.get("power_plant_name")
    if rule == "industrial":
        if source == "power_plant_db":
            what = (
                f"the {plant_name} power plant (WRI)"
                if plant_name
                else "a mapped WRI power plant"
            )
        elif source == "both":
            what = (
                f"both a mapped industrial zone and the {plant_name} power plant"
                if plant_name
                else "both a mapped industrial zone and a power plant"
            )
        else:
            what = "a mapped OSM industrial zone"
        return (
            f"Classified as industrial because it sits within {NEAR_KM:.0f} km of {what}, "
            "confirmed by a live NASA FIRMS hotspot."
        )
    if rule == "forest":
        return (
            f"Classified as forest because it is not near industry but sits within "
            f"{VEGETATION_KM:.0f} km of mapped natural vegetation (OSM forest/scrub)."
        )
    return (
        "No industrial zone or mapped vegetation is within range, so this is most likely "
        "crop/agricultural burning or an isolated natural event."
    )


def _persistent_note(props: dict, rule: str) -> str:
    occurrences = props.get("occurrence_count") or 0
    lookback = settings.persistence_lookback_days
    if rule == "industrial":
        tail = "an ongoing industrial source rather than a one-time incident"
    else:
        tail = "a persistent burning area rather than a one-off event"
    return (
        f"Recurring \u2014 detected {occurrences} times in the past {lookback} days, "
        f"suggesting {tail}."
    )


def add_summary(fires_fc: dict) -> dict:
    """Add the plain-language `summary`, `explanation` and helpers to every fire.

    Mutates and returns the input FeatureCollection.
    """
    for feature in fires_fc["features"]:
        prop = feature["properties"]
        rule = prop.get("fire_type_rule")
        if rule not in HEADLINES:
            rule = "other_natural"
            prop["fire_type_rule"] = rule

        headline = HEADLINES[rule]
        detail = (
            _industrial_detail(prop)
            if rule == "industrial"
            else "deep within a vegetation zone"
            if rule == "forest" and (prop.get("vegetation_distance_m") or 0) < 500
            else f"{_format_distance(prop.get('vegetation_distance_m'))} from the nearest vegetation"
            if rule == "forest"
            else "no nearby industrial or forest activity"
        )

        persistent = ""
        if prop.get("persistent_thermal_source"):
            persistent = _persistent_note(prop, rule)

        prop["summary_headline"] = headline
        prop["summary_detail"] = detail
        prop["summary_icon"] = ICONS[rule]
        prop["summary"] = f"{headline} \u2014 {detail}" + (
            f" {persistent}" if persistent else ""
        )
        prop["summary_persistent"] = persistent or None
        prop["explanation"] = _explanation(prop)
    return fires_fc
