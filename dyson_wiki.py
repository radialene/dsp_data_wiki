#!/usr/bin/python3

"""Utility for maintaining the Dyson Sphere Program wiki.

This command-line script (usually) produces output on stdout in a format that
can be directly cut-and-pasted to the edit box of pages at
https://dyson-sphere-program.fandom.com/. In the usual case where there is
existing content, replace that content entirely, and then use the diff feature
to verify correctness.

To run, this requires the following files in the current directory:
* ItemProtoSet.dat
* RecipeProtoSet.dat
* TechProtoSet.dat
* base.txt
* prototype.txt

These must be extracted from the game files. See the module help in
"dysonsphere.py" for details.
"""

import argparse
import re
import sys

import dysonsphere
from dysonsphere import ERecipeType, EItemType

# These aren't worth importing from a file
STARTING_RECIPES = [1, 2, 3, 4, 5, 6, 50]
STARTING_TECHS = [1]
MADE_FROM = {
    ERecipeType.NONE:'-',
    ERecipeType.SMELT:'冶炼设备',
    ERecipeType.CHEMICAL:'化工设备',
    ERecipeType.REFINE:'精炼设备',
    ERecipeType.ASSEMBLE:'制造台',
    ERecipeType.PARTICLE:'粒子对撞机',
    ERecipeType.EXCHANGE:'能量交换器',
    ERecipeType.PHOTON_STORE:'射线接收站',
    ERecipeType.FRACTIONATE:'分馏设备',
    ERecipeType.RESEARCH:'科研设备',
    None:'未知'}
# The second part of the tuple is crafting power: The power of the building
# (Mk.I in the case of Assembler) divided by the crafting speed.
BUILDINGS = {
    ERecipeType.SMELT:([2302], 360000),
    ERecipeType.CHEMICAL:([2309], 720000),
    ERecipeType.REFINE:([2308], 960000),
    ERecipeType.ASSEMBLE:([2303, 2304, 2305], 360000),
    ERecipeType.PARTICLE:([2310], 12000000),
    ERecipeType.EXCHANGE:([2209], 45000000),
    ERecipeType.PHOTON_STORE:([2208], 0),
    ERecipeType.FRACTIONATE:([2314], 720000),
    ERecipeType.RESEARCH:([2901], 480000)}

# This is the only one set of strings that is not localized, because we ended
# up pluralizing all these categories.
CATEGORIES = {
    EItemType.UNKNOWN:'Unknown Category',
    EItemType.RESOURCE:'Natural Resources',
    EItemType.MATERIAL:'Materials',
    EItemType.COMPONENT:'Components',
    EItemType.PRODUCT:'End Products',
    EItemType.LOGISTICS:'Logistics',
    EItemType.PRODUCTION:'Production Facilities',
    EItemType.DECORATION:'Decorations',
    EItemType.TURRET:'Turrets',
    EItemType.DEFENSE:'Defense',
    EItemType.DARK_FOG:'Dark Fog',
    EItemType.MATRIX:'Science Matrices'}

BUILDING_CATEGORIES = [
    '电力类',    # Power (1)
    '采集类',    # Gathering (2)
    '运输类',    # Logistics (3)
    '仓储类',    # Storage (4)
    '生产类',    # Production (5)
    '物流类',    # Transportation (6)
    '研究类',    # Research (7)
    '戴森球类',  # Dyson Sphere Program (8)
    '环改类']    # Environment Modification (9)


# Patches we make to be explicit about what techs unlock items.
# This lists the recipe id of recipes to be "fixed": Their first output item
# will be marked as having an explict_tech_dep of the tech that unlocks
# the recipe. This works around cases where multiple recipes, unlocked by
# multiple techs produce the same item.
# to the tech id.
UNLOCK_HACKS = [
    16,  # Plasma Extract Refining
    17,  # Energetic Graphite
    37,  # Crystal Silicon
    78]  # Space Warper

# Tweaks to the sort-key function, to get the recipe list to sort in a better
# order.
KEY_TWEAKS = {75: 103, #Universe Matrix -> After Gravity Matrix
    89: 85, #Conveyor Belt MK.II -> After MK.I
    92: 86, #Conveyor Belt MK.III
    85: 87, #Sorter MK.I
    88: 88, #Sorter MK.II
    90: 89, #Sorter Mk.III
    86: 90, #Storage MK. I
    91: 91, #Storage Mk. II
    87: 92} #Splitter
