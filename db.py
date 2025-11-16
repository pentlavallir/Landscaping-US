import datetime
import hashlib
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).parent / "data" / "app.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------- Password helpers ----------

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash


# ---------- DB Init & Seed ----------

def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()

    # Users
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            email TEXT,
            role TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            property_id INTEGER,
            phone TEXT,
            FOREIGN KEY (property_id) REFERENCES properties(id)
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
            zip TEXT
        )
        """
    )

    # Ensure revenue fields exist on properties
    cur.execute("PRAGMA table_info(properties)")
    pcols = [row[1] for row in cur.fetchall()]
    if "annual_quote" not in pcols:
        cur.execute("ALTER TABLE properties ADD COLUMN annual_quote REAL DEFAULT 0")
    if "annual_credited" not in pcols:
        cur.execute("ALTER TABLE properties ADD COLUMN annual_credited REAL DEFAULT 0")

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
            status TEXT NOT NULL DEFAULT 'Scheduled',
            last_updated_at TEXT,
            last_updated_by TEXT,
            FOREIGN KEY (property_id) REFERENCES properties(id)
        )
        """
    )


    # Ensure new date fields exist on property_services for tracking
    cur.execute("PRAGMA table_info(property_services)")
    cols = [row[1] for row in cur.fetchall()]
    if "start_date" not in cols:
        cur.execute("ALTER TABLE property_services ADD COLUMN start_date TEXT")
    if "end_date" not in cols:
        cur.execute("ALTER TABLE property_services ADD COLUMN end_date TEXT")

    # Tickets
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER NOT NULL,
            owner_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            admin_comment TEXT,
            FOREIGN KEY (property_id) REFERENCES properties(id),
            FOREIGN KEY (owner_id) REFERENCES users(id)
        )
        """
    )

    # Service attachments (images, etc.)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS service_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            uploaded_by TEXT,
            FOREIGN KEY (service_id) REFERENCES property_services(id)
        )
        """
    )
    # Service persons (crew / technicians)
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



    # Service events (scheduled activities)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS service_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER NOT NULL,
            service_id INTEGER,
            provider_id INTEGER,
            service_category TEXT NOT NULL,
            scheduled_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Scheduled',
            followup_required INTEGER NOT NULL DEFAULT 0,
            followup_notes TEXT,
            last_reminder_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (property_id) REFERENCES properties(id),
            FOREIGN KEY (service_id) REFERENCES property_services(id),
            FOREIGN KEY (provider_id) REFERENCES service_persons(id)
        )
        """
    )

    conn.commit()

    # Schema upgrades for older DBs
    _upgrade_schema(cur)
    conn.commit()

    # Seed data if empty
    seed_properties(cur)
    seed_price_master(cur)
    conn.commit()
    seed_property_services_and_users(cur)
    conn.commit()
    conn.close()


def _column_exists(cur: sqlite3.Cursor, table: str, column: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r["name"] for r in cur.fetchall()]
    return column in cols


def _upgrade_schema(cur: sqlite3.Cursor) -> None:
    """Ensure newer columns exist for older DBs."""
    # users.phone
    if not _column_exists(cur, "users", "phone"):
        cur.execute("ALTER TABLE users ADD COLUMN phone TEXT")

    # property_services.status / last_updated_at / last_updated_by
    if not _column_exists(cur, "property_services", "status"):
        cur.execute("ALTER TABLE property_services ADD COLUMN status TEXT NOT NULL DEFAULT 'Scheduled'")
    if not _column_exists(cur, "property_services", "last_updated_at"):
        cur.execute("ALTER TABLE property_services ADD COLUMN last_updated_at TEXT")
    if not _column_exists(cur, "property_services", "last_updated_by"):
        cur.execute("ALTER TABLE property_services ADD COLUMN last_updated_by TEXT")

    
    # service_events.scheduled_time
    if not _column_exists(cur, "service_events", "scheduled_time"):
        cur.execute("ALTER TABLE service_events ADD COLUMN scheduled_time TEXT")
# service_attachments table
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS service_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            uploaded_by TEXT,
            FOREIGN KEY (service_id) REFERENCES property_services(id)
        )
        """
    )


