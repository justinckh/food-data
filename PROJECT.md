# Food Data Project

This document is in ASD-STE100 Simplified Technical English.

Last update: 2026-11-12.

## 1. Purpose

This project collects food composition data from public sources.
It puts the data into one database.
A web site shows the data to users.
Other systems and AI tools will also use the data.

## 2. Current status

### 2.1 Summary

| Item | Status |
|---|---|
| Web site on Cloudflare Pages | The live site is the old static site. The new site with the API is on the preview address (section 4.4). |
| Data source: Hong Kong CFS | Done. The data has 2,999 foods. |
| Local database (`data/food.db`) | Done. It has all sources: 26,480 foods. |
| Search | Done. The API searches the names and the synonyms (section 3.4). |
| Data source: Taiwan TFDA | Done. The data has 2,213 foods (section 2.6). |
| Data source: Japan MEXT | Done. The data has 2,538 foods (section 2.7). |
| Data source: Australia AFCD | Done. The data has 1,588 foods (section 2.8). |
| Data source: USDA (Foundation Foods, SR Legacy) | Done. The data has 8,262 foods (section 2.5). |
| Data source: UK CoFID | Done. The data has 2,887 foods (section 2.9). |
| Data source: Canada CNF | Done. The data has 5,993 foods (section 2.10). |
| Backend API | Done. It is on the preview address (section 4.4). |
| Cloudflare D1 | Done. The database `food-data` has all data. |
| Other data sources | France Ciqual is on hold (section 4.3). |

### 2.2 Files and folders

| Path | Content |
|---|---|
| `scrape_cfs.py` | This script gets the food data from the CFS web site. It writes `cfs_foods.csv`. |
| `cfs_foods.csv` | The CFS data. It has one row for each food. Values are for 100 g. |
| `cache/` | The script keeps the CFS web pages here. Git does not keep this folder. |
| `site/` | The web site files. `app.js` gets the data from the API. |
| `functions/` | The API (Cloudflare Pages Functions). Section 4.4 gives the endpoints. |
| `wrangler.jsonc` | The Cloudflare configuration: the Pages project and the D1 database. |
| `pipeline/display.py` | This script makes the food groups, the main record of each group and the display names (section 3.9). |
| `pipeline/export_d1.py` | This script makes the SQL file for D1: `data/export/d1.sql`. |
| `db/schema.sql` | The database tables. |
| `pipeline/common.py` | The nutrient list, the value parser and the search text function. |
| `pipeline/importers/cfs.py` | This importer reads `cfs_foods.csv` for the database. |
| `pipeline/importers/tfda.py` | This importer reads the TFDA zip file in `data/raw/tfda/`. |
| `pipeline/download_tfda.py` | This script downloads the TFDA zip file to `data/raw/tfda/`. |
| `pipeline/importers/mext.py` | This importer reads the MEXT Excel files in `data/raw/mext/`. |
| `pipeline/download_mext.py` | This script downloads the MEXT Excel files to `data/raw/mext/`. |
| `pipeline/importers/afcd.py` | This importer reads the AFCD Excel files in `data/raw/afcd/`. |
| `pipeline/download_afcd.py` | This script downloads the AFCD Excel files to `data/raw/afcd/`. |
| `pipeline/importers/cofid.py` | This importer reads the CoFID Excel file in `data/raw/cofid/`. |
| `pipeline/importers/cofid_groups.csv` | The CoFID food group names. We copied them from Appendix B of the CoFID 2021 user guide. |
| `pipeline/download_cofid.py` | This script downloads the CoFID Excel file to `data/raw/cofid/`. |
| `pipeline/importers/cnf.py` | This importer reads the CNF zip file in `data/raw/cnf/`. |
| `pipeline/importers/usda.py` | This importer reads the USDA zip files in `data/raw/usda/`. It does not extract the zip files. |
| `pipeline/download_usda.py` | This script downloads the newest USDA zip files to `data/raw/usda/`. |
| `pipeline/link.py` | This script finds the duplicates and records them in `food_links`. The build runs it after the import. |
| `pipeline/synonyms.py` | This script uses the synonym table for search and for links (section 3.7). |
| `pipeline/synonyms.csv` | The synonym table. Each row is 1 food concept with the words for HK, TW, CN, JA and EN. |
| `pipeline/synonyms_ambiguous.csv` | Words that have different meanings in different regions, and our decision for each word. |
| `pipeline/build_db.py` | This script makes `data/food.db` from all importers. If the files for a source are missing, the script does not import that source. |
| `data/raw/` | The downloaded source files. Git does not keep this folder. |
| `data/food.db` | The master copy of the database. Git does not keep this file. You can make it again at any time. |
| `PROJECT.md` | This document. |

