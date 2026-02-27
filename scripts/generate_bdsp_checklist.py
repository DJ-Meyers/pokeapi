#!/usr/bin/env python3
"""Generate a markdown checklist for manually verifying BDSP encounter data.

Reads the PokeAPI CSV data and produces a structured checklist broken down by:
  Location > Area > Encounter Method > Slots/Conditions

Each location links to Serebii and Bulbapedia for easy cross-referencing.
"""

import csv
import os
import urllib.parse
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "v2", "csv")


def read_csv(filename):
    with open(os.path.join(DATA_DIR, filename)) as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Load reference data
# ---------------------------------------------------------------------------

slots_by_id = {}
for row in read_csv("encounter_slots.csv"):
    slots_by_id[int(row["id"])] = {
        "version_group": int(row["version_group_id"]),
        "method": int(row["encounter_method_id"]),
        "slot": row["slot"],
        "rarity": int(row["rarity"]) if row["rarity"] else 0,
    }

methods_by_id = {int(r["id"]): r["identifier"] for r in read_csv("encounter_methods.csv")}

locations_by_id = {int(r["id"]): r["identifier"] for r in read_csv("locations.csv")}

area_rows = read_csv("location_areas.csv")
areas_by_id = {}
area_to_location = {}
for r in area_rows:
    aid = int(r["id"])
    areas_by_id[aid] = r["identifier"]
    area_to_location[aid] = int(r["location_id"])

cond_vals_by_id = {int(r["id"]): r["identifier"] for r in read_csv("encounter_condition_values.csv")}

cond_map = defaultdict(set)
for r in read_csv("encounter_condition_value_map.csv"):
    cond_map[int(r["encounter_id"])].add(cond_vals_by_id[int(r["encounter_condition_value_id"])])

pokemon_by_id = {int(r["id"]): r["identifier"] for r in read_csv("pokemon.csv")}

# ---------------------------------------------------------------------------
# Load BDSP encounters (both versions)
# ---------------------------------------------------------------------------

VERSION_BD = 37
VERSION_SP = 38
VERSION_GROUP_BDSP = 23

Encounter = dict  # just a type alias for readability

# Structure: location_id -> area_id -> method_id -> list[encounter_info]
tree = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

for row in read_csv("encounters.csv"):
    version = int(row["version_id"])
    if version not in (VERSION_BD, VERSION_SP):
        continue

    slot_id = int(row["encounter_slot_id"])
    slot = slots_by_id.get(slot_id)
    if not slot or slot["version_group"] != VERSION_GROUP_BDSP:
        continue

    area_id = int(row["location_area_id"])
    loc_id = area_to_location.get(area_id, 0)
    enc_id = int(row["id"])

    tree[loc_id][area_id][slot["method"]].append(
        {
            "enc_id": enc_id,
            "version": version,
            "pokemon": pokemon_by_id.get(int(row["pokemon_id"]), f"pokemon-{row['pokemon_id']}"),
            "slot_num": slot["slot"],
            "rarity": slot["rarity"],
            "min_level": row["min_level"],
            "max_level": row["max_level"],
            "conditions": frozenset(cond_map.get(enc_id, set())),
        }
    )

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

BULBAPEDIA_OVERRIDES = {
    "sinnoh-victory-road": "Victory_Road_(Sinnoh)",
    "sinnoh-pokemon-league": "Pok%C3%A9mon_League_(Sinnoh)",
    "mt-coronet": "Mt._Coronet",
    "sinnoh-hall-of-origin-1": "Hall_of_Origin",
    "honey-tree": "Honey_tree",
}


def bulbapedia_url(location_name):
    if location_name in BULBAPEDIA_OVERRIDES:
        page = BULBAPEDIA_OVERRIDES[location_name]
    else:
        # Strip sinnoh- prefix from routes
        name = location_name
        if name.startswith("sinnoh-sea-"):
            name = name.replace("sinnoh-sea-", "")
        elif name.startswith("sinnoh-"):
            name = name.replace("sinnoh-", "")
        page = name.replace("-", " ").title().replace(" ", "_")
    return f"https://bulbapedia.bulbagarden.net/wiki/{page}"


SEREBII_OVERRIDES = {
    "sinnoh-hall-of-origin-1": "halloforigin",
    "honey-tree": None,  # no dedicated page
}


def serebii_url(location_name):
    if location_name in SEREBII_OVERRIDES:
        slug = SEREBII_OVERRIDES[location_name]
        if slug is None:
            return None
        return f"https://www.serebii.net/pokearth/sinnoh/{slug}.shtml"

    name = location_name
    if name.startswith("sinnoh-sea-"):
        name = name.replace("sinnoh-sea-", "sea")
    elif name.startswith("sinnoh-"):
        name = name.replace("sinnoh-", "")
    slug = name.replace("-", "")
    return f"https://www.serebii.net/pokearth/sinnoh/{slug}.shtml"


def display_name(identifier):
    return identifier.replace("-", " ").title()


def pokemon_display(name):
    """Title-case a pokemon identifier, handling forms like shaymin-land."""
    return name.replace("-", " ").title()


# ---------------------------------------------------------------------------
# Sort helpers for conditions
# ---------------------------------------------------------------------------

CONDITION_ORDER = {
    "time-morning": 0,
    "time-day": 1,
    "time-night": 2,
    "swarm-yes": 3,
    "radar-on": 4,
    "trophy-garden-pokemon": 5,
}


def condition_sort_key(cond_set):
    if not cond_set:
        return (-1, "")
    return (min(CONDITION_ORDER.get(c, 99) for c in cond_set), str(sorted(cond_set)))


