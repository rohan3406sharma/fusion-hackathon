"""Deterministic generator for the SYNTHETIC Food & Beverage demonstration dataset.

Every entity, coordinate, relationship and attribute produced here is synthetic. Business names are
invented. Regions are real *places* used only to make the geography plausible; nothing here is a claim
about a real company, contract or facility. Run:  python backend/data/generate_dataset.py
"""
from __future__ import annotations

import csv
import json
import math
import random
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
SEED = 20261009

# --------------------------------------------------------------------------------------------------
# Product registry: product -> (input specificity/criticality, input substitutability, storable)
# specificity: how essential the input is to the customer's product (1 = cannot make product without)
# substitutability: how readily a *different* input could replace it (independent of supplier switching)
# --------------------------------------------------------------------------------------------------
PRODUCTS: dict[str, tuple[float, float, bool]] = {
    "wheat_grain": (0.90, 0.30, True), "paddy_rice": (0.90, 0.25, True), "maize": (0.90, 0.30, True),
    "soybean": (0.90, 0.30, True), "sugarcane": (0.95, 0.10, False), "coffee_cherry": (0.90, 0.20, False),
    "cocoa_beans": (0.95, 0.15, True), "raw_milk": (1.00, 0.05, False), "orchard_fruit": (0.85, 0.30, False),
    "fresh_vegetables": (0.85, 0.30, False), "citrus_fruit": (0.90, 0.25, False), "olives": (0.90, 0.20, False),
    "oil_palm_fruit": (0.95, 0.10, False), "barley": (0.85, 0.40, True),
    "fertiliser": (0.60, 0.50, True), "seeds": (0.70, 0.40, True), "irrigation_water": (0.90, 0.10, False),
    "diesel_fuel": (0.70, 0.40, True), "electricity": (0.95, 0.25, False),
    "flour": (0.85, 0.35, True), "milled_rice": (0.85, 0.30, True), "maize_starch": (0.70, 0.40, True),
    "soybean_oil": (0.60, 0.50, True), "refined_sugar": (0.70, 0.50, True), "green_coffee": (0.90, 0.25, True),
    "cocoa_mass": (0.90, 0.15, True), "processed_milk": (0.90, 0.10, True), "juice_concentrate": (0.70, 0.40, True),
    "fruit_pulp": (0.60, 0.45, True), "prepared_veg": (0.70, 0.30, True), "refined_palm_oil": (0.60, 0.50, True),
    "olive_oil": (0.55, 0.50, True), "edible_oil_blend": (0.55, 0.50, True), "malt": (0.85, 0.20, True),
    "packaged_bakery": (0.70, 0.40, True), "packaged_snacks": (0.60, 0.50, True), "packaged_noodles": (0.60, 0.50, True),
    "breakfast_cereal": (0.60, 0.50, True), "soft_drinks": (0.70, 0.40, True), "beer": (0.70, 0.40, True),
    "roasted_coffee": (0.80, 0.30, True), "chocolate": (0.75, 0.30, True), "packaged_dairy": (0.80, 0.20, True),
    "ready_meals": (0.70, 0.40, True), "packaged_cooking_oil": (0.60, 0.50, True), "fruit_juice": (0.70, 0.40, True),
    "glass_bottles": (0.85, 0.30, True), "aluminium_cans": (0.85, 0.30, True), "paper_cartons": (0.80, 0.35, True),
    "flexible_packaging": (0.75, 0.35, True), "pet_containers": (0.80, 0.35, True),
    "cold_storage_service": (0.80, 0.30, False), "transport_service": (0.70, 0.50, False),
    "rail_freight": (0.70, 0.40, False), "port_service": (0.85, 0.25, False),
    "distribution_service": (0.80, 0.35, False), "beverage_distribution": (0.80, 0.30, False),
    "wholesale_goods": (0.60, 0.50, True), "financial_service": (0.50, 0.50, False),
}

# Indicative synthetic price (USD/tonne) to turn the revenue proxy into a capacity figure. Not market data.
PRICE_PER_TONNE = {
    "wheat_grain": 300, "paddy_rice": 350, "maize": 250, "soybean": 480, "sugarcane": 40, "coffee_cherry": 1800,
    "cocoa_beans": 3500, "raw_milk": 450, "orchard_fruit": 900, "fresh_vegetables": 700, "citrus_fruit": 500,
    "olives": 1000, "oil_palm_fruit": 150, "barley": 280, "fertiliser": 450, "seeds": 3000, "diesel_fuel": 900,
    "flour": 500, "milled_rice": 600, "maize_starch": 550, "soybean_oil": 1300, "refined_sugar": 600,
    "green_coffee": 4000, "cocoa_mass": 5000, "processed_milk": 700, "juice_concentrate": 1600, "fruit_pulp": 1500,
    "prepared_veg": 1400, "refined_palm_oil": 1100, "olive_oil": 5500, "edible_oil_blend": 1400, "malt": 650,
    "packaged_bakery": 2500, "packaged_snacks": 3500, "packaged_noodles": 2000, "breakfast_cereal": 3200,
    "soft_drinks": 800, "beer": 1100, "roasted_coffee": 9000, "chocolate": 7000, "packaged_dairy": 3000,
    "ready_meals": 4500, "packaged_cooking_oil": 1600, "fruit_juice": 1500, "glass_bottles": 700,
    "aluminium_cans": 3000, "paper_cartons": 1200, "flexible_packaging": 3500, "pet_containers": 2200,
}

# Type defaults. flood / heat / drought vulnerability, inventory days of inputs, alternative-supplier availability,
# operational criticality, spare capacity fraction, value-added ratio, facility type.
TYPE_DEFAULTS = {
    "agricultural_producer": dict(v=(0.70, 0.75, 0.90), inv=14, alt=0.35, crit=0.60, spare=0.08, va=0.55, fac="farm / production region"),
    "agricultural_input":    dict(v=(0.35, 0.25, 0.40), inv=30, alt=0.60, crit=0.60, spare=0.15, va=0.30, fac="input plant / service"),
    "processor":             dict(v=(0.50, 0.35, 0.35), inv=21, alt=0.35, crit=0.65, spare=0.12, va=0.18, fac="processing plant"),
    "manufacturer":          dict(v=(0.45, 0.30, 0.30), inv=25, alt=0.50, crit=0.55, spare=0.15, va=0.28, fac="manufacturing plant"),
    "packaging_supplier":    dict(v=(0.40, 0.30, 0.25), inv=30, alt=0.60, crit=0.55, spare=0.20, va=0.28, fac="packaging plant"),
    "cold_storage":          dict(v=(0.50, 0.65, 0.10), inv=3, alt=0.40, crit=0.65, spare=0.12, va=0.50, fac="refrigerated warehouse"),
    "transport_operator":    dict(v=(0.55, 0.30, 0.10), inv=0, alt=0.60, crit=0.55, spare=0.15, va=0.45, fac="fleet / rail network"),
    "port_hub":              dict(v=(0.65, 0.20, 0.10), inv=0, alt=0.30, crit=0.85, spare=0.10, va=0.50, fac="port terminal"),
    "distribution_centre":   dict(v=(0.45, 0.35, 0.10), inv=10, alt=0.50, crit=0.65, spare=0.15, va=0.35, fac="distribution centre"),
    "wholesaler":            dict(v=(0.40, 0.25, 0.10), inv=7, alt=0.70, crit=0.45, spare=0.20, va=0.15, fac="wholesale depot"),
    "retailer":              dict(v=(0.40, 0.30, 0.10), inv=5, alt=0.80, crit=0.50, spare=0.0, va=0.22, fac="retail network"),
    "utility":               dict(v=(0.40, 0.50, 0.30), inv=0, alt=0.20, crit=0.90, spare=0.05, va=0.40, fac="power utility"),
    "financial":             dict(v=(0.05, 0.05, 0.05), inv=0, alt=0.80, crit=0.30, spare=0.0, va=0.50, fac="head office"),
}