COLOR_RE = re.compile('<color="([^"]*)">([^<]*)</color>')
TRANSLATE_RE = re.compile(r'(.*)\t.?\t[0-9]\t(.*?)\n?')

SPECIAL_MATERIALS_COMMENT="""
-- Raw materials that are not always available, and enable secondary or
-- "special" crafting recipes. In some cases, this just means that harvesting
-- the material directly enables skipping a production chain.
-- These are item_ids, ordered in the way they are presented to the user.
-- Sometimes not all options may be available."""
SPECIAL_MATERIALS = [
    1016,  # Unipolar Magnet
    1015,  # Spiniform Stalagmite Crystal
    1014,  # Optical Grating Crystal
    1117,  # Organic Crystal
    1011,  # Fire Ice
    1116,  # Sulfuric Acid
    1013,  # Fractal Silicon
    1012,  # Kimberlite Ore
    1003]  # Silicon Ore

def translate_fields(translations, proto_set, fields):
    """In-place replace text with translations for one proto_set."""
    for item in proto_set.data_array:
        for field in fields:
            val = getattr(item, field)
            if val:
                setattr(item, field, translations.get(val, '**' + val + '**'))



def translate_data(data):
    """In-place translate all text fields in 'data'."""
    translations = {}
    for line in data.base + data.prototype:
        match = TRANSLATE_RE.fullmatch(line)
        if not match:
            raise RuntimeError(f"Translation line failed to parse: {line}")
        translations[match[1]] = match[2]
    translate_fields(translations, data.ItemProtoSet,
                     ['name', 'mining_from', 'produce_from', 'description'])
    translate_fields(translations, data.RecipeProtoSet, ['name', 'description'])
    translate_fields(translations, data.TechProtoSet, ['name', 'description', 'conclusion'])
    for k, text in MADE_FROM.items():
        MADE_FROM[k] = translations.get(text, text)
    for i, text in enumerate(BUILDING_CATEGORIES):
        BUILDING_CATEGORIES[i] = translations.get(text, text).rstrip(' (0123456789)')

def dump_all(data):
    """Print all the game data in raw-ish form.

    (It's still translated.)
    """
    for set_name in ['ItemProtoSet', 'RecipeProtoSet', 'TechProtoSet']:
        print(f'{set_name}:')
        for item in getattr(data, set_name).data_array:
            print(f'    {item}')

def dump_sorted_names(entry_list):
    """Print just the names, sorted.

    Useful for checking if all pages have been created.
    """
    names = [wiki_title(x.name) for x in entry_list]
    names.sort()
    for name in names:
        print(name)

def wiki_title(name):
    """Like title(), except it never lowercases a letter."""
    return ''.join(min(x,y) for x,y in zip(name, name.title()))

def color_sub(desc):
    """Replace all <color="#B9DFFFC4">(rare)</color> tags with equivalent HTML.

    Also replaces newlines with <br>, which otherwise would get interpreted as
    paragraph breaks.
    """
    return (COLOR_RE
        .sub('<span style="color:\\1">\\2</span>', desc)
        .replace('\n', '<br>'))

def format_item(item_entry):
    """Formats an item as a Lua table."""
    item, disabled = item_entry
    if item.id == 1121:
        # Deuterium: We discover this on our own, it creates duplicates
        item.produce_from = None
    fields = {
        'name':repr(wiki_title(item.name)),
        'type':repr(item.type.name),
        'grid_index':item.grid_index,
        'stack_size':item.stack_size,
    }
    if item.sub_id:
        fields['sub_id'] = item.sub_id
    if item.can_build:
        fields['can_build'] = 'true'
    if item.build_index:
        fields['build_index'] = item.build_index
    if item.is_fluid:
        fields['is_fluid'] = 'true'
    if item.heat_value:
        fields['energy'] = item.heat_value
    if item.reactor_inc or item.heat_value:  # Force include if it's a fuel
        fields['fuel_chamber_boost'] = round(item.reactor_inc, 5)
    if item.unlock_key:
        fields['unlock_key'] = item.unlock_key
    if item.pre_tech_override:
        fields['explicit_tech_dep'] = item.pre_tech_override
    if item.mining_from:
        fields['mining_from'] = repr(color_sub(item.mining_from))
    if item.produce_from:
        fields['explicit_produce_from'] = repr(wiki_title(item.produce_from))
    fields['description'] = repr(color_sub(item.description))
    if disabled:
        fields['disabled'] = 'true'
    return (f'    [{item.id}] = {{\n' +
            ''.join(f'        {k}={v},\n' for k, v in fields.items()) +
            f'        --image={item.icon_path.rsplit("/", 1)[1]!r}\n    }},\n')

