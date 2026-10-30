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
VERSION = "v3"
EXPECTED_INPUT_ROWS = 66_935_021
EXPECTED_DUPLICATES = 2_459_426
EXPECTED_OUTPUT_ROWS = 64_475_595
EXPECTED_DUPLICATES_BY_DATASET = {
    "NF-BoT-IoT": 0,
    "NF-CSE-CIC-IDS2018": 628_474,
    "NF-ToN-IoT": 1_816_137,
    "NF-UNSW-NB15": 14_815,
}
EXPECTED_INPUT_COLUMNS = 57
EXPECTED_OUTPUT_COLUMNS = 54
EXPECTED_ATTACK_VALUES = 32


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


def build_conflict_query(input_path, input_columns, cleaning_config):
    dedup_columns = [
        column for column in input_columns if column != "row_id"
    ]
    dedup_partition = ", ".join(
        quote_identifier(column) for column in dedup_columns
    )
    deduplicated_columns = ", ".join(
        quote_identifier(column) for column in input_columns
    )
    deduplicated = f"""
        SELECT {deduplicated_columns}
        FROM read_parquet({quote_literal(input_path)})
        QUALIFY row_number() OVER (
            PARTITION BY {dedup_partition}
            ORDER BY "row_id" ASC NULLS LAST
        ) = 1
    """

    attack_cases = " ".join(
        f"WHEN {quote_literal(source)} THEN {quote_literal(target)}"
        for source, target in cleaning_config["attack_name_map"].items()
    )
    normalized_attack = f'CASE "Attack" {attack_cases} ELSE "Attack" END'
    normalized_columns = [
        f'{normalized_attack} AS "Attack"'
        if column == "Attack"
        else quote_identifier(column)
        for column in input_columns
    ]

    conflict_columns = [
        column
        for column in input_columns
        if column not in {
            "row_id",
            "Dataset",
            "Label",
            "Attack",
            *cleaning_config["time_columns"],
        }
    ]
    conflict_partition = ", ".join(
        quote_identifier(column) for column in conflict_columns
    )
    label_values = (
        f'count(DISTINCT "Label") OVER (PARTITION BY {conflict_partition})'
        f' + max(CASE WHEN "Label" IS NULL THEN 1 ELSE 0 END) OVER '
        f'(PARTITION BY {conflict_partition})'
    )
    attack_values = (
        f'count(DISTINCT "Attack") OVER (PARTITION BY {conflict_partition})'
        f' + max(CASE WHEN "Attack" IS NULL THEN 1 ELSE 0 END) OVER '
        f'(PARTITION BY {conflict_partition})'
    )
    return f"""
        WITH deduplicated AS (
            {deduplicated}
        ),
        normalized AS (
            SELECT {", ".join(normalized_columns)}
            FROM deduplicated
        ),
        conflicts AS (
            SELECT
                *,
                ({label_values} > 1) AS _label_conflict,
                CAST(
                    CASE WHEN {label_values} > 1 OR {attack_values} > 1
                    THEN 1 ELSE 0 END
                    AS INTEGER
                ) AS "is_conflict"
            FROM normalized
        )
    """