# id, name, type, food_category, output_product, country, region, lat, lon, revenue_musd, overrides
A, AI, PR, MF, PK, CS, TR, PO, DC, WH, RT, UT, FN = (
    "agricultural_producer", "agricultural_input", "processor", "manufacturer", "packaging_supplier",
    "cold_storage", "transport_operator", "port_hub", "distribution_centre", "wholesaler", "retailer", "utility",
    "financial")

ENTITIES: list[tuple] = [
    # ---- agricultural production
    ("farm_wheat_pb", "Punjab Plains Wheat Growers", A, "grains", "wheat_grain", "India", "Punjab", 30.9, 75.8, 420, dict(v=(0.60, 0.80, 0.85))),
    ("farm_wheat_ks", "Kansas Winter Wheat Collective", A, "grains", "wheat_grain", "United States", "Kansas", 38.5, -98.0, 380, dict(v=(0.35, 0.60, 0.90))),
    ("farm_rice_hr", "Haryana Basmati Growers", A, "rice", "paddy_rice", "India", "Haryana", 29.6, 76.4, 260, dict(v=(0.45, 0.65, 0.80))),
    ("farm_rice_mk", "Mekong Delta Rice Farms", A, "rice", "paddy_rice", "Vietnam", "Mekong Delta", 10.0, 105.6, 340, dict(v=(0.50, 0.55, 0.70))),
    ("farm_maize_mt", "Mato Grosso Maize Producers", A, "grains", "maize", "Brazil", "Mato Grosso", -12.6, -56.0, 450, dict(v=(0.40, 0.70, 0.85))),
    ("farm_soy_mt", "Mato Grosso Soy and Oilseed Growers", A, "edible_oils", "soybean", "Brazil", "Mato Grosso", -13.0, -55.0, 500, dict(v=(0.40, 0.65, 0.85))),
    ("farm_cane_sp", "Sao Paulo Sugarcane Estates", A, "sugar", "sugarcane", "Brazil", "Sao Paulo State", -21.2, -48.0, 520, dict(v=(0.45, 0.60, 0.85))),
    ("farm_cane_up", "Uttar Pradesh Cane Cooperative", A, "sugar", "sugarcane", "India", "Uttar Pradesh", 27.0, 80.5, 300, dict(v=(0.60, 0.60, 0.80))),
    ("farm_coffee_mg", "Minas Gerais Coffee Growers", A, "coffee", "coffee_cherry", "Brazil", "Minas Gerais", -21.5, -45.0, 380, dict(v=(0.30, 0.90, 0.85))),
    ("farm_coffee_dl", "Dak Lak Robusta Farms", A, "coffee", "coffee_cherry", "Vietnam", "Central Highlands", 12.7, 108.0, 220, dict(v=(0.35, 0.80, 0.85))),
    ("farm_cocoa_ci", "Daloa Cocoa Smallholder Network", A, "cocoa", "cocoa_beans", "Cote d'Ivoire", "Haut-Sassandra", 6.9, -6.45, 300, dict(v=(0.35, 0.80, 0.90), alt=0.15)),
    ("farm_dairy_fr", "Friesland Dairy Farms", A, "dairy", "raw_milk", "Netherlands", "Friesland", 53.1, 5.8, 410, dict(v=(0.55, 0.75, 0.60))),
    ("farm_dairy_wi", "Wisconsin Dairy Cooperative", A, "dairy", "raw_milk", "United States", "Wisconsin", 44.5, -89.5, 450, dict(v=(0.45, 0.70, 0.55))),
    ("farm_fruit_cv", "Central Valley Orchards", A, "fruit_veg", "orchard_fruit", "United States", "California", 36.7, -119.8, 360, dict(v=(0.45, 0.85, 0.85))),
    ("farm_veg_cv", "Salinas Valley Vegetable Growers", A, "fruit_veg", "fresh_vegetables", "United States", "California", 36.6, -121.6, 290, dict(v=(0.55, 0.85, 0.80))),
    ("farm_olive_an", "Andalusia Olive Growers", A, "edible_oils", "olives", "Spain", "Andalusia", 37.4, -4.5, 280, dict(v=(0.25, 0.70, 0.95))),
    ("farm_palm_sm", "Sumatra Oil Palm Estates", A, "edible_oils", "oil_palm_fruit", "Indonesia", "Sumatra", 1.0, 101.5, 480, dict(v=(0.45, 0.50, 0.75))),
    ("farm_citrus_sp", "Sao Paulo Citrus Orchards", A, "fruit_veg", "citrus_fruit", "Brazil", "Sao Paulo State", -21.8, -48.5, 240, dict(v=(0.35, 0.80, 0.85))),
    ("farm_barley_de", "Bavarian Barley Growers", A, "grains", "barley", "Germany", "Bavaria", 48.5, 11.5, 180, dict(v=(0.40, 0.70, 0.80))),
    # ---- agricultural inputs and utilities
    ("fert_br", "Cerrado Fertiliser Works", AI, "agri_inputs", "fertiliser", "Brazil", "Goias", -16.7, -49.3, 600, {}),
    ("fert_in", "Gujarat Fertiliser Plant", AI, "agri_inputs", "fertiliser", "India", "Gujarat", 22.3, 73.2, 550, {}),
    ("fert_eu", "Zeeland Nitrogen Fertiliser", AI, "agri_inputs", "fertiliser", "Netherlands", "Zeeland", 51.3, 3.8, 520, dict(v=(0.55, 0.25, 0.20))),
    ("seed_us", "Heartland Seed and Crop Inputs", AI, "agri_inputs", "seeds", "United States", "Iowa", 41.9, -93.6, 700, {}),
    ("irrig_pb", "Punjab Canal and Irrigation Service", AI, "agri_inputs", "irrigation_water", "India", "Punjab", 31.0, 75.5, 120, dict(v=(0.60, 0.30, 0.85), crit=0.85)),
    ("irrig_cv", "Central Valley Water District", AI, "agri_inputs", "irrigation_water", "United States", "California", 36.8, -119.9, 140, dict(v=(0.35, 0.30, 0.80), crit=0.85)),
    ("agfuel_br", "Southeast Brazil Agri-Fuel Distributor", AI, "agri_inputs", "diesel_fuel", "Brazil", "Sao Paulo State", -20.5, -47.0, 380, {}),
    ("grid_pb", "Punjab Power Grid Utility", UT, "energy", "electricity", "India", "Punjab", 30.7, 76.7, 900, {}),
    ("grid_sp", "Sao Paulo Power Utility", UT, "energy", "electricity", "Brazil", "Sao Paulo State", -23.0, -47.0, 1200, {}),
    ("grid_nl", "Dutch Regional Grid Operator", UT, "energy", "electricity", "Netherlands", "Noord-Brabant", 52.0, 5.1, 1100, {}),
    ("grid_ca", "Central California Power Utility", UT, "energy", "electricity", "United States", "California", 36.9, -120.0, 1000, {}),
    # ---- processing
    ("mill_pb", "Ludhiana Flour Mills", PR, "grains", "flour", "India", "Punjab", 30.9, 75.85, 310, dict(inv=30)),
    ("mill_ks", "Wichita Flour Milling Co.", PR, "grains", "flour", "United States", "Kansas", 37.7, -97.3, 340, dict(inv=30)),
    ("rmill_mk", "Can Tho Rice Milling", PR, "rice", "milled_rice", "Vietnam", "Mekong Delta", 10.05, 105.8, 260, dict(inv=30)),
    ("rmill_hr", "Karnal Rice Mills", PR, "rice", "milled_rice", "India", "Haryana", 29.7, 76.98, 210, dict(inv=30)),
    ("starch_mt", "Cuiaba Maize Starch and Feed Mill", PR, "grains", "maize_starch", "Brazil", "Mato Grosso", -15.6, -56.1, 330, dict(inv=30)),
    ("oilpress_mt", "Rondonopolis Oilseed Crushing", PR, "edible_oils", "soybean_oil", "Brazil", "Mato Grosso", -16.5, -54.6, 420, dict(inv=25)),
    ("refinery_sp", "Ribeirao Preto Sugar Refinery", PR, "sugar", "refined_sugar", "Brazil", "Sao Paulo State", -21.15, -47.8, 460, dict(inv=3)),
    ("refinery_up", "Lucknow Sugar Mills", PR, "sugar", "refined_sugar", "India", "Uttar Pradesh", 26.85, 80.9, 270, dict(inv=3)),
    ("coffee_proc_mg", "Varginha Coffee Hulling and Export", PR, "coffee", "green_coffee", "Brazil", "Minas Gerais", -21.55, -45.4, 300, dict(inv=10)),
    ("coffee_proc_dl", "Buon Ma Thuot Coffee Processing", PR, "coffee", "green_coffee", "Vietnam", "Central Highlands", 12.67, 108.04, 190, dict(inv=10)),
    ("cocoa_grind_ci", "San-Pedro Cocoa Grinding", PR, "cocoa", "cocoa_mass", "Cote d'Ivoire", "Bas-Sassandra", 4.75, -6.65, 340, dict(alt=0.20, inv=35)),
    ("dairy_proc_fr", "Leeuwarden Milk Processing", PR, "dairy", "processed_milk", "Netherlands", "Friesland", 53.2, 5.8, 480, dict(inv=2, alt=0.15)),
    ("dairy_proc_wi", "Green Bay Dairy Processing", PR, "dairy", "processed_milk", "United States", "Wisconsin", 44.5, -88.0, 520, dict(inv=2, alt=0.15)),
    ("juice_proc_sp", "Araraquara Juice Concentrate Plant", PR, "fruit_veg", "juice_concentrate", "Brazil", "Sao Paulo State", -21.8, -48.2, 280, dict(inv=7)),
    ("fruit_proc_cv", "Fresno Fruit Processing", PR, "fruit_veg", "fruit_pulp", "United States", "California", 36.75, -119.7, 270, dict(inv=5)),
    ("veg_proc_cv", "Salinas Fresh-Cut and Frozen Vegetables", PR, "fruit_veg", "prepared_veg", "United States", "California", 36.68, -121.65, 240, dict(inv=4)),
    ("oilrefine_sm", "Dumai Palm Oil Refinery", PR, "edible_oils", "refined_palm_oil", "Indonesia", "Riau", 1.68, 101.45, 440, dict(inv=7)),
    ("oilmill_an", "Jaen Olive Oil Mill", PR, "edible_oils", "olive_oil", "Spain", "Andalusia", 37.8, -3.8, 230, dict(inv=20)),
    ("oilblend_nl", "Rotterdam Edible Oil Blending", PR, "edible_oils", "edible_oil_blend", "Netherlands", "South Holland", 51.95, 4.1, 400, dict(inv=18)),
    ("malt_de", "Bavarian Malting House", PR, "beverages", "malt", "Germany", "Bavaria", 48.4, 11.7, 190, {}),
    # ---- manufacturing
    ("bakery_uk", "Thames Valley Bakery Group", MF, "grains", "packaged_bakery", "United Kingdom", "South East England", 51.5, -0.9, 620, {}),
    ("biscuit_in", "Ludhiana Biscuits and Snacks", MF, "grains", "packaged_snacks", "India", "Punjab", 30.88, 75.9, 330, {}),
    ("noodle_vn", "Saigon Rice Noodle Maker", MF, "rice", "packaged_noodles", "Vietnam", "Ho Chi Minh City", 10.8, 106.7, 210, {}),
    ("cereal_us", "Kansas City Cereal Co.", MF, "grains", "breakfast_cereal", "United States", "Missouri", 39.1, -94.6, 700, {}),
    ("softdrink_br", "Paulinia Soft-Drink Bottler", MF, "beverages", "soft_drinks", "Brazil", "Sao Paulo State", -22.75, -47.15, 780, dict(inv=14)),
    ("softdrink_us", "Atlanta Beverage Bottling", MF, "beverages", "soft_drinks", "United States", "Georgia", 33.75, -84.4, 900, dict(inv=14)),
    ("juice_us", "Sacramento Juice and Smoothie Co.", MF, "beverages", "fruit_juice", "United States", "California", 38.6, -121.5, 480, dict(inv=10)),
    ("brewery_de", "Munich Brewing Company", MF, "beverages", "beer", "Germany", "Bavaria", 48.15, 11.55, 600, {}),
    ("roaster_de", "Hamburg Coffee Roasters", MF, "coffee", "roasted_coffee", "Germany", "Hamburg", 53.55, 10.0, 520, dict(inv=35)),
    ("roaster_us", "Seattle Specialty Roasters", MF, "coffee", "roasted_coffee", "United States", "Washington", 47.6, -122.3, 400, dict(inv=35)),
    ("choc_be", "Antwerp Chocolatier", MF, "cocoa", "chocolate", "Belgium", "Flanders", 51.2, 4.4, 640, dict(alt=0.30, inv=28)),
    ("dairy_pack_nl", "Utrecht Cheese and Yogurt Maker", MF, "dairy", "packaged_dairy", "Netherlands", "Utrecht", 52.1, 5.1, 590, dict(inv=4)),
    ("dairy_pack_us", "Chicago Dairy Products Co.", MF, "dairy", "packaged_dairy", "United States", "Illinois", 41.85, -87.65, 610, dict(inv=4)),
    ("readymeal_uk", "Manchester Ready-Meal Maker", MF, "prepared_foods", "ready_meals", "United Kingdom", "North West England", 53.48, -2.24, 520, dict(inv=8)),
    ("cookoil_in", "Mumbai Cooking Oil Packers", MF, "edible_oils", "packaged_cooking_oil", "India", "Maharashtra", 19.1, 72.9, 360, {}),
    ("snack_us", "Dallas Snack Foods", MF, "grains", "packaged_snacks", "United States", "Texas", 32.8, -96.8, 540, {}),
    # ---- packaging
    ("glass_eu", "Lorraine Glass Bottle Works", PK, "packaging", "glass_bottles", "France", "Grand Est", 48.7, 6.2, 330, dict(v=(0.35, 0.45, 0.10))),
    ("can_us", "Ohio Aluminium Can Plant", PK, "packaging", "aluminium_cans", "United States", "Ohio", 40.0, -82.9, 450, {}),
    ("can_br", "Campinas Aluminium Can Plant", PK, "packaging", "aluminium_cans", "Brazil", "Sao Paulo State", -22.9, -47.06, 330, {}),
    ("carton_eu", "Nordic Paperboard and Cartons", PK, "packaging", "paper_cartons", "Sweden", "Stockholm", 59.3, 18.0, 420, {}),
    ("flex_asia", "Penang Flexible Packaging", PK, "packaging", "flexible_packaging", "Malaysia", "Penang", 5.4, 100.3, 300, {}),
    ("pet_us", "Charlotte Food-Grade PET Packaging", PK, "packaging", "pet_containers", "United States", "North Carolina", 35.2, -80.8, 310, {}),
    # ---- logistics and storage
    ("cold_nl", "Venlo Cold Store", CS, "logistics", "cold_storage_service", "Netherlands", "Limburg", 51.37, 6.17, 160, {}),
    ("cold_uk", "Northampton Chilled Warehouse", CS, "logistics", "cold_storage_service", "United Kingdom", "East Midlands", 52.24, -0.9, 150, {}),
    ("cold_us", "Memphis Refrigerated Warehouse", CS, "logistics", "cold_storage_service", "United States", "Tennessee", 35.15, -90.05, 170, {}),
    ("cold_ca", "Fresno Cold-Chain Hub", CS, "logistics", "cold_storage_service", "United States", "California", 36.73, -119.8, 120, {}),
    ("cold_br", "Campinas Cold Store", CS, "logistics", "cold_storage_service", "Brazil", "Sao Paulo State", -22.9, -47.1, 110, {}),
    ("cold_in", "Ludhiana Cold Chain", CS, "logistics", "cold_storage_service", "India", "Punjab", 30.9, 75.85, 90, {}),
    ("reefer_eu", "Eurolink Reefer Haulage", TR, "logistics", "transport_service", "Netherlands", "Gelderland", 51.9, 5.9, 260, {}),
    ("rail_us", "Heartland Grain and Freight Rail", TR, "logistics", "rail_freight", "United States", "Kansas", 39.1, -96.0, 480, dict(v=(0.60, 0.25, 0.10))),
    ("truck_uk", "Midlands Food Haulage", TR, "logistics", "transport_service", "United Kingdom", "West Midlands", 52.5, -1.8, 230, {}),
    ("truck_in", "Punjab Freight Carriers", TR, "logistics", "transport_service", "India", "Punjab", 30.8, 76.0, 140, {}),
    ("port_santos", "Port of Santos Terminal Operator", PO, "logistics", "port_service", "Brazil", "Sao Paulo State", -23.95, -46.3, 600, {}),
    ("port_rtm", "Rotterdam Terminal Operator", PO, "logistics", "port_service", "Netherlands", "South Holland", 51.95, 4.05, 750, {}),
    ("port_nsw", "Nhava Sheva Terminal Operator", PO, "logistics", "port_service", "India", "Maharashtra", 18.95, 72.95, 550, {}),
    ("port_hcm", "Cat Lai Terminal Operator", PO, "logistics", "port_service", "Vietnam", "Ho Chi Minh City", 10.77, 106.8, 400, {}),
    ("port_abj", "Abidjan Port Terminal Operator", PO, "logistics", "port_service", "Cote d'Ivoire", "Abidjan", 5.3, -4.0, 280, {}),
    ("dc_uk", "Daventry Distribution Centre", DC, "retail_distribution", "distribution_service", "United Kingdom", "East Midlands", 52.26, -1.16, 260, {}),
    ("dc_us", "Dallas Distribution Centre", DC, "retail_distribution", "distribution_service", "United States", "Texas", 32.75, -96.9, 300, {}),
    ("dc_br", "Guarulhos Distribution Centre", DC, "retail_distribution", "distribution_service", "Brazil", "Sao Paulo State", -23.45, -46.5, 240, {}),
    ("dc_in", "Gurugram Distribution Centre", DC, "retail_distribution", "distribution_service", "India", "Haryana", 28.45, 77.0, 180, {}),
    # ---- distribution and retail
    ("whl_uk", "Midshire Food Wholesale", WH, "retail_distribution", "wholesale_goods", "United Kingdom", "West Midlands", 52.48, -1.9, 400, {}),
    ("whl_us", "Continental Foodservice Distributors", WH, "retail_distribution", "wholesale_goods", "United States", "Texas", 32.9, -97.0, 650, {}),
    ("bevdist_br", "Sudeste Beverage Distributor", WH, "beverages", "beverage_distribution", "Brazil", "Sao Paulo State", -23.5, -46.6, 420, {}),
    ("bevdist_us", "Pacific Beverage Distribution", WH, "beverages", "beverage_distribution", "United States", "California", 34.05, -118.25, 560, {}),
    ("retail_uk", "Albion Supermarkets", RT, "retail_distribution", "", "United Kingdom", "England", 52.0, -1.5, 3200, {}),
    ("retail_us", "Heartland Grocers", RT, "retail_distribution", "", "United States", "Midwest", 39.0, -95.0, 4100, {}),
    ("retail_br", "Brasil Mercado Chain", RT, "retail_distribution", "", "Brazil", "Sao Paulo State", -23.55, -46.65, 2100, {}),
    ("retail_in", "Bharat Fresh Retail", RT, "retail_distribution", "", "India", "Delhi NCR", 28.6, 77.2, 1500, {}),
    ("retail_eu", "Rhineland Grocery Group", RT, "retail_distribution", "", "Germany", "North Rhine-Westphalia", 51.2, 6.8, 3600, {}),
    # ---- financial (kept out of the physical supply channel)
    ("bank_br", "Cerrado Agri-Lending Bank", FN, "finance", "financial_service", "Brazil", "n/a", None, None, 900, dict(inv=0)),
    ("insurer_eu", "Continental Crop and Cargo Insurer", FN, "finance", "financial_service", "Netherlands", "n/a", None, None, 1500, dict(inv=0)),
]

