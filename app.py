from datetime import datetime, timedelta
import hashlib
from flask import Flask, render_template, request, redirect, url_for, session
from db import get_db_connection

app = Flask(__name__)
app.secret_key = 'murun123'

#seat NUMBERS
SEAT_LETTERS = "ABCDEF"   # 6 seats per row: A–F

def generate_seat_labels(num_seats, per_row=6):
    """Return list like ['1A','1B',...,'30F'] for given num_seats."""
    seats = []
    for i in range(num_seats):
        row = i // per_row + 1
        col = SEAT_LETTERS[i % per_row]
        seats.append(f"{row}{col}")
    return seats

#general home page
@app.route("/")
def index():
    conn = get_db_connection()
    if conn is None:
        return "Database connection error.", 500
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT airport_code, city FROM Airport")
    airports = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("home.html", airports=airports)

#login protection
def login_required(role=None):
    def decorator(func):
        from functools import wraps

        @wraps(func)
        def wrapper(*args, **kwargs):

            # Not logged in 
            if "username" not in session:
                session["next_url"] = request.path

            
                if role == "staff":
                    return redirect(url_for("staff_login"))
                else:
                    return redirect(url_for("customer_login"))

            # Logged in but wrong role
            if role and session.get("role") != role:
                return redirect(url_for("index"))

            return func(*args, **kwargs)

        return wrapper
    return decorator

# logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

#customer_login
@app.route("/customer_login", methods=["GET", "POST"])
def customer_login():
    next_url = request.args.get("next")  # <--- GET URL PARAM

    if request.method == "POST":
        email = request.form["email"]
        password_input = request.form["password"]
        hashed = hashlib.md5(password_input.encode()).hexdigest()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Customer WHERE email=%s AND password=%s", (email, hashed))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user:
            session["username"] = user["email"]
            session["role"] = "customer"

            # Prefer session["next_url"] (set by login_required or GET)
            if session.get("next_url"):
                url = session.pop("next_url")
                return redirect(url)

            # Fallback to ?next= in URL if for some reason session didn't get it
            if next_url:
                return redirect(next_url)

            return redirect(url_for("customer_home"))
        
    # Save next parameter into session BEFORE showing login
    if next_url:
        session["next_url"] = next_url

    return render_template("customer_login.html")

#customer registeration
@app.route("/customer_register", methods=["GET", "POST"])
def customer_register():
    if request.method == "POST":
        email = request.form["email"]
        name = request.form["name"]
        password = request.form["password"]
        confirm = request.form["confirm_password"]

        building_number = request.form["building_number"]
        street = request.form["street"]
        city = request.form["city"]
        state = request.form["state"]
        phone_number = request.form["phone_number"]
        passport_number = request.form["passport_number"]
        passport_expiration = request.form["passport_expiration"]
        passport_country = request.form["passport_country"]
        date_of_birth = request.form["date_of_birth"]

        if password != confirm:
            return render_template(
                "customer_register.html",
                error="Passwords do not match."
            )

        hashed_password = hashlib.md5(password.encode()).hexdigest()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Check duplicate email
        cursor.execute("SELECT * FROM Customer WHERE email=%s", (email,))
        existing = cursor.fetchone()
        if existing:
            return render_template(
                "customer_register.html",
                error="Email already registered."
            )

        # Insert all fields
        cursor.execute("""
            INSERT INTO Customer
            (email, name, password,
             building_number, street, city, state,
             phone_number,
             passport_number, passport_expiration, passport_country,
             date_of_birth)
            VALUES (%s, %s, %s,
                    %s, %s, %s, %s,
                    %s,
                    %s, %s, %s,
                    %s)
        """, (
            email, name, hashed_password,
            building_number, street, city, state,
            phone_number,
            passport_number, passport_expiration, passport_country,
            date_of_birth
        ))

        conn.commit()
        cursor.close()
        conn.close()

        # Auto-login
        session["username"] = email
        session["role"] = "customer"

        return redirect(url_for("customer_home"))

    return render_template("customer_register.html")

