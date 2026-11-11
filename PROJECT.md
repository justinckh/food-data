# Food Data Project

This document is in ASD-STE100 Simplified Technical English.

Last update: 2026-11-11.

## 1. Purpose

This project collects food composition data from public sources.
It puts the data into one database.
A web site shows the data to users.
Other systems and AI tools will also use the data.

## 2. Current status

### 2.1 Summary

| Item | Status |
|---|---|
| Web site on Cloudflare Pages | Live. It is a static site with no backend. |
| Data source: Hong Kong CFS | Done. The data has 2,999 foods. |
| Local database (`data/food.db`) | Done. It has the CFS data. |
| Keyword search (FTS5) | Done in the local database. |
| Data source: USDA (Foundation Foods, SR Legacy) | The importer is ready. It has a test with sample data. The real data is not downloaded (section 2.5). |
| Backend API | Not started. |
| Cloudflare D1 | Not started. |
| Other data sources | Not started. |

### 2.2 Files and folders

| Path | Content |
|---|---|
| `scrape_cfs.py` | This script gets the food data from the CFS web site. It writes `cfs_foods.csv`. |
| `cfs_foods.csv` | The CFS data. It has one row for each food. Values are for 100 g. |
| `cache/` | The script keeps the CFS web pages here. Git does not keep this folder. |
| `build_data.py` | This script makes `site/foods.json` from `cfs_foods.csv`. |
| `site/` | The web site files. `app.js` reads all of `foods.json` in the browser. |
| `db/schema.sql` | The database tables. |
| `pipeline/common.py` | The nutrient list, the value parser and the search text function. |
| `pipeline/importers/cfs.py` | This importer reads `cfs_foods.csv` for the database. |
| `pipeline/importers/usda.py` | This importer reads the USDA zip files in `data/raw/usda/`. It does not extract the zip files. |
| `pipeline/download_usda.py` | This script downloads the newest USDA zip files to `data/raw/usda/`. |
| `pipeline/build_db.py` | This script makes `data/food.db` from all importers. If the files for a source are missing, the script does not import that source. |
| `data/raw/` | The downloaded source files. Git does not keep this folder. |
| `data/food.db` | The master copy of the database. Git does not keep this file. You can make it again at any time. |
| `PROJECT.md` | This document. |

### 2.3 Commands

| Command | Result |
|---|---|
| `npm run dev` | Starts the site on your computer at port 8000. |
| `npm run scrape` | Gets the CFS data again. Then it makes `foods.json` again. |
| `npm run build` | Makes `site/foods.json` from `cfs_foods.csv`. |
| `npm run download` | Downloads the USDA files. |
| `npm run db` | Makes `data/food.db` from all sources. |
| `npm run deploy` | Sends the `site/` folder to Cloudflare Pages. |

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

Some foods (codes A and D) will also come directly from USDA and FSANZ.
These are duplicates.
Section 4.2 shows how we will link them.

### 2.5 About the USDA data

The importer uses 2 USDA data sets:

| Source ID | Data set | Approximate number of foods |
|---|---|---|
| `usda_fnd` | Foundation Foods | 400 |
| `usda_sr` | SR Legacy | 7,800 |

The importer finds each nutrient by its USDA nutrient number.
It also examines the unit.
Thus it cannot use a kJ value as a kcal value.

Some foods have no standard value for energy or carbohydrate.
For these foods, the importer uses a different value.
The `method` column records this value type.

| Nutrient | First choice | Second choice | Third choice |
|---|---|---|---|
| Energy | Nutrient 208 | Atwater specific (`atwater_specific`) | Atwater general (`atwater_general`) |
| Carbohydrate | By difference | By summation (`summation`) | - |

The USDA web site does not accept connections from the Claude Code sandbox.
To get the data, do one of these steps:

1. Run `npm run download` in your terminal.
2. Or, download the 2 "CSV" zip files from https://fdc.nal.usda.gov/download-datasets. Put them in `data/raw/usda/`.

Then run `npm run db`.

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
| `foods` | One row for each food from each source. The data is the same as the source data. |
| `food_nutrients` | One row for each value. If a value is missing, there is no row. |
| `servings` | Typical serving sizes, for example "1 small bottle = 330 g". |
| `food_links` | Links between duplicates and between equal foods from different sources. It is empty now. |
| `foods_fts` | The keyword search index. |

### 3.3 Special values