### 2.3 Commands

| Command | Result |
|---|---|
| `npm run download:tfda` | Downloads the TFDA file. Use the same type of command for `mext`, `afcd`, `usda` and `cofid`. |
| `npm run scrape` | Gets the CFS data again. It writes `cfs_foods.csv`. |
| `npm run db` | Makes `data/food.db` from all sources. |
| `npm run export` | Makes the D1 file `data/export/d1.sql` from `data/food.db`. |
| `npm run build` | Does `npm run db` and then `npm run export`. |
| `npm run load:local` | Puts `d1.sql` into the local D1 database (on your computer). |
| `npm run update:plan` | Compares `data/food.db` with the data on D1. Writes the changes as SQL parts (section 4.4). |
| `npm run update:apply` | Sends the next part to D1. |
| `npm run update:status` | Shows the parts and which parts are sent. |
| `npm run load:remote:full` | Puts all of `d1.sql` into D1. Use only for a full rebuild (section 4.4). |
| `npm run dev` | Starts the site and the API on your computer at http://localhost:8788. |
| `npm run deploy` | Sends the site and the API to the live site on Cloudflare Pages. |

### 2.4 About the CFS data

The CFS does not measure all of its values.
It also copies values from 5 other sources.
The column `foods.origin_source` keeps the name of the first source.

| Code | First source | Number of foods |
|---|---|---|
| A | USDA FoodData Central | 157 |
| B | China Food Composition (CFC2002) | 1,246 |
| C | CFS Food Research Laboratory | 742 |
| D | Food Standards Australia New Zealand | 762 |
| E | Thai FCD (Mahidol University) | 92 |

The CFS web site tells the definitions for each first source.
The importer records them in the `method` column.

| Code | Carbohydrate | Dietary fibre |
|---|---|---|
| A (USDA) | Total (`total`) | Total dietary fibre |
| B (China CFC2002) | Total (`total`) | Insoluble fibre only (`insoluble`) |
| C (CFS laboratory) | Available (`available`) | Total dietary fibre |
| D (FSANZ) | Available (`available`) | Total dietary fibre |
| E (Thai FCD) | Available (`available`). Values with "(總量)" are total (`total`). | Not told |

Do not compare the fibre of code B foods with the fibre of other foods.
The values are not of the same type.

Some foods (codes A and D) will also come directly from USDA and FSANZ.
These are duplicates.
Section 4.2 shows how we will link them.

### 2.5 About the USDA data

The importer uses 2 USDA data sets:

| Source ID | Data set | Release | Number of foods |
|---|---|---|---|
| `usda_fnd` | Foundation Foods | 2026-04-30 | 469 |
| `usda_sr` | SR Legacy | 2018-04 | 7,793 |

The licence is public domain (CC0 1.0).

The importer finds each nutrient by its USDA nutrient number.
It also examines the unit.
Thus it cannot use a kJ value as a kcal value.

Some foods have no standard value for energy or carbohydrate.
For these foods, the importer uses a different value.
The `method` column records this value type.

| Nutrient | First choice | Second choice | Third choice |
|---|---|---|---|
| Energy | Nutrient 208 | Atwater specific (`atwater_specific`) | Atwater general (`atwater_general`) |
| Carbohydrate | By difference (`difference`) | By summation (`summation`) | - |