#customer home
@app.route("/customer_home")
@login_required("customer")
def customer_home():
    return render_template("customer_home.html", username=session["username"])

#flight search
@app.route("/search")
def search():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT airport_code, city FROM Airport")
    airports = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("search.html", airports=airports)

#flight search result
@app.route("/search_result", methods=["GET", "POST"])
def search_result():
    if request.method == "POST":
        trip_type = request.form.get("trip_type", "oneway")
        source = request.form["source"]
        destination = request.form["destination"]
        departure_date = request.form["departure_date"]
        return_date = request.form.get("return_date")
    else:
        # coming back here AFTER login via ?next=...
        trip_type = request.args.get("trip_type", "oneway")
        source = request.args.get("source")
        destination = request.args.get("destination")
        departure_date = request.args.get("departure_date")
        return_date = request.args.get("return_date")

    print("\n---------------- DEBUG SEARCH INPUT ----------------")
    print("Source:", source)
    print("Destination:", destination)
    print("Departure Date:", departure_date)
    print("Return Date:", return_date)
    print("Trip Type:", trip_type)
    print("---------------------------------------------------\n")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    one_way_query = """
        SELECT *
        FROM Flight
        WHERE departure_airport = %s
          AND arrival_airport = %s
          AND departure_datetime >= GREATEST(%s, NOW())
          AND departure_datetime < DATE_ADD(%s, INTERVAL 1 DAY);
    """

    cursor.execute(one_way_query, (
        source,
        destination,
        departure_date + " 00:00:00",
        departure_date + " 00:00:00"
    ))
    onward_flights = cursor.fetchall()

    return_flights = []
    if trip_type == "round" and return_date:
        round_query = """
            SELECT *
            FROM Flight
            WHERE departure_airport = %s
              AND arrival_airport = %s
              AND departure_datetime >= GREATEST(%s, NOW())
              AND departure_datetime < DATE_ADD(%s, INTERVAL 1 DAY);
        """
        cursor.execute(round_query, (
            destination,
            source,
            return_date + " 00:00:00",
            return_date + " 00:00:00"
        ))
        return_flights = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "search_result.html",
        trip_type=trip_type,
        onward_flights=onward_flights,
        return_flights=return_flights,
        source=source,
        destination=destination,
        departure_date=departure_date,
        return_date=return_date,
        now=datetime.now()
    )