# (source, target, dependency[, specificity, substitutability]) ; dependency = share of the target's input *of that
# product* that this source provides. Remainder (1 - sum) is explicit "unmodelled suppliers".
EDGES: list[tuple] = [
    # inputs -> farms
    ("fert_in", "farm_wheat_pb", .50), ("fert_in", "farm_rice_hr", .50), ("fert_in", "farm_cane_up", .45),
    ("fert_br", "farm_maize_mt", .50), ("fert_br", "farm_soy_mt", .40), ("fert_br", "farm_cane_sp", .50),
    ("fert_br", "farm_coffee_mg", .45), ("fert_br", "farm_citrus_sp", .40),
    ("fert_eu", "farm_dairy_fr", .35), ("fert_eu", "farm_barley_de", .50),
    ("seed_us", "farm_wheat_ks", .50), ("seed_us", "farm_maize_mt", .30), ("seed_us", "farm_dairy_wi", .30), ("seed_us", "farm_veg_cv", .50),
    ("irrig_pb", "farm_wheat_pb", .85), ("irrig_pb", "farm_rice_hr", .90),
    ("irrig_cv", "farm_fruit_cv", .80), ("irrig_cv", "farm_veg_cv", .85),
    ("agfuel_br", "farm_cane_sp", .60), ("agfuel_br", "farm_maize_mt", .50), ("agfuel_br", "farm_soy_mt", .50), ("agfuel_br", "farm_coffee_mg", .30),
    # power
    ("grid_pb", "irrig_pb", .90), ("grid_pb", "mill_pb", .85), ("grid_pb", "rmill_hr", .80), ("grid_pb", "biscuit_in", .80), ("grid_pb", "cold_in", .95),
    ("grid_sp", "refinery_sp", .40), ("grid_sp", "softdrink_br", .80), ("grid_sp", "juice_proc_sp", .80), ("grid_sp", "can_br", .80), ("grid_sp", "cold_br", .95),
    ("grid_nl", "dairy_proc_fr", .85), ("grid_nl", "cold_nl", .95), ("grid_nl", "oilblend_nl", .80), ("grid_nl", "dairy_pack_nl", .85),
    ("grid_ca", "cold_ca", .95), ("grid_ca", "fruit_proc_cv", .80), ("grid_ca", "veg_proc_cv", .80), ("grid_ca", "irrig_cv", .90),
    # farms -> processors
    ("farm_wheat_pb", "mill_pb", .75), ("farm_wheat_ks", "mill_ks", .80), ("farm_rice_hr", "rmill_hr", .80), ("farm_rice_mk", "rmill_mk", .85),
    ("farm_maize_mt", "starch_mt", .80), ("farm_soy_mt", "oilpress_mt", .85), ("farm_cane_sp", "refinery_sp", .85), ("farm_cane_up", "refinery_up", .85),
    ("farm_coffee_mg", "coffee_proc_mg", .85), ("farm_coffee_dl", "coffee_proc_dl", .85), ("farm_cocoa_ci", "cocoa_grind_ci", .90),
    ("farm_dairy_fr", "dairy_proc_fr", .90), ("farm_dairy_wi", "dairy_proc_wi", .90), ("farm_fruit_cv", "fruit_proc_cv", .70),
    ("farm_veg_cv", "veg_proc_cv", .80), ("farm_citrus_sp", "juice_proc_sp", .85), ("farm_olive_an", "oilmill_an", .85),
    ("farm_palm_sm", "oilrefine_sm", .90), ("farm_barley_de", "malt_de", .85),
    # processors -> manufacturers
    ("mill_pb", "biscuit_in", .75), ("mill_pb", "bakery_uk", .25), ("mill_ks", "bakery_uk", .30), ("mill_ks", "cereal_us", .60),
    ("rmill_mk", "noodle_vn", .80), ("rmill_mk", "readymeal_uk", .30), ("rmill_hr", "readymeal_uk", .25),
    ("refinery_sp", "softdrink_br", .60), ("refinery_sp", "softdrink_us", .20), ("refinery_sp", "choc_be", .30),
    ("refinery_sp", "bakery_uk", .35), ("refinery_sp", "cereal_us", .25), ("refinery_up", "biscuit_in", .55),
    ("refinery_up", "choc_be", .15), ("refinery_up", "readymeal_uk", .20),
    ("starch_mt", "softdrink_br", .25), ("starch_mt", "softdrink_us", .30), ("starch_mt", "snack_us", .30), ("starch_mt", "cereal_us", .30),
    ("oilpress_mt", "cookoil_in", .35), ("oilpress_mt", "oilblend_nl", .10), ("oilpress_mt", "snack_us", .30),
    ("oilrefine_sm", "cookoil_in", .45), ("oilrefine_sm", "oilblend_nl", .50), ("oilrefine_sm", "biscuit_in", .35), ("oilrefine_sm", "snack_us", .20),
    ("oilmill_an", "oilblend_nl", .30), ("oilblend_nl", "bakery_uk", .35), ("oilblend_nl", "readymeal_uk", .40), ("oilblend_nl", "retail_eu", .30),
    ("coffee_proc_mg", "roaster_de", .45), ("coffee_proc_dl", "roaster_de", .30), ("coffee_proc_mg", "roaster_us", .55), ("coffee_proc_dl", "roaster_us", .25),
    ("cocoa_grind_ci", "choc_be", .75), ("cocoa_grind_ci", "biscuit_in", .10),
    ("dairy_proc_fr", "dairy_pack_nl", .85), ("dairy_proc_fr", "choc_be", .30), ("dairy_proc_fr", "readymeal_uk", .25),
    ("dairy_proc_wi", "dairy_pack_us", .85),
    ("juice_proc_sp", "softdrink_br", .25), ("juice_proc_sp", "juice_us", .45), ("fruit_proc_cv", "juice_us", .50),
    ("fruit_proc_cv", "cereal_us", .10), ("fruit_proc_cv", "dairy_pack_us", .20),
    ("veg_proc_cv", "readymeal_uk", .30), ("veg_proc_cv", "whl_us", .50), ("malt_de", "brewery_de", .80),
    # packaging
    ("glass_eu", "brewery_de", .60), ("glass_eu", "softdrink_br", .15), ("glass_eu", "juice_us", .20),
    ("can_us", "softdrink_us", .55), ("can_br", "softdrink_br", .60),
    ("carton_eu", "dairy_pack_nl", .50), ("carton_eu", "bakery_uk", .30), ("carton_eu", "readymeal_uk", .40), ("carton_eu", "choc_be", .35),
    ("carton_eu", "juice_us", .30), ("carton_eu", "cereal_us", .20),
    ("pet_us", "softdrink_us", .35), ("pet_us", "juice_us", .30), ("pet_us", "dairy_pack_us", .50), ("pet_us", "snack_us", .30), ("pet_us", "cereal_us", .20),
    ("flex_asia", "biscuit_in", .50), ("flex_asia", "noodle_vn", .60), ("flex_asia", "snack_us", .35), ("flex_asia", "cookoil_in", .50),
    ("flex_asia", "bakery_uk", .15), ("flex_asia", "choc_be", .15), ("flex_asia", "readymeal_uk", .20), ("flex_asia", "dairy_pack_nl", .15),
    # cold chain, transport, ports
    ("cold_nl", "dairy_pack_nl", .50), ("cold_nl", "retail_eu", .40), ("cold_uk", "readymeal_uk", .50), ("cold_uk", "bakery_uk", .20),
    ("cold_uk", "dc_uk", .40), ("cold_uk", "retail_uk", .30), ("cold_us", "dairy_pack_us", .50), ("cold_us", "dc_us", .35),
    ("cold_us", "whl_us", .30), ("cold_us", "retail_us", .25), ("cold_ca", "veg_proc_cv", .60), ("cold_ca", "fruit_proc_cv", .50),
    ("cold_ca", "juice_us", .35), ("cold_ca", "whl_us", .20), ("cold_br", "dc_br", .40), ("cold_br", "retail_br", .35),
    ("cold_in", "retail_in", .40), ("cold_in", "dc_in", .50),
    ("cold_nl", "reefer_eu", .20),  # intentional feedback loop (reefer fleet staged at the cold store) -> cycle for testing
    ("reefer_eu", "cold_nl", .30), ("reefer_eu", "dairy_pack_nl", .35), ("reefer_eu", "retail_eu", .40), ("reefer_eu", "choc_be", .30), ("reefer_eu", "whl_uk", .15),
    ("rail_us", "mill_ks", .55), ("rail_us", "cereal_us", .30), ("rail_us", "snack_us", .35), ("rail_us", "dc_us", .40), ("rail_us", "softdrink_us", .25),
    ("truck_uk", "dc_uk", .60), ("truck_uk", "retail_uk", .50), ("truck_uk", "whl_uk", .50), ("truck_uk", "bakery_uk", .35),
    ("truck_in", "dc_in", .60), ("truck_in", "retail_in", .50), ("truck_in", "biscuit_in", .40), ("truck_in", "mill_pb", .30), ("truck_in", "rmill_hr", .30),
    ("port_santos", "coffee_proc_mg", .60), ("port_santos", "refinery_sp", .50), ("port_santos", "starch_mt", .40), ("port_santos", "oilpress_mt", .50),
    ("port_santos", "juice_proc_sp", .50), ("port_santos", "dc_br", .30),
    ("port_rtm", "oilblend_nl", .70), ("port_rtm", "choc_be", .40), ("port_rtm", "roaster_de", .50), ("port_rtm", "bakery_uk", .30),
    ("port_rtm", "dairy_proc_fr", .20), ("port_rtm", "retail_eu", .20),
    ("port_nsw", "cookoil_in", .70), ("port_nsw", "rmill_hr", .50), ("port_nsw", "mill_pb", .35), ("port_nsw", "biscuit_in", .30),
    ("port_hcm", "rmill_mk", .60), ("port_hcm", "coffee_proc_dl", .60), ("port_hcm", "noodle_vn", .40),
    ("port_abj", "cocoa_grind_ci", .80),
    # manufacturers -> distribution -> retail
    ("bakery_uk", "dc_uk", .50), ("readymeal_uk", "dc_uk", .40), ("dairy_pack_nl", "dc_uk", .20), ("choc_be", "dc_uk", .20),
    ("dc_uk", "retail_uk", .85), ("dc_uk", "whl_uk", .30), ("whl_uk", "retail_uk", .15), ("bakery_uk", "retail_uk", .30), ("bakery_uk", "whl_uk", .25),
    ("dairy_pack_nl", "retail_eu", .50), ("dairy_pack_nl", "whl_uk", .30), ("choc_be", "retail_eu", .40), ("choc_be", "whl_uk", .30), ("choc_be", "whl_us", .25),
    ("brewery_de", "retail_eu", .50), ("brewery_de", "whl_uk", .30), ("brewery_de", "whl_us", .20),
    ("roaster_de", "retail_eu", .50), ("roaster_de", "whl_uk", .30), ("roaster_de", "retail_uk", .20), ("roaster_us", "retail_us", .30), ("roaster_us", "whl_us", .40),
    ("cereal_us", "dc_us", .60), ("cereal_us", "whl_us", .30), ("snack_us", "dc_us", .50), ("dairy_pack_us", "dc_us", .50),
    ("softdrink_us", "bevdist_us", .80), ("juice_us", "bevdist_us", .50), ("softdrink_br", "bevdist_br", .85), ("softdrink_br", "dc_br", .30),
    ("bevdist_br", "retail_br", .60), ("dc_br", "retail_br", .60), ("bevdist_us", "retail_us", .40), ("bevdist_us", "whl_us", .30),
    ("dc_us", "retail_us", .85), ("dc_us", "whl_us", .30), ("whl_us", "retail_us", .15),
    ("biscuit_in", "dc_in", .50), ("cookoil_in", "dc_in", .50), ("dc_in", "retail_in", .85), ("rmill_hr", "retail_in", .30), ("mill_pb", "retail_in", .35),
    ("noodle_vn", "whl_us", .10),
]

