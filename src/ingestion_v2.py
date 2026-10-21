from pathlib import Path

import duckdb
import yaml

CONFIG_PATH = Path("config/config.yaml")
VERSION = "v2"

TYPES = {
    "IPV4_SRC_ADDR": "VARCHAR",
    "L4_SRC_PORT": "INTEGER",
    "IPV4_DST_ADDR": "VARCHAR",
    "L4_DST_PORT": "INTEGER",
    "PROTOCOL": "INTEGER",
    "L7_PROTO": "DOUBLE",
    "IN_BYTES": "BIGINT",
    "IN_PKTS": "BIGINT",
    "OUT_BYTES": "BIGINT",
    "OUT_PKTS": "BIGINT",
    "TCP_FLAGS": "INTEGER",
    "CLIENT_TCP_FLAGS": "INTEGER",
    "SERVER_TCP_FLAGS": "INTEGER",
    "FLOW_DURATION_MILLISECONDS": "BIGINT",
    "DURATION_IN": "BIGINT",
    "DURATION_OUT": "BIGINT",
    "MIN_TTL": "INTEGER",
    "MAX_TTL": "INTEGER",
    "LONGEST_FLOW_PKT": "INTEGER",
    "SHORTEST_FLOW_PKT": "INTEGER",
    "MIN_IP_PKT_LEN": "INTEGER",
    "MAX_IP_PKT_LEN": "INTEGER",
    "SRC_TO_DST_SECOND_BYTES": "DOUBLE",
    "DST_TO_SRC_SECOND_BYTES": "DOUBLE",
    "RETRANSMITTED_IN_BYTES": "BIGINT",
    "RETRANSMITTED_IN_PKTS": "BIGINT",
    "RETRANSMITTED_OUT_BYTES": "BIGINT",
    "RETRANSMITTED_OUT_PKTS": "BIGINT",
    "SRC_TO_DST_AVG_THROUGHPUT": "BIGINT",
    "DST_TO_SRC_AVG_THROUGHPUT": "BIGINT",
    "NUM_PKTS_UP_TO_128_BYTES": "BIGINT",
    "NUM_PKTS_128_TO_256_BYTES": "BIGINT",
    "NUM_PKTS_256_TO_512_BYTES": "BIGINT",
    "NUM_PKTS_512_TO_1024_BYTES": "BIGINT",
    "NUM_PKTS_1024_TO_1514_BYTES": "BIGINT",
    "TCP_WIN_MAX_IN": "INTEGER",
    "TCP_WIN_MAX_OUT": "INTEGER",
    "ICMP_TYPE": "INTEGER",
    "ICMP_IPV4_TYPE": "INTEGER",
    "DNS_QUERY_ID": "INTEGER",
    "DNS_QUERY_TYPE": "INTEGER",
    "DNS_TTL_ANSWER": "BIGINT",
    "FTP_COMMAND_RET_CODE": "INTEGER",
    "Label": "INTEGER",
    "Attack": "VARCHAR",
}

TYPES_SQL = "{" + ", ".join(f"'{c}': '{t}'" for c, t in TYPES.items()) + "}"


def load_config(path=CONFIG_PATH):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def convert(con, name, csv_path, out_path):
    # se un valore non è compatibile col tipo, DuckDB si ferma con un errore
    con.execute(f"""
        COPY (
            SELECT
                row_number() OVER () - 1 AS row_id,
                '{name}' AS Dataset,
                *
            FROM read_csv('{csv_path}', header = true, types = {TYPES_SQL})
        )
        TO '{out_path}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    n_rows = con.execute(f"SELECT count(*) FROM '{out_path}'").fetchone()[0]
    n_cols = len(con.execute(f"DESCRIBE SELECT * FROM '{out_path}'").fetchall())
    print(f"{name}: {n_rows:,} righe, {n_cols - 2} colonne dati")


def main():
    config = load_config()
    raw_dir = Path(config["paths"]["raw_csv_dir"]) / VERSION
    out_dir = Path(config["paths"]["parquet_dir"]) / VERSION
    out_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{config['duckdb']['memory_limit']}'")
    con.execute(f"SET temp_directory = '{config['duckdb']['temp_directory']}'")

    for source in config["versions"][VERSION]["sources"]:
        name = source["dataset"]
        csv_path = raw_dir / source["file"]
        if not csv_path.exists():
            raise FileNotFoundError(csv_path)
        convert(con, name, csv_path, out_dir / f"{name}.parquet")

    con.close()


if __name__ == "__main__":
    main()