#customer view purchased flight
@app.route("/my_flights")
@login_required("customer")
def my_flights():
    email = session["username"]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            T.ticket_id,
            T.airline_name,
            T.flight_number,
            T.departure_datetime,
            T.seat_number,

            F.departure_airport,
            F.arrival_airport,
            F.arrival_datetime,
            F.departure_datetime AS flight_departure,
            F.base_price AS base_price,

            T.card_type AS payment_method

        FROM Ticket T
        JOIN Flight F
          ON T.airline_name = F.airline_name
         AND T.flight_number = F.flight_number
         AND T.departure_datetime = F.departure_datetime
        
        WHERE T.customer_email = %s
        AND F.departure_datetime >= NOW()
        ORDER BY F.departure_datetime;
    """, (email,))

    tickets = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("my_flights.html", flights=tickets)

#purchase ticket
@app.route("/purchase/<airline>/<flight>/<departure_raw>", methods=["GET", "POST"])
@login_required("customer")
def purchase(airline, flight, departure_raw):
    departure = departure_raw.replace("_", " ")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    #Get flight + airplane num_seats
    cursor.execute("""
        SELECT F.*, A.num_seats
        FROM Flight F
        JOIN Airplane A
          ON F.airline_name = A.airline_name
         AND F.airplane_id = A.airplane_id
        WHERE F.airline_name=%s
          AND F.flight_number=%s
          AND F.departure_datetime=%s
    """, (airline, flight, departure))
    flight_data = cursor.fetchone()

    if not flight_data:
        cursor.close()
        conn.close()
        return "Flight not found.", 404

    #Find already occupied seats
    cursor2 = conn.cursor()
    cursor2.execute("""
        SELECT seat_number
        FROM Ticket
        WHERE airline_name=%s
          AND flight_number=%s
          AND departure_datetime=%s
    """, (airline, flight, departure))

    occupied = {row[0] for row in cursor2.fetchall()}  
    cursor2.close()

    #Generate all seats 
    num_seats = int(flight_data["num_seats"]) 
    all_seats = generate_seat_labels(num_seats)
    available_seats = [s for s in all_seats if s not in occupied]

    #try to purchase 
    if request.method == "POST":
        seat = request.form["seat_number"]
        card_type = request.form["card_type"]
        card_number = request.form["card_number"]
        card_expiration = request.form["card_expiration"]
        name_on_card = request.form["name_on_card"]
        
        cursor3 = conn.cursor()
        cursor3.execute("""
            SELECT 1 FROM Ticket
            WHERE airline_name=%s
              AND flight_number=%s
              AND departure_datetime=%s
              AND seat_number=%s
        """, (airline, flight, departure, seat))
        if cursor3.fetchone():
            cursor3.close()
            cursor.close()
            conn.close()
            return "Sorry, that seat was just taken. Please go back and choose another.", 400

        cursor3.close()

        # Insert ticket
        cursor4 = conn.cursor()
        cursor4.execute("""
            INSERT INTO Ticket
            (customer_email, airline_name, flight_number, departure_datetime,
             seat_number, purchase_date, card_type, card_number, card_expiration, name_on_card)
            VALUES (%s, %s, %s, %s, %s, CURDATE(), %s, %s, %s, %s)
        """, (
            session["username"], airline, flight, departure,
            seat, card_type, card_number, card_expiration, name_on_card
        ))

        conn.commit()
        cursor4.close()
        cursor.close()
        conn.close()

        return render_template("purchase_success.html")

    cursor.close()
    conn.close()

    return render_template("purchase.html",
                           flight=flight_data,
                           airline_name=airline,
                           flight_number=flight,
                           departure_datetime=departure,
                           available_seats=available_seats)
  
#purchase round trip
@app.route("/purchase_round", methods=["GET", "POST"])
@login_required("customer")
def purchase_round():
    email = session["username"]

    def parse_choice(choice):
        airline, flight, departure_raw = choice.split("|")
        departure = departure_raw.replace("_", " ")
        return airline, flight, departure

    def load_flight_and_available(conn, airline, flight, departure):
        cur = conn.cursor(dictionary=True)
        #join Flight with Airplane to get num_seats
        cur.execute("""
            SELECT F.*, A.num_seats
            FROM Flight F
            JOIN Airplane A
              ON F.airline_name = A.airline_name
             AND F.airplane_id = A.airplane_id
            WHERE F.airline_name=%s
              AND F.flight_number=%s
              AND F.departure_datetime=%s
        """, (airline, flight, departure))
        flight_data = cur.fetchone()
        if not flight_data:
            cur.close()
            return None, []

        #occupied seats
        cur2 = conn.cursor()
        cur2.execute("""
            SELECT seat_number
            FROM Ticket
            WHERE airline_name=%s
              AND flight_number=%s
              AND departure_datetime=%s
        """, (airline, flight, departure))
        occupied = {row[0] for row in cur2.fetchall()}
        cur2.close()

        num_seats = int(flight_data["num_seats"])   
        all_seats = generate_seat_labels(num_seats)
        available = [s for s in all_seats if s not in occupied]
        cur.close()
        return flight_data, available

    #show seat & payment page
    if request.method == "GET":
        onward_choice = request.args.get("onward_choice")
        return_choice = request.args.get("return_choice")

        if not onward_choice or not return_choice:
            return "Please choose both an onward and a return flight first.", 400

        on_airline, on_flight, on_dep = parse_choice(onward_choice)
        ret_airline, ret_flight, ret_dep = parse_choice(return_choice)

        conn = get_db_connection()

        onward_flight, available_onward = load_flight_and_available(
            conn, on_airline, on_flight, on_dep
        )
        return_flight, available_return = load_flight_and_available(
            conn, ret_airline, ret_flight, ret_dep
        )

        conn.close()

        if not onward_flight or not return_flight:
            return "Could not load one of the selected flights.", 404

        return render_template(
            "purchase_round.html",
            onward_flight=onward_flight,
            return_flight=return_flight,
            available_onward=available_onward,
            available_return=available_return,
            on_airline=on_airline,
            on_flight=on_flight,
            on_dep=on_dep,
            ret_airline=ret_airline,
            ret_flight=ret_flight,
            ret_dep=ret_dep
        )

    #buy both tickets
    on_airline = request.form["on_airline"]
    on_flight = request.form["on_flight"]
    on_dep = request.form["on_dep"]
    ret_airline = request.form["ret_airline"]
    ret_flight = request.form["ret_flight"]
    ret_dep = request.form["ret_dep"]

    seat_onward = request.form["seat_onward"]
    seat_return = request.form["seat_return"]
    card_type = request.form["card_type"]
    card_number = request.form["card_number"]
    card_expiration = request.form["card_expiration"]
    name_on_card = request.form["name_on_card"]

    conn = get_db_connection()
    cur = conn.cursor()

    #check onward seat
    cur.execute("""
        SELECT 1 FROM Ticket
        WHERE airline_name=%s
          AND flight_number=%s
          AND departure_datetime=%s
          AND seat_number=%s
    """, (on_airline, on_flight, on_dep, seat_onward))
    if cur.fetchone():
        conn.close()
        return "Onward seat already taken. Please go back and choose another.", 400

    #check return seat 
    cur.execute("""
        SELECT 1 FROM Ticket
        WHERE airline_name=%s
          AND flight_number=%s
          AND departure_datetime=%s
          AND seat_number=%s
    """, (ret_airline, ret_flight, ret_dep, seat_return))
    if cur.fetchone():
        conn.close()
        return "Return seat already taken. Please go back and choose another.", 400

    #insert both tickets
    cur.execute("""
        INSERT INTO Ticket
        (customer_email, airline_name, flight_number, departure_datetime,
         seat_number, purchase_date, card_type, card_number, card_expiration, name_on_card)
        VALUES (%s, %s, %s, %s, %s, CURDATE(), %s, %s, %s, %s)
    """, (email, on_airline, on_flight, on_dep,
          seat_onward, card_type, card_number, card_expiration, name_on_card))

    cur.execute("""
        INSERT INTO Ticket
        (customer_email, airline_name, flight_number, departure_datetime,
         seat_number, purchase_date, card_type, card_number, card_expiration, name_on_card)
        VALUES (%s, %s, %s, %s, %s, CURDATE(), %s, %s, %s, %s)
    """, (email, ret_airline, ret_flight, ret_dep,
          seat_return, card_type, card_number, card_expiration, name_on_card))

    conn.commit()
    conn.close()

    return render_template("purchase_success.html")

#customer rating the past flights
@app.route("/rate_past_flights")
@login_required("customer")
def rate_past_flights():
    email = session["username"]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT T.ticket_id, T.airline_name, T.flight_number,
               T.departure_datetime, F.departure_airport, F.arrival_airport
        FROM Ticket T
        JOIN Flight F
          ON T.airline_name=F.airline_name
         AND T.flight_number=F.flight_number
         AND T.departure_datetime=F.departure_datetime
        WHERE customer_email=%s
          AND F.departure_datetime < NOW()
        ORDER BY F.departure_datetime DESC;
    """, (email,))

    flights = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("rate_past_flights.html", past_flights=flights)

