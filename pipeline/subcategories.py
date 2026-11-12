"""Subcategories inside the large shared categories (foods.subcategory), e.g. 肉類 -> 牛肉, 豬肉.

Runs at the end of categories.run(). Matching uses the names of the record (English name,
Chinese name, shown Chinese name incl. machine translations, Japanese name).
Rules per category are tried IN ORDER; the first match wins (so put specific rules first,
e.g. sausages before beef/pork). Foods that match no rule get '<category>.other'.
Categories that are not listed here have no subcategories.
"""
import re

# category -> [(sub id, Chinese, English, English regex, Chinese/Japanese regex), ...]
SUBS = {
    "cereals": [
        ("noodles", "麵及意粉", "Noodles & pasta",
         r"noodle|pasta|spaghetti|macaroni|udon|soba|ramen|vermicelli|lasagn|fettuccin|linguin|couscous",
         r"麵|粉絲|米粉|河粉|通粉|意粉|烏冬|うどん|そば|そうめん|ラーメン|パスタ"),
        ("breakfast", "早餐穀物及麥片", "Breakfast cereals & oats",
         r"cereal|granola|muesli|oat|bran flakes|corn flakes|porridge", r"麥片|早餐穀物|燕麥|穀物脆片|オート"),
        ("rice", "米及飯", "Rice", r"\brice\b|congee", r"米|飯|粥|こめ|めし|かゆ"),
        ("flour", "麵粉及穀物粉", "Flours & meals", r"flour|meal\b|starch|semolina|bran", r"粉|麩"),
        ("other", "其他穀物", "Other grains", None, None),
    ],
    "bakery": [
        ("biscuits", "餅乾及曲奇", "Biscuits, cookies & crackers",
         r"biscuit|cookie|cracker|wafer|rusk|pretzel|graham", r"餅乾|曲奇|梳打餅|威化|ビスケット|クラッカー|せんべい"),
        ("cakes", "蛋糕及糕點", "Cakes & pastries",
         r"cake|pastry|pastries|\bpie\b|tart|muffin|croissant|doughnut|donut|danish|scone|brownie|eclair|strudel|cheesecake|sweet roll|cinnamon roll",
         r"糕|撻|批|酥|蛋卷|冬甩|鬆餅|牛角包|ケーキ|パイ|まんじゅう|もち|餅"),
        ("bread", "麵包", "Bread & buns",
         r"bread|\bbuns?\b|\brolls?\b|bagel|toast|pita|naan|chapati|tortilla|focaccia|baguette|brioche|crumpet|paratha|roti",
         r"麵包|包|多士|餐包|パン"),
        ("other", "其他", "Other", None, None),
    ],
    "starchy": [
        ("potato", "薯仔", "Potatoes", r"potato(?!.*sweet)|french fr|hash brown|chips", r"薯仔|馬鈴薯|薯條|薯片|薯蓉|じゃがいも"),
        ("tubers", "番薯、芋頭及其他根莖", "Sweet potatoes, taro & other tubers",
         r"sweet potato|yam|taro|cassava|konjac|arrowroot|jicama", r"番薯|芋|山藥|淮山|木薯|蒟蒻|さつまいも|さといも|やまのいも|こんにゃく"),
        ("starch", "澱粉及粉製品", "Starches", r"starch|tapioca|sago|vermicelli", r"澱粉|粉|でん粉"),
        ("other", "其他", "Other", None, None),
    ],
    "legumes": [
        ("soy", "大豆及豆腐製品", "Soybeans & tofu",
         r"tofu|soy|soya|bean curd|natto|tempeh|edamame|yuba|okara", r"豆腐|豆漿|腐竹|腐皮|豆卜|納豆|大豆|黃豆|毛豆|枝豆|とうふ|なっとう|だいず"),
        ("beans", "豆類", "Beans, peas & lentils", None, None),
    ],
    "vegetables": [
        ("pickled", "醃菜及漬物", "Pickled vegetables",
         r"pickle|kimchi|sauerkraut|preserved|\bsalted\b(?! water)", r"醃|漬|榨菜|梅菜|酸菜|鹹菜|冬菜|つけ|漬"),
        ("pods_sprouts", "豆莢及芽菜", "Pods, peas & sprouts",
         r"\bpeas?\b|green bean|snap bean|string bean|runner bean|\bbeans?\b|sprout|okra",
         r"豆|芽|秋葵|さや|もやし"),
        ("fruit_veg", "瓜類、茄果及椒類", "Gourds, tomatoes & peppers",
         r"tomato|cucumber|squash|pumpkin|zucchini|courgette|melon|gourd|eggplant|aubergine|pepper|chili|chilli|marrow|corn\b|sweet corn",
         r"番茄|瓜|茄|椒|粟米|トマト|きゅうり|かぼちゃ|なす|ピーマン|とうもろこし"),
        ("root", "根莖及蔥蒜", "Roots, bulbs & stems",
         r"carrot|radish|daikon|turnip|beet|onion|garlic|leek|shallot|ginger|lotus|burdock|celeriac|parsnip|swede|rutabaga|bamboo|asparagus|celery|kohlrabi|water chestnut|scallion",
         r"蘿蔔|甘筍|紅蘿蔔|洋蔥|蔥|蒜|薑|蓮藕|牛蒡|筍|露筍|西芹|芹|馬蹄|にんじん|だいこん|たまねぎ|ねぎ|にんにく|しょうが|れんこん|ごぼう|たけのこ"),
        ("leafy", "葉菜及花菜", "Leafy greens, cabbages & flowers",
         r"lettuce|spinach|cabbage|kale|chard|choy|greens|leaf|leaves|watercress|cress|endive|arugula|rocket|broccoli|cauliflower|brussels|amaranth|mustard|collard|chicory|herb|basil|parsley|coriander|cilantro",
         r"菜|生菜|菠菜|芥蘭|莧|葉|西蘭花|椰菜|韭|香草|芫荽|キャベツ|レタス|ほうれんそう|はくさい|こまつな|ブロッコリー"),
        ("other", "其他蔬菜", "Other vegetables", None, None),
    ],
    "fungi_algae": [
        ("seaweed", "海藻", "Seaweed & algae", r"seaweed|kelp|nori|laver|agar|wakame|kombu|hijiki|spirulina|alga",
         r"海藻|海帶|紫菜|昆布|裙帶菜|羊栖菜|藻|のり|こんぶ|わかめ|ひじき|寒天"),
        ("mushrooms", "菇菌", "Mushrooms & fungi", None, None),
    ],
    "fruits": [
        ("juice", "果汁", "Fruit juices", r"juice|nectar|drink", r"汁|ジュース"),
        ("dried", "乾果", "Dried fruits", r"dried|raisin|prune|currants?\b|sultana|dehydrated", r"乾|提子乾|西梅|干"),
        ("canned", "罐頭及加工水果", "Canned & processed fruits",
         r"canned|syrup|jam|sauce|frozen|candied|preserve|pie filling|cocktail", r"罐頭|糖漿|醬|蜜餞|冷凍|雪藏"),
        ("fresh", "新鮮水果", "Fresh fruits", None, None),
    ],
    "nuts": [
        ("seeds", "種子", "Seeds", r"seed|sesame|flax|chia|pumpkin|sunflower|lotus", r"籽|芝麻|種子|蓮子|ごま|たね"),
        ("nuts", "果仁", "Nuts", None, None),
    ],
    "meat": [
        ("processed", "肉類製品", "Sausages, ham & processed meat",
         r"sausage|\bham\b|bacon|salami|luncheon|frankfurter|hot ?dog|bologna|jerky|pepperoni|corned|pastrami|pate|pâté|spam|meatball|burger|patty|patties|chorizo|prosciutto|liverwurst|bratwurst|kielbasa|wiener|cured|smoked",
         r"腸|火腿|煙肉|午餐肉|臘|肉丸|漢堡|肉餅|燒味|叉燒|肉醬|ハム|ソーセージ|ベーコン"),
        ("offal", "內臟", "Offal",
         r"liver|kidney|heart|tongue|tripe|offal|giblet|brain|sweetbread|chitterling|intestin|lung|spleen|blood|feet|trotter|tail",
         r"肝|腎|膶|心|舌|肚|腸|腦|血|豬手|豬腳|尾|內臟|レバー|もつ"),
        ("beef", "牛肉", "Beef", r"\bbeef\b|veal|\bsteak|\bcalf\b|wagyu|ox\b|oxtail", r"牛|うし|ぎゅう"),
        ("pork", "豬肉", "Pork", r"\bpork\b|\bpig\b|\bhog\b|boar|spare ?rib", r"豬|ぶた|ぶた"),
        ("lamb", "羊肉", "Lamb & mutton", r"\blamb\b|mutton|goat|sheep", r"羊|ひつじ|やぎ"),
        ("other", "其他肉類及野味", "Game & other meats", None, None),
    ],
    "poultry": [
        ("turkey", "火雞", "Turkey", r"turkey", r"火雞|しちめんちょう"),
        ("duck_goose", "鴨及鵝", "Duck & goose", r"\bduck|goose", r"鴨|鵝|あひる|がちょう|かも"),
        ("chicken", "雞", "Chicken", r"chicken|broiler|\bhen\b|capon|fowl", r"雞|にわとり|鶏"),
        ("other", "其他家禽", "Other poultry", None, None),
    ],
    "seafood": [
        ("cephalopod", "魷魚、墨魚及八爪魚", "Squid, cuttlefish & octopus",
         r"squid|cuttlefish|octopus|calamari", r"魷|墨魚|八爪魚|章魚|鎖管|花枝|いか|たこ"),
        ("crustacean", "蝦蟹", "Shrimp, prawns, crab & lobster",
         r"shrimp|prawn|crab|lobster|crayfish|crawfish|langoustine|krill", r"蝦|蟹|龍蝦|えび|かに"),
        ("shellfish", "貝類", "Clams, oysters & other shellfish",
         r"clam|oyster|mussel|scallop|abalone|cockle|whelk|conch|snail|sea urchin|sea cucumber|mollus|shellfish|periwinkle|geoduck",
         r"貝|蠔|蜆|青口|帶子|鮑|海膽|海參|螺|蛤|かき|あさり|ほたて|うに|なまこ|しじみ|はまぐり"),
        ("processed", "魚類製品", "Fish products",
         r"fish ?ball|fish ?cake|surimi|fish finger|fish stick|imitation|roe|caviar|fish paste|kamaboko|chikuwa",
         r"魚蛋|魚丸|魚餅|魚片頭|魚腐|蟹柳|魚子|魚卵|かまぼこ|ちくわ|たらこ|いくら"),
        ("fish", "魚", "Fish", None, None),
    ],
    "dairy": [
        ("yogurt", "乳酪", "Yogurt", r"yogh?urt|kefir|lassi|fromage frais", r"乳酪|優格|酸奶|ヨーグルト"),
        ("cheese", "芝士", "Cheese", r"cheese|cheddar|mozzarella|parmesan|brie|camembert|feta|ricotta|quark|paneer",
         r"芝士|起司|チーズ"),
        ("cream_butter", "忌廉及牛油", "Cream & butter", r"cream|butter|ghee|crème", r"忌廉|牛油|奶油|クリーム|バター"),
        ("milk", "奶及奶粉", "Milk & milk powder", r"milk|buttermilk", r"奶|乳|ミルク"),
        ("other", "其他奶類製品", "Other dairy", None, None),
    ],
    "sweets": [
        ("candy", "糖果及朱古力", "Candy & chocolate",
         r"candy|candies|chocolate|caramel|toffee|fudge|gum\b|lollipop|marshmallow|licorice|liquorice|nougat|praline|truffle|jelly bean|gumm",
         r"糖果|朱古力|巧克力|拖肥|香口膠|棉花糖|軟糖|キャンデー|チョコレート|キャラメル"),
        ("desserts", "甜品及雪糕", "Desserts & ice cream",
         r"ice cream|frozen|sorbet|sherbet|gelato|pudding|custard|dessert|mousse|jelly|jello|gelatin|popsicle|ice pop|frozen yogurt",
         r"雪糕|雪條|布甸|甜品|糖水|啫喱|果凍|豆花|ゼリー|プリン|アイス"),
        ("sugar_syrup", "糖、蜜糖及果醬", "Sugar, honey, syrups & jams",
         r"sugar|syrup|honey|jam|marmalade|molasses|treacle|sweetener|preserves|spread|nectar",
         r"糖|蜜|果醬|醬|シロップ|はちみつ|ジャム|さとう"),
        ("other", "其他", "Other", None, None),
    ],
    "drinks": [
        ("tea_coffee", "茶及咖啡", "Tea & coffee", r"\btea\b|coffee|espresso|latte|cappuccino|matcha|cocoa|chocolate|malt",
         r"茶|咖啡|可可|朱古力|阿華田|好立克|ちゃ|コーヒー|ココア"),
        ("juice", "果汁及蔬菜汁", "Juices", r"juice|nectar|smoothie|lemonade", r"汁|ジュース"),
        ("soft", "汽水及運動飲品", "Soft & sports drinks",
         r"soda|cola|carbonated|soft drink|sports drink|energy drink|tonic|ginger ale|root beer|lemon-lime|electrolyte",
         r"汽水|可樂|運動飲品|能量飲品|サイダー|コーラ"),
        ("milk_drink", "奶類及植物奶飲品", "Milk & plant-based drinks",
         r"milk|soy|almond|oat drink|rice drink|shake|yogh?urt drink|lassi", r"奶|豆漿|乳|ミルク|豆乳"),
        ("water", "水及其他飲品", "Water & other drinks", None, None),
    ],
    "condiments": [
        ("spices", "香料及香草", "Spices & herbs",
         r"spice|herb|pepper|cinnamon|cumin|curry powder|paprika|turmeric|oregano|thyme|basil|parsley|nutmeg|clove|anise|cardamom|seasoning|powder|mustard seed|bay leaf|saffron|vanilla",
         r"香料|胡椒|肉桂|玉桂|八角|咖喱粉|五香|香草|丁香|孜然|調味粉|粉"),
        ("salt", "鹽及調味料", "Salt, stock & seasonings", r"\bsalt\b|bouillon|stock|msg|monosodium|yeast extract|vinegar",
         r"鹽|味精|雞粉|湯塊|醋|酢|しお"),
        ("sauces", "醬料", "Sauces, dressings & dips", None, None),
    ],
    "dishes": [
        ("fast_food", "快餐及連鎖餐廳", "Fast food & restaurant chains",
         r"fast food|restaurant|mcdonald|burger king|kfc|wendy|subway|taco bell|pizza hut|domino|papa john|carrabba|olive garden|denny|applebee|chick-fil|popeye|arby|dairy queen|sonic|jack in the box|little caesar|t\.g\.i|chain",
         r"快餐|餐廳|麥當勞|肯德基|漢堡王"),
        ("dim_sum", "點心及中式小食", "Dim sum & Chinese snacks",
         r"dim sum|dumpling|siu mai|spring roll|wonton|bao\b|cheung fun|turnip cake|glutinous",
         r"點心|燒賣|蝦餃|春卷|雲吞|餃|包|腸粉|蘿蔔糕|糯米雞|粽|糕"),
        ("rice_noodle", "飯、麵及粥", "Rice, noodle & congee dishes",
         r"fried rice|rice dish|risotto|paella|congee|noodle|chow mein|lo mein|pad thai|spaghetti|lasagn|macaroni|pasta|biryani|pilau|pilaf",
         r"飯|麵|粥|粉|意粉|通粉|米粉|河"),
        ("sandwich_pizza", "三文治、漢堡及薄餅", "Sandwiches, burgers & pizza",
         r"sandwich|burger|pizza|hot dog|wrap|burrito|taco|quesadilla|sub\b|panini|toast",
         r"三文治|漢堡|薄餅|熱狗|卷餅|多士"),
        ("frozen_ready", "即食及急凍餐", "Ready & frozen meals",
         r"frozen|ready meal|entree|tv dinner|microwave|canned|meal kit|lunchable|instant",
         r"急凍|即食|冷凍|罐頭|微波"),
        ("other", "其他菜式", "Other dishes", None, None),
    ],
    "baby": [
        ("formula", "嬰兒配方奶", "Infant formula", r"formula|infant milk", r"配方|奶粉"),
        ("food", "嬰兒食品", "Baby foods", None, None),
    ],
}
COMPILED = {c: [(sid, zh, en, re.compile(e, re.I) if e else None, re.compile(z) if z else None)
                for sid, zh, en, e, z in subs] for c, subs in SUBS.items()}


def rows():
    """(id, category, name_zh, name_en, sort_order) for the subcategories table."""
    out = []
    for c, subs in SUBS.items():
        for i, (sid, zh, en, *_rest) in enumerate(subs):
            out.append((f"{c}.{sid}", c, zh, en, i))
    return out


def sub_for(category, name_en, names_zh):
    subs = COMPILED.get(category)
    if not subs:
        return None
    for sid, _zh, _en, en_pat, zh_pat in subs:
        if en_pat is None and zh_pat is None:
            return f"{category}.{sid}"
        if (en_pat and name_en and en_pat.search(name_en)) or (zh_pat and any(zh_pat.search(n) for n in names_zh if n)):
            return f"{category}.{sid}"
    return f"{category}.{subs[-1][0]}"