# Financial/operational channel: displayed, NOT propagated through the physical supply channel (documented).
FINANCIAL_EDGES = [
    ("bank_br", "farm_maize_mt", .30), ("bank_br", "farm_soy_mt", .30), ("bank_br", "farm_cane_sp", .30), ("bank_br", "farm_coffee_mg", .30),
    ("insurer_eu", "cold_nl", .40), ("insurer_eu", "dairy_pack_nl", .40), ("insurer_eu", "port_rtm", .40), ("insurer_eu", "reefer_eu", .40),
]

# Demo portfolio: synthetic holdings (equal weight) used for the network-vs-location hidden-exposure comparison.
PORTFOLIO = ["bakery_uk", "readymeal_uk", "softdrink_br", "softdrink_us", "brewery_de", "choc_be", "dairy_pack_nl",
             "dairy_pack_us", "cereal_us", "snack_us", "roaster_de", "roaster_us", "retail_uk", "retail_us", "retail_eu",
             "retail_in", "biscuit_in", "juice_us"]

# Company structures (SYNTHETIC). A listed holding is a company. Most here own one business unit; these own several
# (segments), each an ordinary entity of the network. other_businesses_share = share of the company's value added in
# businesses OUTSIDE the Food & Beverage scope: a single number, never modelled (no nodes, no links, no hazard), so it can
# only dilute the F&B loss at company level. Shares of the modelled segments come from entity value added at load time.
# Patterns are stylised; names and numbers are invented and describe no real company.
COMPANIES = [
    ("co_five_rivers", "Five Rivers Consumer Group",
     [("biscuit_in", "Biscuits and snacks"), ("mill_pb", "Flour milling"), ("cookoil_in", "Packaged cooking oil")], 0.55,
     "Diversified consumer group: packaged foods and an own flour mill, plus large businesses outside food and beverage (not modelled)"),
    ("co_lone_star", "Lone Star Snacks and Beverages",
     [("snack_us", "Snacks"), ("softdrink_us", "Soft drinks"), ("juice_us", "Juices")], 0.0,
     "Multi-category food and beverage group: three product lines in three US regions"),
    ("co_great_plains", "Great Plains Foods",
     [("cereal_us", "Breakfast cereal"), ("mill_ks", "Flour milling")], 0.0,
     "Vertically integrated: owns the flour mill that supplies its cereal plant"),
    ("co_lowlands_dairy", "Lowlands Dairy Group",
     [("dairy_pack_nl", "Cheese and yogurt"), ("dairy_proc_fr", "Milk processing")], 0.0,
     "Vertically integrated: owns the milk plant that supplies its packing plant"),
]