The Foundation Foods release 2026-10-29 has no `food.csv` and no `food_nutrient.csv`.
Thus we cannot use it.
The download script examines each zip file.
If a zip file does not have these tables, the script uses the release before it.

Foundation Foods has fewer nutrients for each food than SR Legacy.
This is a property of the USDA data, not an import error.
Example: only 140 of 469 Foundation foods have a value for vitamin C.

SR Legacy also has some brand products, for example Pillsbury and Kraft.

We compared the database with the raw files. All 143,925 values are the same.

### 2.6 About the TFDA data

The data set is "食品營養成分資料集" (number 8543) from https://data.fda.gov.tw.
It has 2,213 foods in 18 food groups.
Each food has a Traditional Chinese name.
Most foods also have an English name.

The source file has one row for each nutrient of each food.
The importer uses 39 of the 104 nutrients.
The raw file keeps the other nutrients.
Examples are the amino acids and the fatty acids.

| Item | Rule |
|---|---|
| Energy | `熱量` is `energy_kcal`. `修正熱量` is `energy_kcal_adjusted`. |
| Carbohydrate | The value is total carbohydrate. `method` = `total`. |
| Trans fat | The source unit is mg. The importer changes it to g. |
| Monounsaturated and polyunsaturated fat | The source unit is mg. The importer changes it to g. |
| Empty value | No row |
| Serving `0.0克` | No serving |
| English food group names | We wrote these names. They are not from TFDA. |

The importer examines the unit of each nutrient.
If TFDA changes a unit, the build stops with an error.

We compared the database with the raw file. All 64,385 values are the same.

### 2.7 About the MEXT data

The data set is "日本食品標準成分表（八訂）増補2023年" (Standard Tables of Food Composition in Japan, 8th edition, 2023 supplement).
MEXT updated the data file on 2026-03-27.
It has 2,538 foods in 18 food groups.
The licence is the Public Data License (Japan) v1.0. This licence is compatible with CC BY 4.0.

The main table has Japanese names only.
The importer puts the Japanese name in `name_local`.
The English names come from the 7th edition (2015) English table.
The importer finds the English name by the food number.
2,184 foods have an English name. The new foods after 2015 have no English name.

The header row has an INFOODS identifier for each column.
The importer finds each column by its identifier, not by its position.
The importer uses 44 columns.

| Source value | Database value |
|---|---|
| A number | `value` = the number |
| A number in parentheses, for example `(11.3)` | `value` = the number, `estimated` = 1 |
| `Tr` | `flag` = `TRACE` |
| `(Tr)` | `flag` = `TRACE`, `estimated` = 1 |
| `-` or empty | No row |
| `*` | No row. The value is in a different chapter. |

We compared the database with the raw file. All 99,184 values are the same.

### 2.8 About the AFCD data

The data set is the Australian Food Composition Database, Release 3 (December 2025), from FSANZ.
It has 1,588 foods. The names are in English.
The licence is CC BY 4.0.

The importer uses the sheet "All solids & liquids per 100 g".
It finds each column by the header text.
It examines the unit in each header.
Some fatty acid columns have the same name 2 times: one in `%T` and one in `g`.
The importer uses only the column with the correct unit.

| Item | Rule |
|---|---|
| Energy | The source gives kJ only. `energy_kj` is the source value. `energy_kcal` = kJ / 4.184, `method` = `from_kj`. |
| Carbohydrate | The source gives available carbohydrate. `carbohydrate` has `method` = `available`. `carbohydrate_available` has the same value. |
| Trans fat | The source unit is mg. The importer changes it to g. |
| Derivation (Analysed, Recipe, Borrowed, and others) | The importer adds it to `description`. |
| Empty value | No row |

78 foods have the derivation "Borrowed". Some of these values come from USDA.
Step 6 (links) must examine these foods.

We compared the database with the raw file. All 72,086 values are the same.

### 2.9 About the CoFID data

The data set is "McCance and Widdowson's Composition of Foods Integrated Dataset (CoFID) 2021" from the UK government.
It has 2,887 foods. The names are in English.
The licence is the Open Government Licence v3.0.