#rate one flight
@app.route("/rate_flight/<int:ticket_id>", methods=["GET", "POST"])
@login_required("customer")
def rate_flight(ticket_id):
    email = session["username"]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM Ticket
        WHERE ticket_id=%s AND customer_email=%s
    """, (ticket_id, email))

    ticket = cursor.fetchone()

    if not ticket:
        return "Not your ticket."

    dep_dt = ticket["departure_datetime"]
    if isinstance(dep_dt, str):
        dep_dt = datetime.strptime(dep_dt, "%Y-%m-%d %H:%M:%S")

    if dep_dt > datetime.now():
        return "You cannot rate future flights."

    if request.method == "POST":
        rating = request.form["rating"]
        comment = request.form["comment"]

        cursor.execute("""INSERT INTO FlightRating
                    (customer_email, airline_name, flight_number,
                        departure_datetime, rating, comment)
                        VALUES (%s, %s, %s, %s, %s, %s)""", 
                        (email, ticket["airline_name"], ticket["flight_number"],
              ticket["departure_datetime"], rating, comment))

        conn.commit()
        cursor.close()
        conn.close()
        return render_template("rating_success.html")

    cursor.close()
    conn.close()
    return render_template("rate_flight.html", ticket=ticket)

#staff login
@app.route("/staff_login", methods=["GET", "POST"])
def staff_login():
    if request.method == "POST":
        username = request.form["username"]
        password_input = request.form["password"]
        hashed = hashlib.md5(password_input.encode()).hexdigest()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT * FROM AirlineStaff
            WHERE username=%s AND password=%s
        """, (username, hashed))
        staff = cursor.fetchone()

        cursor.close()
        conn.close()

        if staff:
            session["username"] = staff["username"]
            session["role"] = "staff"
            session["airline"] = staff["airline_name"]
            return redirect(url_for("staff_home"))
        else:
            return render_template("staff_login.html",
                                   error="Invalid staff login.")

    return render_template("staff_login.html")