def haversine(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def r2(x: float) -> float:
    return round(float(x), 3)


def build() -> tuple[list[dict], list[dict], dict]:
    rng = random.Random(SEED)
    ents: list[dict] = []
    by_id: dict[str, dict] = {}
    for (eid, name, etype, cat, prod, country, region, lat, lon, rev, ov) in ENTITIES:
        d = TYPE_DEFAULTS[etype]
        v = ov.get("v", d["v"])
        jit = lambda x, s=0.05: min(1.0, max(0.0, x + rng.uniform(-s, s)))  # noqa: E731
        va = d["va"]
        price = PRICE_PER_TONNE.get(prod)
        has_geo = lat is not None
        e = {
            "id": eid, "name": name, "synthetic": True, "entity_type": etype, "food_category": cat,
            "output_product": prod or None, "country": country, "region": region,
            "latitude": lat, "longitude": lon,
            "location_status": "synthetic_approximate" if has_geo else "missing_headquarters_only",
            "facility_type": d["fac"], "revenue_musd": float(rev), "value_added_musd": r2(rev * va),
            "capacity_tonnes_per_year": round(rev * 1e6 / price, -2) if price else None,
            "inventory_days": float(ov.get("inv", d["inv"])),
            "alternative_supplier_availability": r2(ov.get("alt", jit(d["alt"]))),
            "operational_criticality": r2(ov.get("crit", jit(d["crit"], 0.08))),
            "spare_capacity_fraction": r2(d["spare"]),
            "exposed_asset_share": r2(min(1.0, jit(0.9, 0.1))) if has_geo else None,
            "flood_vulnerability": r2(jit(v[0])), "heat_vulnerability": r2(jit(v[1])), "drought_vulnerability": r2(jit(v[2])),
            "provenance": "synthetic: generated by backend/data/generate_dataset.py (seed %d); not a real company" % SEED,
            "confidence": "low",
            "in_demo_portfolio": eid in PORTFOLIO,
        }
        ents.append(e)
        by_id[eid] = e
    # edges
    n_products_in: dict[str, set] = {}
    for ed in EDGES:
        n_products_in.setdefault(ed[1], set()).add(by_id[ed[0]]["output_product"])
    edges: list[dict] = []
    for ed in EDGES + FINANCIAL_EDGES:
        s, t, dep = ed[0], ed[1], ed[2]
        src, tgt = by_id[s], by_id[t]
        financial = src["entity_type"] == "financial"
        prod = src["output_product"]
        spec, sub, storable = PRODUCTS[prod]
        spec = ed[3] if len(ed) > 3 else spec
        sub = ed[4] if len(ed) > 4 else sub
        if src["latitude"] is not None and tgt["latitude"] is not None:
            dist = haversine(src["latitude"], src["longitude"], tgt["latitude"], tgt["longitude"])
        else:
            dist = None
        if not storable:
            lead = 0.0
        elif src["country"] == tgt["country"]:
            lead = 2.0
        else:
            lead = min(45.0, 7.0 + (dist or 5000.0) / 800.0)
        n_prod = max(1, len(n_products_in.get(t, {prod})))
        flow = dep * tgt["revenue_musd"] * (1 - TYPE_DEFAULTS[tgt["entity_type"]]["va"]) * 0.8 / n_prod
        edges.append({
            "id": f"{s}->{t}", "source": s, "target": t, "product": prod,
            "channel": "financial" if financial else "supply",
            "relationship_type": rel_type(src["entity_type"], tgt["entity_type"]),
            "dependency": dep, "input_specificity": spec, "substitutability": sub,
            "storable": storable, "lead_time_days": round(lead, 1),
            "annual_flow_musd": r2(flow),
            "distance_km": round(dist) if dist is not None else None,
            "status": "synthetic", "confidence": r2(rng.uniform(0.35, 0.65)),
            "provenance": "synthetic: stylised commodity/logistics pattern; not a disclosed contract",
        })
    manifest = {"seed": SEED, "n_entities": len(ents), "n_edges": len(edges)}
    return ents, edges, manifest


def rel_type(a: str, b: str) -> str:
    if a == "financial":
        return "finance_or_insurance"
    if a in ("cold_storage", "transport_operator", "port_hub", "distribution_centre"):
        return "logistics_service"
    if a == "utility":
        return "utility_supply"
    if a == "packaging_supplier":
        return "packaging_supply"
    if a == "agricultural_input":
        return "agri_input_supply"
    if a == "agricultural_producer":
        return "raw_material_supply"
    return "product_supply"


def scenarios() -> list[dict]:
    def comp(h, i, dur, lat=None, lon=None, rad=None, regions=None, ents=None, label=""):
        return {"hazard_type": h, "intensity": i, "duration_days": dur, "center_lat": lat, "center_lon": lon,
                "radius_km": rad, "regions": regions or [], "affected_entity_ids": ents or [], "label": label}

    base = dict(time_horizon_year=2035, data_source="synthetic_footprint", propagation_max_depth=6,
                inventory_scale=1.0, substitution_scale=1.0, dependency_scale=1.0, compound_amplification=0.0,
                monte_carlo_runs=500, monte_carlo_seed=42, builtin=True, synthetic=True)
    return [
        {**base, "id": "sc_punjab_flood", "name": "Punjab-Haryana Monsoon Flood",
         "description": "Synthetic riverine flood footprint over the Punjab/Haryana wheat-rice belt (SYNTHETIC footprint, not a hazard map).",
         "hazards": [comp("flood", 0.75, 21, 30.4, 76.2, 120, label="Monsoon flood")]},
        {**base, "id": "sc_brazil_drought", "name": "Southeast Brazil Multi-Season Drought",
         "description": "Synthetic drought over Sao Paulo / Minas Gerais affecting sugarcane, coffee and citrus.",
         "hazards": [comp("drought", 0.65, 120, -21.5, -47.0, 350, label="Multi-season drought")]},
        {**base, "id": "sc_ca_heatwave", "name": "California Central Valley Heatwave",
         "description": "Synthetic extreme-heat event over orchards, vegetables, cold storage and the local grid.",
         "hazards": [comp("heat", 0.80, 14, 36.7, -119.8, 250, label="Extreme heat")]},
        {**base, "id": "sc_mekong_flood", "name": "Mekong Delta Flood",
         "description": "Synthetic delta flood affecting rice, coffee highlands margin and the Cat Lai terminal.",
         "hazards": [comp("flood", 0.70, 28, 10.4, 106.0, 160, label="Delta flood")]},
        {**base, "id": "sc_nweurope_compound", "name": "NW Europe Compound Heat then Drought",
         "description": "Synthetic consecutive heat and drought. The 10% compound amplification is an analyst assumption, not an estimate.",
         "compound_amplification": 0.10,
         "hazards": [comp("heat", 0.60, 14, 52.0, 5.5, 350, label="Heatwave"), comp("drought", 0.55, 60, 52.0, 5.5, 350, label="Following drought")]},
        {**base, "id": "sc_rotterdam_port_flood", "name": "Rotterdam Terminal Flood (single node)",
         "description": "Synthetic flood that disables one port node only, to expose logistics bottleneck propagation.",
         "hazards": [comp("flood", 0.90, 10, ents=["port_rtm"], label="Terminal inundation")]},
    ]


def reference_audit() -> dict:
    """Audit the supplied Sectivia files; records why they are NOT used as food data."""
    comp_path = HERE / "reference/sectivia/sectivia-companies.csv"
    rel_path = HERE / "reference/sectivia/sectivia-relations.csv"
    if not comp_path.exists():
        return {"present": False}
    with comp_path.open() as f:
        comps = list(csv.DictReader(f))
    with rel_path.open() as f:
        rels = list(csv.DictReader(f))
    sectors = Counter(c["sector"] for c in comps)
    segs = {c["segment"] for c in comps}
    food_like = sorted(s for s in segs if any(k in s.lower() for k in ("food", "beverage", "agri", "grocery", "farm")))
    linked = {r["supplier_id"] for r in rels} | {r["customer_id"] for r in rels}
    return {
        "present": True, "n_companies": len(comps), "n_relations": len(rels), "sectors": dict(sectors),
        "countries_usa_share": round(sum(c["country"] == "USA" for c in comps) / len(comps), 3),
        "companies_without_any_link": len(comps) - len(linked),
        "relations_with_source_field": sum(1 for r in rels if r.get("source")),
        "relations_with_what_field": sum(1 for r in rels if r.get("what")),
        "food_and_beverage_segments_found": food_like,
        "has_weights": False, "has_coordinates": False,
        "verdict": "No Food & Beverage coverage, no link weights, no facility coordinates: used only to test generic graph tooling.",
    }


def portfolio(ents: list[dict]) -> dict:
    """Synthetic position weights proportional to sqrt(revenue proxy): a stand-in for size weighting, NOT market caps."""
    raw = {e["id"]: math.sqrt(e["revenue_musd"]) for e in ents if e["in_demo_portfolio"]}
    tot = sum(raw.values())
    return {"name": "Synthetic F&B demo portfolio", "synthetic": True,
            "weighting": "proportional to sqrt(revenue proxy); synthetic, not market capitalisation or real holdings",
            "holdings": [{"entity_id": k, "weight": round(v / tot, 6)} for k, v in raw.items()]}


def companies() -> dict:
    """Synthetic company structures: which business units (entities) a listed holding owns, and the share of its value
    added outside the F&B scope. A company's position weight is the sum of its held units' weights in portfolio.json."""
    return {"name": "Synthetic company structures for the demo portfolio", "synthetic": True,
            "share_basis": "value_added",
            "note": ("Holdings not listed here are single-business companies. Segment shares are computed at load time from "
                     "entity value added; other_businesses_share is outside the Food & Beverage scope and never modelled."),
            "companies": [{"id": cid, "name": name, "synthetic": True, "pattern": pattern,
                           "segments": [{"entity_id": eid, "segment": seg} for eid, seg in segs],
                           "other_businesses_share": other} for cid, name, segs, other, pattern in COMPANIES]}


if __name__ == "__main__":
    ents, edges, meta = build()
    (HERE / "fnb_entities.json").write_text(json.dumps(ents, indent=1))
    (HERE / "fnb_relations.json").write_text(json.dumps(edges, indent=1))
    (HERE / "scenarios.json").write_text(json.dumps(scenarios(), indent=1))
    (HERE / "portfolio.json").write_text(json.dumps(portfolio(ents), indent=1))
    (HERE / "companies.json").write_text(json.dumps(companies(), indent=1))
    (HERE / "reference_audit.json").write_text(json.dumps(reference_audit(), indent=1))
    print(meta, "portfolio:", len(PORTFOLIO), "multi-segment companies:", len(COMPANIES))