The importer uses 3 sheets: "1.3 Proximates", "1.4 Inorganics" and "1.5 Vitamins".
It joins the 3 sheets by the food code.
It finds each column by the identifier row below the header.
It examines the unit in each header.

| Source value | Database value |
|---|---|
| A number | `value` = the number |
| `Tr` | `flag` = `TRACE` |
| `N` (the food has the nutrient, but there is no reliable value) | No row |
| Empty | No row |

| Item | Rule |
|---|---|
| Carbohydrate | CoFID gives available carbohydrate as monosaccharide equivalents. `method` = `available_monosaccharide`. |
| Fibre | The importer uses AOAC fibre. It does not use NSP fibre, because other sources do not use NSP. |
| Alcoholic beverages (group Q) | CoFID gives the values for 100 ml, not for 100 g. The `description` of these 31 foods tells this. |

CoFID uses the food code 13-669 for 2 different foods.
The importer keeps the 2 foods.
For a code that is used 2 times, the ID has the food name, for example `cofid:13-669~watercress-raw`.

We compared the database with the raw file. All 103,806 values are the same.

### 2.10 About the CNF data

The data set is the Canadian Nutrient File (CNF) 2026 from Health Canada.
It has 5,993 foods. Each food has an English name and a French name.
The importer puts the French name in `name_local`.
The licence is the Open Government Licence - Canada.

This computer cannot connect to the Health Canada web site.
To get the data, do these steps:

1. Open the Canadian Nutrient File page on https://www.canada.ca in your browser.
2. Download the 2026 zip file with all the data files (`cnf_fcen_all-files-data_2026.zip`).
3. Put the zip file in `data/raw/cnf/`. Do not extract it.
4. Run `npm run db`.

The importer does not use the 2015 file (`cnf-fcen-csv.zip`). You can delete it.

The importer finds each nutrient by its nutrient code.
These codes are the same as the USDA SR Legacy nutrient numbers.
The importer examines the unit of each nutrient.

| Item | Rule |
|---|---|
| Carbohydrate | By difference. `method` = `difference`. |
| Alternative English name | `alias` |
| Comment | `description` |
| Data origin | `origin_source` |
| USDA code (`USDA_NDB_Code`) | `origin_code` |
| Servings | Only measure type 6 (user-defined, for example 250 ml). The weight is in grams. |
| Measure type 3 (refuse) and type 9 (yield) | Not used. They are not servings. |

3,529 CNF foods (59 %) are USDA data with no changes.
4,798 CNF foods have a USDA code.
4,615 of these codes are in our USDA SR Legacy data.
Step 6 (links) must use `origin_code` to link these foods.

We compared the database with the raw file. All 236,465 values are the same.

### 2.11 Data versions

We examined each source for a newer version on 2026-11-12.

| Source | Version in the database | Newest version | Status |
|---|---|---|---|
| HK CFS | Web site, scraped 2025-09-29 | Same. The site has the same 2,999 foods. | Current |
| Taiwan TFDA | Download of 2026-11-11 | Same | Current |
| Japan MEXT | 8th edition, 2023 supplement, data file of 2026-03-27 | Same | Current |
| Australia AFCD | Release 3 (December 2025) | Same | Current |
| USDA Foundation Foods | 2026-04-30 | 2026-10-29. The CSV file of this release is not complete (section 2.5). | Newest usable version |
| USDA SR Legacy | 2018-04 | Same. USDA does not update SR Legacy. | Current (final) |
| UK CoFID | 2021 | Same | Current |
| Canada CNF | 2026 | Same | Current |
| France Ciqual | Not in the database | Unknown. The web site is in maintenance. | On hold |

## 3. Database design

### 3.1 Main rules

1. The database is a build result. Do not change it by hand.
2. The pipeline makes the full database again from the source files each time.
3. The SQL is portable. It works on SQLite, Cloudflare D1 and Turso. A change to Postgres is easy.
4. Each food has a stable ID: `<source>:<source code>`. An example is `cfs:0617002710630`. Do not change an ID after you publish it.
5. All nutrient values are for 100 g (or 100 ml) of the part that you can eat.