#staff registeration
@app.route("/staff_register", methods=["GET", "POST"])
def staff_register():

    # Load airlines for dropdown
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT airline_name FROM Airline")
    airlines = cursor.fetchall()
    cursor.close()
    conn.close()

    if request.method == "POST":
        username = request.form["username"]
        first_name = request.form["first_name"]
        last_name = request.form["last_name"]
        date_of_birth = request.form["date_of_birth"]
        email = request.form["email"]
        airline_name = request.form["airline_name"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if password != confirm_password:
            return render_template(
                "staff_register.html",
                airlines=airlines,
                error="Passwords do not match."
            )

        hashed_password = hashlib.md5(password.encode()).hexdigest()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            #check duplicate username
            cursor.execute("SELECT username FROM AirlineStaff WHERE username=%s", (username,))
            if cursor.fetchone():
                return render_template(
                    "staff_register.html",
                    airlines=airlines,
                    error="Username already registered."
                )

            cursor.execute("""
                INSERT INTO AirlineStaff
                (username, password, first_name, last_name, date_of_birth, email, airline_name)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                username,
                hashed_password,
                first_name,
                last_name,
                date_of_birth,
                email,
                airline_name
            ))

            conn.commit()
            cursor.close()
            conn.close()

            #auto login
            session["username"] = username
            session["role"] = "staff"
            session["airline"] = airline_name

            return redirect(url_for("staff_home"))

        except Exception as e:
            print("❌ Staff registration error:", e)
            return render_template(
                "staff_register.html",
                airlines=airlines,
                error="Database error. Please try again."
            )

    return render_template("staff_register.html", airlines=airlines)

#staff home
@app.route("/staff_home")
@login_required("staff")
def staff_home():
    return render_template("staff_home.html",
                           username=session["username"],
                           airline=session.get("airline"))
    
#staff view customers on flight
@app.route("/staff_view_customers/<airline>/<flight>/<departure>")
@login_required("staff")
def staff_view_customers(airline, flight, departure):
    departure = departure.replace("_", " ")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT customer_email, seat_number
        FROM Ticket
        WHERE airline_name=%s
          AND flight_number=%s
          AND departure_datetime=%s
    """, (airline, flight, departure))

    customers = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("staff_view_customers.html",
                           customers=customers,
                           airline=airline,
                           flight=flight,
                           departure=departure)
    
# staff view flights
@app.route("/staff_view_flights", methods=["GET", "POST"])
@login_required("staff")
def staff_view_flights():
    airline = session["airline"]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT airport_code FROM Airport")
    airports = cursor.fetchall()

    start_date = None
    end_date = None
    dep_airport = None
    arr_airport = None

    if request.method == "POST":
        start_date = request.form.get("start_date") or None
        end_date = request.form.get("end_date") or None
        dep_airport = request.form.get("dep_airport") or None
        arr_airport = request.form.get("arr_airport") or None

        # Build dynamic WHERE clause
        conditions = ["airline_name = %s"]
        params = [airline]

        if start_date:
            conditions.append("departure_datetime >= %s")
            params.append(start_date + " 00:00:00")

        if end_date:
            conditions.append("departure_datetime <= %s")
            params.append(end_date + " 23:59:59")

        if dep_airport:
            conditions.append("departure_airport = %s")
            params.append(dep_airport)

        if arr_airport:
            conditions.append("arrival_airport = %s")
            params.append(arr_airport)

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT *
            FROM Flight
            WHERE {where_clause}
            ORDER BY departure_datetime;
        """

        cursor.execute(query, tuple(params))
        filtered = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template("staff_view_flights.html",
                               filtered=filtered,
                               airports=airports,
                               filters_applied=True,
                               now=datetime.now())

    
    cursor.execute("""
        SELECT *
        FROM Flight
        WHERE airline_name = %s
          AND departure_datetime >= NOW()
          AND departure_datetime <= DATE_ADD(NOW(), INTERVAL 30 DAY)
        ORDER BY departure_datetime;
    """, (airline,))
    upcoming = cursor.fetchall()

    cursor.execute("""
        SELECT *
        FROM Flight
        WHERE airline_name = %s
          AND departure_datetime < NOW()
        ORDER BY departure_datetime DESC;
    """, (airline,))
    past = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("staff_view_flights.html",
                           upcoming=upcoming,
                           past=past,
                           airports=airports,
                           filters_applied=False)

#staff create flight
@app.route("/staff_create_flight", methods=["GET", "POST"])
@login_required("staff")
def staff_create_flight():
    airline = session["airline"]

    if request.method == "POST":
        data = (
            airline,
            request.form["flight_number"],
            request.form["departure_airport"],
            request.form["arrival_airport"],
            request.form["departure_datetime"],
            request.form["arrival_datetime"],
            request.form["base_price"],
            request.form["airplane_id"]
        )

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO Flight
            (airline_name, flight_number, departure_airport, arrival_airport,
             departure_datetime, arrival_datetime, base_price, airplane_id, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'On-Time')
        """, data)

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for("staff_view_flights"))


    return render_template("staff_create_flight.html")

