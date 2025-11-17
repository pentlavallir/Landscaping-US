
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional
import datetime
import os

DB_PATH = Path("landscaping.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables and seed initial data if needed."""
    conn = get_connection()
    cur = conn.cursor()

    # Users
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT,
            role TEXT NOT NULL,           -- 'admin' or 'owner'
            property_id INTEGER,
            created_at TEXT NOT NULL
        )
        """
    )

    # Properties
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            address TEXT,
            city TEXT,
            state TEXT,
            zip TEXT,
            annual_quote REAL DEFAULT 0,
            annual_credited REAL DEFAULT 0,
            annual_cost REAL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    # Property services
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS property_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            frequency TEXT NOT NULL,
            times_per_year INTEGER NOT NULL,
            each_time_cost REAL NOT NULL,
            notes TEXT
        )
        """
    )

    # Service personnel
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS service_persons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            role TEXT,
            notes TEXT,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )

    # Price master
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS price_master (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            frequency TEXT NOT NULL,
            default_cost REAL NOT NULL,
            notes TEXT
        )
        """
    )

    # Service events (scheduled/completed visits)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS service_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER NOT NULL,
            service_id INTEGER,
            provider_id INTEGER,
            service_category TEXT NOT NULL,
            scheduled_date TEXT NOT NULL,    -- YYYY-MM-DD
            scheduled_time TEXT,             -- HH:MM
            status TEXT NOT NULL DEFAULT 'Scheduled',
            followup_required INTEGER NOT NULL DEFAULT 0,
            followup_notes TEXT,
            last_reminder_at TEXT
        )
        """
    )

    # Tickets
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER NOT NULL,
            owner_id INTEGER,
            created_by_user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Open',      -- Open / In Progress / Closed
            priority TEXT NOT NULL DEFAULT 'Medium',  -- Low / Medium / High
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    # Ticket attachments
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ticket_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            mime_type TEXT,
            size_bytes INTEGER,
            uploaded_at TEXT NOT NULL
        )
        """
    )

    # Regions for quoting
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS regions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            state TEXT NOT NULL,
            city TEXT NOT NULL,
            property_type TEXT NOT NULL,     -- e.g. 'Residential', 'Small Industrial'
            labor_factor REAL NOT NULL DEFAULT 1.0,
            material_factor REAL NOT NULL DEFAULT 1.0
        )
        """
    )

    # Service catalog (for quoting templates)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS service_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,       -- e.g. 'WEED_CONTROL'
            display_name TEXT NOT NULL,
            default_times_per_year INTEGER NOT NULL
        )
        """
    )

    # Region-specific service rates
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS region_service_rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            region_id INTEGER NOT NULL,
            service_code TEXT NOT NULL,
            base_price_per_visit REAL NOT NULL,
            min_sqft INTEGER,
            max_sqft INTEGER,
            active INTEGER NOT NULL DEFAULT 1
        )
        """
    )

    conn.commit()

    # ---- Seed data if needed ----
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")

    # Seed users
    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        # Admin
        cur.execute(
            "INSERT INTO users (username, password, full_name, role, created_at) VALUES (?,?,?,?,?)",
            ("admin", "admin123", "System Admin", "admin", now),
        )
        # Owners will be added after properties exist

    # Seed properties if none
    cur.execute("SELECT COUNT(*) FROM properties")
    props_count = cur.fetchone()[0]
    if props_count == 0:
        sample_props = [
            ("Oakridge Villas", "123 Oakridge Ln", "Frisco", "TX", "75034"),
            ("Maple Heights", "456 Maple St", "Plano", "TX", "75025"),
            ("Cedar Grove Business Park", "12 Cedar Grove Dr", "Frisco", "TX", "75034"),
            ("Lakeview Estates", "87 Lakeview Cir", "Little Elm", "TX", "75068"),
            ("Willow Creek Offices", "25 Willow Creek Trl", "McKinney", "TX", "75071"),
            ("Sunset Ridge Center", "90 Sunset Ridge Rd", "Frisco", "TX", "75036"),
            ("Pine Meadows Plaza", "311 Pine Meadows Pl", "Plano", "TX", "75024"),
            ("Brookstone Park", "77 Brookstone Way", "Allen", "TX", "75013"),
            ("Heritage Oaks Campus", "64 Heritage Oaks Blvd", "Frisco", "TX", "75034"),
            ("Stonebridge Court", "19 Stonebridge Ct", "McKinney", "TX", "75070"),
        ]
        for name, addr, city, state, zip_code in sample_props:
            cur.execute(
                """
                INSERT INTO properties
                    (name, address, city, state, zip, annual_quote, annual_credited, annual_cost, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (name, addr, city, state, zip_code, 0.0, 0.0, 0.0, now, now),
            )

    conn.commit()

    # Seed owners mapped to properties if none
    cur.execute("SELECT COUNT(*) FROM users WHERE role = 'owner'")
    owner_count = cur.fetchone()[0]
    if owner_count == 0:
        cur.execute("SELECT id, name FROM properties ORDER BY id")
        props = cur.fetchall()
        idx = 1
        for p in props:
            username = f"owner{idx}"
            full_name = f"Property Owner {idx}"
            cur.execute(
                """
                INSERT INTO users (username, password, full_name, role, property_id, created_at)
                VALUES (?,?,?,?,?,?)
                """,
                (username, "owner123", full_name, "owner", p["id"], now),
            )
            idx += 1

    # Seed service catalog (standard 6 services)
    standard_services = [
        ("WEED_CONTROL", "Weed Control Spraying", 3),
        ("MOWING", "Mowing", 22),
        ("BLOWING", "Blowing & Trash Cleanup", 22),
        ("FERTILIZER", "Fertilizer", 5),
        ("TREE_SHRUB", "Tree & Shrub Care", 2),
        ("MULCH", "Mulch", 2),
    ]
    for code, name, times in standard_services:
        cur.execute("SELECT id FROM service_catalog WHERE code = ?", (code,))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO service_catalog (code, display_name, default_times_per_year) VALUES (?,?,?)",
                (code, name, times),
            )

    # Seed Frisco, TX, Small Industrial region
    cur.execute(
        "SELECT id FROM regions WHERE state = ? AND city = ? AND property_type = ?",
        ("TX", "Frisco", "Small Industrial"),
    )
    row = cur.fetchone()
    if row:
        region_id = row["id"]
    else:
        cur.execute(
            """
            INSERT INTO regions (state, city, property_type, labor_factor, material_factor)
            VALUES (?,?,?,?,?)
            """,
            ("TX", "Frisco", "Small Industrial", 1.0, 1.0),
        )
        region_id = cur.lastrowid

    # Seed region service rates for that region
    region_rates = {
        "WEED_CONTROL": 85.0,
        "MOWING": 60.0,
        "BLOWING": 15.0,
        "FERTILIZER": 80.0,
        "TREE_SHRUB": 120.0,
        "MULCH": 600.0,
    }
    for code, price in region_rates.items():
        cur.execute(
            "SELECT id FROM region_service_rates WHERE region_id = ? AND service_code = ?",
            (region_id, code),
        )
        if not cur.fetchone():
            cur.execute(
                """
                INSERT INTO region_service_rates
                    (region_id, service_code, base_price_per_visit, min_sqft, max_sqft, active)
                VALUES (?,?,?,?,?,1)
                """,
                (region_id, code, price, 0, 8000),
            )

    # Seed price master with generic entries
    price_rows = [
        ("Weed Control Spraying", "3 Times / Year", 85.0),
        ("Mowing", "Weekly (22 Visits)", 60.0),
        ("Blowing & Trash Cleanup", "Weekly (22 Visits)", 15.0),
        ("Fertilizer", "5 Times / Year", 80.0),
        ("Tree & Shrub Care", "Twice / Year", 120.0),
        ("Mulch", "Every 6 Months", 600.0),
    ]
    for cat, freq, cost in price_rows:
        cur.execute(
            "SELECT id FROM price_master WHERE category = ? AND frequency = ?",
            (cat, freq),
        )
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO price_master (category, frequency, default_cost) VALUES (?,?,?)",
                (cat, freq, cost),
            )

    conn.commit()

    # Seed property services for each property if it has none
    cur.execute("SELECT id, city, state FROM properties")
    props_all = cur.fetchall()
    for p in props_all:
        cur.execute(
            "SELECT COUNT(*) FROM property_services WHERE property_id = ?",
            (p["id"],),
        )
        if cur.fetchone()[0] == 0:
            # Add the 6 standard services
            for code, name, times in standard_services:
                # Map display names & frequency labels
                if code == "WEED_CONTROL":
                    freq = "3 Times / Year"
                    price = region_rates["WEED_CONTROL"]
                elif code == "MOWING":
                    freq = "Weekly (22 Visits)"
                    price = region_rates["MOWING"]
                elif code == "BLOWING":
                    freq = "Weekly (22 Visits)"
                    price = region_rates["BLOWING"]
                elif code == "FERTILIZER":
                    freq = "5 Times / Year"
                    price = region_rates["FERTILIZER"]
                elif code == "TREE_SHRUB":
                    freq = "Twice / Year"
                    price = region_rates["TREE_SHRUB"]
                elif code == "MULCH":
                    freq = "Every 6 Months"
                    price = region_rates["MULCH"]
                else:
                    freq = "Custom"
                    price = 100.0

                cur.execute(
                    """
                    INSERT INTO property_services
                        (property_id, category, frequency, times_per_year, each_time_cost, notes)
                    VALUES (?,?,?,?,?,?)
                    """,
                    (p["id"], name, freq, times, price, f"Standard {name} package"),
                )

    conn.commit()

    # Update annual cost / quote / credited for each property
    cur.execute("SELECT id FROM properties")
    for row_p in cur.fetchall():
        pid = row_p["id"]
        cur.execute(
            "SELECT times_per_year, each_time_cost FROM property_services WHERE property_id = ?",
            (pid,),
        )
        svcs = cur.fetchall()
        annual_cost = sum((s["times_per_year"] or 0) * (s["each_time_cost"] or 0.0) for s in svcs)
        annual_quote = annual_cost * 1.3  # 30% markup
        annual_credited = annual_quote * 0.95  # assume 95% realization
        cur.execute(
            """
            UPDATE properties
            SET annual_cost = ?, annual_quote = ?, annual_credited = ?, updated_at = ?
            WHERE id = ?
            """,
            (annual_cost, annual_quote, annual_credited, now, pid),
        )

    conn.commit()

    # Seed service persons
    cur.execute("SELECT COUNT(*) FROM service_persons")
    if cur.fetchone()[0] == 0:
        persons = [
            ("John Green", "john.green@example.com", "214-555-0101", "Crew Lead"),
            ("Maria Lopez", "maria.lopez@example.com", "214-555-0102", "Mower"),
            ("Sam Patel", "sam.patel@example.com", "214-555-0103", "Spray Tech"),
        ]
        for name, email, phone, role in persons:
            cur.execute(
                """
                INSERT INTO service_persons (full_name, email, phone, role, is_active)
                VALUES (?,?,?,?,1)
                """,
                (name, email, phone, role),
            )

    conn.commit()

    # Seed some service events for current year
    current_year = datetime.date.today().year
    cur.execute("SELECT COUNT(*) FROM service_events")
    if cur.fetchone()[0] == 0:
        # For each property, create some mowing events
        cur.execute(
            "SELECT id FROM properties ORDER BY id"
        )
        props = cur.fetchall()
        for p in props:
            pid = p["id"]
            # get mowing service
            cur.execute(
                """
                SELECT id, category FROM property_services
                WHERE property_id = ? AND category = 'Mowing'
                LIMIT 1
                """,
                (pid,),
            )
            mowing = cur.fetchone()
            if mowing:
                service_id = mowing["id"]
                # 3 completed, 1 scheduled
                for i in range(3):
                    date_str = f"{current_year}-04-{10+i:02d}"
                    cur.execute(
                        """
                        INSERT INTO service_events
                            (property_id, service_id, service_category, scheduled_date, scheduled_time, status)
                        VALUES (?,?,?,?,?,?)
                        """,
                        (pid, service_id, "Mowing", date_str, "09:00", "Completed"),
                    )
                cur.execute(
                    """
                    INSERT INTO service_events
                        (property_id, service_id, service_category, scheduled_date, scheduled_time, status)
                    VALUES (?,?,?,?,?,?)
                    """,
                    (pid, service_id, "Mowing", f"{current_year}-05-01", "09:00", "Scheduled"),
                )

    conn.commit()

    # Seed a couple of tickets
    cur.execute("SELECT COUNT(*) FROM tickets")
    if cur.fetchone()[0] == 0:
        cur.execute("SELECT id FROM properties ORDER BY id LIMIT 2")
        props = cur.fetchall()
        for idx, p in enumerate(props, start=1):
            pid = p["id"]
            # get first owner for that property
            cur.execute(
                "SELECT id FROM users WHERE role = 'owner' AND property_id = ? LIMIT 1",
                (pid,),
            )
            owner = cur.fetchone()
            owner_id = owner["id"] if owner else None
            subject = f"Irrigation concern #{idx}"
            desc = "Noticed dry patches near the entrance. Please inspect irrigation coverage."
            cur.execute(
                """
                INSERT INTO tickets
                    (property_id, owner_id, created_by_user_id, subject, description, status, priority, created_at, updated_at)
                VALUES (?,?,?,?,?,'Open','Medium',?,?)
                """,
                (pid, owner_id, owner_id or 1, subject, desc, now, now),
            )

    conn.commit()
    conn.close()


# ---------- Generic getters ----------

def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_properties() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM properties ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_property_by_id(property_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM properties WHERE id = ?", (property_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def add_property(name: str, address: str, city: str, state: str, zip_code: str,
                 annual_quote: float, annual_credited: float, annual_cost: float) -> int:
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO properties
            (name, address, city, state, zip, annual_quote, annual_credited, annual_cost, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (name, address, city, state, zip_code, annual_quote, annual_credited, annual_cost, now, now),
    )
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    return pid


def update_property(property_id: int, name: str, address: str, city: str, state: str, zip_code: str,
                    annual_quote: float, annual_credited: float, annual_cost: float) -> None:
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE properties
        SET name = ?, address = ?, city = ?, state = ?, zip = ?,
            annual_quote = ?, annual_credited = ?, annual_cost = ?, updated_at = ?
        WHERE id = ?
        """,
        (name, address, city, state, zip_code, annual_quote, annual_credited, annual_cost, now, property_id),
    )
    conn.commit()
    conn.close()