### 3.2 Tables

| Table | Content |
|---|---|
| `sources` | One row for each data source. It has the licence and the attribution text. |
| `nutrients` | The master list of nutrients. Each nutrient has one ID and one unit. |
| `foods` | One row for each food from each source. The data is the same as the source data. The `description` column keeps the source description, for example the cooking method. For republished data, `origin_source` and `origin_code` tell the first source and its food code. |
| `food_nutrients` | One row for each value. If a value is missing, there is no row. |
| `servings` | Typical serving sizes, for example "1 small bottle = 330 g". |
| `food_codes` | Other codes for a food, for example the USDA NDB number. |
| `food_links` | Links between duplicates and between equal foods from different sources (section 3.5). |
| `food_concepts` | The synonym concepts of each food, for example `broccoli`. |
| `foods_fts` | The keyword search index. |

### 3.3 Special values

| Source value | Database value |
|---|---|
| A number | `value` = the number, `flag` = empty |
| `NA` or empty | No row |
| `ND` (not detected) | `value` = empty, `flag` = `ND` |
| `Trace` | `value` = empty, `flag` = `TRACE` |
| Total carbohydrate | `method` = `total` |
| Available carbohydrate (CFS codes C, D and E) | `method` = `available` |
| Insoluble fibre only (CFS code B) | `method` = `insoluble` |
| Carbohydrate by difference (MEXT, USDA) | `method` = `difference` |
| Available carbohydrate (AFCD) | `method` = `available` |
| Available carbohydrate as monosaccharide equivalents (CoFID) | `method` = `available_monosaccharide` |
| Energy in kcal that we calculated from kJ | `method` = `from_kj` |
| A value that the source estimated or calculated | `estimated` = 1 |
| A different value type (USDA, section 2.5) | `method` = the value type |

### 3.4 Search

The function `search_text()` in `pipeline/common.py` makes the search text for each food.
The text has the names in all languages, the aliases and the food group names.
The synonym step adds the synonyms (section 3.7).
The search text does not have nutrient values.

The API searches `foods.search_text` with `LIKE`.
This finds parts of words, also in Chinese text.
For 26,480 foods, a search takes approximately 30 ms in D1.
The local database also has an FTS5 index (`foods_fts`). D1 does not use it.

The API gives 1 result for each food group (section 3.9).
It shows the record that matches best.
The order of the results:

1. The name is the same as the search text.
2. The name starts with the search text. For English search text, steps 1 and 2 have the same level.
3. The Chinese name, the local name or an alias contains the search text.
4. The English name contains the search text.
5. Only a synonym or a group name contains the search text.

For the same level: foods with a Chinese name first, then HK records, then groups with data from more sources, then shorter names.

### 3.5 Duplicates

We keep all rows from all sources.
We do not delete duplicates.
The `food_links` table records the duplicates.

| Link type | Meaning | Action on the site |
|---|---|---|
| `exact_copy` | The same values from a different publisher | Show one row. Hide the other row. |
| `equivalent` | The same food from a different country | Show the two rows. |
| `similar` | A related food | Show as a suggestion. |

The script `pipeline/link.py` makes the links. It uses these rules:

| Rule | Copy | Original | Method | Number of links |
|---|---|---|---|---|
| 1 | CNF food with a USDA code | USDA food with the same NDB number | Code. If the values are the same: `exact_copy`. If not: `equivalent`. | 3,896 `exact_copy`, 719 `equivalent` |
| 2 | CFS food from USDA (code A) | USDA food | Same values | 76 `exact_copy` |
| 3 | CFS food from FSANZ (code D) | AFCD food | Same values. Energy is not compared, because CFS uses a different energy definition for FSANZ. | 601 `exact_copy` |
| 4 | Any food | The same food from a different source | English name (section 3.6) | 1,264 `equivalent`, 212 `similar` |