def seed_properties(cur: sqlite3.Cursor) -> None:
    cur.execute("SELECT COUNT(*) FROM properties")
    (count,) = cur.fetchone()
    if count > 0:
        return

    properties = [
        ("Property 1 - Frisco", "123 Main St", "Frisco", "TX", "75034"),
        ("Property 2 - Frisco", "456 Oak Lane", "Frisco", "TX", "75035"),
        ("Property 3 - Frisco", "789 Maple Ave", "Frisco", "TX", "75036"),
        ("Property 4 - Frisco", "101 Pine Ridge", "Frisco", "TX", "75033"),
        ("Property 5 - Frisco", "202 Cedar Trail", "Frisco", "TX", "75034"),
    ]
    cur.executemany(
        "INSERT INTO properties (name, address, city, state, zip) VALUES (?, ?, ?, ?, ?)",
        properties,
    )


def seed_price_master(cur: sqlite3.Cursor) -> None:
    cur.execute("SELECT COUNT(*) FROM price_master")
    (count,) = cur.fetchone()
    if count > 0:
        return

    price_rows = [
        ("Mowing", "Weekly", 40, "Standard weekly mowing"),
        ("Mowing", "Bi-weekly", 45, "Standard bi-weekly mowing"),
        ("Weed", "Monthly", 25, "Weed control / beds"),
        ("Blowing", "With Mowing", 0, "Included in mowing cost"),
        ("Fertilizer", "Every 6 Months", 75, "Lawn fertilization"),
        ("Tree Shrub", "Every 6 Months", 90, "Tree and shrub care (small/medium)"),
        ("Mulch", "Yearly", 150, "Mulch refresh for typical yard"),
        ("Leaf Cleanup", "Seasonal", 120, "Fall leaf cleanup"),
        ("Spring Cleanup", "Seasonal", 130, "Spring yard/beds cleanup"),
        ("Irrigation Check", "Monthly", 30, "Sprinkler system inspection"),
    ]

    cur.executemany(
        """
        INSERT INTO price_master (category, frequency, default_cost, notes)
        VALUES (?, ?, ?, ?)
        """,
        price_rows,
    )