# ---------- Property services ----------

def get_services_for_property(property_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM property_services WHERE property_id = ? ORDER BY category",
        (property_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_property_service(property_id: int, category: str, frequency: str,
                         times_per_year: int, each_time_cost: float, notes: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO property_services
            (property_id, category, frequency, times_per_year, each_time_cost, notes)
        VALUES (?,?,?,?,?,?)
        """,
        (property_id, category, frequency, times_per_year, each_time_cost, notes),
    )
    conn.commit()
    sid = cur.lastrowid
    conn.close()
    return sid


def update_property_service(service_id: int, category: str, frequency: str,
                            times_per_year: int, each_time_cost: float, notes: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE property_services
        SET category = ?, frequency = ?, times_per_year = ?, each_time_cost = ?, notes = ?
        WHERE id = ?
        """,
        (category, frequency, times_per_year, each_time_cost, notes, service_id),
    )
    conn.commit()
    conn.close()


def delete_property_service(service_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM property_services WHERE id = ?", (service_id,))
    conn.commit()
    conn.close()


# ---------- Service personnel ----------

def get_all_service_persons() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM service_persons ORDER BY full_name")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_service_person(full_name: str, email: str, phone: str, role: str, notes: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO service_persons
            (full_name, email, phone, role, notes, is_active)
        VALUES (?,?,?,?,?,1)
        """,
        (full_name, email, phone, role, notes),
    )
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    return pid


def update_service_person(person_id: int, full_name: str, email: str, phone: str,
                          role: str, notes: str, is_active: bool) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE service_persons
        SET full_name = ?, email = ?, phone = ?, role = ?, notes = ?, is_active = ?
        WHERE id = ?
        """,
        (full_name, email, phone, role, notes, 1 if is_active else 0, person_id),
    )
    conn.commit()
    conn.close()


# ---------- Price master ----------

def get_price_master_all() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM price_master ORDER BY category, frequency")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_price_master_entry(category: str, frequency: str, default_cost: float, notes: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO price_master (category, frequency, default_cost, notes)
        VALUES (?,?,?,?)
        """,
        (category, frequency, default_cost, notes),
    )
    conn.commit()
    eid = cur.lastrowid
    conn.close()
    return eid


def update_price_master_entry(entry_id: int, category: str, frequency: str,
                              default_cost: float, notes: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE price_master
        SET category = ?, frequency = ?, default_cost = ?, notes = ?
        WHERE id = ?
        """,
        (category, frequency, default_cost, notes, entry_id),
    )
    conn.commit()
    conn.close()


def delete_price_master_entry(entry_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM price_master WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()


# ---------- Events & fulfilment ----------

def add_service_event(property_id: int, service_id: Optional[int], provider_id: Optional[int],
                      service_category: str, scheduled_date: str, scheduled_time: Optional[str],
                      followup_required: bool, followup_notes: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO service_events
            (property_id, service_id, provider_id, service_category,
             scheduled_date, scheduled_time, status,
             followup_required, followup_notes)
        VALUES (?,?,?,?,?,?,'Scheduled',?,?)
        """,
        (
            property_id,
            service_id,
            provider_id,
            service_category,
            scheduled_date,
            scheduled_time,
            1 if followup_required else 0,
            followup_notes,
        ),
    )
    conn.commit()
    eid = cur.lastrowid
    conn.close()
    return eid


def get_scheduled_events(from_date: str, to_date: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT e.*, p.name AS property_name,
               sp.full_name AS provider_name,
               sp.email AS provider_email,
               sp.phone AS provider_phone
        FROM service_events e
        JOIN properties p ON e.property_id = p.id
        LEFT JOIN service_persons sp ON e.provider_id = sp.id
        WHERE e.scheduled_date BETWEEN ? AND ?
        ORDER BY e.scheduled_date, COALESCE(e.scheduled_time, '')
        """,
        (from_date, to_date),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_service_event_status(event_id: int, status: str,
                                followup_required: bool, followup_notes: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE service_events
        SET status = ?, followup_required = ?, followup_notes = ?
        WHERE id = ?
        """,
        (status, 1 if followup_required else 0, followup_notes, event_id),
    )
    conn.commit()
    conn.close()


def touch_service_event_reminder(event_id: int) -> None:
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE service_events SET last_reminder_at = ? WHERE id = ?",
        (now, event_id),
    )
    conn.commit()
    conn.close()


def delete_service_event(event_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM service_events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()


def get_events_for_property(property_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM service_events WHERE property_id = ? ORDER BY scheduled_date, COALESCE(scheduled_time,'')",
        (property_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_service_fulfilment_for_property(property_id: int, year: int) -> List[Dict[str, Any]]:
    """Return per-service fulfilment stats for a property and year."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM property_services WHERE property_id = ?",
        (property_id,),
    )
    services = cur.fetchall()

    results = []
    for s in services:
        sid = s["id"]
        planned = s["times_per_year"] or 0

        cur.execute(
            """
            SELECT
                SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN status = 'Scheduled' THEN 1 ELSE 0 END) AS scheduled
            FROM service_events
            WHERE property_id = ?
              AND service_id = ?
              AND substr(scheduled_date,1,4) = ?
            """,
            (property_id, sid, str(year)),
        )
        r = cur.fetchone()
        completed = r["completed"] or 0
        scheduled = r["scheduled"] or 0
        pending = max(planned - completed, 0)
        completion_pct = (completed / planned * 100.0) if planned > 0 else None

        results.append(
            {
                "service_id": sid,
                "category": s["category"],
                "frequency": s["frequency"],
                "times_per_year": planned,
                "completed_count": completed,
                "pending_count": pending,
                "scheduled_count": scheduled,
                "completion_pct": completion_pct,
            }
        )

    conn.close()
    return results


def get_portfolio_fulfilment(year: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM properties")
    props = cur.fetchall()
    rows = []
    for p in props:
        pf = get_service_fulfilment_for_property(p["id"], year)
        total_planned = sum(s["times_per_year"] or 0 for s in pf)
        total_completed = sum(s["completed_count"] or 0 for s in pf)
        total_pending = max(total_planned - total_completed, 0)
        completion_pct = (total_completed / total_planned * 100.0) if total_planned > 0 else None

        # Status
        if total_planned == 0:
            status = "Not configured"
        elif total_pending == 0:
            status = "On Track"
        elif total_completed == 0:
            status = "Not Started"
        else:
            status = "In Progress"

        rows.append(
            {
                "property_id": p["id"],
                "property_name": p["name"],
                "planned": total_planned,
                "completed": total_completed,
                "pending": total_pending,
                "completion_pct": completion_pct,
                "status": status,
            }
        )
    conn.close()
    return rows


# ---------- Tickets ----------

def get_tickets_for_owner(owner_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT t.*, p.name AS property_name
        FROM tickets t
        JOIN properties p ON t.property_id = p.id
        WHERE t.owner_id = ?
        ORDER BY t.created_at DESC
        """,
        (owner_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_tickets() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT t.*, p.name AS property_name, u.full_name AS owner_name
        FROM tickets t
        JOIN properties p ON t.property_id = p.id
        LEFT JOIN users u ON t.owner_id = u.id
        ORDER BY t.created_at DESC
        """
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_ticket(property_id: int, owner_id: Optional[int], created_by_user_id: int,
               subject: str, description: str, priority: str) -> int:
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO tickets
            (property_id, owner_id, created_by_user_id,
             subject, description, status, priority,
             created_at, updated_at)
        VALUES (?,?,?,?,?,'Open',?,?,?)
        """,
        (property_id, owner_id, created_by_user_id, subject, description, priority, now, now),
    )
    conn.commit()
    tid = cur.lastrowid
    conn.close()
    return tid


def update_ticket_status(ticket_id: int, status: str, priority: str, description: Optional[str]) -> None:
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    conn = get_connection()
    cur = conn.cursor()
    if description is not None:
        cur.execute(
            """
            UPDATE tickets
            SET status = ?, priority = ?, description = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, priority, description, now, ticket_id),
        )
    else:
        cur.execute(
            """
            UPDATE tickets
            SET status = ?, priority = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, priority, now, ticket_id),
        )
    conn.commit()
    conn.close()


def add_ticket_attachment(ticket_id: int, filename: str, stored_path: str,
                          mime_type: str, size_bytes: int) -> None:
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO ticket_attachments
            (ticket_id, filename, stored_path, mime_type, size_bytes, uploaded_at)
        VALUES (?,?,?,?,?,?)
        """,
        (ticket_id, filename, stored_path, mime_type, size_bytes, now),
    )
    conn.commit()
    conn.close()


def get_attachments_for_ticket(ticket_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM ticket_attachments WHERE ticket_id = ? ORDER BY uploaded_at DESC, id DESC",
        (ticket_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------- Counts for dashboard ----------

def count_open_tickets() -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM tickets WHERE status = 'Open'")
    n = cur.fetchone()[0]
    conn.close()
    return n


def count_overdue_events(today_iso: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*) FROM service_events
        WHERE status = 'Scheduled' AND scheduled_date < ?
        """,
        (today_iso,),
    )
    n = cur.fetchone()[0]
    conn.close()
    return n


def count_active_service_persons() -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM service_persons WHERE is_active = 1")
    n = cur.fetchone()[0]
    conn.close()
    return n


def count_price_master_entries() -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM price_master")
    n = cur.fetchone()[0]
    conn.close()
    return n


# ---------- Regions & quoting ----------

def get_regions() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM regions ORDER BY state, city, property_type")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_region_by_id(region_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM regions WHERE id = ?", (region_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_region_service_rates(region_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT rsr.*, sc.display_name, sc.default_times_per_year
        FROM region_service_rates rsr
        JOIN service_catalog sc ON rsr.service_code = sc.code
        WHERE rsr.region_id = ? AND rsr.active = 1
        ORDER BY sc.display_name
        """,
        (region_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ----------------------
# Quotes & Quote Line Items
# ----------------------

def _ensure_quote_tables() -> None:
    """Create quotes + quote_line_items tables if they don't already exist."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            region_label TEXT NOT NULL,
            customer_name TEXT,
            customer_email TEXT,
            property_name TEXT,
            property_size_band TEXT,
            sqft_estimate INTEGER,
            notes TEXT,
            annual_quote REAL NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS quote_line_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_id INTEGER NOT NULL,
            service_code TEXT NOT NULL,
            service_name TEXT NOT NULL,
            times_per_year INTEGER NOT NULL,
            price_per_visit REAL NOT NULL,
            annual_total REAL NOT NULL,
            included INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (quote_id) REFERENCES quotes (id)
        )
        """
    )

    conn.commit()
    conn.close()


def add_quote(
    region_label: str,
    customer_name: Optional[str],
    customer_email: Optional[str],
    property_name: Optional[str],
    property_size_band: Optional[str],
    sqft_estimate: Optional[int],
    notes: Optional[str],
    annual_quote: float,
    line_items: List[Dict[str, Any]],
) -> int:
    """Insert a quote and its line items, returning the quote id."""
    _ensure_quote_tables()
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")

    cur.execute(
        """
        INSERT INTO quotes (
            region_label, customer_name, customer_email,
            property_name, property_size_band, sqft_estimate,
            notes, annual_quote, created_at
        )
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            region_label,
            customer_name,
            customer_email,
            property_name,
            property_size_band,
            sqft_estimate,
            notes,
            annual_quote,
            now,
        ),
    )
    quote_id = cur.lastrowid

    for item in line_items:
        cur.execute(
            """
            INSERT INTO quote_line_items (
                quote_id, service_code, service_name,
                times_per_year, price_per_visit, annual_total, included
            )
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                quote_id,
                item.get("service_code") or "",
                item.get("service_name") or "",
                int(item.get("times_per_year") or 0),
                float(item.get("price_per_visit") or 0.0),
                float(item.get("annual_total") or 0.0),
                1 if item.get("included", True) else 0,
            ),
        )

    conn.commit()
    conn.close()
    return quote_id


def get_quote_with_items(quote_id: int) -> tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Fetch a quote and its included line items."""
    _ensure_quote_tables()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM quotes WHERE id = ?", (quote_id,))
    q_row = cur.fetchone()
    if not q_row:
        conn.close()
        return None, []
    cur.execute(
        "SELECT * FROM quote_line_items WHERE quote_id = ? AND included = 1",
        (quote_id,),
    )
    items = cur.fetchall()
    conn.close()
    return dict(q_row), [dict(r) for r in items]


def _derive_frequency_label(times_per_year: int, service_name: str) -> str:
    """Derive a human-readable frequency label from times/year and service name."""
    name = (service_name or "").lower()
    if "mulch" in name:
        return "Every 6 Months"
    if times_per_year == 22:
        return "Weekly (22 visits)"
    if times_per_year == 3:
        return "3 Times / Year"
    if times_per_year == 5:
        return "5 Times / Year"
    if times_per_year == 2:
        return "Twice / Year"
    if times_per_year == 1:
        return "Once / Year"
    if times_per_year <= 0:
        return "Not configured"
    return f"{times_per_year} Times / Year"


def convert_quote_to_property(quote_id: int) -> Optional[int]:
    """Create a new property and property_services rows from a saved quote.

    Returns the new property_id, or None if the quote cannot be converted.
    """
    quote, items = get_quote_with_items(quote_id)
    if not quote or not items:
        return None

    conn = get_connection()
    cur = conn.cursor()
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")

    # region_label format is expected like "TX - Frisco - Small Industrial"
    state = ""
    city = ""
    region_label = quote.get("region_label") or ""
    parts = [p.strip() for p in region_label.split("-")]
    if len(parts) >= 1:
        state = parts[0]
    if len(parts) >= 2:
        city = parts[1]

    prop_name = quote.get("property_name") or f"Quoted Property #{quote_id}"

    cur.execute(
        """
        INSERT INTO properties (
            name, address, city, state, zip,
            annual_quote, annual_credited, annual_cost,
            created_at, updated_at
        )
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            prop_name,
            "",
            city,
            state,
            "",
            float(quote.get("annual_quote") or 0.0),
            0.0,
            0.0,
            now,
            now,
        ),
    )
    property_id = cur.lastrowid

    for item in items:
        service_name = item.get("service_name") or ""
        times = int(item.get("times_per_year") or 0)
        price = float(item.get("price_per_visit") or 0.0)
        freq_label = _derive_frequency_label(times, service_name)
        cur.execute(
            """
            INSERT INTO property_services (
                property_id, category, frequency, times_per_year, each_time_cost, notes
            )
            VALUES (?,?,?,?,?,?)
            """,
            (
                property_id,
                service_name,
                freq_label,
                times,
                price,
                f"Imported from quote #{quote_id}",
            ),
        )

    conn.commit()
    conn.close()
    return property_id