For a value link, the 2 foods must have the same values for at least 4 key nutrients.
At least 2 of these values must not be zero.
If more than 1 food matches, the script uses the name to select 1.
If the name does not show a clear selection, the script does not make a link.

We examined samples of the links. All links in the samples were correct.

### 3.6 Links by name (rule 4)

Rule 4 compares the English names of foods from different sources.
It does not use the foods that rules 1 to 3 linked as copies.

1. The script changes each name to a set of words. It removes plurals and common words. It changes UK words to US words, for example "aubergine" to "eggplant".
2. The script calculates a score from 0 to 1. Rare words have more weight than common words.
3. The cooking state must be the same, for example "raw" and "raw". For TFDA foods, the script reads the state from the description ("樣品狀態:生" is raw).
4. The product form must be the same, for example "flour" and "flour".
5. Protein, fat, carbohydrate and water must be almost the same.

| Score | Link type | Meaning on the site |
|---|---|---|
| 0.90 or more | `equivalent` | The same food from a different country |
| 0.75 to 0.90 | `similar` | A related food |
| Less than 0.75 | No link | - |

We examined samples with the user on 2026-11-12. At 0.90 or more, all foods in the samples were correct.
Example: "Broccoli, raw" now has 9 records from 7 sources, which include Japan and Taiwan.

Rule 4 does not link foods that have no English name.
The synonym table (section 4.2) will link these foods.
Rule 4 does not yet stop links such as pork to beef. Thus it does not use scores less than 0.75.

### 3.7 Synonyms

The synonym table `pipeline/synonyms.csv` has 93 food concepts.
Each concept has the words for Hong Kong, Taiwan, Mainland China, Japan and English.
Example: broccoli = 西蘭花 (HK), 青花菜 (TW), 綠菜花 (CN), ブロッコリー (JA), broccoli (EN).

At each build, the script `pipeline/synonyms.py` does these steps:

1. It finds the concepts in the name of each food. It uses the words of the region of the source (CFS: HK, then CN. TFDA: TW. MEXT: JA). It uses English for all sources.
2. It records the concepts in the table `food_concepts`.
3. It adds all words of these concepts to `foods.search_text`. Thus a search with a word from any region finds the food.
4. It links a food with no English name to the same food in a different source, if the name is exactly 1 concept word (rule 5).

Rules for matching:

- Chinese: the script finds the longest words first. Thus 洋蔥 (onion) does not match 蔥 (spring onion).
- Japanese: the word must be a full word in the name. Thus たまねぎ does not match ねぎ.
- English: the script ignores punctuation. Thus "Chicken, egg" matches "chicken egg" (egg), not "chicken".

Some words have different meanings in different regions, for example 乳酪 (yogurt in HK, cheese in TW).
The script uses these words only for the sources of their region.
The file `pipeline/synonyms_ambiguous.csv` gives the decision for each of these words.

Result: 12,181 foods have at least 1 concept.
A search for 西蘭花, 青花菜, ブロッコリー or broccoli finds broccoli in all 8 sources.

To add a synonym, add a row or a word to `pipeline/synonyms.csv`. Then run `npm run db`.

### 3.8 Reasons for the link table

- We can always find the first source of a value.
- A new import does not bring the duplicates back.
- It is easy to remove an incorrect link.

### 3.9 Food groups and display names

The script `pipeline/display.py` runs at the end of each build.
We agreed these rules with the user on 2026-11-12.

1. Foods with an `exact_copy` or `equivalent` link make a food group (`foods.cluster_id`). A `similar` link does not.
2. Each group has 1 main record (`foods.is_primary` = 1). The order of preference: CFS, TFDA, MEXT, AFCD, CoFID, USDA Foundation, USDA SR Legacy, CNF.
3. The Chinese display name (`foods.display_zh`):
   - A CFS record always shows its own CFS name. If the record comes from the China table and its name is a Mainland word, the script shows the HK word. Example: 鱷梨 becomes 牛油果.
   - Other records show the name of the group. This is the CFS name, if the group has a CFS record.
   - If not, the script uses the HK word from the synonym table and adds the cooking state. Example: USDA "Broccoli, boiled" becomes 西蘭花(煮).
   - If not, the script uses the TFDA name.