| Source value | Database value |
|---|---|
| A number | `value` = the number, `flag` = empty |
| `NA` or empty | No row |
| `ND` (not detected) | `value` = empty, `flag` = `ND` |
| `Trace` | `value` = empty, `flag` = `TRACE` |
| Total carbohydrate | `method` = `total` |
| A different value type (USDA, section 2.5) | `method` = the value type |

### 3.4 Search

The search index uses the trigram tokenizer.
This tokenizer finds parts of words.
Chinese text has no spaces between words, so this is necessary.

The trigram index cannot find a query that has less than 3 characters.
For these queries, the search must use `LIKE` on `foods.search_text`.
Example: "粥" and "叉燒" use `LIKE`. "叉燒包" uses the index.

The function `search_text()` in `pipeline/common.py` makes the search text for each food.
The text has the names in all languages, the aliases and the food group names.
It does not have nutrient values.
SQL queries find foods by nutrient values.

### 3.5 Duplicates

We keep all rows from all sources.
We do not delete duplicates.
The `food_links` table records the duplicates.

| Link type | Meaning | Action on the site |
|---|---|---|
| `exact_copy` | The same values from a different publisher | Show one row. Hide the other row. |
| `equivalent` | The same food from a different country | Show the two rows. |
| `similar` | A related food | Show as a suggestion. |

Reasons:

- We can always find the first source of a value.
- A new import does not bring the duplicates back.
- It is easy to remove an incorrect link.

## 4. Plan

### 4.1 Steps

| Step | Task | Status |
|---|---|---|
| 1 | Start a Git repository | Done |
| 2 | Write the database tables (`db/schema.sql`) | Done |
| 3 | Write the CFS importer and the build script | Done |
| 4 | Write the importer for USDA (Foundation Foods and SR Legacy) | Code done. Test with the real data is necessary. |
| 5 | Write the importer for the Taiwan TFDA data | To do |
| 6 | Link the duplicates in `food_links` (section 4.2) | To do |
| 7 | Make a script that sends `food.db` to Cloudflare D1 | To do |
| 8 | Make the API with Pages Functions | To do |
| 9 | Change the site to use the API, not `foods.json` | To do |
| 10 | Write the importers for the other sources (section 4.3) | To do |
| 11 | Export the data to Parquet for AI and analysis | To do |
| 12 | Add vector search (section 4.5) | Only if necessary |

### 4.2 Duplicate links

1. Find CFS foods with code A or D.
2. Compare each one with the USDA or FSANZ foods.
3. If the name and the values are the same, record an `exact_copy` link.
4. Record other matches as `equivalent` or `similar`.
5. Record the method and the confidence for each link.

### 4.3 Data sources

The numbers of foods are approximate. Make sure that each number and each licence is correct before you write the importer.

| Source | Country | Approximate number of foods | Licence |
|---|---|---|---|
| USDA FoodData Central (Foundation, SR Legacy, FNDDS) | US | 13,000 | Public domain |
| Taiwan TFDA food composition | TW | 2,000 | Taiwan Open Data |
| Japan MEXT Standard Tables (8th edition) | JP | 2,500 | Free with attribution |
| Canadian Nutrient File (CNF) | CA | 5,700 | Open Government Licence |
| UK CoFID (McCance and Widdowson) | GB | 3,000 | Open Government Licence |
| Australian Food Composition Database (AFCD) | AU | 1,600 | CC BY |
| France Ciqual | FR | 3,000 | Open licence |

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

If a source has a new nutrient, add it to `NUTRIENTS` in `pipeline/common.py`.
Do not change the ID of a nutrient that is in the list.

### 4.4 Hosting

```
raw files --> importers --> data/food.db (master copy)
                              |
                              +--> Cloudflare D1 (for the site API)
                              +--> Parquet files (for AI and analysis)

Browser --> Cloudflare Pages site --> Pages Functions /api/* --> D1
```

Planned API:

| Endpoint | Function |
|---|---|
| `/api/search?q=` | Find foods by name in any language |
| `/api/food/:id` | Get all data for one food |
| `/api/filter?...` | Find foods by nutrient values |

The site and AI tools must use only the API.
They must not read the tables directly.
Then a change to the search method does not change the site or the AI tools.

Make sure of these items before step 7:

- D1 supports FTS5 with the trigram tokenizer.
- `wrangler d1 export` does not support virtual tables. Make the D1 SQL file from `food.db` with a script. Make the `foods_fts` index again in D1.

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