def format_recipe(recipe_entry):
    """Formats a recipe as a Lua table."""
    rec, disabled = recipe_entry
    if rec.id == 115:
        # Deuterium Fractionation: The game does a bunch of hacks and so do we.
        if len(rec.result_counts) == 1:
            rec.results.append(1120)
            rec.result_counts.append(99)
        rec.result_counts = [x / 100.0 for x in rec.result_counts]
        rec.item_counts = [x / 100.0 for x in rec.item_counts]
    time_spend = round(rec.time_spend / 60.0, 3)
    if time_spend == int(time_spend):
        time_spend = int(time_spend)  # Changes str() formating
    if 0 < time_spend < 1:
        # We need the extra precision. Format without leading 0.
        time_spend = repr(str(time_spend).lstrip('0'))

    outputs = ', '.join(str(x) for tup in zip(rec.results, rec.result_counts)
            for x in tup)
    inputs = ', '.join(str(x) for tup in zip(rec.items, rec.item_counts)
            for x in tup)
    fields = {
        'id':rec.id,
        'name':repr(wiki_title(rec.name)),
        'type':repr(rec.type.name),
        'outputs':'{' + outputs + '}',
        'inputs':'{' + inputs + '}',
        'grid_index':rec.grid_index,
        'handcraft':'true' if rec.handcraft else 'false',
        'seconds':time_spend,
    }
    if rec.explicit:
        fields['explicit'] = 'true'
    if rec.description:
        fields['description'] = repr(color_sub(rec.description))
    if disabled:
        fields['disabled'] = 'true'
    footer = '    },'
    if rec.icon_path:
        footer = f'        --image={rec.icon_path.rsplit("/", 1)[1]!r}\n    }},'
    return '{\n' + ''.join(f'        {k}={v},\n' for k, v in fields.items()) + footer

def format_tech(tech):
    """Formats a tech as a Lua table."""
    add_items = ', '.join(str(x) for tup in zip(tech.add_items, tech.add_item_counts)
            for x in tup)
    research_items = ', '.join(str(x) for tup in zip(tech.items, tech.item_points)
            for x in tup)
    recipes = ', '.join(str(x) for x in tech.unlock_recipes)
    pre_techs = ', '.join(str(x) for x in tech.pre_techs)
    pre_techs_implicit = ', '.join(str(x) for x in tech.pre_techs_implicit)
    pre_item = ', '.join(str(x) for x in tech.pre_item)
    fields = {
        'id':tech.id,
        'name':repr(wiki_title(tech.name)),
        'hash_needed':tech.hash_needed,
        'inputs':f'{{{research_items}}}',
    }
    if tech.level_coef1:
        fields['level_coef1'] = tech.level_coef1
    if tech.level_coef2:
        fields['level_coef2'] = tech.level_coef2
    if recipes:
        fields['recipes'] = f'{{{recipes}}}'
    if add_items:
        fields['add_items'] = f'{{{add_items}}}'
    if tech.level:
        fields['level'] = tech.level
    if tech.max_level:
        fields['max_level'] = tech.max_level
    if pre_techs:
        fields['pre_techs'] = f'{{{pre_techs}}}'
    if pre_techs_implicit:
        fields['pre_techs_implicit'] = f'{{{pre_techs_implicit}}}'
    if pre_item:
        fields['pre_item'] = f'{{{pre_item}}}'
    if tech.is_hidden_tech:
        fields['is_hidden_tech'] = 'true'
    fields['image'] = repr(tech.icon_path.split('/')[-1])
    fields['position'] = f'{{{tech.position[0]}, {tech.position[1]}}}'
    fields['description'] = repr(color_sub(tech.description))
    if tech.conclusion:
        fields['conclusion'] = repr(color_sub(tech.conclusion))
    if not tech.published:
        fields['disabled'] = 'true'
    return '{\n' + ''.join(f'        {k}={v},\n' for k, v in fields.items()) + '    },'

def format_facility(facility, items_map):
    """Formats an ERecipeType enum as a Lua table."""
    building_list, power = BUILDINGS.get(facility, ([], 0))
    buildings = ', '.join(str(x) for x in building_list)
    building_comment = ', '.join(items_map[x][0].name for x in building_list)
    return (f'    {facility.name}={{name={MADE_FROM.get(facility, MADE_FROM[None])!r}, ' +
            f'power={power}, ' +
            f'buildings={{{buildings}}}}},  --{building_comment}\n')


