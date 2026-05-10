import json
import time
import os
from datetime import datetime, timezone, timedelta
import requests
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv


load_dotenv()
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "bdo_market")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT", "5432")

REGION = "EU"
ENHANCEMENT_LEVEL = 0

START_DT = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
END_DT = datetime.now(timezone.utc)

CHUNK_DAYS = 7
ITEMS_FILE = "bdodatabase.txt"

BASE_URL_TEMPLATE = "https://apiv2.bdolytics.com/market/analytics/{item_id}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://bdolytics.com/",
    "Origin": "https://bdolytics.com"
}


NEIGHBOR_VOLUME_THRESHOLD = 1000
ALLOW_ONE_STRONG_NEIGHBOR = True
STRONG_NEIGHBOR_THRESHOLD = 5000


REQUEST_SLEEP_SECONDS = 0.5


COMPLETE_3H_THRESHOLD = 3000
LOW_DAILY_THRESHOLD = 500




def get_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )

    # Wymuszenie UTC po stronie sesji
    with conn.cursor() as cur:
        cur.execute("SET TIME ZONE 'UTC';")
    conn.commit()

    return conn


def create_table_if_not_exists(conn):
    sql = """
    CREATE TABLE IF NOT EXISTS bdolytics_history (
        id BIGSERIAL PRIMARY KEY,
        item_id INTEGER NOT NULL,
        recorded_at TIMESTAMPTZ NOT NULL,
        base_price BIGINT NOT NULL,
        current_stock BIGINT NOT NULL,
        trade_volume BIGINT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (item_id, recorded_at)
    );
    """
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def insert_rows(conn, rows):
    if not rows:
        return 0

    sql = """
    INSERT INTO bdolytics_history (
        item_id,
        recorded_at,
        base_price,
        current_stock,
        trade_volume
    )
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (item_id, recorded_at) DO NOTHING;
    """

    with conn.cursor() as cur:
        execute_batch(cur, sql, rows, page_size=500)

    conn.commit()
    return len(rows)