4. The English display name (`foods.display_en`) is the shortest English name in the group.
5. The original names do not change. The food page shows them.

## 4. Plan

### 4.1 Steps

| Step | Task | Status |
|---|---|---|
| 1 | Start a Git repository | Done |
| 2 | Write the database tables (`db/schema.sql`) | Done |
| 3 | Write the CFS importer and the build script | Done |
| 4 | Write the importer for USDA (Foundation Foods and SR Legacy) | Code done. Test with the real data is necessary. |
| 5 | Write the importer for the Taiwan TFDA data | Done |
| 5a | Write the importer for the Japan MEXT data | Done |
| 5b | Write the importer for the Australia AFCD data | Done |
| 5c | Write the importer for USDA | Done |
| 5e | Write the importer for UK CoFID | Done |
| 5f | Write the importer for Canada CNF | Done |
| 5d | Write the importer for France Ciqual | On hold. The Ciqual web site is in maintenance (section 4.3). |
| 6 | Link the duplicates in `food_links` (section 4.2) | Done (sections 3.5 to 3.7). The synonym table can grow. |
| 7 | Make a script that sends `food.db` to Cloudflare D1 | Done (`npm run export`, `npm run load:remote`) |
| 8 | Make the API with Pages Functions | Done. On the preview address. |
| 9 | Change the site to use the API, not `foods.json` | Done. On the preview address. The live site changes after the user approves it. |
| 10 | Write the importers for the other sources (section 4.3) | To do |
| 11 | Export the data to Parquet for AI and analysis | To do |
| 12 | Add vector search (section 4.5) | Only if necessary |

### 4.2 Duplicate links

1. Find CFS foods with code A or D.
2. Compare each one with the USDA or FSANZ foods.
3. If the name and the values are the same, record an `exact_copy` link.
4. Record other matches as `equivalent` or `similar`.
5. Record the method and the confidence for each link.

Hong Kong and Taiwan use different words for some foods.
Examples: 西蘭花 (HK) and 青花菜 (TW), 番薯 (HK) and 地瓜 (TW).
Thus a search for 西蘭花 does not find the TFDA food.
Make a synonym table for these words.
The search text and the links must use this table.

### 4.3 Data sources

The numbers of foods are approximate. Make sure that each number and each licence is correct before you write the importer.

| Source | Country | Approximate number of foods | Licence |
|---|---|---|---|
| USDA FoodData Central (Foundation, SR Legacy) | US | 8,262 (done) | Public domain |
| Taiwan TFDA food composition | TW | 2,000 | Taiwan Open Data |
| Japan MEXT Standard Tables (8th edition) | JP | 2,538 (done) | Public Data License (Japan) v1.0 |
| Canadian Nutrient File (CNF) | CA | 5,690 (done) | Open Government Licence - Canada. Download the file by hand (section 2.10). |
| UK CoFID (McCance and Widdowson) | GB | 2,887 (done) | Open Government Licence v3.0 |
| Australian Food Composition Database (AFCD) | AU | 1,588 (done) | CC BY 4.0 |
| France Ciqual | FR | 3,000 | Licence Ouverte (Etalab). On 2026-11-11 the Ciqual web site was in maintenance. Try again later. The files are listed on data.gouv.fr. |

We do not use these sources now:

- **Open Food Facts.** It has data for brand products, not for basic foods.
- **USDA Branded Foods.** The reason is the same.
- **China CFC2002 and Thai FCD.** These sources have no open download. The CFS data has a part of them.

Each importer must:

1. Put the downloaded files in `data/raw/<source>/`.
2. Record the source, the licence and the date in the `sources` table.
3. Change each source nutrient to an ID in `pipeline/common.py`.
4. Change each unit to the unit of that nutrient.
5. Use `search_text()` for the search text.

If a source has a new nutrient, add it to the end of `NUTRIENTS` in `pipeline/common.py`.
Do not change the ID of a nutrient that is in the list.
The list has 54 nutrients now.