#staff change flight status
@app.route("/staff_change_status/<airline>/<flight>/<departure>", methods=["GET", "POST"])
@login_required("staff")
def staff_change_status(airline, flight, departure):
    departure = departure.replace("_", " ")

    if request.method == "POST":
        new_status = request.form["status"]

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE Flight
            SET status=%s
            WHERE airline_name=%s
              AND flight_number=%s
              AND departure_datetime=%s
        """, (new_status, airline, flight, departure))

        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for("staff_view_flights"))

    return render_template("staff_change_status.html",
                           airline=airline,
                           flight=flight,
                           departure=departure)
    
#staff add airplane
@app.route("/staff_add_airplane", methods=["GET", "POST"])
@login_required("staff")
def staff_add_airplane():
    airline = session["airline"]

    if request.method == "POST":
        # Debug: see exactly what keys arrived
        print("📨 FORM DATA:", request.form)

        airplane_id   = request.form.get("id")
        num_seats     = request.form.get("seats")          # no KeyError now
        manufacturer  = request.form.get("manufacturer")
        age           = request.form.get("age")

        # Basic validation
        if not all([airplane_id, num_seats, manufacturer, age]):
            return render_template(
                "staff_add_airplane.html",
                error="Please fill in all fields."
            )

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)   # dict makes template nicer

        cursor.execute("""
            INSERT INTO Airplane
            (airline_name, airplane_id, num_seats, manufacturer, age)
            VALUES (%s, %s, %s, %s, %s)
        """, (airline, airplane_id, num_seats, manufacturer, age))

        conn.commit()

        cursor.execute("SELECT * FROM Airplane WHERE airline_name = %s", (airline,))
        planes = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template(
            "staff_airplane_confirm.html",
            planes=planes,
            airline=airline
        )

    return render_template("staff_add_airplane.html")

#staff view flight ratings
@app.route("/staff_ratings/<flight>/<departure>")
@login_required("staff")
def staff_ratings(flight, departure):
    airline = session["airline"]
    departure = departure.replace("_", " ")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # get average rating
    cursor.execute("""
        SELECT AVG(rating) AS avg_rating
        FROM FlightRating
        WHERE airline_name=%s AND flight_number=%s AND departure_datetime=%s
    """, (airline, flight, departure))
    avg_rating = cursor.fetchone()

    # get all reviews
    cursor.execute("""
        SELECT customer_email, rating, comment
        FROM FlightRating
        WHERE airline_name=%s AND flight_number=%s AND departure_datetime=%s
    """, (airline, flight, departure))
    reviews = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("staff_ratings.html",
                           avg=avg_rating,
                           reviews=reviews)
    
#staff view total reports
@app.route("/staff_reports", methods=["GET", "POST"])
@login_required("staff")
def staff_reports():
    airline = session["airline"]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # default last 30 days
    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    if request.method == "POST":
        filter_type = request.form.get("filter_type")

        if filter_type == "range":
            start_date = request.form.get("start_date")
            end_date = request.form.get("end_date")

        elif filter_type == "last_month":
            today = datetime.today()
            first_day_this_month = today.replace(day=1)
            last_month_end = first_day_this_month - timedelta(days=1)
            last_month_start = last_month_end.replace(day=1)

            start_date = last_month_start.strftime("%Y-%m-%d")
            end_date = last_month_end.strftime("%Y-%m-%d")

        elif filter_type == "last_year":
            today = datetime.today()
            last_year_start = today.replace(year=today.year - 1, month=1, day=1)
            last_year_end = today.replace(year=today.year - 1, month=12, day=31)

            start_date = last_year_start.strftime("%Y-%m-%d")
            end_date = last_year_end.strftime("%Y-%m-%d")

    #total tickets sold
    cursor.execute("""
        SELECT COUNT(*) AS total_tickets
        FROM Ticket
        WHERE airline_name=%s AND purchase_date BETWEEN %s AND %s
    """, (airline, start_date, end_date))
    total = cursor.fetchone()

    #monthly breakdown
    cursor.execute("""
        SELECT DATE_FORMAT(purchase_date, '%Y-%m') AS month,
               COUNT(*) AS sold
        FROM Ticket
        WHERE airline_name=%s
          AND purchase_date BETWEEN %s AND %s
        GROUP BY month
        ORDER BY month
    """, (airline, start_date, end_date))
    monthly = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("staff_reports.html",
                           total=total,
                           monthly=monthly,
                           start_date=start_date,
                           end_date=end_date)


# main server
if __name__ == "__main__":
    app.run(debug=True)
