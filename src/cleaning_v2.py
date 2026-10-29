from pathlib import Path

import duckdb
import yaml


def find_root():
    for path in Path(__file__).resolve().parents:
        if (path / "config/config.yaml").exists():
            return path
    raise FileNotFoundError("config/config.yaml non trovato")


ROOT = find_root()
CONFIG_PATH = ROOT / "config/config.yaml"
VERSION = "v2"
EXPECTED_INPUT_ROWS = 75_987_976
EXPECTED_DUPLICATES = 120_210
EXPECTED_OUTPUT_ROWS = 75_867_766


def load_config(path=CONFIG_PATH):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def quote_identifier(value):
    return '"' + value.replace('"', '""') + '"'


def quote_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def get_schema(con, path):
    result = con.execute(
        f"DESCRIBE SELECT * FROM read_parquet({quote_literal(path)})"
    ).fetchall()
    return [(column[0], column[1]) for column in result]


def get_columns(schema):
    return [column[0] for column in schema]


def clean_file(con, input_path, output_path, cleaning_config):
    input_schema = get_schema(con, input_path)
    input_columns = get_columns(input_schema)
    required_columns = {
        "row_id",
        "Attack",
        "MAX_IP_PKT_LEN",
        "LONGEST_FLOW_PKT",
    }
    missing_columns = required_columns - set(input_columns)
    if missing_columns:
        raise ValueError(
            f"{input_path.name}: colonne richieste mancanti: "
            f"{sorted(missing_columns)}"
        )
    if "attack_family" in input_columns:
        raise ValueError(f"{input_path.name}: attack_family è già presente")

    drop_columns = cleaning_config["drop_columns"]
    protected_columns = {
        "row_id",
        "Dataset",
        "IPV4_SRC_ADDR",
        "IPV4_DST_ADDR",
    }
    forbidden_columns = protected_columns.intersection(drop_columns)
    if forbidden_columns:
        raise ValueError(
            f"cleaning.v2.drop_columns contiene colonne da conservare: "
            f"{sorted(forbidden_columns)}"
        )
    missing_drop_columns = set(drop_columns) - set(input_columns)
    if missing_drop_columns:
        raise ValueError(
            f"{input_path.name}: colonne da eliminare mancanti: "
            f"{sorted(missing_drop_columns)}"
        )

    input_rows, invalid_rows = con.execute(f"""
        SELECT
            count(*),
            count(*) FILTER (
                WHERE "MAX_IP_PKT_LEN" <> "LONGEST_FLOW_PKT"
            )
        FROM read_parquet({quote_literal(input_path)})
    """).fetchone()
    if invalid_rows:
        raise ValueError(
            f"{input_path.name}: MAX_IP_PKT_LEN differisce da "
            f"LONGEST_FLOW_PKT in {invalid_rows:,} righe"
        )

    columns_sql = ", ".join(quote_identifier(column) for column in input_columns)
    dedup_columns = [
        column for column in input_columns if column != "row_id"
    ]
    partition_sql = ", ".join(
        quote_identifier(column) for column in dedup_columns
    )
    deduplicated_query = f"""
        SELECT {columns_sql}
        FROM read_parquet({quote_literal(input_path)})
        QUALIFY row_number() OVER (
            PARTITION BY {partition_sql}
            ORDER BY "row_id" ASC NULLS LAST
        ) = 1
    """

    attack_name_map = cleaning_config["attack_name_map"]
    attack_cases = " ".join(
        f"WHEN {quote_literal(source)} THEN {quote_literal(target)}"
        for source, target in attack_name_map.items()
    )
    normalized_attack = (
        f'CASE "Attack" {attack_cases} ELSE "Attack" END'
    )
    web_config = cleaning_config["web_attack"]
    web_classes = ", ".join(
        quote_literal(value) for value in web_config["classes"]
    )
    attack_family = (
        f'CASE WHEN "Attack" IN ({web_classes}) '
        f'THEN {quote_literal(web_config["family_name"])} '
        f'ELSE "Attack" END'
    )

    normalized_columns = []
    for column in input_columns:
        if column == "Attack":
            normalized_columns.append(f'{normalized_attack} AS "Attack"')
        else:
            normalized_columns.append(quote_identifier(column))

    output_columns = [
        column for column in input_columns if column not in drop_columns
    ]
    attack_index = output_columns.index("Attack")
    output_columns.insert(attack_index + 1, "attack_family")
    output_select = []
    for column in output_columns:
        if column == "Attack":
            output_select.append(quote_identifier("Attack"))
        elif column == "attack_family":
            output_select.append(f'{attack_family} AS "attack_family"')
        else:
            output_select.append(quote_identifier(column))

    con.execute(f"""
        COPY (
            WITH deduplicated AS (
                {deduplicated_query}
            ),
            normalized AS (
                SELECT {", ".join(normalized_columns)}
                FROM deduplicated
            )
            SELECT {", ".join(output_select)}
            FROM normalized
            ORDER BY "row_id"
        )
        TO {quote_literal(output_path)}
        (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    output_rows, null_attack, non_unique_ids = con.execute(f"""
        SELECT
            count(*),
            count(*) FILTER (
                WHERE "Attack" IS NULL OR "attack_family" IS NULL
            ),
            count(*) - count(DISTINCT "row_id")
        FROM read_parquet({quote_literal(output_path)})
    """).fetchone()
    duplicate_rows = input_rows - output_rows
    output_schema = get_schema(con, output_path)
    output_file_columns = get_columns(output_schema)
    if output_file_columns != output_columns:
        raise ValueError(
            f"{output_path.name}: colonne in uscita non corrette. "
            f"Attese: {output_columns}; trovate: {output_file_columns}"
        )

    if null_attack:
        raise ValueError(
            f"{output_path.name}: Attack o attack_family contengono "
            f"NULL in {null_attack:,} righe"
        )

    if non_unique_ids:
        raise ValueError(
            f"{output_path.name}: row_id non è unico "
            f"({non_unique_ids:,} righe in eccesso)"
        )

    input_types = dict(input_schema)
    expected_schema = [
        (column, input_types[column])
        for column in output_columns
        if column != "attack_family"
    ]
    expected_schema.insert(
        expected_schema.index(("Attack", input_types["Attack"])) + 1,
        ("attack_family", input_types["Attack"]),
    )
    if output_schema != expected_schema:
        raise ValueError(
            f"{output_path.name}: tipi in uscita non corrispondenti "
            f"all'input. Attesi: {expected_schema}; trovati: {output_schema}"
        )

    print(
        f"{input_path.name}: {input_rows:,} righe in ingresso, "
        f"{duplicate_rows:,} duplicati eliminati, {output_rows:,} righe "
        f"in uscita, {len(input_columns)} colonne in ingresso, "
        f"{len(output_file_columns)} colonne in uscita"
    )
    return input_rows, duplicate_rows, output_rows


def add_counts(con, path, column, counts):
    rows = con.execute(f"""
        SELECT {quote_identifier(column)}, count(*)
        FROM read_parquet({quote_literal(path)})
        GROUP BY {quote_identifier(column)}
    """).fetchall()
    for value, count in rows:
        counts[value] = counts.get(value, 0) + count


def print_counts(title, counts):
    print(title)
    for value, count in sorted(counts.items()):
        print(f"  {value}: {count:,}")


def check_attack_names(attack_counts):
    by_casefold = {}
    for value in attack_counts:
        by_casefold.setdefault(value.casefold(), []).append(value)

    collisions = [
        sorted(values)
        for values in by_casefold.values()
        if len(values) > 1
    ]
    if collisions:
        raise ValueError(
            "Varianti di Attack che coincidono ignorando maiuscole/minuscole: "
            + "; ".join(" / ".join(values) for values in sorted(collisions))
        )


def main():
    config = load_config()
    input_dir = ROOT / config["paths"]["parquet_dir"] / VERSION
    output_dir = ROOT / config["paths"]["clean_parquet_dir"] / VERSION
    output_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{config['duckdb']['memory_limit']}'")
    con.execute(f"SET temp_directory = '{config['duckdb']['temp_directory']}'")

    totals = [0, 0, 0]
    attack_counts = {}
    family_counts = {}
    cleaning_config = config["cleaning"][VERSION]

    for source in config["versions"][VERSION]["sources"]:
        name = source["dataset"]
        input_path = input_dir / f"{name}.parquet"
        output_path = output_dir / input_path.name
        if not input_path.exists():
            raise FileNotFoundError(input_path)

        file_totals = clean_file(
            con, input_path, output_path, cleaning_config
        )
        totals = [total + value for total, value in zip(totals, file_totals)]
        add_counts(con, output_path, "Attack", attack_counts)
        add_counts(con, output_path, "attack_family", family_counts)

    print_counts("\nValori distinti di Attack:", attack_counts)
    print_counts("\nValori distinti di attack_family:", family_counts)
    check_attack_names(attack_counts)

    missing_web_classes = sorted(
        set(cleaning_config["web_attack"]["classes"]) - set(attack_counts)
    )
    if missing_web_classes:
        raise ValueError(
            "Classi web_attack mancanti in Attack: "
            + ", ".join(missing_web_classes)
        )

    input_rows, duplicate_rows, output_rows = totals
    print(
        f"\nTotale: {input_rows:,} righe in ingresso, "
        f"{duplicate_rows:,} duplicati eliminati, "
        f"{output_rows:,} righe in uscita"
    )
    expected_totals = (
        ("righe in ingresso", input_rows, EXPECTED_INPUT_ROWS),
        ("duplicati eliminati", duplicate_rows, EXPECTED_DUPLICATES),
        ("righe in uscita", output_rows, EXPECTED_OUTPUT_ROWS),
    )
    for label, actual, expected in expected_totals:
        if actual != expected:
            print(
                f"AVVISO: {label}: attese {expected:,}, "
                f"ottenute {actual:,} (differenza {actual - expected:+,})"
            )

    con.close()


if __name__ == "__main__":
    main()