def seed_property_services_and_users(cur: sqlite3.Cursor) -> None:
    # Seed users if needed
    cur.execute("SELECT COUNT(*) FROM users")
    (user_count,) = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM property_services")
    (svc_count,) = cur.fetchone()

    # Get properties
    cur.execute("SELECT id, name FROM properties ORDER BY id")
    props = cur.fetchall()
    if not props:
        return

    # Map category/frequency to default_cost
    cur.execute("SELECT category, frequency, default_cost FROM price_master")
    rows = cur.fetchall()
    price_map = {
        (r["category"], r["frequency"]): r["default_cost"]
        for r in rows
    }

    # Dummy schedules similar to the Excel version
    dummy_data_by_property = {
        1: [
            ("Mowing", "Bi-weekly", 26),
            ("Weed", "Monthly", 12),
            ("Fertilizer", "Every 6 Months", 2),
            ("Mulch", "Yearly", 1),
        ],
        2: [
            ("Mowing", "Weekly", 32),
            ("Weed", "Monthly", 10),
            ("Tree Shrub", "Every 6 Months", 2),
            ("Leaf Cleanup", "Seasonal", 1),
        ],
        3: [
            ("Mowing", "Bi-weekly", 20),
            ("Blowing", "With Mowing", 20),
            ("Fertilizer", "Every 6 Months", 2),
            ("Spring Cleanup", "Seasonal", 1),
        ],
        4: [
            ("Mowing", "Weekly", 30),
            ("Weed", "Monthly", 8),
            ("Irrigation Check", "Monthly", 6),
        ],
        5: [
            ("Mowing", "Bi-weekly", 24),
            ("Weed", "Monthly", 12),
            ("Tree Shrub", "Every 6 Months", 2),
            ("Mulch", "Yearly", 1),
            ("Leaf Cleanup", "Seasonal", 1),
        ],
    }

    # Seed services if empty
    if svc_count == 0:
        for prop in props:
            prop_id = prop["id"]
            data = dummy_data_by_property.get(prop_id, [])
            for category, frequency, times in data:
                default_cost = price_map.get((category, frequency), 0.0)
                cur.execute(
                    """
                    INSERT INTO property_services (
                        property_id, category, frequency, times_per_year, each_time_cost, status
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (prop_id, category, frequency, times, default_cost, "Scheduled"),
                )

    # Seed users if none
    if user_count == 0:
        # Admin
        cur.execute(
            """
            INSERT INTO users (username, full_name, email, role, password_hash, property_id, phone)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "admin",
                "Admin User",
                "admin@example.com",
                "admin",
                hash_password("admin123"),
                None,
                None,
            ),
        )

        # Two owner accounts mapped to first two properties
        owner_defs = [
            ("owner1", "Property Owner 1", "owner1@example.com", 1, "+15550000001"),
            ("owner2", "Property Owner 2", "owner2@example.com", 2, "+15550000002"),
        ]
        for username, full_name, email, prop_index, phone in owner_defs:
            if prop_index <= len(props):
                prop_id = props[prop_index - 1]["id"]
            else:
                prop_id = None
            cur.execute(
                """
                INSERT INTO users (username, full_name, email, role, password_hash, property_id, phone)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    full_name,
                    email,
                    "owner",
                    hash_password("owner123"),
                    prop_id,
                    phone,
                ),
            )


# ---------- Users ----------

def get_user_by_username(username: str) -> Optional[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return row


def get_owners_for_property(property_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM users
        WHERE property_id = ? AND role = 'owner'
        """,
        (property_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------- Properties & Services ----------

def get_all_properties() -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM properties ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_property_by_id(property_id: int) -> Optional[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM properties WHERE id = ?", (property_id,))
    row = cur.fetchone()
    conn.close()
    return row

def add_property(
    name: str,
    address: str,
    city: str,
    state: str,
    zip_code: str,
    annual_quote: float,
    annual_credited: float,
) -> None:
    """Insert a new property including initial financials."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO properties (name, address, city, state, zip, annual_quote, annual_credited) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name, address, city, state, zip_code, annual_quote, annual_credited),
    )
    conn.commit()
    conn.close()


def update_property(
    property_id: int,
    name: str,
    address: str,
    city: str,
    state: str,
    zip_code: str,
    annual_quote: float,
    annual_credited: float,
) -> None:
    """Update core property details including financials."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE properties SET name = ?, address = ?, city = ?, state = ?, zip = ?, annual_quote = ?, annual_credited = ? WHERE id = ?",
        (name, address, city, state, zip_code, annual_quote, annual_credited, property_id),
    )
    conn.commit()
    conn.close()


def get_properties_summary() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            p.id,
            p.name,
            COALESCE(SUM(ps.times_per_year), 0) AS total_services,
            COALESCE(SUM(ps.times_per_year * ps.each_time_cost), 0) AS total_cost,
            COALESCE(p.annual_quote, 0) AS annual_quote,
            COALESCE(p.annual_credited, 0) AS annual_credited
        FROM properties p
        LEFT JOIN property_services ps ON ps.property_id = p.id
        GROUP BY p.id, p.name, p.annual_quote, p.annual_credited
        ORDER BY p.id
        """
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_property_summary(property_id: int) -> Dict[str, Any]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            COALESCE(SUM(times_per_year), 0) AS total_services,
            COALESCE(SUM(times_per_year * each_time_cost), 0) AS total_cost
        FROM property_services
        WHERE property_id = ?
        """,
        (property_id,),
    )
    row = cur.fetchone()
    conn.close()
    return {
        "total_services": row["total_services"] or 0,
        "total_cost": row["total_cost"] or 0.0,
    }


def get_services_for_property(property_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, category, frequency, times_per_year, each_time_cost,
               status, last_updated_at, last_updated_by
        FROM property_services
        WHERE property_id = ?
        ORDER BY category, frequency
        """,
        (property_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_service_by_id(service_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, property_id, category, frequency, times_per_year, each_time_cost,
               status, last_updated_at, last_updated_by
        FROM property_services
        WHERE id = ?
        """,
        (service_id,),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def add_service_to_property(
    property_id: int, category: str, frequency: str, times_per_year: int
) -> None:
    # Use price master default if available
    default_cost = get_price_for_category_frequency(category, frequency)
    if default_cost is None:
        default_cost = 0.0

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO property_services (
            property_id, category, frequency, times_per_year, each_time_cost, status
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (property_id, category, frequency, times_per_year, default_cost, "Scheduled"),
    )
    conn.commit()
    conn.close()


def update_service_status(service_id: int, status: str, updated_by: str) -> None:
    now = datetime.datetime.datetime.utcnow().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE property_services
        SET status = ?, last_updated_at = ?, last_updated_by = ?
        WHERE id = ?
        """,
        (status, now, updated_by, service_id),
    )
    conn.commit()
    conn.close()

def update_service_details(
    service_id: int,
    category: str,
    frequency: str,
    times_per_year: int,
    each_time_cost: float,
    start_date: str,
    end_date: str,
    updated_by: str,
) -> None:
    now = datetime.datetime.datetime.utcnow().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE property_services
        SET category = ?, frequency = ?, times_per_year = ?, each_time_cost = ?,
            start_date = ?, end_date = ?,
            last_updated_at = ?, last_updated_by = ?
        WHERE id = ?
        """,
        (category, frequency, times_per_year, each_time_cost, start_date, end_date, now, updated_by, service_id),
    )
    conn.commit()
    conn.close()


def get_frequency_summary() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT frequency, SUM(times_per_year) AS total_services
        FROM property_services
        GROUP BY frequency
        ORDER BY total_services DESC
        """
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {"frequency": r["frequency"], "total_services": r["total_services"]}
        for r in rows
    ]


# ---------- Attachments ----------

def add_service_attachment(
    service_id: int,
    file_name: str,
    file_path: str,
    uploaded_by: Optional[str],
) -> None:
    now = datetime.datetime.datetime.utcnow().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO service_attachments (
            service_id, file_name, file_path, uploaded_at, uploaded_by
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (service_id, file_name, file_path, now, uploaded_by),
    )
    conn.commit()
    conn.close()


def get_service_attachments(service_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, service_id, file_name, file_path, uploaded_at, uploaded_by
        FROM service_attachments
        WHERE service_id = ?
        ORDER BY uploaded_at DESC
        """,
        (service_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------- Price Master ----------

def get_price_master_all() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, category, frequency, default_cost, notes FROM price_master "
        "ORDER BY category, frequency"
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_price_for_category_frequency(
    category: str, frequency: str
) -> Optional[float]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT default_cost
        FROM price_master
        WHERE category = ? AND frequency = ?
        """,
        (category, frequency),
    )
    row = cur.fetchone()
    conn.close()
    if row:
        return float(row["default_cost"])
    return None


def add_price_master_entry(
    category: str, frequency: str, default_cost: float, notes: str
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO price_master (category, frequency, default_cost, notes)
        VALUES (?, ?, ?, ?)
        """,
        (category, frequency, default_cost, notes),
    )
    conn.commit()
    conn.close()



def update_price_master_entry(
    entry_id: int,
    category: str,
    frequency: str,
    default_cost: float,
    notes: str,
) -> None:
    """Update an existing price master row."""
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
    """Delete a price master entry permanently."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM price_master WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()


# ---------- Tickets ----------

def create_ticket(
    property_id: int,
    owner_id: int,
    title: str,
    description: str,
) -> None:
    now = datetime.datetime.datetime.utcnow().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO tickets (
            property_id, owner_id, title, description, status,
            created_at, updated_at, admin_comment
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (property_id, owner_id, title, description, "Open", now, now, None),
    )
    conn.commit()
    conn.close()


def list_tickets_for_owner(owner_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            t.id,
            t.title,
            t.description,
            t.status,
            t.created_at,
            t.updated_at,
            t.admin_comment
        FROM tickets t
        WHERE t.owner_id = ?
        ORDER BY t.created_at DESC
        """,
        (owner_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_all_tickets() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            t.id,
            t.title,
            t.description,
            t.status,
            t.created_at,
            t.updated_at,
            t.admin_comment,
            p.name AS property_name,
            u.username AS owner_username
        FROM tickets t
        JOIN properties p ON t.property_id = p.id
        JOIN users u ON t.owner_id = u.id
        ORDER BY t.created_at DESC
        """
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_ticket(ticket_id: int, status: str, admin_comment: str) -> None:
    now = datetime.datetime.datetime.utcnow().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE tickets
        SET status = ?, admin_comment = ?, updated_at = ?
        WHERE id = ?
        """,
        (status, admin_comment, now, ticket_id),
    )
    conn.commit()
    conn.close()

# ---------- Service Persons (Crew) ----------

def list_service_persons(active_only: bool = False) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    if active_only:
        cur.execute(
            "SELECT id, full_name, email, phone, role, notes, is_active FROM service_persons WHERE is_active = 1 ORDER BY full_name"
        )
    else:
        cur.execute(
            "SELECT id, full_name, email, phone, role, notes, is_active FROM service_persons ORDER BY full_name"
        )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_service_person(
    full_name: str,
    email: str,
    phone: str,
    role: str,
    notes: str,
    is_active: bool = True,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO service_persons (full_name, email, phone, role, notes, is_active)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (full_name, email, phone, role, notes, 1 if is_active else 0),
    )
    conn.commit()
    conn.close()


def update_service_person(
    person_id: int,
    full_name: str,
    email: str,
    phone: str,
    role: str,
    notes: str,
    is_active: bool,
) -> None:
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


def get_service_person_by_id(person_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, full_name, email, phone, role, notes, is_active
        FROM service_persons
        WHERE id = ?
        """,
        (person_id,),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None



def get_all_service_persons() -> List[Dict[str, Any]]:
    """Return all service persons for assignment & admin screens."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, full_name, email, phone, role, notes, is_active
        FROM service_persons
        ORDER BY full_name
        """
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ---------- Users Management (Admin) ----------

def list_users(role: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    if role:
        cur.execute(
            """
            SELECT u.id, u.username, u.full_name, u.email, u.role, u.property_id,
                   u.phone, p.name AS property_name
            FROM users u
            LEFT JOIN properties p ON u.property_id = p.id
            WHERE u.role = ?
            ORDER BY u.username
            """,
            (role,),
        )
    else:
        cur.execute(
            """
            SELECT u.id, u.username, u.full_name, u.email, u.role, u.property_id,
                   u.phone, p.name AS property_name
            FROM users u
            LEFT JOIN properties p ON u.property_id = p.id
            ORDER BY u.username
            """
        )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_user(
    username: str,
    full_name: str,
    email: str,
    role: str,
    password: str,
    property_id: Optional[int],
    phone: str,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO users (username, full_name, email, role, password_hash, property_id, phone)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            username,
            full_name,
            email,
            role,
            hash_password(password),
            property_id,
            phone,
        ),
    )
    conn.commit()
    conn.close()


def update_user(
    user_id: int,
    full_name: str,
    email: str,
    role: str,
    property_id: Optional[int],
    phone: str,
    new_password: Optional[str] = None,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    if new_password:
        cur.execute(
            """
            UPDATE users
            SET full_name = ?, email = ?, role = ?, property_id = ?, phone = ?, password_hash = ?
            WHERE id = ?
            """,
            (
                full_name,
                email,
                role,
                property_id,
                phone,
                hash_password(new_password),
                user_id,
            ),
        )
    else:
        cur.execute(
            """
            UPDATE users
            SET full_name = ?, email = ?, role = ?, property_id = ?, phone = ?
            WHERE id = ?
            """,
            (
                full_name,
                email,
                role,
                property_id,
                phone,
                user_id,
            ),
        )
    conn.commit()
    conn.close()


def delete_user(user_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


# ---------- All Services (for Reporting) ----------

def get_all_services_with_property() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            ps.id,
            ps.property_id,
            p.name AS property_name,
            ps.category,
            ps.frequency,
            ps.times_per_year,
            ps.each_time_cost,
            ps.status,
            ps.last_updated_at,
            ps.last_updated_by
        FROM property_services ps
        JOIN properties p ON ps.property_id = p.id
        ORDER BY p.id, ps.category, ps.frequency
        """
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]



# ---------- Service Events (Scheduling) ----------

def add_service_event(
    property_id: int,
    service_id: Optional[int],
    provider_id: Optional[int],
    service_category: str,
    scheduled_date: str,
    scheduled_time: Optional[str],
    followup_required: bool,
    followup_notes: str,
) -> None:
    """Create a scheduled service activity."""
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    cur.execute(
        """
        INSERT INTO service_events (
            property_id,
            service_id,
            provider_id,
            service_category,
            scheduled_date,
            scheduled_time,
            status,
            followup_required,
            followup_notes,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'Scheduled', ?, ?, ?, ?)
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
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()


def get_scheduled_events(date_from: str, date_to: str) -> List[Dict[str, Any]]:
    """Get events between two dates inclusive, joined with property and provider info."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            e.id,
            e.property_id,
            p.name AS property_name,
            e.service_id,
            e.service_category,
            e.provider_id,
            sp.full_name AS provider_name,
            sp.email AS provider_email,
            sp.phone AS provider_phone,
            e.scheduled_date,
            e.scheduled_time,
            e.status,
            e.followup_required,
            e.followup_notes,
            e.last_reminder_at,
            e.created_at,
            e.updated_at
        FROM service_events e
        JOIN properties p ON e.property_id = p.id
        LEFT JOIN service_persons sp ON e.provider_id = sp.id
        WHERE date(e.scheduled_date) BETWEEN date(?) AND date(?)
        ORDER BY e.scheduled_date, p.name, e.id
        """,
        (date_from, date_to),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_events_for_property(property_id: int) -> List[Dict[str, Any]]:
    """Get all events for a single property."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            e.id,
            e.property_id,
            e.service_id,
            e.service_category,
            e.scheduled_date,
            e.scheduled_time,
            e.status,
            e.followup_required,
            e.followup_notes,
            e.last_reminder_at,
            e.created_at,
            e.updated_at
        FROM service_events e
        WHERE e.property_id = ?
        ORDER BY e.scheduled_date DESC, e.id DESC
        """,
        (property_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]




def update_service_event_core(
    event_id: int,
    property_id: int,
    service_id: Optional[int],
    provider_id: Optional[int],
    service_category: str,
    scheduled_date: str,
    scheduled_time: Optional[str],
) -> None:
    """Update core editable details of an event (not status)."""
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    cur.execute(
        """
        UPDATE service_events
        SET
            property_id = ?,
            service_id = ?,
            provider_id = ?,
            service_category = ?,
            scheduled_date = ?,
            scheduled_time = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            property_id,
            service_id,
            provider_id,
            service_category,
            scheduled_date,
            scheduled_time,
            now,
            event_id,
        ),
    )
    conn.commit()
    conn.close()
def update_service_event_status(
    event_id: int,
    status: str,
    followup_required: bool,
    followup_notes: str,
) -> None:
    """Update status and follow-up flags/notes for an event."""
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    cur.execute(
        """
        UPDATE service_events
        SET status = ?, followup_required = ?, followup_notes = ?, updated_at = ?
        WHERE id = ?
        """,
        (status, 1 if followup_required else 0, followup_notes, now, event_id),
    )
    conn.commit()
    conn.close()


def touch_service_event_reminder(event_id: int) -> None:
    """Mark that a reminder was sent just now for this event."""
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.datetime.utcnow().isoformat(timespec="seconds")
    cur.execute(
        "UPDATE service_events SET last_reminder_at = ?, updated_at = ? WHERE id = ?",
        (now, now, event_id),
    )
    conn.commit()
    conn.close()



def delete_service_event(event_id: int) -> None:
    """Delete a scheduled event permanently."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM service_events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()