def set_valid(items_map, recipe_entry):
    """Set the given recipe_entry valid, and also the associated item(s)"""
    recipe_entry[1] = False
    # Don't bother checking the inputs, we'll assume that a valid tech
    # means they're attainable.
    for iid in recipe_entry[0].results:
        items_map[iid][1] = False

def recipe_key(recipe):
    """Calculate a sort key for recipes"""
    key = recipe.id
    return KEY_TWEAKS.get(key, key)

def create_augmented_maps(data):
    """Create augmented maps to determine whether items/recipes are disabled or not.

    The return is a tuple of (items_map, recipes_map), where each map goes
    from id -> [object, is_disabled]. For recipes, disabled means it should
    never be shown. For items, it should still probably be allowed for direct
    lookups (i.e. Infobox queries), but not for traversals (e.g. creating a
    grid layout of all the items).
    """
    items = data.ItemProtoSet.data_array
    items.sort(key=lambda x:x.id)
    items_map = {}
    # The unlock_key field lets us know for sure that an item is not disabled,
    # and if a recipe is unlocked from a non-disabled tech, or if it is
    # unlocked from the start, then it is not disabled.
    for item in items:
        # Second element is whether item is disabled
        items_map[item.id] = [item, item.unlock_key == 0]

    recipes = data.RecipeProtoSet.data_array
    # The first part of the key determines if this is a building recipe, based
    # on its grid index.
    recipes.sort(key=lambda x:(
        x.grid_index // 1000, x.type.name, recipe_key(x)))
    recipes_map = {}
    for rec in recipes:
        # Second element is whether recipe is disabled
        entry = [rec, True]
        recipes_map[rec.id] = entry
        if rec.id in STARTING_RECIPES:
            set_valid(items_map, entry)

    techs = data.TechProtoSet.data_array
    techs.sort(key=lambda x:x.id)
    for tech in techs:
        if not tech.published:
            continue
        for rid in tech.unlock_recipes:
            set_valid(items_map, recipes_map[rid])
    return items_map, recipes_map

def print_wiki(data):
    """Prints wiki-text dump.

    This is designed to replace (most of) what's at Module:Recipe/Data.
    """
    items_map, recipes_map = create_augmented_maps(data)
    # Deal with UNLOCK_HACKS.
    techs = data.TechProtoSet.data_array
    for tech in techs:
        for hack in UNLOCK_HACKS:
            if hack in tech.unlock_recipes:
                items_map[recipes_map[hack][0].results[0]][0].pre_tech_override = tech.id

    items_str = ''.join(format_item(x) for x in items_map.values())
    recipes_str = ''.join(format_recipe(x) for x in recipes_map.values())
    techs_str = ''.join(format_tech(x) for x in techs)
    facilities_str = ''.join(format_facility(x, items_map) for x in ERecipeType)
    starting_recipes_str = ', '.join(str(x) for x in STARTING_RECIPES)
    special_materials_str = '\n'.join(
        f'    {x},  -- {items_map[x][0].name}' for x in SPECIAL_MATERIALS)
    categories_str = ''.join(f'    {k.name}={v!r},\n' for k, v in CATEGORIES.items())
    building_categories_str = ''.join(f'    {x!r},\n' for x in BUILDING_CATEGORIES)

    print(f"""return {{
--[[
Data for all the items. Each entry is a table, keyed by the item's id. The
entries are sorted by id, although you can't count on this when using pairs()
in Lua.

The item data is mostly self-explanatory. Fields are omitted if they are not
relevant/present for the given item. The valid fields are:
    name - Title-Cased vs. what's in the game.
    type - The category of the item, not the full story for buildings
    grid_index - Where this appears in the item grid. The format is ZXXY,
                 where Z is 1 for components and 2 for buildings. Note that
                 this has the same format as the grid_index for recipes, but
                 different values - recipe grid_index is used with the
                 replicator, while item grid_index is used with filters (for
                 example).
    stack_size
    sub_id - Set for building with different types (i.e. conveyers), and also
             all the different energy producers.
    can_build - Mostly equivalent to "is_building?", except also true for
                Foundation.
    build_index - Where this appears in the build shortcut menus, in the form
                  ZXX, where Z is the top-level and XX is the inner level.
    is_fluid - boolean, omitted when false.
    energy - This is measured in Joules.
    fuel_chamber_boost - This is a floating-point number, so 1.0 corresponds
                         to a +100% boost.
    unlock_key - The item ID of an item that is used to determine the tech
                 unlock requirements of this item. For instance,
                 Accumulator(Full) is unlocked whenever Accumulator is,
                 without it being explicitly stated in the tech tree.
    explicit_tech_dep - The explicit tech dependency of this item, for display
                        purposes.
    mining_from - A free-text string that sometimes includes colored spans.
    explicit_produce_from - A text string that should name an item. Used for
                            items that are produced without conventional recipes.
    description - The in-game tooltip text. May include colored spans.
    disabled - If true, this item won't show up in the item grid. Set for
               items that are in the game data, but not accessible yet.
    image - Included as a comment only, this is the name of the item image
            as stored in the game files. It should be renamed to the item's
            name when uploaded.
]]
game_items = {{
{items_str}}},

--[[
Data for all the recipes. Each entry is a table, stored as a flat array. The
entries are sorted first by component/building, then by type, and lastly by id,
although with some tweaks so that different ranks of buildings come next to
each other. This is because Template:Crafting outputs items in the order they
are listed here.

The recipe data is mostly self-explanatory. Fields are omitted if they are not
relevant/present for the given recipe. The valid fields are:
    id
    name - Title-Cased vs. what's in the game.
    type - The type of building that makes the recipe
    outputs - What the recipe produces. This is an alternating array of
              "item_id, count, item_id, count, ..." As a result, there will
              always be an even number of elements.
    inputs - What the recipe requires. Same format as outputs.
    grid_index - Where this appears in the recipe grid. The format is ZXXY,
                 where Z is 1 for components and 2 for buildings. Note that
                 this has the same format as the grid_index for items, but
                 different values - recipe grid_index is used with the
                 replicator, while item grid_index is used with filters (for
                 example).
    handcraft - Can it be made in the replicator?
    seconds - How long to craft at 1x speed.
    explicit - Whether this is an "explicit" recipe, as opposed to the
               implicit or "primary" recipe for an item. You can tell the
               difference in-game because hovering over an explicit recipe
               shows "(Recipe)" in front of the name, and there's other
               differences in the tooltip.
    description - The in-game tooltip text. May include colored spans.
                  Generally only present (and used) for explicit recipes.
    disabled - If true, this item won't show up in the item grid. Set for
               items that are in the game data, but not accessible yet.
    image - Included as a comment only, this is the name of the item image
            as stored in the game files. It should be renamed to the item's
            name when uploaded. Generally only present for explicit recipes.
]]
game_recipes = {{
    {recipes_str}
}},

--[[
Data for all the techs. Each entry is a table, stored as a flat array. The
entries are sorted by id, which means that regular technologies come before
upgrades.

The tech data is mostly self-explanatory. Fields are omitted if they are not
relevant/present for the given tech. The valid fields are:
    id
    name - Title-Cased vs. what's in the game.
    hash_needed - The amount of hash needed to research, as a raw number.
                  Sometimes this is not the true amount, when it changes
                  per-level: See level_coef below.
    level_coef1 - This times the tech's (raw) level is added to hash_needed
                  to calculate the true amount. Used to create infinitely
                  researchable upgrades with linearly scaling costs.
    level_coef2 - This times [the tech's (raw) level squared] is added to
                  hash_needed to calculate the true amount. Used to create
                  infinitely researchable upgrades with quadratically scaling
                  costs.
    inputs - The items needed to complete one step of research. This has the
             same format as recipes: Alternating item_id, count, etc. For
             early techs this will be regular items, for later techs it will
             be matrices. Note that one step of research lasts one second,
             i.e. it provides 3600 hash. So the total number of items will be
             the count * hash_needed / 3600.
    recipes - What recipe_ids are unlocked by this tech. Omitted if empty.
    add_items - Item ids that are added directly to your inventory on
                completion of this tech. Same format as inputs. Omitted if empty.
    level - If present, indicates the "level" of this tech, usually indicating
            that this tech can be researched multiple times. Either the same
            tech can be researched (if there is a range between level and
            max_level), or there can be multiple instances with the same name
            (this is how upgrades are handled, since they have different icons
            and other differences at each level).
    max_level - The highest level that can be attained with this instance of
                the tech, but there may be other instances with the same name
                and different level ranges. Always paired with level.
    pre_techs - Prerequisite technologies. Omitted if empty.
    pre_techs_implicit - *Also* prerequisite technologies, but they couldn't
                         figure out how to draw these lines on the tech tree
                         and still have it look pretty. In other words, it's a
                         big hack. Omitted if empty.
    pre_item - Prerequisite items to research. Omitted if empty.
    is_hidden_tech - Is this normally hidden? Tends to go with pre_item.
    is_obsolete - True when obsolete.
    image - The name of the image. Usually the same as the id, but not always.
    position - Where it's located on the tech tree.
    description - The in-game tech-tree text. May include colored spans.
    conclusion - The text shown in the pop-up when you finish researching.
    disabled - If true, this tech shows up in the tech tree, but isn't
               available yet.
]]
game_techs = {{
    {techs_str}
}},

-- These (below this point) don't come from the game files, because they're
-- totally buried in the game logic.

-- This is a map from recipe type (which is effectively facility type) to its name
-- and an array of item ids of buildings that can produce those types of recipes.
-- The power field measures the power usage of the facility, divided by its
-- production speed (so its effective power usage to craft at 1s nominal.)
game_facilities = {{
{facilities_str}}},

-- This is just an array of what you start out being able to craft.
-- (Both in the replicator, and in buildings once you get them.)
starting_recipes = {{{starting_recipes_str}}},
{SPECIAL_MATERIALS_COMMENT}
special_materials = {{
{special_materials_str}
}},

-- This maps the symbolic item type names to wiki categories.
-- These don't come from the game files at all, although they're essentially
-- the pluralized version of the equivalent strings.
categories = {{
{categories_str}}},

-- An array of building categories. Maps from the shortcut key you press
-- in-game to the name of the category.
building_categories = {{
{building_categories_str}}},
}}""")

def fuzzy_lookup_item(name_or_id, lst):
    """Lookup an item by either name or id.

    Looking up by id is exact match. Looking up by name is by containment, and
    if the term is entirely lowercase then it's also case-insensitive.
    Multiple matches will throw an exception, unless one of them was an exact
    match.
    """
    try:
        idd = int(name_or_id)
        for val in lst:
            if val.id == idd:
                return val
        raise RuntimeError('Id %d not found!' % idd)
    except ValueError:
        insensitive = name_or_id.islower()
        matches = []
        for val in lst:
            name = val.name
            if name_or_id == name:
                return val
            if insensitive:
                name = name.lower()
            if name_or_id in name:
                matches.append(val)
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise RuntimeError(f'No name containing {name_or_id!r} found!') from None
        raise RuntimeError(
            f'Multiple matches for {name_or_id!r}: {[x.name for x in matches]}') from None

# pylint: disable=too-many-branches
def main():
    """Main function, keeps a separate scope"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--find_item',
                        help='Lookup a specific item, by name or id')
    parser.add_argument('--find_recipe',
                        help='Lookup a specific recipe, by name or id')
    parser.add_argument('--find_tech',
                        help='Lookup a specific tech, by name or id')
    parser.add_argument('--dump_item_names', action='store_true',
                        help='Print a sorted list of item names')
    parser.add_argument('--dump_tech_names', action='store_true',
                        help='Print a sorted list of tech names')
    parser.add_argument('--dump_strings', action='store_true',
                        help='Print all the translations, raw')
    parser.add_argument('--dump_all', action='store_true',
                        help='Dump everything')
    parser.add_argument('--wiki', action='store_true',
                        help='Print wiki text for Module:Recipe/Data')
    args = parser.parse_args()

    print('Reading data... ', end='', flush=True, file=sys.stderr)
    data = dysonsphere.load_all()
    translate_data(data)
    print('Done!', flush=True, file=sys.stderr)

    try:
        item = None
        if args.find_item:
            item = fuzzy_lookup_item(
                    args.find_item, data.ItemProtoSet.data_array)
        if args.find_recipe:
            item = fuzzy_lookup_item(
                    args.find_recipe, data.RecipeProtoSet.data_array)
        if args.find_tech:
            item = fuzzy_lookup_item(
                    args.find_tech, data.TechProtoSet.data_array)
        if item:
            print(repr(item))
        else:
            if args.dump_all:
                dump_all(data)
            elif args.dump_item_names:
                dump_sorted_names(data.ItemProtoSet.data_array)
            elif args.dump_tech_names:
                dump_sorted_names(data.TechProtoSet.data_array)
            elif args.dump_strings:
                for entry in data.StringProtoSet.data_array:
                    print(entry)
            elif args.wiki:
                print_wiki(data)
            else:
                print('Nothing to do!', file=sys.stderr)
    except RuntimeError as ex:
        print(ex, file=sys.stderr)

if __name__ == '__main__':
    main()