def clean_file(con, input_path, output_path, cleaning_config):
    input_schema = get_schema(con, input_path)
    input_columns = get_columns(input_schema)
    required_columns = {
        "row_id",
        "Dataset",
        "Label",
        "Attack",
        "FLOW_START_MILLISECONDS",
        "MAX_IP_PKT_LEN",
        "LONGEST_FLOW_PKT",
    }
    required_columns.update(cleaning_config["time_columns"])
    missing_columns = required_columns - set(input_columns)
    if missing_columns:
        raise ValueError(
            f"{input_path.name}: colonne richieste mancanti: "
            f"{sorted(missing_columns)}"
        )
    if "is_conflict" in input_columns:
        raise ValueError(f"{input_path.name}: is_conflict è già presente")

    drop_columns = cleaning_config["drop_columns"]
    protected_columns = {
        "row_id",
        "Dataset",
        "IPV4_SRC_ADDR",
        "IPV4_DST_ADDR",
        "FLOW_START_MILLISECONDS",
        "FLOW_END_MILLISECONDS",
    }
    forbidden_columns = protected_columns.intersection(drop_columns)
    if forbidden_columns:
        raise ValueError(
            f"cleaning.v3.drop_columns contiene colonne da conservare: "
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

    conflict_query = build_conflict_query(
        input_path, input_columns, cleaning_config
    )
    deduplicated_rows, conflict_rows, label_conflict_rows = con.execute(
        f"""
            {conflict_query}
            SELECT
                count(*),
                count(*) FILTER (WHERE "is_conflict" = 1),
                count(*) FILTER (
                    WHERE "is_conflict" = 1 AND _label_conflict
                )
            FROM conflicts
        """
    ).fetchone()

    output_columns = [
        column for column in input_columns if column not in drop_columns
    ]
    attack_index = output_columns.index("Attack")
    output_columns.insert(attack_index + 1, "is_conflict")
    output_select = ", ".join(
        quote_identifier(column) for column in output_columns
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"""
        COPY (
            {conflict_query}
            SELECT {output_select}
            FROM conflicts
            ORDER BY "FLOW_START_MILLISECONDS", "row_id"
        )
        TO {quote_literal(output_path)}
        (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    output_rows, null_attack_or_conflict, invalid_conflicts, non_unique_ids = (
        con.execute(f"""
            SELECT
                count(*),
                count(*) FILTER (
                    WHERE "Attack" IS NULL OR "is_conflict" IS NULL
                ),
                count(*) FILTER (
                    WHERE "is_conflict" NOT IN (0, 1)
                ),
                count(*) - count(DISTINCT "row_id")
            FROM read_parquet({quote_literal(output_path)})
        """).fetchone()
    )
    duplicate_rows = input_rows - deduplicated_rows
    if output_rows != deduplicated_rows:
        raise ValueError(
            f"{output_path.name}: il numero di righe scritte "
            f"({output_rows:,}) non corrisponde alle righe deduplicate "
            f"({deduplicated_rows:,})"
        )
    output_schema = get_schema(con, output_path)
    output_file_columns = get_columns(output_schema)
    expected_columns = [
        column for column in input_columns if column not in drop_columns
    ]
    expected_columns.insert(
        expected_columns.index("Attack") + 1, "is_conflict"
    )
    if output_file_columns != expected_columns:
        raise ValueError(
            f"{output_path.name}: colonne in uscita non corrette. "
            f"Attese: {expected_columns}; trovate: {output_file_columns}"
        )
    if null_attack_or_conflict:
        raise ValueError(
            f"{output_path.name}: Attack o is_conflict contengono NULL "
            f"in {null_attack_or_conflict:,} righe"
        )
    if invalid_conflicts:
        raise ValueError(
            f"{output_path.name}: is_conflict contiene valori diversi da "
            f"0 e 1 in {invalid_conflicts:,} righe"
        )
    if non_unique_ids:
        raise ValueError(
            f"{output_path.name}: row_id non è unico "
            f"({non_unique_ids:,} righe in eccesso)"
        )

    input_types = dict(input_schema)
    expected_schema = [
        (column, input_types[column])
        for column in expected_columns
        if column != "is_conflict"
    ]
    expected_schema.insert(
        expected_schema.index(("Attack", input_types["Attack"])) + 1,
        ("is_conflict", input_types["Label"]),
    )
    if output_schema != expected_schema:
        raise ValueError(
            f"{output_path.name}: tipi in uscita non corrispondenti "
            f"all'input. Attesi: {expected_schema}; trovati: {output_schema}"
        )

    order_violations = con.execute(f"""
        SELECT count(*)
        FROM (
            SELECT
                "FLOW_START_MILLISECONDS" AS current_time,
                "row_id" AS current_id,
                lag("FLOW_START_MILLISECONDS") OVER (
                    ORDER BY file_row_number
                ) AS previous_time,
                lag("row_id") OVER (
                    ORDER BY file_row_number
                ) AS previous_id,
                row_number() OVER (
                    ORDER BY file_row_number
                ) AS position
            FROM read_parquet(
                {quote_literal(output_path)}, file_row_number = true
            )
        )
        WHERE position > 1 AND (
            (previous_time IS NULL AND current_time IS NOT NULL)
            OR (
                previous_time IS NOT NULL
                AND current_time IS NOT NULL
                AND (
                    current_time < previous_time
                    OR (
                        current_time = previous_time
                        AND current_id < previous_id
                    )
                )
            )
            OR (
                previous_time IS NULL
                AND current_time IS NULL
                AND current_id < previous_id
            )
        )
    """).fetchone()[0]
    if order_violations:
        raise ValueError(
            f"{output_path.name}: {order_violations:,} righe non rispettano "
            "l'ordine crescente per FLOW_START_MILLISECONDS e row_id"
        )

    print(
        f"{input_path.name}: {input_rows:,} righe in ingresso, "
        f"{duplicate_rows:,} duplicati eliminati, {output_rows:,} righe "
        f"in uscita, {conflict_rows:,} con is_conflict = 1 "
        f"({label_conflict_rows:,} in gruppi con più valori di Label), "
        f"{len(input_columns)} colonne in ingresso, "
        f"{len(output_file_columns)} colonne in uscita"
    )
    return input_rows, duplicate_rows, output_rows, conflict_rows, label_conflict_rows


def add_counts(con, path, column, counts):
    rows = con.execute(f"""
        SELECT {quote_identifier(column)}, count(*)
        FROM read_parquet({quote_literal(path)})
        GROUP BY {quote_identifier(column)}
    """).fetchall()
    for value, count in rows:
        counts[value] = counts.get(value, 0) + count


def add_used_attack_keys(con, path, attack_name_map, used_keys):
    if not attack_name_map:
        return
    keys_sql = ", ".join(quote_literal(key) for key in attack_name_map)
    rows = con.execute(f"""
        SELECT "Attack", count(*)
        FROM read_parquet({quote_literal(path)})
        WHERE "Attack" IN ({keys_sql})
        GROUP BY "Attack"
    """).fetchall()
    for key, count in rows:
        used_keys[key] = used_keys.get(key, 0) + count


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


def warn_if_different(label, actual, expected):
    if actual != expected:
        print(
            f"AVVISO: {label}: attesi {expected:,}, ottenuti {actual:,} "
            f"(differenza {actual - expected:+,})"
        )


def main():
    config = load_config()
    input_dir = ROOT / config["paths"]["parquet_dir"] / VERSION
    output_dir = ROOT / config["paths"]["clean_parquet_dir"] / VERSION
    output_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{config['duckdb']['memory_limit']}'")
    con.execute(f"SET temp_directory = '{config['duckdb']['temp_directory']}'")

    totals = [0, 0, 0, 0, 0]
    attack_counts = {}
    used_attack_keys = {}
    cleaning_config = config["cleaning"][VERSION]

    try:
        for source in config["versions"][VERSION]["sources"]:
            name = source["dataset"]
            input_path = input_dir / f"{name}.parquet"
            output_path = output_dir / input_path.name
            if not input_path.exists():
                raise FileNotFoundError(input_path)

            add_used_attack_keys(
                con, input_path, cleaning_config["attack_name_map"],
                used_attack_keys,
            )
            file_totals = clean_file(
                con, input_path, output_path, cleaning_config
            )
            totals = [
                total + value for total, value in zip(totals, file_totals)
            ]
            add_counts(con, output_path, "Attack", attack_counts)

            expected_duplicates = EXPECTED_DUPLICATES_BY_DATASET.get(name)
            if expected_duplicates is not None:
                warn_if_different(
                    f"{name}: duplicati eliminati",
                    file_totals[1],
                    expected_duplicates,
                )
            if len(get_schema(con, input_path)) != EXPECTED_INPUT_COLUMNS:
                print(
                    f"AVVISO: {name}: attese {EXPECTED_INPUT_COLUMNS} "
                    f"colonne in ingresso"
                )
            if len(get_schema(con, output_path)) != EXPECTED_OUTPUT_COLUMNS:
                print(
                    f"AVVISO: {name}: attese {EXPECTED_OUTPUT_COLUMNS} "
                    f"colonne in uscita"
                )

        print_counts("\nValori distinti di Attack:", attack_counts)
        check_attack_names(attack_counts)
        unused_keys = sorted(
            set(cleaning_config["attack_name_map"]) - set(used_attack_keys)
        )
        if unused_keys:
            print(
                "AVVISO: chiavi di attack_name_map non presenti nei dati: "
                + ", ".join(unused_keys)
            )

        input_rows, duplicate_rows, output_rows, conflict_rows, label_rows = (
            totals
        )
        print(
            f"\nTotale: {input_rows:,} righe in ingresso, "
            f"{duplicate_rows:,} duplicati eliminati, "
            f"{output_rows:,} righe in uscita, {conflict_rows:,} "
            f"con is_conflict = 1 ({label_rows:,} in gruppi con più "
            "valori di Label)"
        )
        warn_if_different(
            "righe in ingresso", input_rows, EXPECTED_INPUT_ROWS
        )
        warn_if_different(
            "duplicati eliminati", duplicate_rows, EXPECTED_DUPLICATES
        )
        warn_if_different(
            "righe in uscita", output_rows, EXPECTED_OUTPUT_ROWS
        )
        warn_if_different(
            "valori distinti di Attack",
            len(attack_counts),
            EXPECTED_ATTACK_VALUES,
        )
    finally:
        con.close()


if __name__ == "__main__":
    main()