def count_rows_for_item(conn, item_id):
    sql = """
    SELECT COUNT(*)
    FROM bdolytics_history
    WHERE item_id = %s;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (item_id,))
        row = cur.fetchone()

    return int(row[0]) if row and row[0] is not None else 0



def load_item_ids(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    item_ids = []
    for item in data:
        item_id = item.get("id")
        if isinstance(item_id, int):
            item_ids.append(item_id)

    return item_ids



def should_drop_zero_volume_row(prev_row, curr_row, next_row):


    curr_volume = curr_row[3]

    if curr_volume != 0:
        return False

    prev_volume = prev_row[3] if prev_row is not None else None
    next_volume = next_row[3] if next_row is not None else None

    if (
        prev_volume is not None
        and next_volume is not None
        and prev_volume >= NEIGHBOR_VOLUME_THRESHOLD
        and next_volume >= NEIGHBOR_VOLUME_THRESHOLD
    ):
        return True

    if ALLOW_ONE_STRONG_NEIGHBOR:
        if (
            prev_volume is not None
            and next_volume is not None
            and (
                (prev_volume >= STRONG_NEIGHBOR_THRESHOLD and next_volume > 0) or
                (next_volume >= STRONG_NEIGHBOR_THRESHOLD and prev_volume > 0)
            )
        ):
            return True

    return False


def filter_rows_with_smart_zero_logic(raw_rows):
    if not raw_rows:
        return [], 0

    filtered = []
    dropped_zero_rows = 0

    for i, curr_row in enumerate(raw_rows):
        prev_row = raw_rows[i - 1] if i > 0 else None
        next_row = raw_rows[i + 1] if i < len(raw_rows) - 1 else None

        if should_drop_zero_volume_row(prev_row, curr_row, next_row):
            dropped_zero_rows += 1
            continue

        filtered.append(curr_row)

    return filtered, dropped_zero_rows


def should_fetch_item(conn, item_id):
    row_count = count_rows_for_item(conn, item_id)

    print(f"[item_id={item_id}] Liczba rekordów w bazie: {row_count}")

    if row_count >= COMPLETE_3H_THRESHOLD:
        print(f"[item_id={item_id}] Wygląda na kompletny zapis 3h -> pomijam.")
        return False

    if row_count <= LOW_DAILY_THRESHOLD:
        print(f"[item_id={item_id}] Wygląda na dane dzienne / bardzo niepełne -> pobieram pełny zakres.")
        return True

    print(f"[item_id={item_id}] Dane częściowe -> pobieram pełny zakres dla bezpieczeństwa.")
    return True




def fetch_item_history(item_id, start_dt, end_dt, chunk_days=7):

    url = BASE_URL_TEMPLATE.format(item_id=item_id)
    session = requests.Session()
    session.headers.update(HEADERS)

    raw_rows = []
    seen_timestamps = set()

    current_start = start_dt

    while current_start < end_dt:
        if chunk_days <= 0:
            current_end = end_dt
        else:
            current_end = min(current_start + timedelta(days=chunk_days), end_dt)

        start_ms = int(current_start.timestamp() * 1000)
        end_ms = int(current_end.timestamp() * 1000)

        params = {
            "start_date": start_ms,
            "end_date": end_ms,
            "region": REGION,
            "enhancement_level": ENHANCEMENT_LEVEL
        }

        print(f"[item_id={item_id}] Pobieram: {current_start} -> {current_end}")

        try:
            response = session.get(url, params=params, timeout=30)
            response.raise_for_status()

            json_data = response.json()
            data = json_data.get("data", [])

            chunk_added = 0

            for row in data:
                # spodziewany format: [timestamp_ms, base_price, current_stock, trade_volume]
                if not isinstance(row, list) or len(row) < 4:
                    continue

                ts, base_price, current_stock, trade_volume = row[:4]

                try:
                    ts = int(ts)
                    base_price = int(base_price)
                    current_stock = int(current_stock)
                    trade_volume = int(trade_volume)
                except (TypeError, ValueError):
                    continue

                if ts in seen_timestamps:
                    continue

                seen_timestamps.add(ts)
                raw_rows.append((ts, base_price, current_stock, trade_volume))
                chunk_added += 1

            print(f"[item_id={item_id}] OK, surowych rekordów z tego zakresu: {chunk_added}")

        except Exception as e:
            print(f"[item_id={item_id}] Błąd dla zakresu {current_start} -> {current_end}: {e}")

        current_start = current_end
        time.sleep(REQUEST_SLEEP_SECONDS)

    raw_rows.sort(key=lambda x: x[0])

    filtered_rows, dropped_zero_rows = filter_rows_with_smart_zero_logic(raw_rows)

    db_rows = []
    for ts, base_price, current_stock, trade_volume in filtered_rows:
        recorded_at = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        db_rows.append((
            item_id,
            recorded_at,
            base_price,
            current_stock,
            trade_volume
        ))

    print(f"[item_id={item_id}] Surowe rekordy łącznie: {len(raw_rows)}")
    print(f"[item_id={item_id}] Usunięte podejrzane zera: {dropped_zero_rows}")
    print(f"[item_id={item_id}] Rekordy końcowe do bazy: {len(db_rows)}")

    return db_rows




def main():
    global END_DT
    END_DT = datetime.now(timezone.utc)

    item_ids = load_item_ids(ITEMS_FILE)

    if not item_ids:
        print("Nie znaleziono żadnych item_id w pliku bdodatabase.txt")
        return

    print(f"Wczytano {len(item_ids)} itemów z pliku.")
    print(f"Zakres pobierania: {START_DT} -> {END_DT}")
    print(f"Próg kompletności 3h: {COMPLETE_3H_THRESHOLD}")
    print(f"Próg starych danych dziennych: {LOW_DAILY_THRESHOLD}")

    conn = get_connection()

    try:
        create_table_if_not_exists(conn)

        total_rows_for_insert = 0
        fetched_items = 0
        skipped_items = 0

        for index, item_id in enumerate(item_ids, start=1):
            print("=" * 100)
            print(f"Przetwarzam item {index}/{len(item_ids)}: item_id={item_id}")

            if not should_fetch_item(conn, item_id):
                skipped_items += 1
                continue

            fetched_items += 1

            rows = fetch_item_history(
                item_id=item_id,
                start_dt=START_DT,
                end_dt=END_DT,
                chunk_days=CHUNK_DAYS
            )

            inserted_count = insert_rows(conn, rows)
            total_rows_for_insert += inserted_count

            print(f"[item_id={item_id}] Przekazane do insertu: {inserted_count}")

        print("=" * 100)
        print("Zakończono.")
        print(f"Itemy pobierane: {fetched_items}")
        print(f"Itemy pominięte: {skipped_items}")
        print(f"Łączna liczba rekordów przekazanych do bazy: {total_rows_for_insert}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()