# ---------------------------------------------------------------------------
# Generate markdown
# ---------------------------------------------------------------------------

lines = []


def emit(line=""):
    lines.append(line)


emit("# BDSP Encounter Verification Checklist")
emit()
emit("Verify each location's encounter data against Serebii and Bulbapedia.")
emit("Each slot should have exactly **one** Pokemon per condition combination.")
emit()
emit("**Conditions used:** time (morning/day/night), swarm, radar, trophy-garden")
emit()
emit("**Slot rates (D/P standard):**")
emit("| Method | Slots (rate%) |")
emit("|--------|--------------|")
emit("| Walk | 20, 20, 10, 10, 10, 10, 5, 5, 4, 4, 1, 1 |")
emit("| Surf | 60, 30, 5, 4, 1 |")
emit("| Old Rod | 60, 30, 5, 4, 1 |")
emit("| Good Rod | 40, 40, 15, 4, 1 |")
emit("| Super Rod | 40, 40, 15, 4, 1 |")
emit()
emit("---")
emit()

# Sort locations alphabetically
for loc_id in sorted(tree, key=lambda lid: locations_by_id.get(lid, "")):
    loc_name = locations_by_id.get(loc_id, f"location-{loc_id}")
    loc_display = display_name(loc_name)

    bulba = bulbapedia_url(loc_name)
    serebii = serebii_url(loc_name)

    link_parts = [f"[Bulbapedia]({bulba})"]
    if serebii:
        link_parts.append(f"[Serebii]({serebii})")
    links = " · ".join(link_parts)

    area_ids = sorted(tree[loc_id])
    has_multiple_areas = len(area_ids) > 1

    emit(f"## {loc_display}")
    emit()
    emit(f"{links}")
    emit()

    for area_id in area_ids:
        area_name = areas_by_id.get(area_id, "")

        if has_multiple_areas or area_name:
            area_display = display_name(area_name) if area_name else "Default"
            emit(f"### {area_display}")
            emit()

        emit(f"- [ ] Verified")
        emit()

        method_data = tree[loc_id][area_id]

        for method_id in sorted(method_data, key=lambda m: methods_by_id.get(m, "")):
            method_name = display_name(methods_by_id.get(method_id, f"method-{method_id}"))
            encounters = method_data[method_id]

            emit(f"#### {method_name}")
            emit()

            # Separate BD and SP encounters
            bd_encs = [e for e in encounters if e["version"] == VERSION_BD]
            sp_encs = [e for e in encounters if e["version"] == VERSION_SP]

            # Group BD encounters by conditions
            by_cond = defaultdict(list)
            for e in bd_encs:
                by_cond[e["conditions"]].append(e)

            # Also gather SP for comparison
            sp_by_cond = defaultdict(list)
            for e in sp_encs:
                sp_by_cond[e["conditions"]].append(e)

            counter = 1

            for conds in sorted(by_cond, key=condition_sort_key):
                cond_str = ", ".join(sorted(conds)) if conds else "default"
                encs = by_cond[conds]

                # Group by slot
                by_slot = defaultdict(list)
                for e in encs:
                    by_slot[e["slot_num"]].append(e)

                regular_total = sum(e["rarity"] for e in encs if e["slot_num"] != "")
                has_dups = any(len(v) > 1 for k, v in by_slot.items() if k != "")

                # Check SP differences
                sp_encs_for_cond = sp_by_cond.get(conds, [])
                sp_pokemon = {e["pokemon"] for e in sp_encs_for_cond}
                bd_pokemon = {e["pokemon"] for e in encs}
                sp_only = sp_pokemon - bd_pokemon
                bd_only = bd_pokemon - sp_pokemon

                if regular_total == 100 and not has_dups:
                    badge = "✅"
                elif has_dups:
                    badge = "⚠️ DUPLICATES"
                elif regular_total == 0:
                    badge = ""
                else:
                    badge = f"❌ {regular_total}%"

                emit(f"**{cond_str}** {badge}")

                if sp_only or bd_only:
                    diffs = []
                    if bd_only:
                        diffs.append(f"BD-only: {', '.join(sorted(bd_only))}")
                    if sp_only:
                        diffs.append(f"SP-only: {', '.join(sorted(sp_only))}")
                    emit(f"*Version differences: {'; '.join(diffs)}*")

                emit()

                for slot in sorted(by_slot, key=lambda x: (x == "", int(x) if x else 99)):
                    slot_encs = by_slot[slot]
                    for e in slot_encs:
                        slot_display = f"slot {slot}" if slot else "special"
                        lvl = (
                            f"Lv.{e['min_level']}-{e['max_level']}"
                            if e["min_level"] != e["max_level"]
                            else f"Lv.{e['min_level']}"
                        )
                        dup = " **⚠️ DUPLICATE SLOT**" if len(slot_encs) > 1 else ""
                        emit(f"{counter}. {pokemon_display(e['pokemon'])} — {e['rarity']}%, {slot_display}, {lvl}{dup}")
                        counter += 1

                emit()

    emit("---")
    emit()

# ---------------------------------------------------------------------------
# Write output
# ---------------------------------------------------------------------------

output_path = os.path.join(
    os.path.dirname(__file__), "..", "thoughts", "2-16-26-bdsp-encounter-verification-checklist.md"
)
os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, "w") as f:
    f.write("\n".join(lines))

print(f"Wrote checklist to {output_path}")
print(f"  {len(tree)} locations, {sum(len(a) for a in tree.values())} areas")
