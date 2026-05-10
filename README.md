# BDO Market Data Collector

Python data collector for downloading historical market data from the BDOlytics API and storing it in a PostgreSQL database.

## Overview

This project collects historical market data for Black Desert Online items using the BDOlytics API.  
The downloaded data is saved into a PostgreSQL database for further analysis, reporting, forecasting, or dashboard development.

The collector supports chunked API requests, duplicate prevention, and basic filtering of suspicious zero-volume records.

## Features

- Downloads historical market data from the BDOlytics API
- Saves item history into PostgreSQL
- Uses chunked date ranges to avoid large API requests
- Prevents duplicate records with a unique database constraint
- Filters suspicious zero-volume records
- Supports environment-based database configuration
- Can be used as a base for data analysis or dashboard projects

## Tech Stack

- Python
- PostgreSQL
- requests
- psycopg2
- python-dotenv

## Database Table

The collector stores data in the `bdolytics_history` table.

```sql
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
```

## Environment Variables

Create a `.env` file based on `.env.example`.

Example:

```env
DB_HOST=localhost
DB_NAME=bdo_market
DB_USER=postgres
DB_PASSWORD=your_password_here
DB_PORT=5432
```
## Installation

Clone the repository:

```bash
git clone https://github.com/Sassenach03/bdo-market-data-collector.git
cd bdo-market-data-collector
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate the virtual environment:

Windows:

```bash
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

Run the collector:

```bash
python src/data_collector.py
```

The script will:

1. Connect to PostgreSQL
2. Create the database table if it does not exist
3. Load item IDs from the input file
4. Download historical market data from the API
5. Filter suspicious records
6. Insert new records into the database

## Notes

This project is intended for educational and portfolio purposes.  
It can be extended with additional data analysis, forecasting, API endpoints, or dashboard integration.

## Possible Future Improvements

- Add command-line arguments for date range and region
- Add better logging instead of print statements
- Add Docker Compose for PostgreSQL setup
- Add automatic database migrations
- Add tests for data filtering logic
- Add FastAPI endpoints for accessing collected data
- Add data analysis and forecasting modules

## Author

Created by Sassenach03.