### 4.4 Hosting

```
raw files --> importers --> data/food.db (master copy)
                              |
                              +--> data/export/d1.sql --> Cloudflare D1 "food-data"
                              +--> Parquet files (for AI and analysis, planned)

Browser --> Cloudflare Pages "hk-food-nutrition" --> Pages Functions /api/* --> D1
```

| Item | Value |
|---|---|
| Cloudflare account | "Justinckhcheung@hotmail.com's Account" |
| Pages project | `hk-food-nutrition` |
| Live address | https://hk-food-nutrition.pages.dev |
| Preview address | https://preview.hk-food-nutrition.pages.dev |
| D1 database | `food-data` (location: Asia-Pacific) |
| Deployment | By hand (`npm run deploy`). There is no connection to GitHub. |

The API:

| Endpoint | Function |
|---|---|
| `/api/meta` | Counts, sources, the nutrient list and the HK food groups |
| `/api/search?q=&limit=` | Find foods by name in any language (section 3.4) |
| `/api/food?id=` | All data for 1 food: nutrients, servings, source, the other records of its group, similar foods and related foods |
| `/api/group?g=&s=&sort=` | The foods of 1 HK food group |
| `/api/foods?ids=` | Short data for a list of foods |
| `/api/filter?...` | Find foods by nutrient values. Not done yet. |

The site and AI tools must use only the API.
They must not read the tables directly.
Then a change to the search method does not change the site or the AI tools.

The API keeps its answers in the Cloudflare cache for 1 hour (short searches: 1 day).
The constant `DATA_VERSION` in `functions/_lib.js` is part of the cache key.

### 4.4.1 Limits of the D1 free plan

The account uses the D1 free plan.

| Limit | Value | Effect |
|---|---|---|
| Rows written | 100,000 each day (all databases) | Uploads of data |
| Rows read | 5 million each day | Searches and pages that are not in the cache |
| Storage | 500 MB for each database | The database is 96 MB |

Batch requests do not decrease the count. D1 counts each written row and each index entry.
A full load writes approximately 2.6 million rows. Thus do not use a full load on the free plan.
On 2026-11-12 the first full load used the limit of that day.

The Workers Paid plan (5 USD each month) includes 50 million written rows each month.

### 4.4.2 Put new data on the site

Send only the changes. Do these steps:

1. Run `npm run build`.
2. Run `npm run update:plan`. The tool compares `data/food.db` with `data/export/remote_baseline.db` (the data on D1). It writes the changes in parts of no more than 90,000 estimated row writes.
3. Run `npm run update:apply`. This sends 1 part. On the free plan, send 1 part each day.
4. Do step 3 again until all parts are sent. After the last part, the tool replaces the baseline.
5. Change `DATA_VERSION` in `functions/_lib.js` and `API_VERSION` in `site/app.js`.
6. Run `npm run deploy`.

We tested the tool: the old data and the parts make exactly the new database.

### 4.4.3 Searches and the read limit

A search with 3 or more characters uses the index `search_fts` (FTS5, trigram). It reads only the rows that match.
A search with 1 or 2 characters (for example 白飯) reads all foods. Its result stays in the cache for 1 day.

### 4.5 Vector search (future)

We do not need vector search now.
Keyword search and SQL filters do most of the work.
Vector search helps when the words are different but the meaning is the same.
Example: "congee", "rice porridge" and "粥".

D1 cannot do vector search.
If we need vector search, do these steps:

1. Use a multilingual embedding model, for example bge-m3.
2. Make embeddings from `search_text()`.
3. Add the table `food_embeddings(food_id, model, vector)`.
4. Move the database from D1 to Turso. Turso uses the SQLite format and has vector search.
5. Change only the `/api/search` code.

We will not use a separate vector database.

### 4.6 Future: Postgres

Move to Postgres with pgvector if one of these conditions occurs:

- Other systems must write data to the database.
- Other systems need standard database connections.
- We need user accounts and access control.

The pipeline makes the database from the source files.
Thus a move to Postgres is a change of the build target.
